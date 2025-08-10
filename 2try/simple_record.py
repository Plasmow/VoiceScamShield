import asyncio
import json
import wave
import numpy as np
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription

pcs = set()

class SimpleWavWriter:
    def __init__(self, filename):
        self.filename = filename
        self.wavefile = wave.open(filename, 'wb')
        self.wavefile.setnchannels(1)       # Mono
        self.wavefile.setsampwidth(2)       # 16 bits
        self.wavefile.setframerate(48000)   # Use original sample rate
        self.frames_written = 0

    def write_chunk(self, chunk_bytes):
        self.wavefile.writeframes(chunk_bytes)
        self.frames_written += len(chunk_bytes) // 2

    def close(self):
        self.wavefile.close()
        duration = self.frames_written / 48000
        print(f"WAV file saved: {self.filename}, duration: {duration:.2f}s")

async def index(request):
    html = """
<!doctype html>
<html>
<head><title>Simple Audio Recording</title></head>
<body>
<h2>Simple Audio Recording</h2>
<button id="start">Start Recording</button>
<button id="stop" disabled>Stop Recording</button>
<div id="status"></div>

<script>
const statusEl = document.getElementById('status');
let pc;

document.getElementById('start').onclick = async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ 
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false
      } 
    });
    
    pc = new RTCPeerConnection();
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

    statusEl.textContent = 'Recording started...';
    document.getElementById('start').disabled = true;
    document.getElementById('stop').disabled = false;
  } catch (e) {
    statusEl.textContent = 'Error: ' + e.message;
  }
};

document.getElementById('stop').onclick = () => {
  if (pc) {
    pc.getSenders().forEach(s => { if (s.track) s.track.stop(); });
    pc.close();
    pc = null;
  }
  statusEl.textContent = 'Recording stopped.';
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
    
    wav_writer = SimpleWavWriter("simple_recording.wav")
    print("Starting new recording...")

    @pc.on("track")
    def on_track(track):
        print(f"Track received: {track.kind}")
        if track.kind == "audio":
            async def save_audio():
                frame_count = 0
                try:
                    while True:
                        frame = await track.recv()
                        frame_count += 1
                        
                        # Get raw audio data
                        arr = frame.to_ndarray()
                        
                        # Simple conversion to mono int16
                        if arr.ndim == 2:
                            # Take one channel
                            audio = arr[0]
                        else:
                            audio = arr.flatten()
                        
                        # Convert to int16
                        if audio.dtype.kind == 'f':
                            audio_int16 = (audio * 32767).astype(np.int16)
                        else:
                            audio_int16 = audio.astype(np.int16)
                        
                        # Write to file
                        wav_writer.write_chunk(audio_int16.tobytes())
                        
                        if frame_count % 100 == 0:
                            print(f"Frames processed: {frame_count}")
                            
                except Exception as e:
                    print(f"Audio processing stopped: {e}")
                finally:
                    wav_writer.close()
                    
            asyncio.create_task(save_audio())

    @pc.on("connectionstatechange")
    def on_connection_state_change():
        print(f"Connection state: {pc.connectionState}")
        if pc.connectionState == "closed":
            wav_writer.close()

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
    print("Starting simple recording server on http://localhost:8080")
    web.run_app(app, port=8080)
