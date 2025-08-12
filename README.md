# Voice Scam Shield - 24h Prototype

## What this prototype does
- Frontend: captures microphone audio via WebRTC (getUserMedia + ScriptProcessor) and streams 1s PCM chunks to backend WebSocket.
- Backend: receives chunks, saves WAV files, runs _stub_ speech-to-text and _stub_ anti-spoofing heuristics, and returns JSON analysis messages with the expected fields for parts B and C.

This is a functioning **integration prototype** you can run locally and demonstrate the end-to-end pipeline. Replace the stub functions with Whisper/AASIST models later for production-quality results.

## Run (local)
1. Create a virtualenv and install requirements:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run the backend:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

3. Open `frontend/index.html` in Chrome (file://) or serve it with a simple HTTP server (recommended):

```bash
python -m http.server 8080
# then open http://localhost:8080/frontend/index.html
```

4. Allow microphone access. Choose a Call ID, select Speaker, press Start. The page will stream chunks to the backend. Analysis messages will show live in the UI.

## Outputs
- Live JSON messages over WebSocket with keys:
  - `speaker`, `timestamp_ms`, `text`, `language`, `intent_label`, `intent_confidence`, `rationale`, `spoof_label`, `spoof_confidence`.
- Saved WAV files in `./calls/<call_id>/`.
- End-of-call report JSON message with list of saved segments.

## How to swap stubs for real models
- Replace `stt_stub` in `backend/main.py` with a call to Whisper (whisperx, openai-whisper, or an ASR service).
- Replace `spoof_stub` with a real anti-spoofing model (AASIST/RawNet2). Emit `spoof_label` and `spoof_confidence` as shown.

