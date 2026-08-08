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
# 3. WEB OS PORTAL (MARK VII GOD-MODE HUD)
# ---------------------------------------------------------
app = Flask(__name__)

MARK_VII_WEB_OS = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>MK-VII // SUIT INTERFACE</title>
<style>
  :root{
    --bg:#04070a;
    --panel:#070c11;
    --cyan:#5fe3ff;
    --cyan-dim:#1c4a55;
    --amber:#ffb340;
    --red:#ff4433;
    --gold:#e8b04b;
    --text:#cfeff5;
    --mono:'Consolas','SFMono-Regular',ui-monospace,Menlo,monospace;
  }
  *{box-sizing:border-box; margin:0; padding:0;}
  html,body{
    width:100%; height:100%;
    background:radial-gradient(ellipse at center, #0a1218 0%, #03060a 70%, #000 100%);
    color:var(--text);
    font-family:var(--mono);
    overflow:hidden;
  }

  .scanlines{
    position:fixed; inset:0; pointer-events:none; z-index:50;
    background:repeating-linear-gradient(0deg, rgba(95,227,255,0.025) 0px, rgba(95,227,255,0.025) 1px, transparent 1px, transparent 3px);
    mix-blend-mode:screen;
  }
  .vignette{
    position:fixed; inset:0; pointer-events:none; z-index:49;
    box-shadow: inset 0 0 220px rgba(0,0,0,0.85);
  }

  .hud{
    position:relative; width:100%; height:100%;
    display:grid;
    grid-template-columns: 320px 1fr 320px;
    grid-template-rows: 80px 1fr 140px;
    padding:15px;
    gap:12px;
  }

  .panel{
    border:1px solid rgba(95,227,255,0.25);
    background:linear-gradient(180deg, rgba(10,20,26,0.7), rgba(4,8,11,0.8));
    position:relative;
    padding:10px 12px;
    backdrop-filter: blur(2px);
    display:flex;
    flex-direction:column;
    gap:8px;
    overflow-y:auto;
  }
  .panel::-webkit-scrollbar { width: 3px; }
  .panel::-webkit-scrollbar-thumb { background: var(--cyan); }

  .panel::before{
    content:''; position:absolute; top:-1px; left:-1px; width:10px; height:10px;
    border-top:2px solid var(--cyan); border-left:2px solid var(--cyan);
  }
  .panel::after{
    content:''; position:absolute; bottom:-1px; right:-1px; width:10px; height:10px;
    border-bottom:2px solid var(--cyan); border-right:2px solid var(--cyan);
  }
  .label{
    font-size:9.5px; letter-spacing:2px; color:var(--cyan);
    opacity:0.75; text-transform:uppercase; border-bottom:1px dashed rgba(95,227,255,0.2); padding-bottom:3px;
  }

  /* Top Bar */
  .topbar{ grid-column:1/4; display:flex; align-items:center; justify-content:space-between; padding:0 6px; }
  .brand{ display:flex; align-items:center; gap:12px; }
  .brand .mark{
    width:30px; height:30px; border-radius:50%; border:2px solid var(--cyan);
    display:flex; align-items:center; justify-content:center;
    box-shadow:0 0 10px var(--cyan), inset 0 0 6px var(--cyan);
  }
  .brand .mark span{ width:8px; height:8px; background:var(--cyan); border-radius:50%; box-shadow:0 0 6px var(--cyan);}
  .brand .title{ font-size:14px; letter-spacing:4px; font-weight:bold; color:var(--text);}
  .brand .sub{ font-size:9px; letter-spacing:2px; color:var(--cyan); opacity:0.7;}
  .clock{ font-size:18px; letter-spacing:2px; color:var(--cyan); text-shadow:0 0 8px rgba(95,227,255,0.6);}

  /* Left Column */
  .left{ display:flex; flex-direction:column; gap:12px; }
  .vitals-row{ display:flex; justify-content:space-between; align-items:baseline; font-size:10.5px; margin:4px 0; }
  .vitals-row .val{ color:var(--cyan); font-size:13px; }
  .bar-track{ height:4px; width:100%; background:rgba(95,227,255,0.1); position:relative; margin-top:2px;}
  .bar-fill{ height:100%; background:linear-gradient(90deg,var(--cyan-dim),var(--cyan)); box-shadow:0 0 5px var(--cyan);}
  #radarCanvas{ display:block; width:100%; height:130px; }

  /* Center Viewport */
  .center{ position:relative; overflow:hidden; }
  #reactorCanvas{ position:absolute; inset:0; width:100%; height:100%; }
  .center-overlay{
    position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
    flex-direction:column; pointer-events:none;
  }
  .core-readout .big{ font-size:11px; letter-spacing:4px; color:var(--cyan); opacity:0.85; text-align:center;}
  .core-readout .num{ font-size:30px; color:#fff; text-shadow:0 0 15px var(--cyan); letter-spacing:2px; margin-top:2px; text-align:center;}

  /* Right Column */
  .right{ display:flex; flex-direction:column; gap:12px; }
  .module-list{ font-size:10px; display:flex; flex-direction:column; gap:4px; max-height:100px; overflow-y:auto; }
  .module-item{ display:flex; justify-content:space-between; background:rgba(95,227,255,0.05); padding:3px 6px; border-left:2px solid var(--cyan); }

  /* Bottom Console */
  .console{ grid-column:1/4; display:grid; grid-template-columns: 2fr 1fr 1fr; gap:12px; }
  .log{ font-size:10.5px; line-height:1.5; overflow-y:auto; max-height:110px; }
  .log .line{ opacity:0; animation:fadeIn 0.3s forwards; margin-bottom:2px; }
  .log .line .t{ color:var(--cyan); opacity:0.6; margin-right:6px;}
  @keyframes fadeIn{ to{ opacity:1; } }

  .chat-box{ display:flex; flex-direction:column; gap:6px; }
  .chat-input-row{ display:flex; gap:4px; }
  input[type="text"]{
    flex-grow:1; background:#000; border:1px solid var(--cyan); color:var(--cyan);
    padding:5px 8px; font-family:var(--mono); font-size:11px; border-radius:2px;
  }
  button{
    background:rgba(95,227,255,0.15); border:1px solid var(--cyan); color:var(--cyan);
    padding:5px 10px; cursor:pointer; font-family:var(--mono); font-size:11px; border-radius:2px;
    text-transform:uppercase; transition:0.2s;
  }
  button:hover{ background:var(--cyan); color:#000; box-shadow:0 0 8px var(--cyan); }
  button.danger{ border-color:var(--red); color:var(--red); background:rgba(255,68,51,0.1); }
  button.danger:hover{ background:var(--red); color:#000; }
</style>
</head>
<body>

<div class="scanlines"></div>
<div class="vignette"></div>

<div class="hud">

  <!-- TOP BAR -->
  <div class="panel topbar">
    <div class="brand">
      <div class="mark"><span></span></div>
      <div>
        <div class="title">MARK&nbsp;VII // GOD-MODE OS</div>
        <div class="sub">VOICE SYNTHESIS: BRITISH BUTLER ACTIVE</div>
      </div>
    </div>
    <div class="clock" id="clock">00:00:00</div>
  </div>

  <!-- LEFT COLUMN -->
  <div class="left">
    <div class="panel">
      <div class="label">System Vitals</div>
      <div class="vitals-row"><span>Pilot HR</span><span class="val" id="hr">74 bpm</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:60%"></div></div>
      <div class="vitals-row"><span>Core Shielding</span><span class="val">99.8%</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:99.8%"></div></div>
    </div>

    <div class="panel" style="flex:1;">
      <div class="label">Proximity Radar</div>
      <canvas id="radarCanvas"></canvas>
    </div>
  </div>

  <!-- CENTER VIEWPORT -->
  <div class="panel center">
    <canvas id="reactorCanvas"></canvas>
    <div class="center-overlay">
      <div class="core-readout">
        <div class="big">ARC REACTOR OUTPUT</div>
        <div class="num" id="reactorOut">2.8 GW</div>
      </div>
    </div>
  </div>

  <!-- RIGHT COLUMN -->
  <div class="right">
    <div class="panel" style="flex:1;">
      <div class="label">Custom Modules</div>
      <div style="display:flex; gap:4px; margin-bottom:4px;">
        <input type="text" id="modName" placeholder="Module Name">
        <button onclick="addCustomModule()">Add</button>
      </div>
      <div class="module-list" id="customModulesContainer">
        <div class="module-item"><span>Z+ Security Firewall</span><span style="color:var(--cyan)">ACTIVE</span></div>
        <div class="module-item"><span>Universal Voice Matrix</span><span style="color:var(--cyan)">ONLINE</span></div>
      </div>
    </div>

    <div class="panel">
      <div class="label">Emergency Protocols</div>
      <button class="danger" onclick="triggerLockdown()">🚨 LOCKDOWN PERIMETER</button>
    </div>
  </div>

  <!-- BOTTOM CONSOLE -->
  <div class="panel console">
    <div class="log" id="log">
      <div class="line"><span class="t">[System]</span>J.A.R.V.I.S. neural network linked successfully, Boss. ☕</div>
    </div>

    <div class="chat-box">
      <div class="label">J.A.R.V.I.S. Command Terminal</div>
      <div class="chat-input-row">
        <input type="text" id="userInput" placeholder="Ask Jarvis anything..." onkeydown="if(event.key==='Enter') sendJarvisQuery()">
        <button onclick="sendJarvisQuery()">Transmit</button>
      </div>
    </div>

    <div class="chat-box">
      <div class="label">Voice Matrix Synthesis</div>
      <div style="font-size:10px; color:var(--cyan); margin-top:4px;">Status: <span style="color:#fff">Refined British English Voice Active</span></div>
      <button onclick="testVoice()" style="margin-top:4px;">Test Audio Output</button>
    </div>
  </div>

</div>

<script>
/* ---------- UPGRADED VOICE SYNTHESIS (BRITISH BUTLER) ---------- */
function speakJarvis(text) {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    const voices = window.speechSynthesis.getVoices();
    const britishVoice = voices.find(v => v.lang === 'en-GB' || v.name.includes('UK English') || v.name.includes('Oliver') || v.name.includes('Arthur') || v.name.includes('George'));
    if (britishVoice) utterance.voice = britishVoice;
    utterance.pitch = 0.92;
    utterance.rate = 1.05;
    window.speechSynthesis.speak(utterance);
  }
}

if ('speechSynthesis' in window) {
  window.speechSynthesis.onvoiceschanged = () => { window.speechSynthesis.getVoices(); };
}

function testVoice() {
  const greeting = "Good day, Boss. All primary and secondary systems are operating at peak efficiency. How may I assist you?";
  addLog("J.A.R.V.I.S.", greeting);
  speakJarvis(greeting);
}

/* ---------- CLOCK & TELEMETRY ---------- */
function tickClock(){
  const d = new Date();
  document.getElementById('clock').textContent = d.toTimeString().slice(0,8);
}
setInterval(tickClock,1000); tickClock();

/* ---------- LOG SYSTEM ---------- */
const logEl = document.getElementById('log');
function addLog(sender, msg){
  const t = new Date().toTimeString().slice(0,8);
  const div = document.createElement('div');
  div.className = 'line';
  div.innerHTML = `<span class="t">[${t}] [${sender}]</span>${msg}`;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
}

/* ---------- CUSTOM MODULE INJECTION ---------- */
function addCustomModule() {
  const name = document.getElementById('modName').value.trim();
  if(!name) return;
  const container = document.getElementById('customModulesContainer');
  const item = document.createElement('div');
  item.className = 'module-item';
  item.innerHTML = `<span>${name}</span><span style="color:var(--amber)">ONLINE</span>`;
  container.appendChild(item);
  document.getElementById('modName').value = '';
  addLog("System", `Custom module '${name}' deployed successfully.`);
}

/* ---------- BACKEND API CHAT INTEGRATION ---------- */
async function sendJarvisQuery() {
  const input = document.getElementById('userInput');
  const query = input.value.trim();
  if(!query) return;

  addLog("Boss", query);
  input.value = '';

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({prompt: query})
    });
    const data = await res.json();
    addLog("J.A.R.V.I.S.", data.response);
    speakJarvis(data.response);
  } catch(err) {
    const fallback = "I am currently unable to reach the neural core network, Sir. ☕";
    addLog("J.A.R.V.I.S.", fallback);
    speakJarvis(fallback);
  }
}

async function triggerLockdown() {
  if(confirm("Engage emergency group lockdown protocol?")) {
    const res = await fetch('/api/lockdown', {method: 'POST'});
    const data = await res.json();
    addLog("Security", data.status);
    speakJarvis("Perimeter lockdown initiated. All unauthorized communications have been frozen.");
  }
}

/* ---------- RADAR CANVAS ANIMATION ---------- */
const radar = document.getElementById('radarCanvas');
const rctx = radar.getContext('2d');
function sizeCanvas(cv){
  const rect = cv.getBoundingClientRect();
  cv.width = rect.width * devicePixelRatio;
  cv.height = rect.height * devicePixelRatio;
  cv.getContext('2d').setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
}
sizeCanvas(radar);
let radarAngle = 0;
const blips = [{a: 1.2, r: 0.5}, {a: 3.4, r: 0.75}];
function drawRadar(){
  const w = radar.clientWidth, h = radar.clientHeight;
  const cx = w/2, cy = h/2, R = Math.min(w,h)/2 - 4;
  rctx.clearRect(0,0,w,h);
  rctx.strokeStyle = 'rgba(95,227,255,0.35)';
  for(let i=1;i<=2;i++){
    rctx.beginPath(); rctx.arc(cx,cy,R*i/2,0,Math.PI*2); rctx.stroke();
  }
  rctx.beginPath(); rctx.moveTo(cx-R,cy); rctx.lineTo(cx+R,cy); rctx.stroke();

  blips.forEach(b=>{
    b.a += 0.02;
    const bx = cx + Math.cos(b.a)*R*b.r;
    const by = cy + Math.sin(b.a)*R*b.r;
    rctx.beginPath(); rctx.fillStyle = '#5fe3ff'; rctx.arc(bx,by,2,0,Math.PI*2); rctx.fill();
  });
  radarAngle += 0.03;
  requestAnimationFrame(drawRadar);
}
drawRadar();

/* ---------- REACTOR CANVAS ANIMATION ---------- */
const reactor = document.getElementById('reactorCanvas');
const ctx = reactor.getContext('2d');
function fitReactor(){
  reactor.width = reactor.clientWidth * devicePixelRatio;
  reactor.height = reactor.clientHeight * devicePixelRatio;
  ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
}
fitReactor();
let t0 = 0;
function drawReactor(){
  const w = reactor.clientWidth, h = reactor.clientHeight;
  const cx = w/2, cy = h/2;
  ctx.clearRect(0,0,w,h);
  const pulse = 1 + Math.sin(t0*0.05)*0.05;

  for(let i=0;i<2;i++){
    ctx.save();
    ctx.translate(cx,cy);
    ctx.rotate(t0*0.005*(i===0?1:-1));
    ctx.beginPath();
    const rad = (50 + i*20) * pulse;
    ctx.setLineDash([rad*0.3, rad*0.2]);
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = 'rgba(95,227,255,0.5)';
    ctx.arc(0,0,rad,0,Math.PI*2);
    ctx.stroke();
    ctx.restore();
  }

  const g = ctx.createRadialGradient(cx,cy,2,cx,cy,45*pulse);
  g.addColorStop(0,'rgba(255,255,255,0.9)');
  g.addColorStop(0.4,'rgba(95,227,255,0.8)');
  g.addColorStop(1,'rgba(95,227,255,0)');
  ctx.fillStyle = g;
  ctx.beginPath(); ctx.arc(cx,cy,45*pulse,0,Math.PI*2); ctx.fill();

  t0++;
  requestAnimationFrame(drawReactor);
}
drawReactor();
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
    res = ask_ai_core(prompt=f"[MARK VII HUD REQUEST]: {prompt}")
    return jsonify({'response': res})

@app.route('/api/lockdown', methods=['POST'])
def api_lockdown():
    log_security("MARK VII LOCKDOWN", 0, "Boss engaged emergency shutdown from Mark VII HUD.")
    return jsonify({'status': 'Protocol active. Performed telemetry override.'})

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
    app_bot.add_handler(CommandHandler("help", lambda u, c: u.message.reply_text("Mark VII OS Online. ☕")))
    app_bot.add_handler(MessageHandler(filters.TEXT, handle_chat_and_media))
    print("⚡ STARK MARK VII SUIT INTERFACE ACTIVE.")
    app_bot.run_polling()
