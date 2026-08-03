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
        print(f"Health-check server listening on port {port} for Render.")
        server.serve_forever()
    except Exception: pass

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

cursor.execute("CREATE TABLE IF NOT EXISTS bot_config (config_key TEXT PRIMARY KEY, config_val TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, actor TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS messages_log (msg_id INTEGER, chat_id INTEGER, user_id INTEGER, username TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(msg_id, chat_id))")
cursor.execute("CREATE TABLE IF NOT EXISTS stark_economy (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0, last_claim TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS behavior_log (user_id INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS spam_patterns (id INTEGER PRIMARY KEY AUTOINCREMENT, pattern TEXT UNIQUE, pattern_type TEXT, hit_count INTEGER DEFAULT 1, false_positive_count INTEGER DEFAULT 0, accuracy REAL DEFAULT 1.0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")

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

# --- AI CORE (CRINGE-FREE PERSONA) ---
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
# 4. EMOTIONAL DISTRESS RADAR
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
            report = f"🚨 **EMOTIONAL SAFETY RADAR**\n**User:** {user_name}\n**Group:** {group_title}\n**Emotion:** `{data.get('emotion')}`\n\n📋 **What Happened:**\n{data.get('what_happened')}\n💡 **Boss Tips:**\n" + "\n".join([f"• {t}" for t in data.get('tips', [])])
            await context.bot.send_message(chat_id=boss_id, text=report, parse_mode="Markdown")
    except Exception: pass

# ---------------------------------------------------------
# 5. LIVE CALL (VOICE/VIDEO CHAT) DETECTORS
# ---------------------------------------------------------
async def vc_started_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.effective_chat.title or ""
    if "DINO" in title.upper(): await reply_smart(update, "🎙️ **VC IS LIVE!** Get in here, everyone! J.A.R.V.I.S. is tuning into the frequencies! ⚡")
    else: await reply_smart(update, "🎙️ **COMMUNICATION CHANNEL OPENED.**\nVoice chat initiated. I am monitoring the network, Sir.")

async def vc_ended_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.effective_chat.title or ""
    duration = getattr(update.message.video_chat_ended, 'duration', 0)
    mins, secs = duration // 60, duration % 60
    if "DINO" in title.upper(): await reply_smart(update, f"🔇 **VC Ended!** We talked for {mins}m {secs}s. My virtual circuits need a rest! 😴")
    else: await reply_smart(update, f"🔇 **COMMUNICATION CHANNEL CLOSED.**\nDuration: {mins} minutes, {secs} seconds.")

async def vc_invited_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.effective_chat.title or ""
    if "DINO" in title.upper(): await reply_smart(update, "📞 **RING RING!** You've been summoned to the VC! Don't keep them waiting! 🏃‍♂️💨")
    else: await reply_smart(update, "📞 **SUMMONS ISSUED.** Participants have been pinged for the voice chat.")

# ---------------------------------------------------------
# 6. COMMANDS (BROADCAST, LOCKDOWN, ECONOMY)
# ---------------------------------------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "⚙️ **J.A.R.V.I.S. SYSTEM MANUAL**\n\n**Recon:** `/members`\n**Economy:** `/daily`, `/credits`, `/rob`, `/leaderboard`"
    if is_boss(update.effective_user): msg += "\n\n👑 **BOSS OVERRIDES:** `/lockdown`, `/broadcast`"
    await reply_smart(update, msg)

@boss_gate(critical=False)
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await reply_smart(update, "Usage: `/broadcast [Group Chat ID] [Your Message]`")
        return
    
    target_chat_id = context.args[0]
    raw_message = " ".join(context.args[1:])
    
    prompt = f"Rewrite this instruction from the Boss into a friendly, slightly funny, and warm announcement for his friends in the DINO GROUP. Keep it brief. Raw instruction: '{raw_message}'"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    ai_announcement = ask_ai_multi_provider(prompt)
    
    try:
        await context.bot.send_message(chat_id=target_chat_id, text=f"📢 **J.A.R.V.I.S. BROADCAST:**\n\n{ai_announcement}", parse_mode="Markdown")
        await reply_smart(update, f"✅ **Message successfully broadcasted!**\n\n*Here is what I sent:*\n{ai_announcement}")
    except Exception as e:
        await reply_smart(update, f"⚠️ Failed to deliver broadcast: `{e}`")

async def group_members_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']: return await reply_smart(update, "Sir, this command must be run inside a group chat.")
    try: await reply_smart(update, f"📊 **GROUP TELEMETRY:** `{chat.title}`\n• Total Registered Entities: `{await chat.get_member_count()}` members.")
    except Exception as e: pass

@boss_gate(critical=True)
async def lockdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.set_chat_permissions(chat_id=update.effective_chat.id, permissions=ChatPermissions(can_send_messages=False))
        await reply_smart(update, "🚨 **PANIC PROTOCOL ACTIVATED.** Group chat locked down.")
    except Exception as e: await reply_smart(update, f"Failed: {e}")

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
    cursor.execute("SELECT credits FROM stark_economy WHERE user_id = ?", (update.effective_user.id,))
    row = cursor.fetchone()
    await reply_smart(update, f"💳 **VAULT:** `{row[0] if row else 0}` Credits")

async def rob_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return await reply_smart(update, "Reply to the user you wish to rob.")
    attacker, target = update.effective_user, update.message.reply_to_message.from_user
    if attacker.id == target.id or is_boss(target): return await reply_smart(update, "🛡️ Invalid target. Robbery aborted.")
    
    a_cred = (cursor.execute("SELECT credits FROM stark_economy WHERE user_id = ?", (attacker.id,)).fetchone() or [0])[0]
    t_cred = (cursor.execute("SELECT credits FROM stark_economy WHERE user_id = ?", (target.id,)).fetchone() or [0])[0]
    
    if a_cred < 100 or t_cred < 100: return await reply_smart(update, "Both users need at least 100 credits for a heist.")
    if random.choice([True, False]):
        stolen = int(t_cred * 0.2)
        cursor.execute("UPDATE stark_economy SET credits = credits + ? WHERE user_id = ?", (stolen, attacker.id))
        cursor.execute("UPDATE stark_economy SET credits = credits - ? WHERE user_id = ?", (stolen, target.id))
        await reply_smart(update, f"🥷 **HEIST SUCCESSFUL!** Stole `{stolen}` credits.")
    else:
        cursor.execute("UPDATE stark_economy SET credits = credits - 200 WHERE user_id = ?", (attacker.id,))
        await reply_smart(update, f"🚨 **HEIST FAILED!** Fined `200` credits.")
    conn.commit()

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT user_id, credits FROM stark_economy ORDER BY credits DESC LIMIT 5")
    msg = "🏆 **ECONOMY LEADERBOARD**\n\n"
    for idx, r in enumerate(cursor.fetchall(), 1): msg += f"{idx}. User `{r[0]}`: {r[1]} Credits\n"
    await reply_smart(update, msg)

# ---------------------------------------------------------
# 7. DYNAMIC AI HANDLER (WITH MEMORY & PERSONA PATCH) 🧠⚡
# ---------------------------------------------------------
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, text, chat_id = update.effective_user, update.message.text, update.effective_chat.id
    chat_title = update.effective_chat.title or "Private Chat"
    
    # 1. Spam & Rate Limiter
    cursor.execute("INSERT INTO behavior_log (user_id) VALUES (?)", (user.id,))
    if (cursor.execute("SELECT COUNT(*) FROM behavior_log WHERE user_id = ? AND timestamp >= datetime('now', '-1 minute')", (user.id,)).fetchone()[0] > 6) and not is_boss(user): return 

    cursor.execute("SELECT pattern FROM spam_patterns WHERE accuracy > 0.5")
    for (pat,) in cursor.fetchall():
        if re.search(pat, text, re.IGNORECASE):
            try:
                await update.message.delete()
                await context.bot.send_message(chat_id, f"🛡️ **THREAT NEUTRALIZED**\nSpam signature detected from {user.first_name}.")
                return 
            except Exception: pass

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
    history_context += "J.A.R.V.I.S.: " 

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
# 8. LAUNCH
# ---------------------------------------------------------
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
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("lockdown", lockdown_command))
    app.add_handler(CommandHandler("members", group_members_command))
    app.add_handler(CommandHandler("daily", claim_daily))
    app.add_handler(CommandHandler("credits", check_credits))
    app.add_handler(CommandHandler("rob", rob_user))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    
    app.add_handler(MessageHandler(filters.StatusUpdate.VIDEO_CHAT_STARTED, vc_started_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.VIDEO_CHAT_ENDED, vc_ended_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.VIDEO_CHAT_PARTICIPANTS_INVITED, vc_invited_handler))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    print("⚡ STARK NETWORK ONLINE. MEMORY RESTORED. FULL ARSENAL DEPLOYED.")
    app.run_polling()
