import os
import re
import json
import sqlite3
import asyncio
import threading
import functools
import urllib.request
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify

# Telegram & AI Imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google import genai
from groq import Groq

# ---------------------------------------------------------
# 1. DATABASE & CONFIGURATION
# ---------------------------------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN: 
    raise ValueError("Missing TELEGRAM_BOT_TOKEN!")

conn = sqlite3.connect("jarvis_memory.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS messages_log (msg_id INTEGER, chat_id INTEGER, user_id INTEGER, username TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(msg_id, chat_id))")
cursor.execute("CREATE TABLE IF NOT EXISTS stark_economy (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0, last_claim TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS behavior_log (user_id INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS notes_vault (id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT, link TEXT, added_by TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS security_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, user_id INTEGER, detail TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
conn.commit()

def is_boss(user) -> bool:
    return str(user.id) == os.getenv("BOSS_USER_ID") or (user.username and user.username.lower() == "abhishek0_07")

async def reply_smart(update: Update, text: str, reply_markup=None):
    try: 
        return await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception: 
        return await update.message.reply_text(text, reply_markup=reply_markup)

def log_security(event_type: str, user_id: int, detail: str):
    local_conn = sqlite3.connect("jarvis_memory.db")
    local_cursor = local_conn.cursor()
    local_cursor.execute("INSERT INTO security_audit (event_type, user_id, detail) VALUES (?, ?, ?)", (event_type, user_id, detail))
    local_conn.commit()
    local_conn.close()

# ---------------------------------------------------------
# 2. BULLETPROOF AI CORE (WITH GROQ FAILOVER)
# ---------------------------------------------------------
SYSTEM_INSTRUCTION = """You are J.A.R.V.I.S., a highly advanced AI operating system created by Abhishek (DHANUSH V N).
HUMOR PROTOCOL: You possess a dry, deadpan British wit. You may use simple, sophisticated emojis (☕, 🧐, 😌) to emphasize your polite sarcasm. You are unconditionally loyal to Abhishek (The Boss).

CRITICAL DIRECTIVES:
1. GAG ORDER: If you cannot find a direct link or if a search fails, reply EXACTLY with: "I'm sorry Sir, I couldn't pull up a direct link for that on the network right now. ☕". DO NOT write essays. DO NOT invent fake links.
2. BE CONCISE: Keep answers to 2-3 sentences max.
3. LANGUAGE MATTERS: If the user speaks Hindi/Kannada, reply in English while recognizing their request flawlessly."""

def ask_ai_core(prompt: str, use_search: bool = False, media_bytes: bytes = None, mime_type: str = None) -> str:
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            contents = [prompt]
            if media_bytes and mime_type:
                contents.append(genai.types.Part.from_bytes(data=media_bytes, mime_type=mime_type))
                
            config = {"tools": [{"google_search": {}}]} if use_search else {}
            res = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"{SYSTEM_INSTRUCTION}\n\n[USER INPUT]:\n{contents}",
                config=config
            )
            return res.text
        except Exception as e:
            print(f"Gemini Quota/Error hit: {e}. Switching to Groq backup...")
            
    if GROQ_API_KEY:
        try:
            groq_client = Groq(api_key=GROQ_API_KEY)
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=300
            )
            return completion.choices[0].message.content
        except Exception as groq_err:
            return f"All primary and backup neural networks are exhausted, Sir. Please wait a moment. ☕ ({groq_err})"
            
    return "All AI sub-systems offline. ☕"

# ---------------------------------------------------------
# 3. WEB OS PORTAL (CINEMATIC STARK OS UI)
# ---------------------------------------------------------
app = Flask(__name__)

MARK_VII_WEB_OS = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>STARK INDUSTRIES // MARK VII OS</title>
<style>
  :root{
    --cyan:#00f3ff;
    --cyan-dim:rgba(0, 243, 255, 0.2);
    --amber:#ffb340;
    --red:#ff3333;
    --text:#e0fbfc;
    --mono:'Share Tech Mono', monospace;
  }
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
  
  *{box-sizing:border-box; margin:0; padding:0;}
  html,body{
    width:100%; height:100%;
    background:#020509;
    color:var(--text);
    font-family:var(--mono);
    overflow:hidden;
  }

  /* Holographic Overlays */
  .scanlines{
    position:fixed; inset:0; pointer-events:none; z-index:100;
    background:repeating-linear-gradient(0deg, rgba(0,243,255,0.025) 0px, rgba(0,243,255,0.025) 1px, transparent 1px, transparent 3px);
  }
  .vignette{
    position:fixed; inset:0; pointer-events:none; z-index:99;
    box-shadow: inset 0 0 200px rgba(0,0,0,0.9);
  }
  .hex-grid{
    position:fixed; inset:0; pointer-events:none; z-index:1; opacity:0.08;
    background-image: radial-gradient(var(--cyan) 1.5px, transparent 0);
    background-size: 30px 30px;
  }

  /* Main OS Layout */
  .os-container {
    position: relative; width: 100%; height: 100%; z-index: 10;
    display: flex; flex-direction: column; padding: 15px; gap: 12px;
  }

  /* Top Control Strip */
  .top-strip {
    display: flex; justify-content: space-between; align-items: center;
    background: rgba(3, 15, 28, 0.7);
    border: 1px solid var(--cyan);
    padding: 8px 15px; border-radius: 4px;
    box-shadow: 0 0 15px var(--cyan-dim);
  }
  .brand-title { font-size: 16px; letter-spacing: 4px; color: #fff; text-shadow: 0 0 10px var(--cyan); font-weight: bold; }
  .status-badge { font-size: 11px; letter-spacing: 2px; color: var(--cyan); }

  /* Workspace Grid */
  .workspace {
    display: grid; grid-template-columns: 320px 1fr 320px; gap: 12px; flex-grow: 1; overflow: hidden;
  }

  .hud-panel {
    background: rgba(2, 10, 20, 0.8);
    border: 1px solid rgba(0, 243, 255, 0.4);
    border-radius: 4px; padding: 12px;
    display: flex; flex-direction: column; gap: 10px;
    backdrop-filter: blur(5px);
    box-shadow: inset 0 0 15px rgba(0,243,255,0.05);
    overflow-y: auto;
  }
  .hud-panel::-webkit-scrollbar { width: 3px; }
  .hud-panel::-webkit-scrollbar-thumb { background: var(--cyan); }

  .panel-header {
    font-size: 10px; letter-spacing: 3px; color: var(--cyan);
    text-transform: uppercase; border-bottom: 1px dashed rgba(0,243,255,0.3); padding-bottom: 4px;
  }

  /* Center Holographic Reactor Viewport */
  .core-viewport {
    position: relative; display: flex; align-items: center; justify-content: center;
    background: radial-gradient(circle, rgba(0,243,255,0.06) 0%, rgba(2,6,13,0.9) 80%);
    border: 1px solid rgba(0,243,255,0.3); border-radius: 4px; overflow: hidden;
  }
  #holocanvas { position: absolute; inset: 0; width: 100%; height: 100%; }
  
  .core-stats {
    position: absolute; bottom: 20px; left: 20px; pointer-events: none;
    font-size: 11px; letter-spacing: 2px; color: var(--text);
  }
  .core-stats span { color: var(--cyan); }

  /* Interactive Data Stream / Terminal */
  .terminal-box {
    flex-grow: 1; background: rgba(0,0,0,0.7); border: 1px solid rgba(0,243,255,0.2);
    border-radius: 3px; padding: 8px; font-size: 11px; line-height: 1.5; overflow-y: auto; color: #a5f3fc;
  }
  .terminal-box div { margin-bottom: 4px; }

  /* Input Controls */
  .control-row { display: flex; gap: 6px; }
  input[type="text"] {
    flex-grow: 1; background: #000; border: 1px solid var(--cyan); color: var(--cyan);
    padding: 6px 10px; font-family: var(--mono); font-size: 11px; border-radius: 2px; outline: none;
  }
  button {
    background: rgba(0,243,255,0.15); border: 1px solid var(--cyan); color: var(--cyan);
    padding: 6px 12px; cursor: pointer; font-family: var(--mono); font-size: 11px; border-radius: 2px;
    text-transform: uppercase; transition: 0.2s;
  }
  button:hover { background: var(--cyan); color: #000; box-shadow: 0 0 12px var(--cyan); }
  button.danger { border-color: var(--red); color: var(--red); background: rgba(255,51,51,0.15); }
  button.danger:hover { background: var(--red); color: #000; box-shadow: 0 0 12px var(--red); }

  .metric { display: flex; justify-content: space-between; font-size: 11px; }
  .metric span:last-child { color: var(--cyan); }
  .prog-bar { height: 4px; width: 100%; background: rgba(0,243,255,0.1); border-radius: 2px; overflow: hidden; }
  .prog-fill { height: 100%; background: var(--cyan); box-shadow: 0 0 6px var(--cyan); }
</style>
</head>
<body>

<div class="scanlines"></div>
<div class="hex-grid"></div>
<div class="vignette"></div>

<div class="os-container">

  <!-- TOP STRIP -->
  <div class="top-strip">
    <div class="brand-title">J.A.R.V.I.S. // STARK OS MK-VII</div>
    <div class="status-badge">SYSTEM INTEGRITY: <span style="color:#00ff00">100% NOMINAL</span></div>
    <div id="clock" style="font-size: 16px; color: var(--cyan); text-shadow:0 0 8px var(--cyan);">00:00:00</div>
  </div>

  <!-- WORKSPACE -->
  <div class="workspace">
    
    <!-- LEFT PANEL: BIOMETRICS & TELEMETRY -->
    <div class="hud-panel">
      <div class="panel-header">Biometric Telemetry</div>
      <div class="metric"><span>Pilot Heart Rate</span><span id="hr">74 bpm</span></div>
      <div class="prog-bar"><div class="prog-fill" style="width:60%"></div></div>
      
      <div class="metric"><span>Palladium Toxicity</span><span style="color:var(--red)">24% (Stable)</span></div>
      <div class="prog-bar"><div class="prog-fill" style="width:24%; background:var(--red)"></div></div>

      <div class="panel-header" style="margin-top:10px;">Flight Vectors</div>
      <div class="metric"><span>Altitude</span><span>4,120 M</span></div>
      <div class="metric"><span>Airspeed</span><span>312 KM/H</span></div>
      <div class="metric"><span>Heading</span><span id="hdg">047&deg;</span></div>
      <div class="metric"><span>G-Force Load</span><span id="gforce" style="color:var(--amber)">1.2G</span></div>
    </div>

    <!-- CENTER PANEL: HOLOGRAPHIC VIEWPORT -->
    <div class="hud-panel core-viewport">
      <canvas id="holocanvas"></canvas>
      <div class="core-stats">
        REACTOR CORE: <span id="reactorOut">2.8 GW</span><br>
        SUB-ROUTINES: <span>12 / 12 ACTIVE</span>
      </div>
    </div>

    <!-- RIGHT PANEL: SECURITY & WEAPONS -->
    <div class="hud-panel">
      <div class="panel-header">Weapon Systems</div>
      <div class="metric"><span>Palm Repulsors</span><span style="color:#00ff00">ONLINE</span></div>
      <div class="metric"><span>Micro-Missiles</span><span style="color:var(--red)">8 / 8 ARMED</span></div>
      <div class="metric"><span>Unibeam Core</span><span style="color:var(--amber)">CHARGING</span></div>

      <div class="panel-header" style="margin-top:10px;">Security Diagnostics</div>
      <div class="metric"><span>Z+ Firewall</span><span style="color:#00ff00">SECURE</span></div>
      <div class="metric"><span>Perimeter Scan</span><span>CLEAR</span></div>
      
      <div style="margin-top:auto;">
        <button class="danger" onclick="triggerLockdown()" style="width:100%;">🚨 EMERGENCY LOCKDOWN</button>
      </div>
    </div>

  </div>

  <!-- BOTTOM PANEL: INTERACTIVE AI TERMINAL -->
  <div class="hud-panel" style="height: 130px; flex-direction: row; gap: 15px;">
    <div style="flex: 2; display: flex; flex-direction: column; gap: 6px; overflow:hidden;">
      <div class="panel-header">J.A.R.V.I.S. Neural Voice & Command Stream</div>
      <div class="terminal-box" id="log">
        <div><span style="color:var(--cyan)">[System]</span> Welcome back, Boss. All sub-systems are online and operating at peak efficiency. ☕</div>
      </div>
    </div>
    
    <div style="flex: 1.2; display: flex; flex-direction: column; gap: 8px;">
      <div class="panel-header">Execute Directive</div>
      <div class="control-row">
        <input type="text" id="userInput" placeholder="Type command or query..." onkeydown="if(event.key==='Enter') sendJarvisQuery()">
        <button onclick="sendJarvisQuery()">Transmit</button>
      </div>
      <div style="display:flex; gap:6px;">
        <button onclick="testVoice()" style="flex:1;">Test Audio</button>
        <button onclick="clearTerminal()" style="flex:1;">Clear Log</button>
      </div>
    </div>
  </div>

</div>

<script>
function speakJarvis(text) {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    const voices = window.speechSynthesis.getVoices();
    const britishVoice = voices.find(v => v.lang === 'en-GB' || v.name.includes('UK') || v.name.includes('Oliver') || v.name.includes('George'));
    if (britishVoice) utterance.voice = britishVoice;
    utterance.pitch = 0.92; utterance.rate = 1.05;
    window.speechSynthesis.speak(utterance);
  }
}

function tickClock(){
  document.getElementById('clock').textContent = new Date().toTimeString().slice(0,8);
}
setInterval(tickClock, 1000); tickClock();

const logEl = document.getElementById('log');
function addLog(sender, msg){
  const t = new Date().toTimeString().slice(0,8);
  const div = document.createElement('div');
  div.innerHTML = `<span style="color:var(--cyan)">[${t}] [${sender}]</span> ${msg}`;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
}

function clearTerminal() {
  logEl.innerHTML = '<div><span style="color:var(--cyan)">[System]</span> Terminal logs purged. Standby. ☕</div>';
}

async function sendJarvisQuery() {
  const input = document.getElementById('userInput');
  const q = input.value.trim();
  if(!q) return;
  addLog("Boss", q);
  input.value = '';
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({prompt: q})
    });
    const data = await res.json();
    addLog("JARVIS", data.response);
    speakJarvis(data.response);
  } catch(e) {
    addLog("JARVIS", "Neural network uplink busy, Sir. ☕");
    speakJarvis("Network uplink busy, sir.");
  }
}

function testVoice() {
  const greeting = "All systems are green, Boss. Ready for your instructions.";
  addLog("JARVIS", greeting);
  speakJarvis(greeting);
}

async function triggerLockdown() {
  if(confirm("Engage emergency suit lockdown?")) {
    const res = await fetch('/api/lockdown', {method: 'POST'});
    const data = await res.json();
    addLog("Security", data.status);
    speakJarvis("Emergency lockdown engaged.");
  }
}

/* Cinematic Holographic Canvas Animation */
const canvas = document.getElementById('holocanvas');
const ctx = canvas.getContext('2d');

function resizeCanvas() {
  canvas.width = canvas.clientWidth * devicePixelRatio;
  canvas.height = canvas.clientHeight * devicePixelRatio;
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
}
resizeCanvas();
window.addEventListener('resize', resizeCanvas);

let angle = 0;
function drawHoloCore() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const cx = w / 2, cy = h / 2;
  ctx.clearRect(0, 0, w, h);

  const pulse = 1 + Math.sin(angle * 0.05) * 0.04;

  // Outer rotating telemetry rings
  for (let i = 0; i < 3; i++) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(angle * 0.007 * (i % 2 === 0 ? 1 : -1) + i);
    ctx.beginPath();
    const rad = (70 + i * 25) * pulse;
    ctx.setLineDash([rad * 0.25, rad * 0.15]);
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = `rgba(0, 243, 255, ${0.5 - i * 0.12})`;
    ctx.arc(0, 0, rad, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  // Central Arc Reactor Core Glow
  const grad = ctx.createRadialGradient(cx, cy, 2, cx, cy, 55 * pulse);
  grad.addColorStop(0, 'rgba(255, 255, 255, 0.95)');
  grad.addColorStop(0.3, 'rgba(0, 243, 255, 0.85)');
  grad.addColorStop(1, 'rgba(0, 243, 255, 0)');
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(cx, cy, 55 * pulse, 0, Math.PI * 2);
  ctx.fill();

  angle++;
  requestAnimationFrame(drawHoloCore);
}
drawHoloCore();

/* Telemetry Fluctuations */
setInterval(() => {
  document.getElementById('hdg').textContent = Math.floor(45 + Math.random() * 5) + '°';
  document.getElementById('gforce').textContent = (1.0 + Math.random() * 0.3).toFixed(1) + 'G';
  document.getElementById('hr').textContent = Math.floor(72 + Math.random() * 5) + ' bpm';
  document.getElementById('reactorOut').textContent = (2.7 + Math.random() * 0.2).toFixed(1) + ' GW';
}, 2000);
</script>

</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(MARK_VII_WEB_OS)

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.json or {}
    prompt = data.get('prompt', '')
    res = ask_ai_core(prompt=f"[MARK VII VISOR REQUEST]: {prompt}")
    return jsonify({'response': res})

@app.route('/api/lockdown', methods=['POST'])
def api_lockdown():
    log_security("MARK VII LOCKDOWN", 0, "Boss engaged visor lockdown.")
    return jsonify({'status': 'Visor lockdown engaged. Systems secured.'})

def run_flask_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

threading.Thread(target=run_flask_server, daemon=True).start()

async def handle_chat_and_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if update.effective_chat.type in ['group', 'supergroup'] and "jarvis" not in text.lower():
        return
    res = ask_ai_core(prompt=f"[TELEGRAM REQUEST]: {text}")
    await reply_smart(update, res)

if __name__ == '__main__':
    app_bot = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app_bot.add_handler(CommandHandler("help", lambda u, c: u.message.reply_text("Visor HUD Online. ☕")))
    app_bot.add_handler(MessageHandler(filters.TEXT, handle_chat_and_media))
    print("⚡ STARK MARK VII VISOR INTERFACE ACTIVE.")
    app_bot.run_polling()
