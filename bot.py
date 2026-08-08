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
    # Try Gemini First
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
            
    # Failover to Groq if Gemini hits 429 quota limits
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
# 3. WEB OS PORTAL & API ENDPOINTS
# ---------------------------------------------------------
app = Flask(__name__)

STARK_WEB_OS = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>J.A.R.V.I.S. Standalone Web OS</title>
    <script src="https://unpkg.com/three"></script>
    <script src="https://unpkg.com/globe.gl"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Share+Tech+Mono&display=swap');
        * { box-sizing: border-box; }
        body, html { margin: 0; padding: 0; width: 100%; height: 100%; background: #02060d; color: #00f3ff; font-family: 'Share Tech Mono', monospace; overflow: hidden; }
        #globeViz { position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 1; }
        .hud { position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 10; pointer-events: none; display: grid; grid-template-columns: 340px 1fr 360px; padding: 20px; gap: 20px; }
        .panel { pointer-events: auto; background: rgba(2, 10, 20, 0.85); backdrop-filter: blur(12px); border: 1px solid rgba(0, 243, 255, 0.3); border-radius: 8px; padding: 18px; display: flex; flex-direction: column; gap: 15px; max-height: 94vh; overflow-y: auto; box-shadow: 0 0 25px rgba(0, 243, 255, 0.15); }
        .panel::-webkit-scrollbar { width: 4px; } .panel::-webkit-scrollbar-thumb { background: #00f3ff; }
        h1, h2 { font-family: 'Orbitron', sans-serif; text-transform: uppercase; margin: 0; }
        h1 { font-size: 1.1rem; text-align: center; border-bottom: 2px solid #00f3ff; padding-bottom: 8px; text-shadow: 0 0 10px #00f3ff; }
        h2 { font-size: 0.9rem; color: #fff; border-bottom: 1px dashed rgba(0, 243, 255, 0.4); padding-bottom: 5px; }
        .terminal { flex-grow: 1; background: rgba(0,0,0,0.6); border: 1px solid rgba(0,243,255,0.2); border-radius: 5px; padding: 10px; overflow-y: auto; font-size: 0.85rem; display: flex; flex-direction: column; gap: 10px; max-height: 350px; }
        .msg { padding: 6px 10px; border-radius: 4px; line-height: 1.4; }
        .msg.user { background: rgba(0, 243, 255, 0.1); border-left: 3px solid #00f3ff; align-self: flex-end; width: 90%; }
        .msg.jarvis { background: rgba(255, 255, 255, 0.05); border-left: 3px solid #00ff00; align-self: flex-start; width: 90%; color: #fff; }
        .controls { display: flex; gap: 5px; }
        input[type="text"] { flex-grow: 1; background: #000; border: 1px solid #00f3ff; color: #00f3ff; padding: 8px; font-family: 'Share Tech Mono'; border-radius: 4px; }
        button { background: rgba(0, 243, 255, 0.15); border: 1px solid #00f3ff; color: #00f3ff; padding: 8px 12px; cursor: pointer; font-family: 'Share Tech Mono'; border-radius: 4px; text-transform: uppercase; transition: 0.2s; }
        button:hover { background: #00f3ff; color: #000; box-shadow: 0 0 10px #00f3ff; }
        button.danger { border-color: #ff3333; color: #ff3333; background: rgba(255, 51, 51, 0.1); }
        button.danger:hover { background: #ff3333; color: #000; box-shadow: 0 0 10px #ff3333; }
        ul { list-style: none; padding: 0; margin: 0; }
        li { font-size: 0.8rem; margin-bottom: 8px; padding: 8px; background: rgba(0,243,255,0.04); border-left: 2px solid #00f3ff; }
        a { color: #fff; text-decoration: none; } a:hover { color: #00f3ff; }
    </style>
</head>
<body>
    <div id="globeViz"></div>
    <div class="hud">
        <div class="panel">
            <h1>🤖 J.A.R.V.I.S. VOICE & TERMINAL</h1>
            <div class="terminal" id="terminal">
                <div class="msg jarvis">System initialized, Boss. Standing by for voice or text commands. ☕</div>
            </div>
            <div class="controls">
                <input type="text" id="userInput" placeholder="Ask J.A.R.V.I.S..." onkeydown="if(event.key==='Enter') sendWebQuery()">
                <button onclick="sendWebQuery()">Send</button>
                <button id="micBtn" onclick="toggleVoice()">🎙️</button>
            </div>
        </div>
        <div></div>
        <div class="panel">
            <h2>📚 STARK VAULT MANAGER</h2>
            <div style="display:flex; flex-direction:column; gap:5px;">
                <input type="text" id="vaultTopic" placeholder="Topic">
                <input type="text" id="vaultLink" placeholder="URL">
                <button onclick="addVaultItem()">Save To Vault</button>
            </div>
            <ul id="vaultList" style="margin-top:10px;">
                {% for n in notes %}
                <li><strong>{{ n[0] }}</strong><br><a href="{{ n[1] }}" target="_blank">Open Link</a> | <small>By {{ n[2] }}</small></li>
                {% endfor %}
            </ul>
        </div>
    </div>
    <script>
        const world = Globe()(document.getElementById('globeViz'))
            .globeImageUrl('https://unpkg.com/three-globe/example/img/earth-dark.jpg')
            .bumpImageUrl('https://unpkg.com/three-globe/example/img/earth-topology.png')
            .backgroundColor('rgba(0,0,0,0)');
        world.controls().autoRotate = true; world.controls().autoRotateSpeed = 0.5; world.controls().enableZoom = false;

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
                appendMsg("Connection failed. ☕", 'jarvis');
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
        function toggleVoice() { if (recognition) { recognition.start(); appendMsg("Listening...", 'jarvis'); } }

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
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    local_conn = sqlite3.connect("jarvis_memory.db")
    local_cursor = local_conn.cursor()
    notes = local_cursor.execute("SELECT topic, link, added_by FROM notes_vault ORDER BY id DESC LIMIT 10").fetchall()
    audits = local_cursor.execute("SELECT event_type, user_id, detail FROM security_audit ORDER BY id DESC LIMIT 5").fetchall()
    local_conn.close()
    return render_template_string(STARK_WEB_OS, notes=notes, audits=audits)

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.json or {}
    prompt = data.get('prompt', '')
    res = ask_ai_core(prompt=f"[WEB TERMINAL REQUEST]: {prompt}")
    return jsonify({'response': res})

@app.route('/api/vault', methods=['POST'])
def api_vault():
    data = request.json or {}
    local_conn = sqlite3.connect("jarvis_memory.db")
    local_cursor = local_conn.cursor()
    local_cursor.execute("INSERT INTO notes_vault (topic, link, added_by) VALUES (?, ?, ?)", (data.get('topic'), data.get('link'), 'Web Boss HUD'))
    local_conn.commit()
    local_conn.close()
    return jsonify({'status': 'Success'})

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
    app_bot.add_handler(CommandHandler("help", lambda u, c: u.message.reply_text("J.A.R.V.I.S. Online. ☕")))
    app_bot.add_handler(MessageHandler(filters.TEXT, handle_chat_and_media))
    print("⚡ STARK OS ACTIVE WITH AUTO-FAILOVER.")
    app_bot.run_polling()
