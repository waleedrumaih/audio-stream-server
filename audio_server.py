import asyncio
import websockets
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ─── All connected browser listeners ─────────────────
listeners = set()

# ─── HTML Player Page ─────────────────────────────────
HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🎙️ Live Audio Stream</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #0f0f1a;
      color: #fff;
      font-family: -apple-system, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      gap: 30px;
    }
    h1 { font-size: 2rem; }
    .status {
      padding: 10px 24px;
      border-radius: 20px;
      font-size: 0.9rem;
      background: #1e1e2e;
    }
    .status.connected  { background: #1a3a2a; color: #4ade80; }
    .status.disconnected { background: #3a1a1a; color: #f87171; }
    button {
      padding: 16px 40px;
      font-size: 1.2rem;
      border: none;
      border-radius: 50px;
      cursor: pointer;
      background: #6366f1;
      color: white;
      transition: all 0.2s;
    }
    button:hover  { background: #4f46e5; transform: scale(1.05); }
    button:disabled { background: #374151; cursor: not-allowed; }
    canvas {
      width: 300px; height: 80px;
      border-radius: 12px;
      background: #1e1e2e;
    }
    .info { color: #6b7280; font-size: 0.85rem; }
  </style>
</head>
<body>
  <h1>🎙️ Live Audio</h1>
  <div class="status disconnected" id="status">⚫ Disconnected</div>
  <canvas id="viz" width="300" height="80"></canvas>
  <button id="btn" onclick="startListening()">▶ Start Listening</button>
  <div class="info">16kHz · Stereo · PCM</div>

  <script>
    const WS_URL = `ws://${location.hostname}:8765/listen`;
    let ws, audioCtx, analyser, animFrame;
    let sampleRate = 16000;
    let isPlaying  = false;
    let nextPlayTime = 0;

    function setStatus(text, connected) {
      const el = document.getElementById('status');
      el.textContent = text;
      el.className = 'status ' + (connected ? 'connected' : 'disconnected');
    }

    function startListening() {
      if (isPlaying) { stopListening(); return; }

      audioCtx = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: sampleRate
      });
      analyser = audioCtx.createAnalyser();
      analyser.connect(audioCtx.destination);
      nextPlayTime = audioCtx.currentTime;
      isPlaying = true;
      document.getElementById('btn').textContent = '⏹ Stop';

      ws = new WebSocket(WS_URL);
      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        setStatus('🟢 Connected — Listening live!', true);
        drawViz();
      };

      ws.onmessage = (event) => {
        const int16   = new Int16Array(event.data);
        const float32 = new Float32Array(int16.length / 2);
        for (let i = 0; i < float32.length; i++) {
          float32[i] = ((int16[i*2] + int16[i*2+1]) / 2) / 32768.0;
        }
        const buffer = audioCtx.createBuffer(1, float32.length, sampleRate);
        buffer.copyToChannel(float32, 0);
        const source = audioCtx.createBufferSource();
        source.buffer = buffer;
        source.connect(analyser);
        if (nextPlayTime < audioCtx.currentTime) nextPlayTime = audioCtx.currentTime + 0.05;
        source.start(nextPlayTime);
        nextPlayTime += buffer.duration;
      };

      ws.onclose = () => { setStatus('⚫ Disconnected', false); stopListening(); };
      ws.onerror = () => setStatus('❌ Error', false);
    }

    function stopListening() {
      isPlaying = false;
      if (ws) ws.close();
      if (audioCtx) audioCtx.close();
      if (animFrame) cancelAnimationFrame(animFrame);
      document.getElementById('btn').textContent = '▶ Start Listening';
      setStatus('⚫ Disconnected', false);
    }

    function drawViz() {
      const canvas = document.getElementById('viz');
      const ctx = canvas.getContext('2d');
      const W = canvas.width, H = canvas.height;
      function draw() {
        animFrame = requestAnimationFrame(draw);
        if (!analyser) return;
        const data = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteTimeDomainData(data);
        ctx.fillStyle = '#1e1e2e';
        ctx.fillRect(0, 0, W, H);
        ctx.strokeStyle = '#6366f1';
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (let i = 0; i < data.length; i++) {
          const x = (i / data.length) * W;
          const y = (data[i] / 128.0) * H / 2;
          i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
      draw();
    }
  </script>
</body>
</html>"""

# ─── HTTP server for the web page ────────────────────
class PageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(HTML.encode())
    def log_message(self, format, *args):
        pass

def start_http():
    server = HTTPServer(('0.0.0.0', 8080), PageHandler)
    server.serve_forever()

# ─── WebSocket handler (new API) ──────────────────────
async def handle_connection(websocket):
    global listeners
    path = websocket.request.path  # ← new API way to get path

    if path == "/audio":
        # ESP32 connects here and sends audio
        print(f"🎙️  ESP32 connected!")
        try:
            async for message in websocket:
                if listeners:
                    await asyncio.gather(
                        *[l.send(message) for l in listeners],
                        return_exceptions=True
                    )
        except Exception as e:
            print(f"ESP32 error: {e}")
        finally:
            print("📴 ESP32 disconnected")

    elif path == "/listen":
        # Browser connects here to receive audio
        listeners.add(websocket)
        print(f"👂 Browser listener connected! Total: {len(listeners)}")
        try:
            await websocket.wait_closed()
        finally:
            listeners.discard(websocket)
            print(f"👋 Listener left. Total: {len(listeners)}")

    else:
        await websocket.close()

async def main():
    # Start HTTP in background thread
    t = threading.Thread(target=start_http, daemon=True)
    t.start()

    print("🚀 Audio Streaming Server Started!")
    print("─────────────────────────────────────")
    print("🌐 Web player  : http://localhost:8080")
    print("🔌 ESP32 port  : 8765  (path: /audio)")
    print("👂 Browser port: 8765  (path: /listen)")
    print("─────────────────────────────────────")
    print("To share publicly run:")
    print("  ngrok http 8080")
    print("─────────────────────────────────────\n")

    async with websockets.serve(handle_connection, "0.0.0.0", 8765):
        await asyncio.Future()

asyncio.run(main())