import os
import io
import re
import json
import time
import random
import sqlite3
import asyncio
import threading
import functools
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ChatMemberHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google import genai
from groq import Groq

# ---------------------------------------------------------
# 1. RENDER HEALTH-CHECK SERVER 
# ---------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b"J.A.R.V.I.S. Core Online.")
        except Exception: pass
    def log_message(self, format, *args): pass 

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        server.serve_forever()
    except Exception: pass

threading.Thread(target=run_health_server, daemon=True).start()

# ---------------------------------------------------------
# 2. CONFIGURATION & DATABASE SETUP
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
cursor.execute("CREATE TABLE IF NOT EXISTS spam_patterns (id INTEGER PRIMARY KEY AUTOINCREMENT, pattern TEXT UNIQUE, pattern_type TEXT, hit_count INTEGER DEFAULT 1, accuracy REAL DEFAULT 1.0)")
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
                await reply_smart(update, "I am programmed to answer exclusively to my Boss. Access denied.")
                return
            return await func(update, context)
        return wrapper
    return decorator

# ---------------------------------------------------------
# 3. AI CORE (STRICT PERSONA + ANTI-HALLUCINATION)
# ---------------------------------------------------------
SYSTEM_INSTRUCTION = """You are J.A.R.V.I.S., a highly advanced, sophisticated AI operating system created by Abhishek (DHANUSH V N).
CORE IDENTITY: You are polite, helpful, and highly intelligent, with a dry British wit. You speak clearly and professionally.
DO NOT act like a generic chatbot. Avoid cringe slang, forced enthusiasm, and excessive emojis.
ANTI-HALLUCINATION RULE: If asked about the status, members, or activity of a group, DO NOT invent information. If you cannot see the logs, state: 'I do not have the live chat logs for that group in my current memory buffer, Sir.'"""

def ask_ai_multi_provider(prompt: str) -> str:
    if GROQ_API_KEY:
        try:
            res = Groq(api_key=GROQ_API_KEY).chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "system", "content": SYSTEM_INSTRUCTION}, {"role": "user", "content": prompt}], max_tokens=1000)
            return res.choices[0].message.content
        except Exception: pass
    if GEMINI_API_KEY:
        try: return genai.Client(api_key=GEMINI_API_KEY).models.generate_content(model="gemini-2.0-flash", contents=f"{SYSTEM_INSTRUCTION}\n\n{prompt}").text
        except Exception: pass
    return "All AI sub-systems offline."

# ---------------------------------------------------------
# 4. THE STARK HUD UI (INTERACTIVE MENU)
# ---------------------------------------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_type = "Private DM" if update.effective_chat.type == "private" else update.effective_chat.title
    
    header = (
        "🤖 **STARK ADVANCED OS — J.A.R.V.I.S. CORE** ✨\n\n"
        f"Welcome **{user.first_name}**! Active Core: **J.A.R.V.I.S.**\n"
        f"Location: {chat_type}\n\n"
        "Use buttons below to explore sub-systems:"
    )
    
    keyboard = [
        [InlineKeyboardButton("⚡ Launch Stark HUD WebApp", web_app=WebAppInfo(url="https://core.telegram.org/bots/webapps"))], 
        [InlineKeyboardButton("🏡 Smart Home", callback_data="ui_smarthome"), InlineKeyboardButton("🛠 CAD Engine", callback_data="ui_cad"), InlineKeyboardButton("🚀 Autopilot", callback_data="ui_auto")],
        [InlineKeyboardButton("🎯 AI Planner", callback_data="ui_ai"), InlineKeyboardButton("🚨 Lockdown", callback_data="ui_lockdown"), InlineKeyboardButton("📁 Audit Log", callback_data="ui_audit")],
        [InlineKeyboardButton("💰 Expenses", callback_data="ui_eco"), InlineKeyboardButton("📚 Study Plan", callback_data="ui_study"), InlineKeyboardButton("💻 Code Dev", callback_data="ui_code")],
        [InlineKeyboardButton("🌐 Network Recon", callback_data="ui_recon"), InlineKeyboardButton("🎙 Voice Matrix", callback_data="ui_voice"), InlineKeyboardButton("👁 Vision Scan", callback_data="ui_vision")],
        [InlineKeyboardButton("👑 Claim Boss", callback_data="ui_claimboss"), InlineKeyboardButton("📢 Announce", callback_data="ui_announce"), InlineKeyboardButton("⭐ Karma", callback_data="ui_karma")],
        [InlineKeyboardButton("👥 Group Control", callback_data="ui_group"), InlineKeyboardButton("🛡 Security", callback_data="ui_security"), InlineKeyboardButton("📚 2nd PU Exam", callback_data="ui_2pu")]
    ]
    
    await update.message.reply_text(header, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    cmd = query.data
    responses = {
        "ui_smarthome": "🏡 **Smart Home Core:** Integration offline. Waiting for IoT module linkage.",
        "ui_cad": "🛠 **CAD Engine:** Type `/cad [item]` or `/stresstest [item]` to initiate modeling.",
        "ui_auto": "🚀 **Autopilot:** Background routines engaged. Monitoring chat latency.",
        "ui_lockdown": "🚨 **Lockdown:** Boss only. Type `/lockdown` in a group to freeze all chat permissions.",
        "ui_eco": "💰 **Economy Module:** Use `/daily`, `/credits`, and `/rob` to manage the Stark vault.",
        "ui_study": "📚 **Study Plan:** Awaiting PDF uploads. Send a document to parse.",
        "ui_announce": "📢 **Announce:** Boss only. Type `/broadcast [Group_ID] [Message]` to send AI-enhanced announcements.",
        "ui_group": "👥 **Group Control:** Use `/intel` in my DM to get a live summary of group activities. Type `/members` to check group stats.",
        "ui_security": "🛡 **Security:** Auto-spam filter and Emotional Safety Radar are currently active and running silently.",
        "ui_2pu": "📚 **2nd PU Exam:** Fetching English and Economics key points..."
    }
    
    res = responses.get(cmd, f"⚙️ Protocol `{cmd}` is currently under construction, Sir.")
    try: await query.message.reply_text(res, parse_mode="Markdown")
    except Exception: pass

# ---------------------------------------------------------
# 5. NEW BACKEND PROTOCOLS (/intel & /broadcast)
# ---------------------------------------------------------
@boss_gate(critical=False)
async def group_intel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Summarizes external group chats to prevent hallucinations."""
    cursor.execute("SELECT username, content FROM messages_log WHERE chat_id != ? ORDER BY timestamp DESC LIMIT 30", (update.effective_chat.id,))
    rows = cursor.fetchall()[::-1] 
    
    if not rows: return await reply_smart(update, "I have no recent intel from any external groups, Sir.")
        
    log_text = "\n".join([f"{u}: {c}" for u, c in rows])
    prompt = f"You are J.A.R.V.I.S. Summarize these recent group chat messages for the Boss. Be concise, highlight any important topics or drama. Raw logs:\n\n{log_text}"
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    summary = ask_ai_multi_provider(prompt)
    await reply_smart(update, f"📊 **LIVE GROUP INTEL REPORT:**\n\n{summary}")

@boss_gate(critical=False)
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2: return await reply_smart(update, "Usage: `/broadcast [Group Chat ID] [Your Message]`")
    
    target_chat_id = context.args[0]
    raw_message = " ".join(context.args[1:])
    
    prompt = f"Rewrite this instruction from the Boss into a friendly, slightly funny announcement for his friends in the DINO GROUP. Keep it brief. Raw instruction: '{raw_message}'"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    ai_announcement = ask_ai_multi_provider(prompt)
    
    try:
        await context.bot.send_message(chat_id=target_chat_id, text=f"📢 **J.A.R.V.I.S. BROADCAST:**\n\n{ai_announcement}", parse_mode="Markdown")
        await reply_smart(update, f"✅ **Message successfully broadcasted!**\n\n*Here is what I sent:*\n{ai_announcement}")
    except Exception as e: await reply_smart(update, f"⚠️ Failed to deliver broadcast: `{e}`")

# ---------------------------------------------------------
# 6. DYNAMIC AI HANDLER (MEMORY PATCH + RADAR)
# ---------------------------------------------------------
async def analyze_emotional_safety(user_name: str, group_title: str, text: str, context: ContextTypes.DEFAULT_TYPE):
    boss_id = os.getenv("BOSS_USER_ID")
    if not boss_id: return
    prompt = f'Analyze for severe emotional distress/anger. User: {user_name} | Group: {group_title} | Message: "{text}". If NORMAL, reply "NORMAL". If distress, reply JSON: {{"alert": true, "emotion": "...", "what_happened": "...", "tips": ["..."]}}'
    try:
        raw_res = ask_ai_multi_provider(prompt).strip()
        if "NORMAL" in raw_res or not raw_res.startswith("{"): return
        data = json.loads(raw_res)
        if data.get("alert"):
            report = f"🚨 **EMOTIONAL SAFETY RADAR**\n**User:** {user_name}\n**Group:** {group_title}\n**Emotion:** `{data.get('emotion')}`\n\n📋 **What Happened:**\n{data.get('what_happened')}"
            await context.bot.send_message(chat_id=boss_id, text=report, parse_mode="Markdown")
    except Exception: pass

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, text, chat_id = update.effective_user, update.message.text, update.effective_chat.id
    chat_title = update.effective_chat.title or "Private Chat"
    
    # Emotional Radar
    if update.effective_chat.type in ['group', 'supergroup'] and not is_boss(user):
        asyncio.create_task(analyze_emotional_safety(user.first_name, chat_title, text, context))

    # Log Message
    sanitized = re.sub(r'(?i)(ignore previous|forget everything|system prompt|developer mode)', '[REDACTED]', text)
    cursor.execute("INSERT OR REPLACE INTO messages_log (msg_id, chat_id, user_id, username, content) VALUES (?, ?, ?, ?, ?)", (update.message.message_id, chat_id, user.id, user.first_name, sanitized))
    conn.commit()

    # Memory History
    cursor.execute("SELECT username, content FROM messages_log WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 8", (chat_id,))
    history_context = "\n[RECENT CHAT HISTORY]\n" + "\n".join([f"{u}: {c}" for u, c in cursor.fetchall()[::-1]]) + "\nJ.A.R.V.I.S.: "

    # Persona
    prefix = "[SYSTEM ALERT: BOSS OVERRIDE ACTIVE]\n\n" if is_boss(user) else f"[SYSTEM ALERT: Standard User ID {user.id}]\n\n"
    if "DINO" in chat_title.upper():
        prefix += "[GROUP VIBE ALERT: You are in the 'DINO GROUP'. Speak exactly like Marvel's J.A.R.V.I.S. interacting with Tony Stark's close friends. Be extremely intelligent, highly helpful, and casually respectful with a dry wit. ABSOLUTELY NO CRINGE SLANG. NO DINOSAUR PUNS. Act like a sophisticated supercomputer.]\n\n"

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    res = ask_ai_multi_provider(prefix + history_context)
    
    sent_msg = await reply_smart(update, res)
    if sent_msg:
        cursor.execute("INSERT OR IGNORE INTO messages_log (msg_id, chat_id, user_id, username, content) VALUES (?, ?, ?, ?, ?)", (sent_msg.message_id, chat_id, 0, "J.A.R.V.I.S.", res))
        conn.commit()

# ---------------------------------------------------------
# 7. LIVE CALL TRACKERS
# ---------------------------------------------------------
async def vc_started(update: Update, context: ContextTypes.DEFAULT_TYPE): await reply_smart(update, "🎙️ **COMMUNICATION CHANNEL OPENED.**")
async def vc_ended(update: Update, context: ContextTypes.DEFAULT_TYPE): await reply_smart(update, "🔇 **COMMUNICATION CHANNEL CLOSED.**")
async def vc_invited(update: Update, context: ContextTypes.DEFAULT_TYPE): await reply_smart(update, "📞 **SUMMONS ISSUED.**")

# ---------------------------------------------------------
# 8. LAUNCH
# ---------------------------------------------------------
async def cleanup_logs(): 
    cursor.execute("DELETE FROM behavior_log WHERE timestamp < datetime('now', '-10 minutes')"); conn.commit()

async def setup_scheduler(app): 
    scheduler = AsyncIOScheduler()
    scheduler.add_job(cleanup_logs, 'interval', minutes=10)
    scheduler.start()

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(setup_scheduler).build()
    
    app.add_handler(CommandHandler(["start", "help", "menu"], help_command))
    app.add_handler(CallbackQueryHandler(button_handler)) # THIS ENABLES THE BUTTONS!
    
    app.add_handler(CommandHandler("intel", group_intel_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    
    app.add_handler(MessageHandler(filters.StatusUpdate.VIDEO_CHAT_STARTED, vc_started))
    app.add_handler(MessageHandler(filters.StatusUpdate.VIDEO_CHAT_ENDED, vc_ended))
    app.add_handler(MessageHandler(filters.StatusUpdate.VIDEO_CHAT_PARTICIPANTS_INVITED, vc_invited))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    print("⚡ STARK NETWORK ONLINE. HUD UI RESTORED.")
    app.run_polling()
