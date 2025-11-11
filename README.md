# 🎙️ Voice Scam Shield – Multilingual AI for Real-Time Call Scam Detection

Voice Scam Shield is a real-time call monitoring system designed to **detect potential scam or fraud calls** using AI speech-to-text transcription and intent classification.  
It can handle **multiple languages**, works with both **live microphone input** and **audio files**, and detects both **scam intent** and **voice spoofing**.

---

## 🚀 Features
- **🎧 Real-time audio streaming** via WebRTC
- **🌍 Multilingual transcription** powered by OpenAI Whisper
- **🤖 AI intent detection** using multilingual transformer models (Hugging Face)
- **🔍 Voice spoof detection** with spectral feature analysis
- **📈 Smoothed confidence scores** for stable predictions
- **💻 Simple web frontend** for live visualization and transcripts
- **🛠 Fallback heuristics** when AI models are unavailable

---

## 🛑 Problem
Phone scams are a growing problem worldwide, often targeting vulnerable populations.  
Existing solutions usually only block known numbers or work after the scam has already occurred.  
Voice Scam Shield proactively analyzes the call **in real time** to warn the user before sensitive information is shared.

---

## 🎯 Target Audience
- Elderly or vulnerable individuals
- Customer service teams handling high volumes of calls
- Businesses at risk of phishing or vishing attacks

---

## 🧠 How It Works
1. **Audio capture** from microphone or audio file (via browser frontend)
2. **Real-time streaming** to the backend over WebSocket
3. **Speech-to-text** transcription with Whisper
4. **Intent detection** using multilingual AI model (`joeddav/xlm-roberta-large-xnli`)
5. **Spoof detection** using audio spectral analysis
6. **Smooth scoring** to avoid false jumps in predictions
7. **Frontend display** of transcript, intent, confidence, and spoof score

---

## 🛠 Tech Stack
- **Backend:** FastAPI + WebSocket
- **Speech-to-Text:** OpenAI Whisper
- **Intent Detection:** Hugging Face Transformers
- **Audio Processing:** librosa, soundfile, numpy
- **Frontend:** HTML + JavaScript (WebRTC)
- **Model Serving:** Local inference (no cloud dependency after install)

---

## 📦 Installation
```bash
git clone https://github.com/YOUR_USERNAME/VoiceScamShield.git
cd VoiceScamShield

# Create a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Install protobuf & sentencepiece for Hugging Face models
pip install protobuf sentencepiece

```
## ▶️ Quick Launch

Backend:
```powershell/bash
uvicorn backend.main:app --reload
```

Frontend (static HTML/JS) on another terminal:
```powershell
cd frontend
py -m http.server 5500
```
Opens at: http://127.0.0.1:5500/ 

Alternative for frontend : open index.html
