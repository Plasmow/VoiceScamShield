import React, { useEffect, useRef, useState } from "react";

function AudioStreamer() {
  const ws = useRef(null);
  const mediaRecorder = useRef(null);
  const audioContext = useRef(null);
  const sourceNode = useRef(null);
  const processorNode = useRef(null);
  const [isStreaming, setIsStreaming] = useState(false);

  // Fonction pour convertir Float32Array [-1,1] en Int16 PCM
  function floatTo16BitPCM(input) {
    const output = new Int16Array(input.length);
    for (let i = 0; i < input.length; i++) {
      let s = Math.max(-1, Math.min(1, input[i]));
      output[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return output;
  }

  // Resample buffer audio à 16kHz mono
  function downsampleBuffer(buffer, inputSampleRate, outputSampleRate = 16000) {
    if (outputSampleRate === inputSampleRate) return buffer;
    const sampleRateRatio = inputSampleRate / outputSampleRate;
    const newLength = Math.round(buffer.length / sampleRateRatio);
    const result = new Float32Array(newLength);
    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < result.length) {
      const nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio);
      let accum = 0, count = 0;
      for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
        accum += buffer[i];
        count++;
      }
      result[offsetResult] = accum / count;
      offsetResult++;
      offsetBuffer = nextOffsetBuffer;
    }
    return result;
  }

  async function startStreaming() {
    ws.current = new WebSocket("ws://localhost:8000/ws/media");
    ws.current.onopen = () => console.log("WebSocket connected");

    audioContext.current = new (window.AudioContext || window.webkitAudioContext)();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    sourceNode.current = audioContext.current.createMediaStreamSource(stream);

    processorNode.current = audioContext.current.createScriptProcessor(4096, 1, 1);
    processorNode.current.onaudioprocess = (e) => {
      const inputData = e.inputBuffer.getChannelData(0);
      // Downsample to 16kHz mono
      const downsampled = downsampleBuffer(inputData, audioContext.current.sampleRate, 16000);
      // Convert to 16bit PCM
      const pcm16 = floatTo16BitPCM(downsampled);
      // Encode en base64
      const audioBase64 = btoa(String.fromCharCode(...new Uint8Array(pcm16.buffer)));

      // Send JSON chunk
      if (ws.current.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify({
          event: "media",
          media: {
            payload: audioBase64,
            mime_type: "audio/pcm",
            sample_rate: 16000,
            channels: 1,
            sample_width: 2
          }
        }));
      }
    };

    sourceNode.current.connect(processorNode.current);
    processorNode.current.connect(audioContext.current.destination);

    setIsStreaming(true);
  }

  function stopStreaming() {
    if (processorNode.current) processorNode.current.disconnect();
    if (sourceNode.current) sourceNode.current.disconnect();
    if (audioContext.current) audioContext.current.close();
    if (ws.current) ws.current.close();
    setIsStreaming(false);
  }

  return (
    <div>
      <button onClick={startStreaming} disabled={isStreaming}>
        Start Streaming
      </button>
      <button onClick={stopStreaming} disabled={!isStreaming}>
        Stop Streaming
      </button>
    </div>
  );
}

export default AudioStreamer;
