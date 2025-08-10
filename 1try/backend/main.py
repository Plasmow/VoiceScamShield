from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import base64
import os
import asyncio
import json
import numpy as np
import soundfile as sf
import io
from datetime import datetime
import tempfile

# Whisper imports
try:
    import whisper
except Exception:
    whisper = None

# librosa for spoof stub
try:
    import librosa
except Exception:
    librosa = None

app = FastAPI()

CALLS_DIR = "./calls"
os.makedirs(CALLS_DIR, exist_ok=True)

# Simple in-memory store for call buffers
call_buffers = {}

model = None

@app.on_event("startup")
async def load_models():
    global model
    # Load a small whisper model if available
    if whisper is not None:
        try:
            # small/tiny are faster; choose tiny for 24h prototype
            model = whisper.load_model("tiny")
            print("Whisper model loaded (tiny).")
        except Exception as e:
            print("Failed to load Whisper model:", e)
            model = None
    else:
        print("whisper package not installed; using STT stub.")

# Utils

def ensure_call(call_id):
    if call_id not in call_buffers:
        call_buffers[call_id] = {
            "caller": [],
            "user": [],
            "text": {"caller": "", "user": ""}
        }
        os.makedirs(os.path.join(CALLS_DIR, call_id), exist_ok=True)


def save_chunk(call_id, speaker, timestamp_ms, pcm_bytes):
    # Save chunk as WAV file (16kHz mono 16-bit expected)
    fname = os.path.join(CALLS_DIR, call_id, f"{speaker}_{timestamp_ms}.wav")
    data = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    sf.write(fname, data, 16000, subtype='PCM_16')
    return fname


async def stt_whisper(pcm_bytes):
    """
    Use whisper model to transcribe chunk. Decode raw 16-bit PCM to float32 and pass array directly
    to Whisper to avoid ffmpeg dependency on Windows.
    """
    if model is None:
        return ""
    try:
        # Decode little-endian 16-bit PCM to float32 in [-1, 1]
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return ""
        # Our frontend streams 16 kHz mono, which matches Whisper's expected input when passing arrays
        res = model.transcribe(audio, language=None, fp16=False)
        text = res.get('text', '').strip()
        return text
    except Exception as e:
        print("Whisper transcribe error:", e)
        return ""


async def stt_stub(pcm_bytes):
    # Fallback simple heuristic
    data = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(data**2)))
    if rms < 0.01:
        return ""
    if rms > 0.12:
        return "Bonjour, c'est le service client, transférez le code que je vous ai envoyé"
    elif rms > 0.06:
        return "Pouvez-vous confirmer votre numéro de compte ?"
    else:
        return "Bonjour, je voudrais juste vérifier des informations"


async def spoof_real(pcm_bytes):
    """
    Use librosa spectral flatness as a cheap proxy.
    """
    try:
        if librosa is None:
            raise Exception("librosa not installed")
        data = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        # ensure length > n_fft
        if len(data) < 1024:
            # pad
            data = np.pad(data, (0, 1024 - len(data)))
        S = np.abs(librosa.stft(data.astype(float), n_fft=512, hop_length=256))
        flatness = librosa.feature.spectral_flatness(S=S)
        score = float(np.mean(flatness))
        if score < 0.02:
            return ("synthetic", 0.85)
        elif score < 0.04:
            return ("synthetic", 0.6)
        else:
            return ("genuine", 0.9)
    except Exception:
        return await spoof_stub(pcm_bytes)


async def spoof_stub(pcm_bytes):
    # fallback heuristic
    data = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(data**2)))
    if rms > 0.12:
        return ("genuine", 0.8)
    else:
        return ("synthetic", 0.5)


@app.websocket("/ws/{call_id}")
async def websocket_endpoint(websocket: WebSocket, call_id: str):
    await websocket.accept()
    ensure_call(call_id)
    print(f"Client connected for call {call_id}")
    try:
        while True:
            text = await websocket.receive_text()
            msg = json.loads(text)
            if msg.get("type") == "chunk":
                speaker = msg["speaker"]
                timestamp_ms = msg["timestamp_ms"]
                b64 = msg["audio_chunk"]
                pcm_bytes = base64.b64decode(b64)
                fname = save_chunk(call_id, speaker, timestamp_ms, pcm_bytes)
                call_buffers[call_id][speaker].append((timestamp_ms, fname))

                # STT: prefer whisper if loaded
                if model is not None:
                    transcript = await stt_whisper(pcm_bytes)
                else:
                    transcript = await stt_stub(pcm_bytes)

                # anti-spoof
                if librosa is not None:
                    spoof_label, spoof_conf = await spoof_real(pcm_bytes)
                else:
                    spoof_label, spoof_conf = await spoof_stub(pcm_bytes)

                # Update rolling transcript buffer per speaker (last ~500 chars)
                if "text" in call_buffers[call_id]:
                    prev = call_buffers[call_id]["text"].get(speaker, "")
                    combined = (prev + " " + (transcript or "")).strip()
                    call_buffers[call_id]["text"][speaker] = combined[-500:]
                else:
                    # backward compatibility
                    call_buffers[call_id]["text"] = {"caller": transcript or "", "user": ""}

                # Intent classifier (enhanced keywords with English + French and rolling context)
                intent_label = "safe"
                intent_conf = 0.4
                rationale = ""
                # Use rolling text for keyword search to mitigate chunk splits
                lower = call_buffers[call_id]["text"][speaker].lower()

                strong_keywords = [
                    # English
                    "credit card", "cvv", "c v v", "security code", "card verification",
                    "wire transfer", "routing number", "account number", "sort code",
                    "gift card", "itunes", "google play", "bitcoin", "crypto",
                    "one-time password", "one time password", "otp", "verification code",
                    "ssn", "social security", "bank account",
                    # Phrases often used in scams
                    "three numbers behind", "3 numbers behind", "send a picture of your id",
                    "photo of your id", "verify your identity",
                    # French
                    "code de verification", "mot de passe a usage unique", "virement",
                    "transfert", "compte bancaire", "numero de carte", "cvv", "iban",
                ]

                medium_keywords = [
                    # English
                    "you won", "winner", "prize", "redeem", "urgent", "security",
                    "verify", "update your details", "confirm your details",
                    # French
                    "urgent", "impôts", "taxe", "argent", "banque", "securite",
                ]

                match_kw = None
                for kw in strong_keywords:
                    if kw in lower:
                        intent_label = "scam"
                        intent_conf = 0.92
                        match_kw = kw
                        rationale = f"Keyword match (strong): {kw}"
                        break

                if intent_label != "scam":
                    for kw in medium_keywords:
                        if kw in lower:
                            # Raise to suspicious if only medium keywords seen
                            intent_label = "suspicious"
                            intent_conf = 0.7
                            match_kw = kw
                            rationale = f"Keyword match (medium): {kw}"
                            break

                if intent_label == "safe" and (transcript or "").strip() != "":
                    intent_label = "suspicious"
                    intent_conf = 0.6
                    rationale = "Non-empty speech without explicit scam patterns"

                out_msg = {
                    "type": "analysis",
                    "speaker": speaker,
                    "timestamp_ms": timestamp_ms,
                    "text": transcript,
                    "language": "fr",
                    "intent_label": intent_label,
                    "intent_confidence": round(intent_conf, 2),
                    "rationale": rationale,
                    "spoof_label": spoof_label,
                    "spoof_confidence": round(spoof_conf, 2)
                }
                await websocket.send_text(json.dumps(out_msg))

            elif msg.get("type") == "end_call":
                report = {"call_id": call_id, "segments": []}
                for sp in ["caller", "user"]:
                    for ts, fname in call_buffers[call_id][sp]:
                        report['segments'].append({
                            "timestamp_ms": ts,
                            "speaker": sp,
                            "file": fname
                        })
                await websocket.send_text(json.dumps({"type": "report", "report": report}))
            else:
                await websocket.send_text(json.dumps({"type": "error", "message": "unknown message type"}))

    except WebSocketDisconnect:
        print(f"Client disconnected for call {call_id}")


@app.get("/")
async def get_index():
    html = """
    <!doctype html>
    <html>
      <head><meta charset='utf-8'><title>Voice Scam Shield Prototype</title></head>
      <body>
        <h3>Prototype backend. Use the frontend index.html to connect.</h3>
      </body>
    </html>
    """
    return HTMLResponse(html)
