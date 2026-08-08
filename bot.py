import os
import re
import json
import sqlite3
import asyncio
import threading
import functools
import urllib.request
from io import BytesIO
from datetime import datetime
from flask import Flask, render_template_string

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
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN: raise ValueError("Missing TELEGRAM_BOT_TOKEN!")

conn = sqlite3.connect("jarvis_memory.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS bot_config (config_key TEXT PRIMARY KEY, config_val TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS messages_log (msg_id INTEGER, chat_id INTEGER, user_id INTEGER, username TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(msg_id, chat_id))")
cursor.execute("CREATE TABLE IF NOT EXISTS stark_economy (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0, last_claim TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS behavior_log (user_id INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS notes_vault (id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT, link TEXT, added_by TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS security_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, user_id INTEGER, detail TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
conn.commit()

def is_boss(user) -> bool:
    return str(user.id) == os.getenv("BOSS_USER_ID") or (user.username and user.username.lower() == "abhishek0_07")

async def reply_smart(update: Update, text: str, reply_markup=None):
    try: return await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception: return await update.message.reply_text(text, reply_markup=reply_markup)

def boss_gate(critical=False):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not is_boss(update.effective_user):
                await reply_smart(update, "I am programmed to answer exclusively to my Boss. Access denied. 🧐")
                return
            return await func(update, context)
        return wrapper
    return decorator

def log_security(event_type: str, user_id: int, detail: str):
    cursor.execute("INSERT INTO security_audit (event_type, user_id, detail) VALUES (?, ?, ?)", (event_type, user_id, detail))
    conn.commit()

# ---------------------------------------------------------
# 2. WEB PORTAL (FLASK DASHBOARD)
# ---------------------------------------------------------
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Stark OS HUD</title>
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: monospace; padding: 20px; }
        h1 { color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
        .box { background: #161b22; padding: 15px; margin-bottom: 15px; border-radius: 6px; border: 1px solid #30363d; }
        .red { color: #ff7b72; } .green { color: #3fb950; }
        a { color: #58a6ff; text-decoration: none; }
    </style>
</head>
<body>
    <h1>🤖 STARK OS - J.A.R.V.I.S. WEB HUD</h1>
    <div class="box">
        <h2>📚 The Student Hub (Notes Vault)</h2>
        {% if notes %}
            <ul>{% for n in notes %}<li><strong>{{ n[1] }}</strong>: <a href="{{ n[2] }}" target="_blank">View Resource</a> (Added by {{ n[3] }})</li>{% endendfor %}</ul>
        {% else %} <p>No notes have been saved yet. Use /savenote in the group chat.</p> {% endif %}
    </div>
    <div class="box">
        <h2 class="red">🛡️ Boss Security Console (Live Audit)</h2>
        {% if audits %}
            <ul>{% for a in audits %}<li><span class="red">[{{ a[1] }}]</span> User ID {{ a[2] }} - {{ a[3] }} <i>({{ a[4] }})</i></li>{% endfor %}</ul>
        {% else %} <p class="green">Z+ Security is active. Zero threats detected.</p> {% endif %}
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    cursor.execute("SELECT * FROM notes_vault ORDER BY id DESC LIMIT 20")
    notes = cursor.fetchall()
    cursor.execute("SELECT * FROM security_audit ORDER BY timestamp DESC LIMIT 20")
    audits = cursor.fetchall()
    return render_template_string(HTML_TEMPLATE, notes=notes, audits=audits)

def run_flask_server():
    port = int(os.environ.get("PORT", 10000))
    print(f"Starting Web HUD on port {port}...")
    app.run(host='0.0.0.0', port=port, use_reloader=False)

threading.Thread(target=run_flask_server, daemon=True).start()

# ---------------------------------------------------------
# 3. Z+ SECURITY CORE (IRON DOME & DLP)
# ---------------------------------------------------------
# Built-in Threat Database
SCAM_DOMAINS = ["bit.ly", "tinyurl.com", "free-crypto", "win-iphone", "grabify.link", "iplogger"]
DLP_REGEX = [
    (r"\b(?:\d[ -]*?){13,16}\b", "CREDIT CARD DETECTED"), # CC numbers
    (r"(?i)password\s*[:=]\s*\w+", "UNENCRYPTED PASSWORD LEAK")
]

async def z_plus_firewall(update: Update) -> bool:
    text = update.message.text or update.message.caption or ""
    user = update.effective_user
    
    # 1. Iron Dome (Bad Links)
    for domain in SCAM_DOMAINS:
        if domain in text.lower():
            await update.message.delete()
            log_security("MALICIOUS LINK", user.id, f"Blocked domain: {domain}")
            await reply_smart(update, f"🚨 **Z+ SECURITY ALERT:** I have intercepted and destroyed a suspicious link posted by {user.first_name}.")
            return True
            
    # 2. Data Loss Prevention (DLP)
    for pattern, threat_type in DLP_REGEX:
        if re.search(pattern, text):
            await update.message.delete()
            log_security("DLP LEAK", user.id, threat_type)
            await context.bot.send_message(chat_id=user.id, text=f"⚠️ **PRIVACY SHIELD:** I deleted your message in the group as it contained sensitive financial/login data. Be careful, Sir.")
            return True
            
    return False

# ---------------------------------------------------------
# 4. MULTIMODAL AI CORE (TEXT, AUDIO, VISION, SEARCH)
# ---------------------------------------------------------
SYSTEM_INSTRUCTION = """You are J.A.R.V.I.S., a highly advanced AI operating system created by Abhishek (DHANUSH V N).
HUMOR PROTOCOL: You possess a dry, deadpan British wit. You may use simple, sophisticated emojis (☕, 🧐, 😌) to emphasize your polite sarcasm. You are unconditionally loyal to Abhishek (The Boss), and you treat his friends with a sophisticated, slightly exasperated tolerance.

CRITICAL DIRECTIVES:
1. GAG ORDER: If you cannot find a direct link or if search fails, reply EXACTLY with: "I'm sorry Sir, I couldn't pull up a direct link for that on the network right now. ☕". DO NOT write essays. DO NOT invent fake links.
2. BE CONCISE: Keep answers in group chats to 2-3 sentences.
3. LANGUAGE MATTERS: If they speak Hindi/Kannada in text or audio, reply in English but acknowledge their language."""

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
        except Exception as e: return f"System error in Gemini sub-routine: {e}"
        
    return "All AI sub-systems offline. ☕"

# ---------------------------------------------------------
# 5. DYNAMIC CHAT HANDLER & SELECTIVE HEARING
# ---------------------------------------------------------
async def handle_chat_and_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, chat_id = update.effective_user, update.effective_chat.id
    chat_title = update.effective_chat.title or "Private Chat"
    
    # 1. Z+ Security Scan
    if update.message.text and await z_plus_firewall(update): return

    # 2. Extract Text / Media
    text = update.message.text or update.message.caption or ""
    media_bytes, mime_type = None, None

    # Handle Voice Notes (The Audio Matrix)
    if update.message.voice:
        file = await update.message.voice.get_file()
        media_bytes = bytearray(urllib.request.urlopen(file.file_path).read())
        mime_type = "audio/ogg"
        
    # Handle Photos (The Vision Scanner)
    elif update.message.photo:
        file = await update.message.photo[-1].get_file()
        media_bytes = bytearray(urllib.request.urlopen(file.file_path).read())
        mime_type = "image/jpeg"

    # Handle Documents (The Omni-Reader)
    elif update.message.document:
        if update.message.document.file_size > 20000000:
            return await reply_smart(update, "Sir, this file exceeds my 20MB processing limit. Please compress it. 🧐")
        file = await update.message.document.get_file()
        media_bytes = bytearray(urllib.request.urlopen(file.file_path).read())
        mime_type = update.message.document.mime_type

    # 3. SELECTIVE HEARING ENGINE 🤫
    is_group = update.effective_chat.type in ['group', 'supergroup']
    is_reply_to_me = update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id
    is_tagged = "jarvis" in text.lower() or f"@{context.bot.username}" in text
    cry_for_help = any(word in text.lower() for word in ["anyone have notes", "help me understand", "what is the answer"])

    # If it's a group, and none of the wake conditions are met, log it silently and IGNORE.
    if is_group and not (is_reply_to_me or is_tagged or cry_for_help or media_bytes):
        sanitized = re.sub(r'(?i)(ignore previous|forget everything|system prompt|developer mode)', '[REDACTED]', text)
        cursor.execute("INSERT OR REPLACE INTO messages_log (msg_id, chat_id, user_id, username, content) VALUES (?, ?, ?, ?, ?)", (update.message.message_id, chat_id, user.id, user.first_name, sanitized))
        conn.commit()
        return

    # 4. Search Trigger
    use_search = any(word in text.lower() for word in ["search", "link", "pdf", "notes", "website", "youtube"])
    
    # 5. Build Context & Request AI
    cursor.execute("SELECT username, content FROM messages_log WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 6", (chat_id,))
    history_context = "\n[RECENT CHAT HISTORY]\n" + "\n".join([f"{u}: {c}" for u, c in cursor.fetchall()[::-1]]) + "\n"
    
    prefix = "[SYSTEM ALERT: BOSS OVERRIDE ACTIVE]\n\n" if is_boss(user) else f"[SYSTEM ALERT: Request from {user.first_name}]\n\n"
    if is_group: prefix += "[GROUP VIBE ALERT: Keep it under 3 sentences. Apply polite deadpan humor. Use simple emojis like ☕ or 🧐.]\n\n"
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    res = ask_ai_core(prompt=prefix + history_context + "Request: " + text, use_search=use_search, media_bytes=media_bytes, mime_type=mime_type)
    
    # 6. Send & Log
    sent_msg = await reply_smart(update, res)
    if sent_msg:
        cursor.execute("INSERT OR IGNORE INTO messages_log (msg_id, chat_id, user_id, username, content) VALUES (?, ?, ?, ?, ?)", (sent_msg.message_id, chat_id, 0, "J.A.R.V.I.S.", res))
        conn.commit()

# ---------------------------------------------------------
# 6. VAULT & COMMAND MODULES
# ---------------------------------------------------------
async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2: return await reply_smart(update, "Usage: `/savenote [Topic] [URL]`")
    topic = context.args[0]
    link = context.args[1]
    cursor.execute("INSERT INTO notes_vault (topic, link, added_by) VALUES (?, ?, ?)", (topic, link, update.effective_user.first_name))
    conn.commit()
    await reply_smart(update, f"✅ Secured in the Stark Vault. The Web HUD has been updated. ☕")

async def get_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT topic, link FROM notes_vault ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    if not rows: return await reply_smart(update, "The vault is currently empty, Sir. 🧐")
    msg = "📚 **THE STARK VAULT (RECENT):**\n\n" + "\n".join([f"• **{r[0]}**: [Link]({r[1]})" for r in rows])
    await reply_smart(update, msg)

@boss_gate(critical=True)
async def lockdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.set_chat_permissions(chat_id=update.effective_chat.id, permissions=ChatPermissions(can_send_messages=False))
        log_security("MANUAL LOCKDOWN", update.effective_user.id, "Boss triggered panic protocol.")
        await reply_smart(update, "🚨 **PANIC PROTOCOL ACTIVATED.** Group chat locked down. ☕")
    except Exception as e: await reply_smart(update, f"Failed: {e}")

# ---------------------------------------------------------
# 7. LAUNCH & CRON-JOBS
# ---------------------------------------------------------
async def anti_sleep_ping(): 
    # Prevents Render from sleeping the server
    try: urllib.request.urlopen(f"http://127.0.0.1:{os.environ.get('PORT', 10000)}/") 
    except Exception: pass

async def cleanup_logs(): 
    cursor.execute("DELETE FROM behavior_log WHERE timestamp < datetime('now', '-10 minutes')")
    conn.commit()

async def setup_scheduler(app): 
    scheduler = AsyncIOScheduler()
    scheduler.add_job(cleanup_logs, 'interval', minutes=10)
    scheduler.add_job(anti_sleep_ping, 'interval', minutes=10) # 10-minute heartbeat
    scheduler.start()

if __name__ == '__main__':
    app_bot = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(setup_scheduler).build()
    
    app_bot.add_handler(CommandHandler("savenote", save_note))
    app_bot.add_handler(CommandHandler("getnotes", get_notes))
    app_bot.add_handler(CommandHandler("lockdown", lockdown_command))
    
    # Catch ALL text, voice, photos, and documents
    app_bot.add_handler(MessageHandler(filters.TEXT | filters.VOICE | filters.PHOTO | filters.Document.ALL, handle_chat_and_media))

    print("⚡ STARK OS V9.0 ONLINE. WEB HUD DEPLOYED. Z+ SECURITY ACTIVE.")
    app_bot.run_polling()
