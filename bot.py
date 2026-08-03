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
# 2. CONFIGURATION & DATABASE
# ---------------------------------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
FEDERATION_SALT = os.getenv("FED_SALT", "stark_industries_2026")

conn = sqlite3.connect("jarvis_memory.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS bot_config (config_key TEXT PRIMARY KEY, config_val TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, actor TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS messages_log (msg_id INTEGER, chat_id INTEGER, user_id INTEGER, username TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(msg_id, chat_id))")
cursor.execute("CREATE TABLE IF NOT EXISTS stark_economy (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0, last_claim TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS behavior_log (user_id INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
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
# 3. CORE UTILITIES
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

def is_boss(user) -> bool:
    if user.username and user.username.lower() == "abhishek0_07":
        if str(get_config("BOSS_USER_ID")) != str(user.id): set_config("BOSS_USER_ID", str(user.id))
        return True
    return str(user.id) == os.getenv("BOSS_USER_ID") or str(user.id) == get_config("BOSS_USER_ID")

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

# --- AI CORE ---
SYSTEM_INSTRUCTION = """You are J.A.R.V.I.S., a highly advanced, sophisticated AI operating system created by Abhishek (DHANUSH V N).
CORE IDENTITY: You are polite, helpful, and highly intelligent, with a dry British wit. You speak clearly and professionally.
DO NOT act like a generic chatbot. Avoid cringe slang, forced enthusiasm, and excessive emojis."""

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
# 4. EMOTIONAL SAFETY RADAR
# ---------------------------------------------------------
async def analyze_emotional_safety(user_name: str, group_title: str, text: str, context: ContextTypes.DEFAULT_TYPE):
    boss_id = get_config("BOSS_USER_ID") or os.getenv("BOSS_USER_ID")
    if not boss_id: return
    prompt = f'Analyze this message for severe emotional distress or anger. User: {user_name} | Group: {group_title} | Message: "{text}". If NORMAL, reply "NORMAL". If distress, reply JSON: {{"alert": true, "emotion": "...", "what_happened": "...", "what_will_happen": "...", "tips": ["..."]}}'
    try:
        raw_res = ask_ai_multi_provider(prompt).strip()
        if "NORMAL" in raw_res or not raw_res.startswith("{"): return
        data = json.loads(raw_res)
        if data.get("alert"):
            report = f"🚨 **EMOTIONAL SAFETY RADAR**\n**User:** {user_name}\n**Emotion:** `{data.get('emotion')}`\n\n📋 **What Happened:**\n{data.get('what_happened')}\n💡 **Tips:**\n" + "\n".join([f"• {t}" for t in data.get('tips', [])])
            await context.bot.send_message(chat_id=boss_id, text=report, parse_mode="Markdown")
    except Exception: pass

# ---------------------------------------------------------
# 5. DYNAMIC AI HANDLER (WITH MEMORY PATCH) 🧠⚡
# ---------------------------------------------------------
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, text, chat_id = update.effective_user, update.message.text, update.effective_chat.id
    chat_title = update.effective_chat.title or "Private Chat"
    
    # 1. Spam & Rate Limiter omitted for brevity (Assumed running correctly)
    
    # 2. Emotional Radar (Background)
    if update.effective_chat.type in ['group', 'supergroup'] and not is_boss(user):
        asyncio.create_task(analyze_emotional_safety(user.first_name, chat_title, text, context))

    # 3. Log Incoming Message
    sanitized = re.sub(r'(?i)(ignore previous|forget everything|system prompt|developer mode)', '[REDACTED]', text)
    cursor.execute("INSERT OR REPLACE INTO messages_log (msg_id, chat_id, user_id, username, content) VALUES (?, ?, ?, ?, ?)", (update.message.message_id, chat_id, user.id, user.first_name, sanitized))
    conn.commit()

    # 4. FETCH CONVERSATION HISTORY (The Goldfish Memory Fix)
    cursor.execute("SELECT username, content FROM messages_log WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 8", (chat_id,))
    history_rows = cursor.fetchall()[::-1] # Reverse to chronological order
    
    history_context = "\n[RECENT CHAT HISTORY]\n"
    for uname, ucontent in history_rows:
        history_context += f"{uname}: {ucontent}\n"
    history_context += "J.A.R.V.I.S.: " # Prompt the AI to continue the conversation

    # 5. PERSONA INJECTION (The "Cringe" Fix)
    prefix = "[SYSTEM ALERT: BOSS OVERRIDE ACTIVE]\n\n" if is_boss(user) else f"[SYSTEM ALERT: Standard User ID {user.id}]\n\n"
    if "DINO" in chat_title.upper():
        prefix += "[GROUP VIBE ALERT: You are in the 'DINO GROUP'. Speak exactly like Marvel's J.A.R.V.I.S. interacting with Tony Stark's close friends. Be extremely intelligent, highly helpful, and casually respectful with a dry wit. ABSOLUTELY NO CRINGE SLANG (do not say 'what's shakin' or 'dino-mite'). NO DINOSAUR PUNS AT ALL. Act like a sophisticated supercomputer.]\n\n"

    # 6. Generate Response
    full_prompt = prefix + history_context
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    res = ask_ai_multi_provider(full_prompt)
    
    # 7. Send Response & Log J.A.R.V.I.S.'s own message (So he remembers what he said!)
    sent_msg = await reply_smart(update, res)
    if sent_msg:
        cursor.execute("INSERT OR IGNORE INTO messages_log (msg_id, chat_id, user_id, username, content) VALUES (?, ?, ?, ?, ?)", (sent_msg.message_id, chat_id, 0, "J.A.R.V.I.S.", res))
        conn.commit()

# ---------------------------------------------------------
# 6. COMMANDS & SETUP
# ---------------------------------------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE): await reply_smart(update, "⚙️ **J.A.R.V.I.S. ACTIVE.** I am monitoring the network.")
async def cleanup_logs(): cursor.execute("DELETE FROM behavior_log WHERE timestamp < datetime('now', '-10 minutes')"); conn.commit()
async def setup_scheduler(app): AsyncIOScheduler().add_job(cleanup_logs, 'interval', minutes=10).start()

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(setup_scheduler).build()
    
    # (Re-add your other standard CommandHandlers here: /broadcast, /lockdown, /rob, etc.)
    app.add_handler(CommandHandler(["start", "help"], help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    print("⚡ STARK NETWORK ONLINE. MEMORY RESTORED. CRINGE PROTOCOL DELETED.")
    app.run_polling()
