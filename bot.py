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
# 3. WEB OS PORTAL (MARK II THEME & API)
# ---------------------------------------------------------
app = Flask(__name__)

MARK_II_WEB_OS = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>J.A.R.V.I.S. // MARK II OS</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
        
        * { box-sizing: border-box; }
        body, html {
            margin: 0; padding: 0; width: 100%; height: 100%;
            background-color: #050b14;
            background-image: 
                radial-gradient(circle at 50% 50%, rgba(0, 243, 255, 0.08) 0%, transparent 60%),
                linear-gradient(rgba(0, 243, 255, 0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 243, 255, 0.03) 1px, transparent 1px);
            background-size: 100% 100%, 20px 20px, 20px 20px;
            color: #00f3ff;
            font-family: 'Share Tech Mono', monospace;
            overflow: hidden;
        }

        .hud-layout {
            display: grid;
            grid-template-columns: 350px 1fr 350px;
            height: 100vh;
            padding: 15px;
            gap: 15px;
        }

        .panel {
            background: rgba(3, 12, 24, 0.85);
            border: 1px solid #00f3ff;
            border-radius: 4px;
            padding: 15px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            box-shadow: 0 0 15px rgba(0, 243, 255, 0.2), inset 0 0 15px rgba(0, 243, 255, 0.05);
            backdrop-filter: blur(5px);
            max-height: 95vh;
            overflow-y: auto;
        }

        .panel::-webkit-scrollbar { width: 3px; }
        .panel::-webkit-scrollbar-thumb { background: #00f3ff; }

        h2 {
            margin: 0;
            font-size: 0.9rem;
            text-transform: uppercase;
            border-bottom: 1px dashed #00f3ff;
            padding-bottom: 5px;
            letter-spacing: 1px;
            color: #fff;
            text-shadow: 0 0 5px #00f3ff;
        }

        /* Center Holographic Ring Core */
        .center-hud {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            position: relative;
        }

        .arc-reactor {
            width: 220px;
            height: 220px;
            border: 2px dashed rgba(0, 243, 255, 0.4);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            animation: spin 20s linear infinite;
            box-shadow: 0 0 30px rgba(0, 243, 255, 0.3);
        }

        .arc-inner {
            width: 140px;
            height: 140px;
            border: 3px solid #00f3ff;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            animation: spin-reverse 15s linear infinite;
            box-shadow: inset 0 0 20px #00f3ff;
        }

        .arc-core {
            width: 60px;
            height: 60px;
            background: #00f3ff;
            border-radius: 50%;
            box-shadow: 0 0 25px #00f3ff, 0 0 50px #00f3ff;
        }

        @keyframes spin { 100% { transform: rotate(360deg); } }
        @keyframes spin-reverse { 100% { transform: rotate(-360deg); } }

        .status-telemetry {
            margin-top: 20px;
            text-align: center;
            font-size: 0.8rem;
            letter-spacing: 2px;
            text-shadow: 0 0 5px #00f3ff;
        }

        /* Terminal Chat */
        .terminal {
            flex-grow: 1;
            background: rgba(0, 0, 0, 0.6);
            border: 1px solid rgba(0, 243, 255, 0.3);
            border-radius: 3px;
            padding: 10px;
            overflow-y: auto;
            font-size: 0.85rem;
            display: flex;
            flex-direction: column;
            gap: 8px;
            max-height: 400px;
        }

        .msg { padding: 6px 8px; border-radius: 2px; line-height: 1.4; }
        .msg.user { background: rgba(0, 243, 255, 0.1); border-left: 2px solid #00f3ff; align-self: flex-end; width: 92%; }
        .msg.jarvis { background: rgba(255, 255, 255, 0.05); border-left: 2px solid #00ff00; align-self: flex-start; width: 92%; color: #fff; }

        .controls { display: flex; gap: 5px; margin-top: 5px; }
        input[type="text"] {
            flex-grow: 1;
            background: #000;
            border: 1px solid #00f3ff;
            color: #00f3ff;
            padding: 6px 8px;
            font-family: 'Share Tech Mono';
            border-radius: 2px;
        }

        button {
            background: rgba(0, 243, 255, 0.15);
            border: 1px solid #00f3ff;
            color: #00f3ff;
            padding: 6px 12px;
            cursor: pointer;
            font-family: 'Share Tech Mono';
            border-radius: 2px;
            text-transform: uppercase;
            transition: 0.2s;
        }
        button:hover { background: #00f3ff; color: #000; box-shadow: 0 0 10px #00f3ff; }
        button.danger { border-color: #ff3333; color: #ff3333; background: rgba(255, 51, 51, 0.1); }
        button.danger:hover { background: #ff3333; color: #000; box-shadow: 0 0 10px #ff3333; }

        ul { list-style: none; padding: 0; margin: 0; }
        li { font-size: 0.78rem; margin-bottom: 6px; padding: 6px; background: rgba(0,243,255,0.03); border-left: 2px solid #00f3ff; }
        a { color: #fff; text-decoration: none; } a:hover { color: #00f3ff; text-shadow: 0 0 5px #00f3ff; }
    </style>
</head>
<body>

    <div class="hud-layout">
        <!-- LEFT PANEL: TERMINAL & VOICE CONTROL -->
        <div class="panel">
            <h2>// MARK II TERMINAL</h2>
            <div class="terminal" id="terminal">
                <div class="msg jarvis">Systems nominal, Boss. Mark II HUD engaged. ☕</div>
            </div>
            <div class="controls">
                <input type="text" id="userInput" placeholder="Query Stark OS..." onkeydown="if(event.key==='Enter') sendWebQuery()">
                <button onclick="sendWebQuery()">Execute</button>
                <button onclick="toggleVoice()">🎙️</button>
            </div>
        </div>

        <!-- CENTER PANEL: HOLOGRAPHIC ARC REACTOR CORE -->
        <div class="panel center-hud">
            <div class="arc-reactor">
                <div class="arc-inner">
                    <div class="arc-core"></div>
                </div>
            </div>
            <div class="status-telemetry">
                STATUS: SECURE // MARK II OS<br>
                POWER: 100% // CORE STABLE
            </div>
        </div>

        <!-- RIGHT PANEL: VAULT & SECURITY CONSOLE -->
        <h2>// STARK VAULT</h2>
            <div style="display:flex; flex-direction:column; gap:5px;">
                <input type="text" id="vaultTopic" placeholder="Resource Topic">
                <input type="text" id="vaultLink" placeholder="Resource URL">
                <button onclick="addVaultItem()">Upload To Vault</button>
            </div>
            <ul id="vaultList" style="margin-top:5px;">
                {% for n in notes %}
                <li><strong>{{ n[0] }}</strong><br><a href="{{ n[1] }}" target="_blank">Access Link</a> | <small>{{ n[2] }}</small></li>
                {% endfor %}
            </ul>

            <h2 style="color:#ff3333; margin-top:10px;">// SECURITY OVERRIDE</h2>
            <button class="danger" onclick="triggerLockdown()" style="width:100%;">🚨 LOCKDOWN PERIMETER</button>
            <ul style="margin-top:5px;">
                {% for a in audits %}
                <li style="border-color:#ff3333;">
                    <strong style="color:#ff3333;">[{{ a[0] }}]</strong> ID: {{ a[1] }}<br>{{ a[2] }}
                </li>
                {% endfor %}
            </ul>
        </div>
    </div>

    <script>
        function speak(text) {
            if ('speechSynthesis' in window) {
                const utterance = new SpeechSynthesisUtterance(text);
                const voices = window.speechSynthesis.getVoices();
                const britishVoice = voices.find(v => v.lang.includes('en-GB') || v.name.includes('UK'));
                if (britishVoice) utterance.voice = britishVoice;
                window.speechSynthesis.speak(utterance);
            }
        }

        async function sendWebQuery(overrideText = null) {
            const input = document.getElementById('userInput');
            const query = overrideText || input.value.trim();
            if (!query) return;
            appendMsg(query, 'user');
            if(!overrideText) input.value = '';
            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({prompt: query})
                });
                const data = await res.json();
                appendMsg(data.response, 'jarvis');
                speak(data.response);
            } catch (err) {
                appendMsg("Telemetry connection lost, Sir. ☕", 'jarvis');
            }
        }

        function appendMsg(text, sender) {
            const term = document.getElementById('terminal');
            const div = document.createElement('div');
            div.className = `msg ${sender}`;
            div.innerHTML = text.replace(/\\n/g, '<br>');
            term.appendChild(div);
            term.scrollTop = term.scrollHeight;
        }

        let recognition = null;
        if ('webkitSpeechRecognition' in window) {
            recognition = new webkitSpeechRecognition();
            recognition.onresult = (e) => sendWebQuery(e.results[0][0].transcript);
        }
        function toggleVoice() { if (recognition) { recognition.start(); appendMsg("Listening for command...", 'jarvis'); } }

        async function addVaultItem() {
            const topic = document.getElementById('vaultTopic').value;
            const link = document.getElementById('vaultLink').value;
            if(!topic || !link) return;
            await fetch('/api/vault', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({topic, link})
            });
            location.reload();
        }

        async function triggerLockdown() {
            if(confirm("Confirm emergency group lockdown protocol?")) {
                const res = await fetch('/api/lockdown', {method: 'POST'});
                const data = await res.json();
                alert(data.status);
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    local_conn = sqlite3.connect("jarvis_memory.db")
    local_cursor = local_conn.cursor()
    notes = local_cursor.execute("SELECT topic, link, added_by FROM notes_vault ORDER BY id DESC LIMIT 8").fetchall()
    audits = local_cursor.execute("SELECT event_type, user_id, detail FROM security_audit ORDER BY id DESC LIMIT 4").fetchall()
    local_conn.close()
    return render_template_string(MARK_II_WEB_OS, notes=notes, audits=audits)

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.json or {}
    prompt = data.get('prompt', '')
    res = ask_ai_core(prompt=f"[MARK II WEB HUD REQUEST]: {prompt}")
    return jsonify({'response': res})

@app.route('/api/vault', methods=['POST'])
def api_vault():
    data = request.json or {}
    local_conn = sqlite3.connect("jarvis_memory.db")
    local_cursor = local_conn.cursor()
    local_cursor.execute("INSERT INTO notes_vault (topic, link, added_by) VALUES (?, ?, ?)", (data.get('topic'), data.get('link'), 'Mark II HUD'))
    local_conn.commit()
    local_conn.close()
    return jsonify({'status': 'Success'})

@app.route('/api/lockdown', methods=['POST'])
def api_lockdown():
    log_security("MARK II LOCKDOWN", 0, "Boss engaged emergency shutdown from Mark II HUD.")
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
    app_bot.add_handler(CommandHandler("help", lambda u, c: u.message.reply_text("Mark II OS Online. ☕")))
    app_bot.add_handler(MessageHandler(filters.TEXT, handle_chat_and_media))
    print("⚡ STARK MARK II HUD WEB OS ACTIVE.")
    app_bot.run_polling()
