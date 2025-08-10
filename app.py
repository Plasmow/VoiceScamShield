import asyncio
import json
import base64
import numpy as np
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
import webrtcvad
import librosa
from sklearn.cluster import KMeans

pcs = set()

SAMPLE_RATE = 16000
TARGET_BYTES = SAMPLE_RATE * 2  # 1 sec audio (16bit = 2 bytes per sample)
FRAME_DURATION = 30  # ms
BYTES_PER_SAMPLE = 2

vad = webrtcvad.Vad()
vad.set_mode(2)  # agressif

# Buffer pour stocker les chunks vocaux pour clustering
speech_chunks = []

def is_speech(chunk_bytes):
    frame_length = int(SAMPLE_RATE * FRAME_DURATION / 1000) * BYTES_PER_SAMPLE
    for start in range(0, len(chunk_bytes), frame_length):
        frame = chunk_bytes[start:start+frame_length]
        if len(frame) < frame_length:
            break
        if vad.is_speech(frame, SAMPLE_RATE):
            return True
    return False

def extract_mfcc(chunk_bytes):
    # Convert bytes -> numpy array int16
    audio = np.frombuffer(chunk_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    mfcc = librosa.feature.mfcc(y=audio, sr=SAMPLE_RATE, n_mfcc=13)
    return np.mean(mfcc, axis=1)

async def index(request):
    html = """
<!doctype html>
<html>
<head><meta charset="utf-8" /><title>WebRTC Audio Capture VAD+Diarisation</title></head>
<body>
<h2>Test Microphone with VAD + Diarisation Basique</h2>
<button id="start">Start</button>
<button id="stop" disabled>Stop</button>
<pre id="log"></pre>

<script>
const logEl = document.getElementById('log');
function log(s){ logEl.textContent += s + "\\n"; }
let pc;

document.getElementById('start').onclick = async () => {
  pc = new RTCPeerConnection();
  pc.onconnectionstatechange = () => log('PC state: ' + pc.connectionState);
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach(track => pc.addTrack(track, stream));
  } catch(e) {
    log('getUserMedia failed: ' + e);
    return;
  }

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  const resp = await fetch('/offer', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type })
  });
  const answer = await resp.json();
  await pc.setRemoteDescription(answer);
  log('Started streaming to server.');
  document.getElementById('start').disabled = true;
  document.getElementById('stop').disabled = false;
};

document.getElementById('stop').onclick = () => {
  if (!pc) return;
  pc.getSenders().forEach(s => { if(s.track) s.track.stop(); });
  pc.close();
  pc = null;
  document.getElementById('start').disabled = false;
  document.getElementById('stop').disabled = true;
  log('Stopped.');
};
</script>
</body>
</html>
"""
    return web.Response(content_type='text/html', text=html)

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params['sdp'], type=params['type'])
    pc = RTCPeerConnection()
    pcs.add(pc)
    print("New PeerConnection")

    # On va stocker les chunks vocaux ici pour clustering
    local_speech_chunks = []

    @pc.on("track")
    def on_track(track):
        print("Track kind:", track.kind)
        if track.kind == "audio":

            async def recv_audio():
                buffer = bytearray()
                while True:
                    frame = await track.recv()
                    arr = frame.to_ndarray()
                    if arr.ndim == 2:
                        arr_t = arr.T.reshape(-1)
                    else:
                        arr_t = arr.reshape(-1)
                    chunk_bytes = arr_t.tobytes()

                    buffer.extend(chunk_bytes)
                    # Si buffer rempli > TARGET_BYTES (~1sec)
                    while len(buffer) >= TARGET_BYTES:
                        chunk = bytes(buffer[:TARGET_BYTES])
                        del buffer[:TARGET_BYTES]

                        if is_speech(chunk):
                            print(f"Speech chunk received, size={len(chunk)} bytes")
                            # Ajouter au buffer local
                            local_speech_chunks.append(chunk)
                            # Print chunk base64 prefix
                            print("CHUNK base64prefix=" + base64.b64encode(chunk)[:40].decode())
                        else:
                            print("Silence chunk ignoré")

                    # Dès qu'on a plus de 5 chunks, on fait un clustering basique
                    if len(local_speech_chunks) >= 5:
                        print("=== Diarisation clustering (k=2) ===")
                        mfccs = np.array([extract_mfcc(c) for c in local_speech_chunks])
                        kmeans = KMeans(n_clusters=2, random_state=0).fit(mfccs)
                        for i, label in enumerate(kmeans.labels_):
                            print(f"Chunk {i}: Speaker {label}")
                        # Reset la liste
                        local_speech_chunks.clear()

            asyncio.create_task(recv_audio())

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type='application/json',
        text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})
    )

async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

app = web.Application()
app.router.add_get("/", index)
app.router.add_post("/offer", offer)
app.on_cleanup.append(on_shutdown)

if __name__ == "__main__":
    web.run_app(app, port=8080)
