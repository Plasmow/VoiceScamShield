import asyncio
import json
import wave
import numpy as np
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription

pcs = set()

class RealTimeWavWriter:
    def __init__(self, filename, sample_rate=16000):
        self.filename = filename
        self.sample_rate = sample_rate
        self.wavefile = wave.open(filename, 'wb')
        self.wavefile.setnchannels(1)       # Mono
        self.wavefile.setsampwidth(2)       # 16 bits = 2 bytes per sample
        self.wavefile.setframerate(sample_rate)
        self.closed = False
        self.total_frames = 0

    def write_chunk(self, chunk_bytes):
        if self.closed:
            raise RuntimeError("Trying to write to closed file")
        self.wavefile.writeframes(chunk_bytes)
        self.total_frames += len(chunk_bytes) // 2  # 2 bytes per sample
        
    def get_duration(self):
        return self.total_frames / self.sample_rate

    def close(self):
        if not self.closed:
            self.wavefile.close()
            self.closed = True
            print(f"WAV file '{self.filename}' closed. Duration: {self.get_duration():.2f}s")

async def index(request):
    # (même code HTML que précédemment, inchangé)
    html = """
<!doctype html>
<html>
<head><title>WebRTC Audio Capture</title></head>
<body>
<h2>WebRTC Audio Capture Test</h2>
<p>Microphone only</p>
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
  log('Stopped.');
  document.getElementById('start').disabled = false;
  document.getElementById('stop').disabled = true;
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

    wav_writer = RealTimeWavWriter("output.wav")

    @pc.on("track")
    def on_track(track):
        print("Track kind:", track.kind)
        if track.kind == "audio":
            async def recv_audio():
                try:
                    frame_count = 0
                    
                    while True:
                        frame = await track.recv()
                        frame_count += 1
                        
                        # Get frame information
                        sample_rate = frame.sample_rate
                        
                        if frame_count <= 3:  # Log first few frames
                            print(f"Frame {frame_count}: sample_rate={sample_rate}, samples={frame.samples}")
                        
                        # Convert frame to numpy array
                        try:
                            arr = frame.to_ndarray()
                            if frame_count <= 3:
                                print(f"Array shape: {arr.shape}, dtype: {arr.dtype}")
                        except Exception as conv_error:
                            print(f"Error converting frame: {conv_error}")
                            continue
                        
                        # Convert to mono
                        if arr.ndim == 2:
                            # Take first channel
                            arr_mono = arr[0] if arr.shape[0] <= arr.shape[1] else arr[:, 0]
                        else:
                            arr_mono = arr.flatten()
                        
                        # Convert to float32 and normalize
                        if arr_mono.dtype.kind == 'f':
                            audio_float = arr_mono.astype(np.float32)
                        else:
                            if arr_mono.dtype == np.int16:
                                audio_float = arr_mono.astype(np.float32) / 32768.0
                            else:
                                audio_float = arr_mono.astype(np.float32) / np.iinfo(arr_mono.dtype).max
                        
                        # Clip to prevent saturation
                        audio_float = np.clip(audio_float, -1.0, 1.0)
                        
                        # Convert to int16 for WAV
                        audio_int16 = (audio_float * 32767.0).astype(np.int16)
                        
                        # Write to WAV file
                        chunk_bytes = audio_int16.tobytes()
                        wav_writer.write_chunk(chunk_bytes)
                        
                        if frame_count % 100 == 0:  # Log every 100 frames
                            duration = wav_writer.get_duration()
                            print(f"Recording... {duration:.1f}s")
                        
                except Exception as e:
                    print("Audio track recv stopped:", e)
                    wav_writer.close()
            asyncio.create_task(recv_audio())

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type='application/json',
        text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})
    )

async def on_shutdown(app):
    for pc in pcs:
        await pc.close()
    pcs.clear()

app = web.Application()
app.router.add_get("/", index)
app.router.add_post("/offer", offer)
app.on_cleanup.append(on_shutdown)

if __name__ == "__main__":
    web.run_app(app, port=8080)
