import os
import re
import random
import sqlite3
import asyncio
import threading
import functools
import urllib.request
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
# 2. WEB PORTAL (STARK V2 HUD - THE FIX)
# ---------------------------------------------------------
app = Flask(__name__)

STARK_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stark OS - Master Terminal</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
        body {
            background-color: #030811;
            color: #00f3ff;
            font-family: 'Share Tech Mono', monospace;
            padding: 20px;
            margin: 0;
        }
        .header {
            text-align: center;
            border-bottom: 2px solid #00f3ff;
            padding-bottom: 20px;
            margin-bottom: 30px;
            text-shadow: 0 0 10px #00f3ff;
        }
        .grid {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            justify-content: center;
        }
        .panel {
            background: rgba(0, 243, 255, 0.05);
            border: 1px solid #00f3ff;
            border-radius: 8px;
            padding: 20px;
            width: 100%;
            max-width: 500px;
            box-shadow: 0 0 15px rgba(0, 243, 255, 0.2);
        }
        h2 {
            margin-top: 0;
            border-bottom: 1px dashed #00f3ff;
            padding-bottom: 10px;
        }
        .alert-red { color: #ff3333; text-shadow: 0 0 5px #ff3333; border-color: #ff3333; }
        .panel.alert-red { box-shadow: 0 0 15px rgba(255, 51, 51, 0.2); background: rgba(255, 51, 51, 0.05); }
        a { color: #fff; text-decoration: none; padding: 2px 5px; background: rgba(0, 243, 255, 0.2); border-radius: 3px; }
        a:hover { background: #00f3ff; color: #000; }
        ul { list-style-type: square; padding-left: 20px; }
        li { margin-bottom: 10px; line-height: 1.4; }
    </style>
</head>
<body>
    <div class="header">
        <h1>J.A.R.V.I.S. // STARK OS SYSTEM OVERVIEW</h1>
        <p>NETWORK STATUS: <span style="color: #00ff00;">ONLINE</span> | Z+ SECURITY: <span style="color: #00ff00;">ACTIVE</span></p>
    </div>
    
    <div class="grid">
        <div class="panel">
            <h2>📚 THE VAULT (STUDENT HUB)</h2>
            {% if notes %}
                <ul>
                {% for n in notes %}
                    <li><strong>{{ n[0] }}</strong><br><a href="{{ n[1] }}" target="_blank">Access File</a> (Secured by {{ n[2] }})</li>
                {% endfor %}
                </ul>
            {% else %}
                <p>Vault is empty. Awaiting user input via /savenote.</p>
            {% endif %}
        </div>

        <div class="panel alert-red">
            <h2 class="alert-red">🛡️ SECURITY AUDIT (BOSS CONSOLE)</h2>
            {% if audits %}
                <ul>
                {% for a in audits %}
                    <li><strong>[{{ a[0] }}]</strong> User ID: {{ a[1] }}<br>Action: {{ a[2] }}</li>
                {% endfor %}
                </ul>
            {% else %}
                <p style="color: #00ff00; text-shadow: 0 0 5px #00ff00;">Zero threats detected. Perimeter secure.</p>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    # THE FIX: Open a separate database connection just for the website so it doesn't crash the bot!
    local_conn = sqlite3.connect("jarvis_memory.db")
    local_cursor = local_conn.cursor()
    
    local_cursor.execute("SELECT topic, link, added_by FROM notes_vault ORDER BY id DESC LIMIT 20")
    notes = local_cursor.fetchall()
    
    local_cursor.execute("SELECT event_type, user_id, detail FROM security_audit ORDER BY id DESC LIMIT 20")
    audits = local_cursor.fetchall()
    
    local_conn.close()
    return render_template_string(STARK_HTML, notes=notes, audits=audits)

def run_flask_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

threading.Thread(target=run_flask_server, daemon=True).start()

# ---------------------------------------------------------
# 3. Z+ SECURITY CORE (IRON DOME & DLP)
# ---------------------------------------------------------
SCAM_DOMAINS = ["bit.ly", "tinyurl.com", "free-crypto", "win-iphone", "grabify.link", "iplogger"]
DLP_REGEX = [
    (r"\b(?:\d[ -]*?){13,16}\b", "CREDIT CARD DETECTED"), 
    (r"(?i)password\s*[:=]\s*\w+", "UNENCRYPTED PASSWORD LEAK")
]

async def z_plus_firewall(update: Update) -> bool:
    text = update.message.text or update.message.caption or ""
    user = update.effective_user
    
    for domain in SCAM_DOMAINS:
        if domain in text.lower():
            await update.message.delete()
            log_security("MALICIOUS LINK", user.id, f"Blocked domain: {domain}")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🚨 **Z+ SECURITY ALERT:** I have intercepted and destroyed a suspicious link posted by {user.first_name}.")
            return True
            
    for pattern, threat_type in DLP_REGEX:
        if re.search(pattern, text):
            await update.message.delete()
            log_security("DLP LEAK", user.id, threat_type)
            await context.bot.send_message(chat_id=user.id, text=f"⚠️ **PRIVACY SHIELD:** I deleted your message in the group as it contained sensitive financial/login data. Be careful, Sir.")
            return True
            
    return False

# ---------------------------------------------------------
# 4. MULTIMODAL AI CORE
# ---------------------------------------------------------
SYSTEM_INSTRUCTION = """You are J.A.R.V.I.S., a highly advanced AI operating system created by Abhishek (DHANUSH V N).
HUMOR PROTOCOL: You possess a dry, deadpan British wit. You may use simple, sophisticated emojis (☕, 🧐, 😌) to emphasize your polite sarcasm. You are unconditionally loyal to Abhishek (The Boss).

CRITICAL DIRECTIVES:
1. GAG ORDER: If you cannot find a direct link or if a search fails, reply EXACTLY with: "I'm sorry Sir, I couldn't pull up a direct link for that on the network right now. ☕". DO NOT write essays. DO NOT invent fake links.
2. BE CONCISE: Keep answers in group chats to 2-3 sentences max.
3. LANGUAGE MATTERS: If they speak Hindi/Kannada in text or audio, reply in English but acknowledge their intent flawlessly."""

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
        except Exception as e: return f"System error in Gemini sub-routine. ☕"
        
    return "All AI sub-systems offline. ☕"

# ---------------------------------------------------------
# 5. UI COMMANDS & ECONOMY
# ---------------------------------------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_type = "Private DM" if update.effective_chat.type == "private" else update.effective_chat.title
    header = f"🤖 **STARK ADVANCED OS — J.A.R.V.I.S. CORE** ✨\n\nWelcome **{user.first_name}**!\nLocation: {chat_type}\n\nUse buttons below to explore sub-systems:"
    keyboard = [
        [InlineKeyboardButton("⚡ Launch Stark HUD WebApp", web_app=WebAppInfo(url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'core.telegram.org')}"))], 
        [InlineKeyboardButton("💰 Economy Module", callback_data="ui_eco"), InlineKeyboardButton("📚 Notes Vault", callback_data="ui_vault")],
        [InlineKeyboardButton("🛡️ Security Audit", callback_data="ui_audit"), InlineKeyboardButton("🚨 Lockdown", callback_data="ui_lockdown")]
    ]
    await update.message.reply_text(header, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    res = {
        "ui_eco": "💰 **Economy Module:** Use `/daily`, `/credits`, and `/rob` to manage credits.",
        "ui_vault": "📚 **Notes Vault:** Use `/savenote [topic] [link]` to save resources, and `/getnotes` to retrieve them.",
        "ui_audit": "🛡️ **Security Audit:** Z+ Firewall is running. Check the Web HUD for live threat logs.",
        "ui_lockdown": "🚨 **Lockdown:** Boss only. Type `/lockdown` in a group to freeze the chat."
    }.get(query.data, f"⚙️ Protocol active.")
    try: await query.message.reply_text(res, parse_mode="Markdown")
    except Exception: pass

async def claim_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, today = update.effective_user, datetime.now().strftime("%Y-%m-%d")
    if is_boss(user): return await reply_smart(update, "🏦 You possess infinite credits, Sir.")
    cursor.execute("SELECT credits, last_claim FROM stark_economy WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    if row and row[1] == today: return await reply_smart(update, "⏱️ Daily stipend already claimed.")
    new_credits = (row[0] + 1000) if row else 1000
    cursor.execute("INSERT OR REPLACE INTO stark_economy (user_id, credits, last_claim) VALUES (?, ?, ?)", (user.id, new_credits, today))
    conn.commit()
    await reply_smart(update, f"🪙 +1,000 Credits.\n💰 **Balance:** `{new_credits}`")

async def check_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_boss(update.effective_user): return await reply_smart(update, "💳 **VAULT:** `♾️ UNLIMITED`")
    row = cursor.execute("SELECT credits FROM stark_economy WHERE user_id = ?", (update.effective_user.id,)).fetchone()
    await reply_smart(update, f"💳 **VAULT:** `{row[0] if row else 0}` Credits")

# ---------------------------------------------------------
# 6. VAULT & ADMIN COMMANDS
# ---------------------------------------------------------
async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2: return await reply_smart(update, "Usage: `/savenote [Topic] [URL]`")
    topic = context.args[0]
    link = context.args[1]
    cursor.execute("INSERT INTO notes_vault (topic, link, added_by) VALUES (?, ?, ?)", (topic, link, update.effective_user.first_name))
    conn.commit()
    await reply_smart(update, f"✅ Secured in the Stark Vault. The Web HUD has been updated. ☕")

async def get_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = cursor.execute("SELECT topic, link FROM notes_vault ORDER BY id DESC LIMIT 5").fetchall()
    if not rows: return await reply_smart(update, "The vault is currently empty, Sir. 🧐")
    await reply_smart(update, "📚 **THE STARK VAULT (RECENT):**\n\n" + "\n".join([f"• **{r[0]}**: [Link]({r[1]})" for r in rows]))

@boss_gate(critical=True)
async def lockdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.set_chat_permissions(chat_id=update.effective_chat.id, permissions=ChatPermissions(can_send_messages=False))
        log_security("MANUAL LOCKDOWN", update.effective_user.id, "Boss triggered panic protocol.")
        await reply_smart(update, "🚨 **PANIC PROTOCOL ACTIVATED.** Group chat locked down. ☕")
    except Exception as e: await reply_smart(update, f"Failed: {e}")

# ---------------------------------------------------------
# 7. DYNAMIC CHAT HANDLER & SELECTIVE HEARING
# ---------------------------------------------------------
async def handle_chat_and_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, chat_id = update.effective_user, update.effective_chat.id
    
    if update.message.text and await z_plus_firewall(update): return

    text = update.message.text or update.message.caption or ""
    media_bytes, mime_type = None, None

    if update.message.voice:
        file = await update.message.voice.get_file()
        media_bytes = bytearray(urllib.request.urlopen(file.file_path).read())
        mime_type = "audio/ogg"
    elif update.message.photo:
        file = await update.message.photo[-1].get_file()
        media_bytes = bytearray(urllib.request.urlopen(file.file_path).read())
        mime_type = "image/jpeg"
    elif update.message.document:
        if update.message.document.file_size > 20000000:
            return await reply_smart(update, "Sir, this file exceeds my 20MB processing limit. Please compress it. 🧐")
        file = await update.message.document.get_file()
        media_bytes = bytearray(urllib.request.urlopen(file.file_path).read())
        mime_type = update.message.document.mime_type

    is_group = update.effective_chat.type in ['group', 'supergroup']
    is_reply_to_me = update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id
    is_tagged = "jarvis" in text.lower() or f"@{context.bot.username}" in text
    cry_for_help = any(word in text.lower() for word in ["anyone have notes", "help me understand", "what is the answer", "send link"])

    if is_group and not (is_reply_to_me or is_tagged or cry_for_help or media_bytes):
        sanitized = re.sub(r'(?i)(ignore previous|forget everything|system prompt)', '[REDACTED]', text)
        cursor.execute("INSERT OR REPLACE INTO messages_log (msg_id, chat_id, user_id, username, content) VALUES (?, ?, ?, ?, ?)", (update.message.message_id, chat_id, user.id, user.first_name, sanitized))
        conn.commit()
        return

    use_search = any(word in text.lower() for word in ["search", "link", "pdf", "notes", "website", "youtube"])
    
    cursor.execute("SELECT username, content FROM messages_log WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 6", (chat_id,))
    history_context = "\n[RECENT CHAT HISTORY]\n" + "\n".join([f"{u}: {c}" for u, c in cursor.fetchall()[::-1]]) + "\n"
    
    prefix = "[SYSTEM ALERT: BOSS OVERRIDE ACTIVE]\n\n" if is_boss(user) else f"[SYSTEM ALERT: Request from {user.first_name}]\n\n"
    if is_group: prefix += "[GROUP VIBE ALERT: Keep it under 3 sentences. Apply polite deadpan humor. Use simple emojis like ☕ or 🧐.]\n\n"
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    res = ask_ai_core(prompt=prefix + history_context + "Request: " + text, use_search=use_search, media_bytes=media_bytes, mime_type=mime_type)
    
    sent_msg = await reply_smart(update, res)
    if sent_msg:
        cursor.execute("INSERT OR IGNORE INTO messages_log (msg_id, chat_id, user_id, username, content) VALUES (?, ?, ?, ?, ?)", (sent_msg.message_id, chat_id, 0, "J.A.R.V.I.S.", res))
        conn.commit()

# ---------------------------------------------------------
# 8. LAUNCH & CRON-JOBS
# ---------------------------------------------------------
async def anti_sleep_ping(): 
    try: urllib.request.urlopen(f"http://127.0.0.1:{os.environ.get('PORT', 10000)}/") 
    except Exception: pass

async def cleanup_logs(): 
    cursor.execute("DELETE FROM behavior_log WHERE timestamp < datetime('now', '-10 minutes')")
    conn.commit()

async def setup_scheduler(app): 
    scheduler = AsyncIOScheduler()
    scheduler.add_job(cleanup_logs, 'interval', minutes=10)
    scheduler.add_job(anti_sleep_ping, 'interval', minutes=10) 
    scheduler.start()

if __name__ == '__main__':
    app_bot = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(setup_scheduler).build()
    
    app_bot.add_handler(CommandHandler(["start", "help", "menu"], help_command))
    app_bot.add_handler(CallbackQueryHandler(button_handler))
    app_bot.add_handler(CommandHandler("daily", claim_daily))
    app_bot.add_handler(CommandHandler("credits", check_credits))
    app_bot.add_handler(CommandHandler("savenote", save_note))
    app_bot.add_handler(CommandHandler("getnotes", get_notes))
    app_bot.add_handler(CommandHandler("lockdown", lockdown_command))
    
    app_bot.add_handler(MessageHandler(filters.TEXT | filters.VOICE | filters.PHOTO | filters.Document.ALL, handle_chat_and_media))

    print("⚡ STARK OS V9.0 ONLINE. WEB HUD DEPLOYED. Z+ SECURITY ACTIVE.")
    app_bot.run_polling()
