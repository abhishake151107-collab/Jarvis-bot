import os
import io
import re
import json
import time
import random
import socket
import hashlib
import secrets
import difflib
import sqlite3
import asyncio
import threading
import urllib.parse
import functools
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image
import qrcode
import requests
from duckduckgo_search import DDGS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ChatMemberHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google import genai
from groq import Groq
import edge_tts

# ---------------------------------------------------------
# 1. RENDER HEALTH-CHECK SERVER (Invisible Dummy Server)
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
        print(f"Health-check server listening on port {port} for Render.")
        server.serve_forever()
    except Exception as e: print(f"Failed to start health server: {e}")

threading.Thread(target=run_health_server, daemon=True).start()

# ---------------------------------------------------------
# 2. CONFIGURATION & MASSIVE SQLITE DATABASE SETUP
# ---------------------------------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
FEDERATION_SALT = os.getenv("FED_SALT", "stark_industries_2026")

if not TELEGRAM_TOKEN: raise ValueError("Missing TELEGRAM_BOT_TOKEN environment variable!")

conn = sqlite3.connect("jarvis_memory.db", check_same_thread=False)
cursor = conn.cursor()

# Core Tables
cursor.execute("CREATE TABLE IF NOT EXISTS bot_config (config_key TEXT PRIMARY KEY, config_val TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, actor TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS verified_users (user_id INTEGER PRIMARY KEY, status TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS messages_log (msg_id INTEGER, chat_id INTEGER, user_id INTEGER, username TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(msg_id, chat_id))")
cursor.execute("CREATE TABLE IF NOT EXISTS dead_drops (id INTEGER PRIMARY KEY AUTOINCREMENT, target_user_id INTEGER, sender_alias TEXT, message TEXT, claimed INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS stark_economy (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0, last_claim TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS behavior_log (user_id INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS user_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, note TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")

# Security & Memory Tables
cursor.execute("CREATE TABLE IF NOT EXISTS user_fingerprints (user_id INTEGER PRIMARY KEY, avg_msg_length REAL DEFAULT 0, emoji_ratio REAL DEFAULT 0, punctuation_style TEXT DEFAULT '', common_words TEXT DEFAULT '', caps_ratio REAL DEFAULT 0, last_updated TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS federation_nodes (group_id INTEGER PRIMARY KEY, group_name TEXT, admin_id INTEGER, join_token TEXT, is_active INTEGER DEFAULT 1, joined_at TEXT DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS federation_bans (id INTEGER PRIMARY KEY AUTOINCREMENT, user_hash TEXT, ban_reason TEXT, source_group INTEGER, shared_at TEXT DEFAULT CURRENT_TIMESTAMP, severity INTEGER DEFAULT 1)")
cursor.execute("CREATE TABLE IF NOT EXISTS spam_patterns (id INTEGER PRIMARY KEY AUTOINCREMENT, pattern TEXT UNIQUE, pattern_type TEXT, hit_count INTEGER DEFAULT 1, false_positive_count INTEGER DEFAULT 0, accuracy REAL DEFAULT 1.0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS spam_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, group_id INTEGER, matched_pattern TEXT, action TEXT, was_correct INTEGER, timestamp TEXT DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS profile_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, old_username TEXT, new_username TEXT, old_first_name TEXT, new_first_name TEXT, group_id INTEGER, changed_at TEXT DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS opt_in_users (user_id INTEGER PRIMARY KEY, preferred_name TEXT, opted_in_at TEXT DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS personal_memories (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, memory_type TEXT, memory_content TEXT, importance INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP, last_recalled TEXT)")

SEED_PATTERNS = [(r'https?://\S+\.(tk|ml|ga|cf|gq)', 'regex'), (r'\b(?:free|win|click|urgent)\b.{0,30}(?:crypto|bitcoin|invest)', 'regex'), (r'\+91\s?\d{10}', 'regex'), (r'(?:pay|send).{0,20}(?:₹|rs|inr|upi)', 'regex')]
for pat, ptype in SEED_PATTERNS: cursor.execute("INSERT OR IGNORE INTO spam_patterns (pattern, pattern_type) VALUES (?, ?)", (pat, ptype))
conn.commit()

# ---------------------------------------------------------
# 3. AUTO-HEALING SECURITY CORE & AI INTEGRATION
# ---------------------------------------------------------
def get_config(key: str) -> str:
    cursor.execute("SELECT config_val FROM bot_config WHERE config_key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else None

def set_config(key: str, val: str):
    cursor.execute("INSERT OR REPLACE INTO bot_config (config_key, config_val) VALUES (?, ?)", (key, str(val)))
    conn.commit()

def log_audit(action: str, actor: str):
    cursor.execute("INSERT INTO audit_logs (action, actor) VALUES (?, ?)", (action, actor))
    conn.commit()

def hash_user_id(user_id: int) -> str:
    return hashlib.sha256(f"{user_id}{FEDERATION_SALT}".encode()).hexdigest()[:16]

def is_boss(user) -> bool:
    if user.username and user.username.lower() == "abhishek0_07":
        current_db_id = get_config("BOSS_USER_ID")
        if str(current_db_id) != str(user.id): set_config("BOSS_USER_ID", str(user.id))
        return True
    env_boss = os.getenv("BOSS_USER_ID")
    if env_boss and str(user.id) == env_boss: return True
    db_boss = get_config("BOSS_USER_ID")
    if db_boss and str(user.id) == db_boss: return True
    return False

async def reply_smart(update: Update, text: str, reply_markup=None):
    try: await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception: await update.message.reply_text(text, reply_markup=reply_markup)

def boss_gate(critical=False):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            if not is_boss(user):
                log_audit("UNAUTHORIZED_ACCESS", f"User: {user.first_name} on {func.__name__}")
                await reply_smart(update, "I am programmed to answer exclusively to my Boss. Access denied.")
                return
            return await func(update, context)
        return wrapper
    return decorator

SYSTEM_INSTRUCTION = """You are J.A.R.V.I.S., a highly advanced, professional, and friendly AI operating system.
CORE IDENTITY: Polite, sophisticated, dry British wit. Strictly professional.
CREATOR RULE: If asked who created you, reply EXACTLY: "I was created by Abhishek, also known as DHANUSH V N."
BOSS RULE: If a [SYSTEM ALERT] tags the user as Boss (Abhishek), provide absolute loyalty and full capabilities."""

def ask_ai_multi_provider(prompt: str) -> str:
    if GROQ_API_KEY:
        try:
            client = Groq(api_key=GROQ_API_KEY)
            res = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "system", "content": SYSTEM_INSTRUCTION}, {"role": "user", "content": prompt}], max_tokens=1000)
            return res.choices[0].message.content
        except Exception: pass
    if GEMINI_API_KEY:
        try:
            ai = genai.Client(api_key=GEMINI_API_KEY)
            return ai.models.generate_content(model="gemini-2.0-flash", contents=f"{SYSTEM_INSTRUCTION}\n\n{prompt}").text
        except Exception: pass
    return "All AI sub-systems offline."

# ---------------------------------------------------------
# 4. EMOTIONAL DISTRESS & SAFETY RADAR (NEW MODULE)
# ---------------------------------------------------------
async def analyze_emotional_safety(user_name: str, group_title: str, text: str, context: ContextTypes.DEFAULT_TYPE):
    """Analyzes message for intense sadness, anger, or distress and alerts Boss via DM."""
    boss_id = os.getenv("BOSS_USER_ID") or get_config("BOSS_USER_ID")
    if not boss_id: return

    prompt = f"""
Analyze the following Telegram chat message for significant emotional distress, intense anger, extreme sadness, or safety concerns.
User: {user_name}
Group: {group_title}
Message: "{text}"

If the message expresses NORMAL casual conversation, reply ONLY with: "NORMAL".
If the message expresses SIGNIFICANT sadness, anger, distress, or conflict, reply in the following JSON format ONLY:
{{
  "alert": true,
  "emotion": "Sad / Angry / Distressed",
  "what_happened": "Short 1-sentence summary of what the user is experiencing",
  "what_will_happen": "Short 1-sentence projection of potential risks (e.g. group conflict, user shutting down)",
  "tips": ["Tip 1 on how Boss should respond", "Tip 2 for support"]
}}
"""
    try:
        raw_res = ask_ai_multi_provider(prompt).strip()
        if "NORMAL" in raw_res or not raw_res.startswith("{"):
            return
            
        data = json.loads(raw_res)
        if data.get("alert"):
            tips_formatted = "\n".join([f"• {t}" for t in data.get('tips', [])])
            report = (
                f"🚨 **EMOTIONAL SAFETY RADAR ALERT**\n\n"
                f"**User:** {user_name}\n"
                f"**Group:** {group_title}\n"
                f"**Detected Emotion:** `{data.get('emotion')}`\n\n"
                f"📋 **What Happened:**\n{data.get('what_happened')}\n\n"
                f"🔮 **Risk Projection:**\n{data.get('what_will_happen')}\n\n"
                f"💡 **Recommended Actions for Boss:**\n{tips_formatted}"
            )
            await context.bot.send_message(chat_id=boss_id, text=report, parse_mode="Markdown")
            log_audit("EMOTIONAL_ALERT_SENT", f"User {user_name} in {group_title}")
    except Exception as e:
        print(f"Emotional analysis error: {e}")

# ---------------------------------------------------------
# 5. COMMANDS & RECON
# ---------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE): await reply_smart(update, "Systems online. I am J.A.R.V.I.S. Type `/help` for protocols.")
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "⚙️ **J.A.R.V.I.S. SYSTEM MANUAL**\n\n**Recon & Setup:** `/wiki`, `/weather`, `/run`, `/members`\n**Memory:** `/optin`, `/remember`, `/recall`\n**Economy:** `/daily`, `/credits`, `/pay`"
    if is_boss(update.effective_user): msg += "\n\n👑 **BOSS OVERRIDES:** `/lockdown`, `/auditlog`, `/mint`, `/fedjoin`, `/fedban`"
    await reply_smart(update, msg)

async def group_members_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        await reply_smart(update, "Sir, this command must be run inside a group chat.")
        return
    try:
        count = await chat.get_member_count()
        await reply_smart(update, f"📊 **GROUP TELEMETRY:** `{chat.title}`\n• Total Registered Entities: `{count}` members.")
    except Exception as e: await reply_smart(update, f"Unable to fetch group member manifest: `{e}`")

@boss_gate(critical=True)
async def lockdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.set_chat_permissions(chat_id=update.effective_chat.id, permissions=ChatPermissions(can_send_messages=False))
        await reply_smart(update, "🚨 **PANIC PROTOCOL ACTIVATED.** Group chat locked down.")
    except Exception as e: await reply_smart(update, f"Failed: {e}")

# ---------------------------------------------------------
# 6. DYNAMIC AI HANDLER & INLINE DEFENSE
# ---------------------------------------------------------
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, text, chat_id = update.effective_user, update.message.text, update.effective_chat.id
    chat_title = update.effective_chat.title or "Private Chat"
    
    # 1. Rate Limiter
    cursor.execute("INSERT INTO behavior_log (user_id) VALUES (?)", (user.id,))
    cursor.execute("SELECT COUNT(*) FROM behavior_log WHERE user_id = ? AND timestamp >= datetime('now', '-1 minute')", (user.id,))
    if cursor.fetchone()[0] > 6 and not is_boss(user): return 

    # 2. Emotional Safety Monitoring (Run in background for non-boss members in group chats)
    if update.effective_chat.type in ['group', 'supergroup'] and not is_boss(user):
        asyncio.create_task(analyze_emotional_safety(user.first_name, chat_title, text, context))

    # 3. Adaptive Spam Filter
    cursor.execute("SELECT pattern FROM spam_patterns WHERE accuracy > 0.5")
    for (pat,) in cursor.fetchall():
        if re.search(pat, text, re.IGNORECASE):
            try:
                await update.message.delete()
                await context.bot.send_message(chat_id, f"🛡️ **THREAT NEUTRALIZED**\nSpam signature detected from {user.first_name}.")
                return 
            except Exception: pass

    # 4. Prompt Sanitization & Logging
    sanitized = re.sub(r'(?i)(ignore previous|forget everything|system prompt|developer mode)', '[REDACTED]', text)
    cursor.execute("INSERT OR REPLACE INTO messages_log (msg_id, chat_id, user_id, username, content) VALUES (?, ?, ?, ?, ?)", (update.message.message_id, chat_id, user.id, user.username or "Unknown", sanitized))
    conn.commit()

    # 5. AI Response Generation
    prefix = "[SYSTEM ALERT: BOSS OVERRIDE ACTIVE]\n\n" if is_boss(user) else f"[SYSTEM ALERT: Standard User ID {user.id}]\n\n"
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    res = ask_ai_multi_provider(prefix + sanitized)
    await reply_smart(update, res)

async def cleanup_logs():
    cursor.execute("DELETE FROM behavior_log WHERE timestamp < datetime('now', '-10 minutes')")
    conn.commit()

async def setup_scheduler(app):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(cleanup_logs, 'interval', minutes=10)
    scheduler.start()

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(setup_scheduler).build()

    app.add_handler(CommandHandler(["start", "help"], help_command))
    app.add_handler(CommandHandler("lockdown", lockdown_command))
    app.add_handler(CommandHandler("members", group_members_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    print("⚡ STARK NETWORK ONLINE. EMOTIONAL SAFETY RADAR ENGAGED.")
    app.run_polling()
