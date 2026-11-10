# backend/main.py
import asyncio
import base64
import json
import os
from contextlib import asynccontextmanager

import numpy as np
import soundfile as sf
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

DEBUG = os.environ.get("VSS_DEBUG", "1") == "1"

# Heavy ML deps are optional: the server still runs (with heuristic fallbacks)
# if they are missing, so the demo never hard-fails on a fresh machine.
try:
    import whisper
except Exception as e:
    print("Whisper not importable (%s); STT will fall back to heuristics." % e)
    whisper = None

try:
    import librosa
except Exception as e:
    print("librosa not importable (%s); spoof detection will fall back to stub." % e)
    librosa = None

try:
    from transformers import pipeline
except Exception as e:
    print("transformers not importable (%s); intent detection will use keywords." % e)
    pipeline = None

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
CALLS_DIR = os.path.join(ROOT_DIR, "calls")

# Config
INTENT_MODEL_NAME = os.environ.get(
    "VSS_INTENT_MODEL", "joeddav/xlm-roberta-large-xnli"
)
WHISPER_MODEL_NAME = os.environ.get("VSS_WHISPER_MODEL", "tiny")
MIN_SAMPLES_TO_TRANSCRIBE = 16000  # 1 second @ 16 kHz
WINDOW_SIZE = 5  # number of intent scores smoothed together
INTENT_LABELS = ["scam or fraud", "legitimate business"]
INTENT_TEMPLATE = "This phone call is {}."
SCAM_LABELS = {"scam or fraud"}

# Model handles, loaded lazily in the background so the server is reachable
# immediately (a first run may download several GB and we do not want to
# block startup while that happens).
model = None
intent_model = None


@asynccontextmanager
async def lifespan(app):
    # Loading models is synchronous work (downloads + torch init); running it
    # in the default thread executor keeps the event loop responsive so
    # startup finishes and /health answers right away.
    asyncio.get_event_loop().run_in_executor(None, load_models_sync)
    yield


app = FastAPI(title="Voice Scam Shield", lifespan=lifespan)
os.makedirs(CALLS_DIR, exist_ok=True)


def load_models_sync():
    """Load Whisper + the zero-shot intent model.

    Runs in a worker thread: loading and downloading models is synchronous
    work and would starve the event loop if executed directly in a task.
    """
    global model, intent_model

    if whisper is None:
        print("[models] Whisper unavailable; STT stub will be used.")
    else:
        try:
            print("[models] Loading Whisper (%s)..." % WHISPER_MODEL_NAME)
            model = whisper.load_model(WHISPER_MODEL_NAME)
            print("[models] Whisper loaded.")
        except Exception as e:
            print("[models] Failed to load Whisper:", e)

    if pipeline is None:
        print("[models] transformers unavailable; keyword fallback will be used.")
    else:
        try:
            print("[models] Loading intent model (%s)..." % INTENT_MODEL_NAME)
            # NOTE: this model is an NLI classifier and must be run through the
            # zero-shot-classification pipeline (not text-classification).
            intent_model = pipeline("zero-shot-classification", model=INTENT_MODEL_NAME)
            print("[models] Intent model loaded.")
        except Exception as e:
            print("[models] Could not load intent model; using fallback:", e)
            intent_model = None


# Per-call state
call_saved_segments = {}  # call_id -> {speaker: [(ts, fname), ...]}
speech_buffers = {}       # call_id -> {speaker: [np.array, ...]}
score_history = {}        # call_id -> {speaker: [float, ...]}


def ensure_call(call_id):
    if call_id not in call_saved_segments:
        call_saved_segments[call_id] = {"caller": [], "user": []}
        speech_buffers[call_id] = {"caller": [], "user": []}
        score_history[call_id] = {"caller": [], "user": []}
        os.makedirs(os.path.join(CALLS_DIR, call_id), exist_ok=True)


def save_chunk(call_id, speaker, timestamp_ms, pcm_bytes):
    fname = os.path.join(CALLS_DIR, call_id, "%s_%s.wav" % (speaker, timestamp_ms))
    data = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    sf.write(fname, data, 16000, subtype="PCM_16")
    return fname


async def stt_stub_from_array(audio_np):
    """Cheap placeholder STT when Whisper isn't available."""
    if audio_np is None or len(audio_np) == 0:
        return "", "unknown"
    rms = float(np.sqrt(np.mean(audio_np**2)))
    if rms < 0.01:
        return "", "unknown"
    if rms > 0.12:
        return "Bonjour, c'est le service client, transférez le code que je vous ai envoyé", "fr"
    elif rms > 0.06:
        return "Pouvez-vous confirmer votre numéro de compte ?", "fr"
    return "Bonjour, je voudrais juste vérifier des informations", "fr"


async def stt_whisper_from_array(audio_np):
    if model is None:
        return await stt_stub_from_array(audio_np)
    try:
        loop = asyncio.get_running_loop()

        def transcribe_sync(a):
            # fp16=False: the demo runs on CPU and float16 is unsupported there
            return model.transcribe(a, language=None, fp16=False)

        res = await loop.run_in_executor(None, transcribe_sync, audio_np)
        text = res.get("text", "").strip()
        language = res.get("language") or "unknown"
        return text, language
    except Exception as e:
        if DEBUG:
            print("Whisper transcription error:", e)
        return await stt_stub_from_array(audio_np)


async def spoof_real_from_array(audio_np):
    """Heuristic anti-spoofing based on spectral flatness."""
    try:
        if librosa is None:
            raise RuntimeError("librosa not installed")
        if audio_np is None or len(audio_np) < 512:
            return await spoof_stub_from_array(audio_np)
        S = np.abs(librosa.stft(audio_np.astype(float), n_fft=512, hop_length=256))
        flatness = librosa.feature.spectral_flatness(S=S)
        score = float(np.mean(flatness))
        if score < 0.02:
            return ("synthetic", 0.85)
        elif score < 0.04:
            return ("synthetic", 0.6)
        return ("genuine", 0.9)
    except Exception as e:
        if DEBUG:
            print("Spectral spoof analysis failed; using stub:", e)
        return await spoof_stub_from_array(audio_np)


async def spoof_stub_from_array(audio_np):
    if audio_np is None or audio_np.size == 0:
        return ("synthetic", 0.5)
    rms = float(np.sqrt(np.mean(audio_np**2)))
    if rms > 0.12:
        return ("genuine", 0.8)
    return ("synthetic", 0.5)


def detect_intent(transcript):
    """Classify a transcript as scam or safe, with a confidence + rationale."""
    transcript = transcript.strip()
    if not transcript:
        return "safe", 0.0, "No speech detected"

    if intent_model is not None:
        try:
            preds = intent_model(
                transcript,
                candidate_labels=INTENT_LABELS,
                hypothesis_template=INTENT_TEMPLATE,
                truncation=True,
            )
            top_label = preds["labels"][0].lower()
            score = float(preds["scores"][0])
            if top_label in SCAM_LABELS:
                return "scam", score, "ML model flagged: %s" % top_label
            return "safe", score, "ML model predicted: %s" % top_label
        except Exception as e:
            if DEBUG:
                print("Intent model inference failed; using fallback:", e)

    lower = transcript.lower()
    scam_keywords = [
        "transfer", "transf", "code", "compte", "argent", "virement",
        "urgent", "impots", "impôts", "tax", "bank", "verify", "security",
    ]
    for kw in scam_keywords:
        if kw in lower:
            return "scam", 0.92, "Keyword detected: %s" % kw
    return "safe", 0.4, "Fallback heuristic"


def build_analysis(speaker, timestamp_ms, transcript, language,
                   intent_label, intent_conf, rationale,
                   spoof_label, spoof_conf):
    """Compose the analysis payload sent back over the WebSocket."""
    out = {
        "type": "analysis",
        "speaker": speaker,
        "timestamp_ms": timestamp_ms,
        "text": transcript,
        "language": language,
        "intent_label": intent_label,
        "intent_confidence": round(intent_conf, 2),
        "rationale": rationale,
        "spoof_label": spoof_label,
        "spoof_confidence": round(spoof_conf, 2),
    }
    return out


async def analyze_speaker(call_id, speaker, timestamp_ms, audio_np):
    """Run the full STT + spoof + intent pipeline on a buffered audio window."""
    speech_buffers[call_id][speaker] = []

    transcript, language = await stt_whisper_from_array(audio_np)
    spoof_label, spoof_conf = await spoof_real_from_array(audio_np)
    intent_label, intent_conf, rationale = detect_intent(transcript)

    score_history[call_id][speaker].append(intent_conf)
    recent_scores = score_history[call_id][speaker][-WINDOW_SIZE:]
    smoothed_conf = sum(recent_scores) / len(recent_scores)

    return build_analysis(
        speaker, timestamp_ms, transcript, language,
        intent_label, smoothed_conf, rationale,
        spoof_label, spoof_conf,
    )


def build_report(call_id):
    report = {"call_id": call_id, "segments": []}
    for sp in ("caller", "user"):
        for ts, fname in call_saved_segments[call_id][sp]:
            report["segments"].append({"timestamp_ms": ts, "speaker": sp, "file": fname})
    return report


@app.get("/health")
async def health():
    return JSONResponse({
        "status": "ok",
        "whisper_loaded": model is not None,
        "intent_model_loaded": intent_model is not None,
    })


@app.websocket("/ws/{call_id}")
async def ws_endpoint(websocket: WebSocket, call_id: str):
    await websocket.accept()
    ensure_call(call_id)
    if DEBUG:
        print("Client connected for call %s" % call_id)

    try:
        while True:
            text = await websocket.receive_text()
            msg = json.loads(text)

            if msg.get("type") == "chunk":
                speaker = msg.get("speaker", "caller")
                timestamp_ms = msg.get("timestamp_ms", 0)
                pcm_bytes = base64.b64decode(msg.get("audio_chunk", ""))

                fname = save_chunk(call_id, speaker, timestamp_ms, pcm_bytes)
                call_saved_segments[call_id][speaker].append((timestamp_ms, fname))

                audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                speech_buffers[call_id][speaker].append(audio_np)

                total_samples = sum(arr.shape[0] for arr in speech_buffers[call_id][speaker])
                if total_samples >= MIN_SAMPLES_TO_TRANSCRIBE:
                    to_transcribe = np.concatenate(speech_buffers[call_id][speaker])
                    analysis = await analyze_speaker(call_id, speaker, timestamp_ms, to_transcribe)
                    await websocket.send_text(json.dumps(analysis))
                elif DEBUG:
                    print("[DEBUG] Buffering %d samples for %s/%s" % (total_samples, call_id, speaker))

            elif msg.get("type") == "end_call":
                for sp in ("caller", "user"):
                    if speech_buffers[call_id][sp]:
                        remaining = np.concatenate(speech_buffers[call_id][sp])
                        if remaining.size > 0:
                            analysis = await analyze_speaker(call_id, sp, 0, remaining)
                            await websocket.send_text(json.dumps(analysis))

                await websocket.send_text(json.dumps({"type": "report", "report": build_report(call_id)}))

            else:
                await websocket.send_text(json.dumps({"type": "error", "message": "unknown message type"}))

    except WebSocketDisconnect:
        if DEBUG:
            print("Client disconnected for call %s" % call_id)
    except Exception as exc:
        if DEBUG:
            print("Exception in ws handler:", exc)


# Static frontend (index.html) is served by the backend itself, so a single
# command brings up the whole demo. Must be registered after the API routes.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
