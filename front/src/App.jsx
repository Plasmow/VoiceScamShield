// Speedometer component (background, right side)
function Speedometer({ visible, speed = 0 }) {
  if (!visible) return null;
  // SVG arc for speedometer (top half-circle)
  const size = 260;
  const cx = size / 2;
  const cy = size / 2 + 40;
  const r = 110;
  // Top half: 180deg, 0 left, 200 right (normal)
  const startAngle = 180;
  const endAngle = 0;
  // Arc math helpers
  const polarToCartesian = (cx, cy, r, angle) => {
    const a = (angle-90) * Math.PI / 180.0;
    return {
      x: cx + (r * Math.cos(a)),
      y: cy + (r * Math.sin(a))
    };
  };
  // Ticks (dashes)
  const ticks = [];
  for (let i = 0; i <= 10; i++) {
    // Normal tick order
    const angle = startAngle + (endAngle - startAngle) * (i / 10);
    const p1 = polarToCartesian(cx, cy, r-8, angle);
    const p2 = polarToCartesian(cx, cy, r+8, angle);
    ticks.push(<line key={i} x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke="#111" strokeWidth={i%5===0?4:2} opacity={i%2===0?0.9:0.5} />);
  }
  // Labels: 0 left, 200 right
  const labels = [0, 50, 100, 150, 200];
  const labelEls = labels.map((val, i) => {
    // Normal label order
    const angle = startAngle + (endAngle - startAngle) * (i / (labels.length-1));
    // For the 0 label, move it slightly inward to ensure visibility
    let labelRadius = r + 28;
    if (val === 0) labelRadius = r + 12;
    const p = polarToCartesian(cx, cy, labelRadius, angle);
    // Rotate text 90deg right (clockwise) around its center
    return (
      <text
        key={val}
        x={p.x}
        y={p.y}
        fill="#222"
        fontSize="20"
        fontWeight="bold"
        textAnchor="middle"
        alignmentBaseline="middle"
        opacity="0.85"
        transform={`rotate(90 ${p.x} ${p.y})`}
      >
        {val}
      </text>
    );
  });
  // Needle: from center to arc (radius), normal
  const clampedSpeed = Math.max(0, Math.min(200, speed));
  const needleAngle = startAngle + (endAngle - startAngle) * (clampedSpeed / 200);
  const needleEnd = polarToCartesian(cx, cy, r+8, needleAngle);
  return (
    <div style={{
      position: 'fixed',
      right: 72, // increased right margin
      top: '50%',
      transform: 'translateY(-50%)',
      zIndex: 1,
      pointerEvents: 'none',
      opacity: 0.45,
      filter: 'blur(0.5px)',
    }}>
      <svg width={size} height={size+40} style={{ transform: 'rotate(-90deg)', transformOrigin: '50% 50%' }}>
        {/* No arc, only dashes */}
        {ticks}
        {labelEls}
        {/* Red needle: from center to arc */}
        <line x1={cx} y1={cy} x2={needleEnd.x} y2={needleEnd.y} stroke="#e53935" strokeWidth="7" strokeLinecap="round" opacity="0.95" />
        <circle cx={cx} cy={cy} r={13} fill="#e53935" opacity="0.7" />
        <circle cx={cx} cy={cy} r={7} fill="#fff" opacity="0.9" />
      </svg>
    </div>
  );
}
import React, { useEffect, useState, useRef } from "react";


function SunIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5" fill="currentColor" />
      <g stroke="currentColor">
        <line x1="12" y1="1" x2="12" y2="3" />
        <line x1="12" y1="21" x2="12" y2="23" />
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
        <line x1="1" y1="12" x2="3" y2="12" />
        <line x1="21" y1="12" x2="23" y2="12" />
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
      </g>
    </svg>
  );
}

function MoonIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3a7 7 0 0 0 9.79 9.79z" fill="currentColor" />
    </svg>
  );
}

// Define palettes
const lightPalette = ['#328E6E', '#67AE6E', '#90C67C', '#E1EEBC'];
// Interchanged palette for dark mode
const darkPalette = ['#DAD3BE', '#B7B597', '#6B8A7A', '#254336'];

function MicIcon({ isActive }) {
  return (
    <svg
      className={`w-16 h-16 mx-auto mb-4 ${isActive ? "animate-pulse-mic" : ""}`}
      viewBox="0 0 24 24"
      fill={isActive ? "#22c55e" : "#6b7280"}
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10v2a7 7 0 0 0 14 0v-2" stroke="#111" strokeWidth="2" fill="none" />
      <line x1="12" y1="20" x2="12" y2="22" stroke="#111" strokeWidth="2" />
      <line x1="8" y1="22" x2="16" y2="22" stroke="#111" strokeWidth="2" />
    </svg>
  );
}

function VoiceDots({ analyser, palette, shadowColor }) {
  const canvasRef = useRef(null);
  const amplitudeRef = useRef(0);
  useEffect(() => {
    if (!analyser) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const dataArray = new Uint8Array(analyser.fftSize);
    let animationId;
    function easeInOut(t) {
      // cubic ease in/out
      return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    }
    function draw() {
      analyser.getByteTimeDomainData(dataArray);
      // Calculate root mean square (RMS) amplitude for smoothness
      let sumSquares = 0;
      for (let i = 0; i < dataArray.length; i++) {
        const centered = dataArray[i] - 128;
        sumSquares += centered * centered;
      }
      let rms = Math.sqrt(sumSquares / dataArray.length) / 128; // 0..1
      rms = Math.min(1, rms * 4 / 1.5); // Reduce sensitivity by dividing by 1.5
      // Apply a gamma curve to boost low values without affecting high values
      const gamma = 0.5; // < 1 boosts low values
      const adjusted = Math.pow(rms, gamma);
      amplitudeRef.current = amplitudeRef.current * 0.7 + adjusted * 0.3;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      // Dots parameters
      const dotCount = 4;
      const spacing = 48; // 2x bigger
      const baseRadius = 20; // 2x bigger
      const minHeight = 40; // 2x bigger
      const maxHeight = 256; // 20% less than 320 for slightly decreased amplitude
      const centerY = canvas.height / 2;
      const totalWidth = (dotCount - 1) * spacing;
      const startX = (canvas.width - totalWidth) / 2;
      const now = Date.now();
      // Each dot has a different amplitude multiplier and delay
      const ampMultipliers = [1, 0.7, 1.2, 0.85];
      const delays = [0, 80, 160, 240]; // ms delay between dots
      for (let i = 0; i < dotCount; i++) {
        const x = startX + i * spacing;
        // Delay and phase offset
        const t = ((now - delays[i]) % 1000) / 1000;
        // Use amplitude with multiplier and ease
        const eased = easeInOut(amplitudeRef.current);
        const amplitude = Math.max(0, Math.min(1, eased * ampMultipliers[i]));
        let height = minHeight + (maxHeight - minHeight) * amplitude;
        // Clamp height so it never exceeds canvas height
        height = Math.min(height, canvas.height - 4); // 2px margin top/bottom
        const width = baseRadius * 2;
        const radius = baseRadius;
        const rectX = x - width / 2;
        const rectY = centerY - height / 2;
        ctx.save();
        ctx.beginPath();
        // Draw rounded rectangle (bar with soft edges)
        ctx.moveTo(rectX + radius, rectY);
        ctx.lineTo(rectX + width - radius, rectY);
        ctx.quadraticCurveTo(rectX + width, rectY, rectX + width, rectY + radius);
        ctx.lineTo(rectX + width, rectY + height - radius);
        ctx.quadraticCurveTo(rectX + width, rectY + height, rectX + width - radius, rectY + height);
        ctx.lineTo(rectX + radius, rectY + height);
        ctx.quadraticCurveTo(rectX, rectY + height, rectX, rectY + height - radius);
        ctx.lineTo(rectX, rectY + radius);
        ctx.quadraticCurveTo(rectX, rectY, rectX + radius, rectY);
        ctx.closePath();
        // Palette gradient
        const grad = ctx.createLinearGradient(rectX, rectY, rectX, rectY + height);
        grad.addColorStop(0, palette[0]);
        grad.addColorStop(0.33, palette[1]);
        grad.addColorStop(0.66, palette[2]);
        grad.addColorStop(1, palette[3]);
        ctx.fillStyle = grad;
        ctx.shadowColor = shadowColor;
        ctx.shadowBlur = 24;
        ctx.fill();
        ctx.restore();
      }
      animationId = requestAnimationFrame(draw);
    }
    draw();
    return () => cancelAnimationFrame(animationId);
  }, [analyser, palette, shadowColor]);
  return <canvas ref={canvasRef} width={240} height={200} className="mx-auto block" style={{background: 'none', display: 'block'}} />;
}

export default function App() {
  const [status, setStatus] = useState("Idle");
  const [alert, setAlert] = useState(null);
  const [darkMode, setDarkMode] = useState(false);
  const [startDisabled, setStartDisabled] = useState(true);
  const [speed, setSpeed] = useState(0); // 0-200
  const [typedText, setTypedText] = useState("");
  // ...existing code...
  const ws = useRef(null);
  const mediaRecorder = useRef(null);
  const [analyser, setAnalyser] = useState(null);
  const audioContextRef = useRef(null);
  const sourceRef = useRef(null);
  // ...existing code...
  // Choose palette and colors based on mode
  const palette = darkMode ? darkPalette : lightPalette;
  // Use animated palette gradient only in light mode
  const movingBgGradient = darkMode ? 'none' : `linear-gradient(90deg, ${palette[0]}, ${palette[0]}, ${palette[1]}, ${palette[2]}, ${palette[3]}, ${palette[2]}, ${palette[1]}, ${palette[0]})`;
  // Lighten the dark mode background by blending #004030 with a lighter shade
  const bgColor = darkMode ? '#1a4d3a' : '#FFFFFF';
  // In dark mode, swap button and card colors
  const cardBg = darkMode ? palette[2] : '#FFFFFF';
  const cardBorder = darkMode ? palette[1] : '#90C67C';
  const cardShadow = '0 2px 8px #000';
  const btnBg = darkMode ? '#22281f' : '#FFFFFF';
  const btnColor = darkMode ? palette[0] : '#328E6E';
  const btnBorder = darkMode ? palette[3] : '#67AE6E';
  const btnShadow = '0 2px 6px #000';
  const stopBtnBg = darkMode ? palette[3] : '#90C67C';
  const stopBtnColor = darkMode ? palette[0] : '#328E6E';
  const stopBtnBorder = darkMode ? palette[0] : '#67AE6E';
  const alertBg = darkMode ? '#22281f' : '#FFFFFF';
  const alertColor = darkMode ? palette[0] : '#328E6E';
  const alertBorder = darkMode ? palette[1] : '#67AE6E';
  const alertShadow = '0 2px 6px #000';
  const headingColor = darkMode ? palette[0] : '#328E6E';
  const headingShadow = darkMode ? `0 1px 3px #000, 0 1px 2px ${palette[3]}` : '0 1px 3px #000, 0 1px 2px #E1EEBC';
  const dotsShadow = darkMode ? 'rgba(37, 67, 54, 0.25)' : 'rgba(50, 142, 110, 0.25)';
  // Disable Start button for 2 seconds after mount
  useEffect(() => {
    setStartDisabled(true);
    const timer = setTimeout(() => setStartDisabled(false), 2000);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [darkMode]);

  useEffect(() => {
    ws.current = new WebSocket("ws://localhost:8000/ws"); // Adjust your backend URL

    ws.current.onopen = () => setStatus("WebSocket connected");
    ws.current.onclose = () => setStatus("WebSocket disconnected");
    ws.current.onerror = (err) => console.error("WS error", err);
    ws.current.onmessage = (msg) => {
      setAlert(msg.data);
      setTimeout(() => setAlert(null), 5000);
    };

    return () => {
      ws.current.close();
    };
  }, []);

  const startRecording = async () => {
    setStatus("Requesting microphone...");
  // ...existing code...
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Setup Web Audio API for waveform
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;
      const analyserNode = audioContext.createAnalyser();
      analyserNode.fftSize = 256;
      source.connect(analyserNode);
      setAnalyser(analyserNode);

      mediaRecorder.current = new MediaRecorder(stream);
      mediaRecorder.current.ondataavailable = (e) => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
          ws.current.send(e.data);
        }
      };
      mediaRecorder.current.start(1000);
      setStatus("Recording and streaming audio...");
    } catch (e) {
      setStatus("Microphone access denied");
    }
  };

  const stopRecording = () => {
    mediaRecorder.current?.stop();
    setStatus("Stopped");
    setAnalyser(null);
  // ...existing code...
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
  };

  // Animation state for sliding
  const [slid, setSlid] = useState(false);
  useEffect(() => {
    if (status === "Recording and streaming audio...") setSlid(true);
    else setSlid(false);
  }, [status]);

  // Keyboard event for 's' to increase speed and for real-time text
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (status === "Recording and streaming audio...") {
        // Ignore modifier keys
        if (e.key.length === 1) {
          setTypedText((prev) => prev + e.key);
        } else if (e.key === 'Backspace') {
          setTypedText((prev) => prev.slice(0, -1));
        } else if (e.key === 'Enter') {
          setTypedText((prev) => prev + '\n');
        }
      }
      // Keep speed shortcut
      if (e.key === 's' || e.key === 'S') {
        setSpeed((prev) => Math.min(200, prev + 10));
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [status]);

  // Reset typed text when not recording
  useEffect(() => {
    if (status !== "Recording and streaming audio...") {
      setTypedText("");
    }
  }, [status]);

  return (
    <>
      <Speedometer visible={status === "Recording and streaming audio..."} speed={speed} />
      <div className="min-h-screen relative flex flex-col items-center justify-center px-6" style={{background: bgColor}}>
      {/* Animated background blobs */}
      <div style={{position:'absolute', inset:0, zIndex:0, overflow:'hidden', pointerEvents:'none'}} aria-hidden="true">
        {/* Animated background overlay */}
        {!darkMode && (
          <>
            <style>{`
              @keyframes gradientMove {
                0% { opacity: 0.15; background-position: 0% 50%; }
                10% { opacity: 0.35; }
                50% { opacity: 0.35; background-position: 100% 50%; }
                90% { opacity: 0.35; }
                100% { opacity: 0.15; background-position: 0% 50%; }
              }
            `}</style>
            <div style={{
              position:'absolute',
              inset:0,
              width:'100%',
              height:'100%',
              background: movingBgGradient,
              backgroundSize:'200% 200%',
              opacity:0,
              animation:'gradientMove 18s infinite',
              zIndex:1,
              pointerEvents:'none',
            }} />
          </>
        )}
        {darkMode && (
          <>
            <style>{`
              @keyframes darkBgPulse {
                0%   { opacity: 0.10; background-position: 0% 0%; }
                20%  { opacity: 0.16; background-position: 80% 20%; }
                40%  { opacity: 0.22; background-position: 20% 80%; }
                60%  { opacity: 0.18; background-position: 100% 100%; }
                80%  { opacity: 0.14; background-position: 40% 60%; }
                100% { opacity: 0.10; background-position: 0% 0%; }
              }
            `}</style>
            <div style={{
              position:'absolute',
              inset:0,
              width:'100%',
              height:'100%',
              background: 'radial-gradient(circle at 60% 40%, #DAD3BE33 0%, #1a4d3a00 70%)',
              opacity:0.18,
              animation:'darkBgPulse 16s ease-in-out infinite',
              backgroundSize:'200% 200%',
              zIndex:1,
              pointerEvents:'none',
            }} />
          </>
        )}
      </div>
      <header className="w-full max-w-md flex justify-between items-center mb-8 relative z-10"
        style={{
          transform: slid ? 'translateY(-60px)' : 'translateY(0)',
          transition: 'transform 0.7s cubic-bezier(.7,1.7,.5,1)',
        }}>
        <h1 className="text-3xl font-bold" style={{color: headingColor, textShadow: headingShadow}}>Voice Scam Shield</h1>
        <div style={{display: 'flex', alignItems: 'center', gap: 16}}>
          {/* Dashboard Link Button */}
          <a
            href="/hack-app/index.html"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              padding: '6px 18px',
              background: palette[0],
              color: '#fff',
              borderRadius: 16,
              fontWeight: 600,
              fontSize: 16,
              textDecoration: 'none',
              boxShadow: '0 1px 6px #0002',
              border: `2px solid ${palette[1]}`,
              marginRight: 8,
              transition: 'background 0.2s',
            }}
          >
            Dashboard
          </a>
          {/* Custom dark/light mode toggle switch */}
          <div
            onClick={() => setDarkMode(!darkMode)}
            style={{
              width: 54,
              height: 28,
              background: darkMode ? palette[2] : palette[0],
              borderRadius: 20,
              display: 'flex',
              alignItems: 'center',
              cursor: 'pointer',
              boxShadow: btnShadow,
              border: `2px solid ${darkMode ? palette[1] : palette[1]}`,
              position: 'relative',
              transition: 'background 0.3s',
            }}
          >
            <span style={{
              position: 'absolute',
              left: darkMode ? 26 : 4,
              top: 4,
              width: 20,
              height: 20,
              borderRadius: '50%',
              background: darkMode ? palette[0] : '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: darkMode ? palette[2] : palette[0],
              boxShadow: '0 1px 4px #0002',
              transition: 'left 0.3s cubic-bezier(.4,2,.6,1), background 0.3s',
              zIndex: 2,
            }}>
              {darkMode ? <MoonIcon size={16} /> : <SunIcon size={16} />}
            </span>
            {/* Sun icon left, moon icon right */}
            <span style={{marginLeft: 8, color: palette[0], opacity: darkMode ? 0.5 : 1, transition: 'opacity 0.3s'}}>
              <SunIcon size={16} />
            </span>
            <span style={{marginLeft: 'auto', marginRight: 8, color: palette[2], opacity: darkMode ? 1 : 0.5, transition: 'opacity 0.3s'}}>
              <MoonIcon size={16} />
            </span>
          </div>
        </div>
      </header>

          <div className="w-full max-w-md rounded-2xl shadow-2xl p-8 space-y-6 border"
            style={{
              background: cardBg,
              borderColor: cardBorder,
              zIndex:1,
              boxShadow: cardShadow,
              transform: slid ? 'translateX(calc(-120% + 48px))' : 'translateX(0)',
              transition: 'transform 0.7s cubic-bezier(.7,1.7,.5,1)',
            }}>
  {/* ...existing code... */}
  {/* Thermometer (right side, only when recording) - OUTSIDE main container */}
  {/* ...existing code... */}
        <p className="text-lg font-semibold">
          Status: <span className="font-normal">{status}</span>
        </p>
        {/* Animated mic icon and waveform when recording */}
        {status === "Recording and streaming audio..." && (
          <div className="flex justify-center items-center w-full">
            <VoiceDots analyser={analyser} palette={palette} shadowColor={dotsShadow} />
          </div>
        )}
        <div className="flex space-x-4 mt-4">
          <button
            onClick={startRecording}
            disabled={startDisabled}
            className={`flex-1 font-bold py-3 rounded-xl shadow border transition ${startDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            style={{background: btnBg, color: btnColor, borderColor: btnBorder, boxShadow: btnShadow}}>
            Start
          </button>
          <button
            onClick={stopRecording}
            className="flex-1 font-bold py-3 rounded-xl shadow border transition"
            style={{background: stopBtnBg, color: stopBtnColor, borderColor: stopBtnBorder, boxShadow: btnShadow}}>
            Stop
          </button>
        </div>
      </div>

      {alert && (
        <div className="fixed bottom-8 right-8 max-w-xs px-6 py-4 rounded-xl shadow-2xl animate-fadeInOut z-50 border"
          style={{background: alertBg, color: alertColor, borderColor: alertBorder, boxShadow: alertShadow}}>
          <p className="font-bold text-lg drop-shadow">⚠️ Alert</p>
          <p>{alert}</p>
        </div>
      )}

      {/* Real-time typed text at the bottom when recording */}
      {status === "Recording and streaming audio..." && (
        <div style={{
          position: 'fixed',
          left: 0,
          right: 0,
          bottom: 0,
          padding: '24px 0 32px 0',
          background: 'rgba(255,255,255,0.85)',
          color: '#222',
          fontSize: 22,
          fontFamily: 'monospace',
          textAlign: 'center',
          whiteSpace: 'pre-wrap',
          zIndex: 50,
          pointerEvents: 'none',
          boxShadow: '0 -2px 12px #0002',
        }}>
          {typedText || <span style={{opacity:0.4}}>[Type to see text here]</span>}
        </div>
      )}

      <style>{`
        @keyframes fadeInOut {
          0%, 100% {opacity: 0; transform: translateY(10px);}
          10%, 90% {opacity: 1; transform: translateY(0);}
        }
        .animate-fadeInOut {
          animation: fadeInOut 5s ease forwards;
        }
        @keyframes pulse-mic {
          0%, 100% { transform: scale(1); filter: drop-shadow(0 0 0 #22c55e); }
          50% { transform: scale(1.15); filter: drop-shadow(0 0 12px #22c55e); }
        }
        .animate-pulse-mic {
          animation: pulse-mic 1s infinite;
        }
      `}</style>
  </div>
  </>
  )
}
