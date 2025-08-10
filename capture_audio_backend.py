# backend.py
import base64
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

app = FastAPI()

@app.websocket("/ws/media")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            if data.get("event") == "media":
                payload_b64 = data["media"]["payload"]
                audio_bytes = base64.b64decode(payload_b64)
                print(f"Received audio chunk size: {len(audio_bytes)} bytes")
                # Ici tu peux faire processing (ex: envoyer vers ML, diarisation, etc)
    except WebSocketDisconnect:
        print("Client disconnected")

if __name__ == "__main__":
    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=True)
