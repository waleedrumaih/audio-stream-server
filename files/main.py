import asyncio
import os
from aiohttp import web

listeners = set()

HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Live Audio Stream</title>
  <style>
    * { margin:0; padding:0; box-sizing:border-box; }
    body {
      background:#0f0f1a; color:#fff;
      font-family:-apple-system,sans-serif;
      display:flex; flex-direction:column;
      align-items:center; justify-content:center;
      min-height:100vh; gap:28px;
    }
    h1 { font-size:2rem; }
    .pill { padding:8px 22px; border-radius:20px; font-size:.85rem; background:#1e1e2e; }
    .on   { background:#1a3a2a; color:#4ade80; }
    .off  { background:#3a1a1a; color:#f87171; }
    button {
      padding:14px 38px; font-size:1.1rem; border:none;
      border-radius:50px; background:#6366f1; color:#fff;
      cursor:pointer; transition:.2s;
    }
    button:hover { background:#4f46e5; transform:scale(1.04); }
    canvas { border-radius:12px; background:#1e1e2e; }
    small  { color:#4b5563; }
  </style>
</head>
<body>
  <h1>Live Audio</h1>
  <div class="pill off" id="st">Disconnected</div>
  <canvas id="c" width="320" height="72"></canvas>
  <button onclick="go()">Start Listening</button>
  <small>16 kHz - PCM - Real-time</small>
<script>
  let ws,ac,an,af,playing=false,t0=0;
  function st(txt,ok){
    const e=document.getElementById('st');
    e.textContent=txt; e.className='pill '+(ok?'on':'off');
  }
  function go(){ playing?bye():hey(); }
  function hey(){
    ac=new (window.AudioContext||window.webkitAudioContext)({sampleRate:16000});
    an=ac.createAnalyser(); an.connect(ac.destination);
    t0=ac.currentTime; playing=true;
    document.querySelector('button').textContent='Stop';
    ws=new WebSocket('wss://'+location.host+'/listen');
    ws.binaryType='arraybuffer';
    ws.onopen =()=>{ st('Live!',true); viz(); };
    ws.onclose=()=>{ st('Disconnected',false); bye(); };
    ws.onerror=()=> st('Error',false);
    ws.onmessage=({data})=>{
      const i16=new Int16Array(data);
      const f32=new Float32Array(i16.length/2);
      for(let i=0;i<f32.length;i++)
        f32[i]=((i16[i*2]+i16[i*2+1])/2)/32768;
      const b=ac.createBuffer(1,f32.length,16000);
      b.copyToChannel(f32,0);
      const s=ac.createBufferSource();
      s.buffer=b; s.connect(an);
      if(t0<ac.currentTime) t0=ac.currentTime+.08;
      s.start(t0); t0+=b.duration;
    };
  }
  function bye(){
    playing=false;
    if(ws) ws.close();
    if(ac) ac.close();
    if(af) cancelAnimationFrame(af);
    document.querySelector('button').textContent='Start Listening';
    st('Disconnected',false);
  }
  function viz(){
    const cv=document.getElementById('c'),cx=cv.getContext('2d');
    const W=cv.width,H=cv.height;
    (function draw(){
      af=requestAnimationFrame(draw);
      if(!an)return;
      const d=new Uint8Array(an.frequencyBinCount);
      an.getByteTimeDomainData(d);
      cx.fillStyle='#1e1e2e'; cx.fillRect(0,0,W,H);
      cx.strokeStyle='#6366f1'; cx.lineWidth=2; cx.beginPath();
      d.forEach((v,i)=>{
        const x=(i/d.length)*W,y=(v/128)*H/2;
        i?cx.lineTo(x,y):cx.moveTo(x,y);
      });
      cx.stroke();
    })();
  }
</script>
</body>
</html>"""

async def http_handler(request):
    return web.Response(text=HTML, content_type='text/html')

async def health_handler(request):
    return web.Response(text='OK')

async def websocket_handler(request):
    path = request.path
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    if path == "/audio":
        print("ESP32 connected!")
        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.BINARY:
                    dead = set()
                    for listener in listeners:
                        try:
                            await listener.send_bytes(msg.data)
                        except Exception:
                            dead.add(listener)
                    listeners -= dead
        except Exception as e:
            print(f"ESP32 error: {e}")
        finally:
            print("ESP32 disconnected")

    elif path == "/listen":
        listeners.add(ws)
        print(f"Listener joined! Total: {len(listeners)}")
        try:
            async for msg in ws:
                pass  # browser doesn't send anything
        except Exception:
            pass
        finally:
            listeners.discard(ws)
            print(f"Listener left. Total: {len(listeners)}")

    return ws

async def main():
    port = int(os.environ.get("PORT", 8080))

    app = web.Application()
    app.router.add_get('/',        http_handler)
    app.router.add_get('/health',  health_handler)
    app.router.add_get('/audio',   websocket_handler)
    app.router.add_get('/listen',  websocket_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    print(f"Server ready on port {port}")
    await asyncio.Future()

asyncio.run(main())
