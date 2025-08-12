# backend/main.py
import os
import json
import base64
import asyncio
import numpy as np
import soundfile as sf
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# DEBUG toggle
DEBUG = True

# Try to import whisper, librosa, transformers
try:
    import whisper
except Exception:
    whisper = None

try:
    import librosa
except Exception:
    librosa = None

try:
    from transformers import pipeline
except Exception:
    pipeline = None

app = FastAPI()
CALLS_DIR = "./calls"
os.makedirs(CALLS_DIR, exist_ok=True)

# Globals
model = None
intent_model = None
call_saved_segments = {}
speech_buffers = {}
score_history = {}

# Config
MIN_SAMPLES_TO_TRANSCRIBE = 16000  # 1 sec @ 16kHz


@app.on_event("startup")
async def startup_event():
    global model, intent_model

    # Load Whisper
    if whisper is None:
        print("Whisper not installed; using STT stub.")
        model = None
    else:
        try:
            model = whisper.load_model("tiny")
            print("Whisper model loaded (tiny).")
        except Exception as e:
            print("Failed to load Whisper model:", e)
            model = None

    # Load intent detection model
    if pipeline is None:
        print("Transformers not installed; intent detection will use fallback.")
        intent_model = None
    else:
        try:
            print("Loading intent detection model...")
            intent_model = pipeline(
                "text-classification",
                model="joeddav/xlm-roberta-large-xnli",
                tokenizer="joeddav/xlm-roberta-large-xnli"
            )
            print("Intent model loaded.")
        except Exception as e:
            print("Could not load intent model; using fallback:", e)
            intent_model = None


def ensure_call(call_id):
    if call_id not in call_saved_segments:
        call_saved_segments[call_id] = {"caller": [], "user": []}
        speech_buffers[call_id] = {"caller": [], "user": []}
        score_history[call_id] = {"caller": [], "user": []}
        os.makedirs(os.path.join(CALLS_DIR, call_id), exist_ok=True)


def save_chunk(call_id, speaker, timestamp_ms, pcm_bytes):
    fname = os.path.join(CALLS_DIR, call_id, f"{speaker}_{timestamp_ms}.wav")
    data = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    sf.write(fname, data, 16000, subtype="PCM_16")
    return fname


async def stt_stub_from_array(audio_np):
    if audio_np is None or len(audio_np) == 0:
        return "", "unknown"
    rms = float(np.sqrt(np.mean(audio_np**2)))
    if rms < 0.01:
        return "", "unknown"
    if rms > 0.12:
        return "Bonjour, c'est le service client, transférez le code que je vous ai envoyé", "fr"
    elif rms > 0.06:
        return "Pouvez-vous confirmer votre numéro de compte ?", "fr"
    else:
        return "Bonjour, je voudrais juste vérifier des informations", "fr"


async def stt_whisper_from_array(audio_np):
    if model is None:
        return await stt_stub_from_array(audio_np)
    audio = audio_np.astype(np.float32)
    loop = asyncio.get_event_loop()

    def transcribe_sync(a):
        return model.transcribe(a, language=None)

    try:
        res = await loop.run_in_executor(None, transcribe_sync, audio)
        text = res.get("text", "").strip()
        language = res.get("language", None) or "unknown"
        return text, language
    except Exception as e:
        if DEBUG:
            print("Whisper transcription error:", e)
        return await stt_stub_from_array(audio_np)


async def spoof_real_from_array(audio_np):
    try:
        if librosa is None:
            raise Exception("librosa not installed")
        if audio_np is None or len(audio_np) < 512:
            return await spoof_stub_from_array(audio_np)
        S = np.abs(librosa.stft(audio_np.astype(float), n_fft=512, hop_length=256))
        flatness = librosa.feature.spectral_flatness(S=S)
        score = float(np.mean(flatness))
        if score < 0.02:
            return ("synthetic", 0.85)
        elif score < 0.04:
            return ("synthetic", 0.6)
        else:
            return ("genuine", 0.9)
    except Exception:
        return await spoof_stub_from_array(audio_np)


async def spoof_stub_from_array(audio_np):
    if audio_np is None or audio_np.size == 0:
        return ("synthetic", 0.5)
    rms = float(np.sqrt(np.mean(audio_np**2)))
    if rms > 0.12:
        return ("genuine", 0.8)
    else:
        return ("synthetic", 0.5)


def detect_intent(transcript):
    transcript = transcript.strip()
    if not transcript:
        return "safe", 0.0, "No speech detected"

    if intent_model:
        preds = intent_model(transcript, truncation=True)
        label = preds[0]["label"].lower()
        score = float(preds[0]["score"])
        if any(x in label for x in ["scam", "fraud", "spam", "illegal"]):
            return "scam", score, f"ML model predicted {label}"
        else:
            return "safe", score, f"ML model predicted {label}"

    lower = transcript.lower()
    scam_keywords = [
        "transfer", "transf", "code", "compte", "argent", "virement",
        "urgent", "impots", "impôts", "tax", "bank", "verify", "security"
    ]
    for kw in scam_keywords:
        if kw in lower:
            return "scam", 0.92, f"Keyword detected: {kw}"
    return "safe", 0.4, "Fallback heuristic"


@app.websocket("/ws/{call_id}")
async def ws_endpoint(websocket: WebSocket, call_id: str):
    await websocket.accept()
    ensure_call(call_id)
    if DEBUG:
        print(f"Client connected for call {call_id}")

    try:
        while True:
            text = await websocket.receive_text()
            msg = json.loads(text)

            if msg.get("type") == "chunk":
                speaker = msg["speaker"]
                timestamp_ms = msg["timestamp_ms"]
                pcm_bytes = base64.b64decode(msg["audio_chunk"])

                fname = save_chunk(call_id, speaker, timestamp_ms, pcm_bytes)
                call_saved_segments[call_id][speaker].append((timestamp_ms, fname))

                audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                speech_buffers[call_id][speaker].append(audio_np)

                total_samples = sum(arr.shape[0] for arr in speech_buffers[call_id][speaker])
                if total_samples >= MIN_SAMPLES_TO_TRANSCRIBE:
                    to_transcribe = np.concatenate(speech_buffers[call_id][speaker])
                    speech_buffers[call_id][speaker] = []

                    transcript, language = await stt_whisper_from_array(to_transcribe)
                    spoof_label, spoof_conf = await spoof_real_from_array(to_transcribe)
                    intent_label, intent_conf, rationale = detect_intent(transcript)

                    score_history[call_id][speaker].append(intent_conf)
                    window_size = 5
                    recent_scores = score_history[call_id][speaker][-window_size:]
                    smoothed_conf = sum(recent_scores) / len(recent_scores)

                    out = {
                        "type": "analysis",
                        "speaker": speaker,
                        "timestamp_ms": timestamp_ms,
                        "text": transcript,
                        "language": language,
                        "intent_label": intent_label,
                        "intent_confidence": round(smoothed_conf, 2),
                        "rationale": rationale,
                        "spoof_label": spoof_label,
                        "spoof_confidence": round(spoof_conf, 2)
                    }
                    await websocket.send_text(json.dumps(out))
                else:
                    if DEBUG:
                        print(f"[DEBUG] Buffering {total_samples} samples for {call_id}/{speaker}")

            elif msg.get("type") == "end_call":
                for sp in ["caller", "user"]:
                    if speech_buffers[call_id][sp]:
                        remaining = np.concatenate(speech_buffers[call_id][sp])
                        if remaining.size > 0:
                            transcript, language = await stt_whisper_from_array(remaining)
                            spoof_label, spoof_conf = await spoof_real_from_array(remaining)
                            intent_label, intent_conf, rationale = detect_intent(transcript)

                            score_history[call_id][sp].append(intent_conf)
                            recent_scores = score_history[call_id][sp][-5:]
                            smoothed_conf = sum(recent_scores) / len(recent_scores)

                            out = {
                                "type": "analysis",
                                "speaker": sp,
                                "timestamp_ms": 0,
                                "text": transcript,
                                "language": language,
                                "intent_label": intent_label,
                                "intent_confidence": round(smoothed_conf, 2),
                                "rationale": rationale,
                                "spoof_label": spoof_label,
                                "spoof_confidence": round(spoof_conf, 2)
                            }
                            await websocket.send_text(json.dumps(out))
                        speech_buffers[call_id][sp] = []

                report = {"call_id": call_id, "segments": []}
                for sp in ["caller", "user"]:
                    for ts, fname in call_saved_segments[call_id][sp]:
                        report["segments"].append({"timestamp_ms": ts, "speaker": sp, "file": fname})
                await websocket.send_text(json.dumps({"type": "report", "report": report}))

            else:
                await websocket.send_text(json.dumps({"type": "error", "message": "unknown message type"}))

    except WebSocketDisconnect:
        if DEBUG:
            print(f"Client disconnected for call {call_id}")
    except Exception as exc:
        if DEBUG:
            print("Exception in ws handler:", exc)


@app.get("/")
async def index():
    return HTMLResponse("<h3>Voice Scam Shield backend running</h3>")
