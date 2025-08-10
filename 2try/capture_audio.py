import asyncio
import json
import base64
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
import webrtcvad

pcs = set()
filtered_chunks = []

vad = webrtcvad.Vad(2)  # Sensibilité 0-3

TARGET_BYTES = 32000  # taille chunk (~1s 16kHz 16-bit mono)

def is_speech(chunk_bytes, sample_rate=16000):
    frame_length = int(sample_rate * 2 * 0.01)  # 10ms frames = 320 bytes
    if len(chunk_bytes) % frame_length != 0:
        chunk_bytes = chunk_bytes[:len(chunk_bytes) - (len(chunk_bytes) % frame_length)]
    for i in range(0, len(chunk_bytes), frame_length):
        frame = chunk_bytes[i:i+frame_length]
        if vad.is_speech(frame, sample_rate):
            return True
    return False

async def index(request):
    html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>WebRTC Audio Capture with VAD</title>
</head>
<body>
  <h2>WebRTC Audio Capture with VAD Filtering</h2>
  <p>Click start to stream microphone audio (filtered by VAD).</p>
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

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    log('getUserMedia failed: ' + e);
    return;
  }

  stream.getTracks().forEach(track => pc.addTrack(track, stream));

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
  pc.getSenders().forEach(s => { if (s.track) s.track.stop(); });
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
                    # Quand buffer dépasse TARGET_BYTES, on check VAD
                    while len(buffer) >= TARGET_BYTES:
                        chunk = bytes(buffer[:TARGET_BYTES])
                        del buffer[:TARGET_BYTES]
                        if is_speech(chunk):
                            print(f"VAD accepted chunk size={len(chunk)}")
                            filtered_chunks.append(chunk)
                        else:
                            print("VAD rejected chunk (silence/noise)")
            asyncio.create_task(recv_audio())

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type='application/json',
        text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})
    )

async def get_chunks(request):
    # Retourne les chunks filtrés encodés en base64 puis vide la liste
    global filtered_chunks
    chunks_b64 = [base64.b64encode(c).decode() for c in filtered_chunks]
    filtered_chunks = []
    return web.json_response({"chunks": chunks_b64})

async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

app = web.Application()
app.router.add_get("/", index)
app.router.add_post("/offer", offer)
app.router.add_get("/chunks", get_chunks)
app.on_cleanup.append(on_shutdown)

if __name__ == "__main__":
    web.run_app(app, port=8080)
