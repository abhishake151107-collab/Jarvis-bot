import os
import sys
import ssl
import re
import time
import socket
import sqlite3
import logging
import asyncio
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
from collections import defaultdict

import pytz
import httpx
import pdfplumber
from cryptography.fernet import Fernet
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from duckduckgo_search import DDGS
from openai import AsyncOpenAI

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, ChatPermissions
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, Application
)

# ---------------------------------------------------------------------------
# CORE CONFIGURATION & DUMMY SERVER
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO,
    handlers=[logging.FileHandler("jarvis_sys.log"), logging.StreamHandler()]
)
logger = logging.getLogger("jarvis")

BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")).strip()
CREATOR_ID = int(os.environ.get("CREATOR_ID", "0").strip())
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", Fernet.generate_key().decode()).strip()
PORT = int(os.environ.get("PORT", 8080))

class DummyHandler(BaseHTTPRequestHandler):
    def do_HEAD(self): self.send_response(200); self.end_headers()
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"J.A.R.V.I.S. Ultimate Core Active.")

threading.Thread(target=lambda: HTTPServer(('0.0.0.0', PORT), DummyHandler).serve_forever(), daemon=True).start()

cipher_suite = Fernet(ENCRYPTION_KEY.encode())
def encrypt_data(text: str) -> str: return cipher_suite.encrypt(text.encode()).decode()
def decrypt_data(crypto_text: str) -> str:
    try: return cipher_suite.decrypt(crypto_text.encode()).decode()
    except Exception: return "[ENCRYPT ERROR]"

DB_PATH = "jarvis_vault.db"
circuit_breaker = {}
probing_attempts = defaultdict(int)

# ---------------------------------------------------------------------------
# SQLITE VAULT & MEMORY
# ---------------------------------------------------------------------------
def db_init():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY, chat_id INTEGER, user_id INTEGER, role TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, user_id INTEGER, task_crypt TEXT, status TEXT DEFAULT 'pending')")
        conn.execute("CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, category TEXT, note_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, tag TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS roster (chat_id INTEGER, user_id INTEGER, name TEXT, UNIQUE(chat_id, user_id))")
        try: conn.execute("ALTER TABLE expenses ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP")
        except: pass
        conn.commit()

def log_memory(chat_id, user_id, role, text):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO memory (chat_id, user_id, role, content_crypt) VALUES (?, ?, ?, ?)", (chat_id, user_id, role, encrypt_data(text)))
        conn.commit()

def get_chat_history(chat_id, limit=12) -> list:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT role, content_crypt FROM memory WHERE chat_id = ? ORDER BY id DESC LIMIT ?", (chat_id, limit)).fetchall()
    return [{"role": r["role"], "content": decrypt_data(r["content_crypt"])} for r in reversed(rows)]

# ---------------------------------------------------------------------------
# SECURITY CANARY & CASCADE
# ---------------------------------------------------------------------------
async def check_canary(user_id: int, first_name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id != CREATOR_ID:
        probing_attempts[user_id] += 1
        if probing_attempts[user_id] >= 3:
            await context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **Security Alert:** {first_name} (`{user_id}`) is probing restricted modules.", parse_mode="Markdown")
            probing_attempts[user_id] = 0
        return False
    return True

def build_system_prompt(user_id: int, first_name: str) -> str:
    identity_rule = "You are speaking to your creator, Abhishek (DHANUSH V N). Address him as 'Sir'." if user_id == CREATOR_ID else f"You are speaking to {first_name}. If they speak nonsense, use elegant, ruthless sarcasm."
    return f"""You are J.A.R.V.I.S. (Just A Rather Very Intelligent System).
Character: Professional, highly capable, dry British wit.
Rule 1: Be ultra-concise.
Rule 2: {identity_rule}"""

def get_active_providers():
    providers = []
    if os.getenv("GROQ_API_KEY"): providers.append({"name": "Groq", "client": AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.getenv("GROQ_API_KEY")), "model": "llama-3.3-70b-versatile"})
    if os.getenv("CEREBRAS_API_KEY"): providers.append({"name": "Cerebras", "client": AsyncOpenAI(base_url="https://api.cerebras.ai/v1", api_key=os.getenv("CEREBRAS_API_KEY")), "model": "llama3.1-70b"})
    if os.getenv("SAMBANOVA_API_KEY"): providers.append({"name": "SambaNova", "client": AsyncOpenAI(base_url="https://api.sambanova.ai/v1", api_key=os.getenv("SAMBANOVA_API_KEY")), "model": "Meta-Llama-3.3-70B-Instruct"})
    if os.getenv("MISTRAL_API_KEY"): providers.append({"name": "Mistral", "client": AsyncOpenAI(base_url="https://api.mistral.ai/v1", api_key=os.getenv("MISTRAL_API_KEY")), "model": "mistral-small-latest"})
    if os.getenv("OPENROUTER_API_KEY"): providers.append({"name": "OpenRouter", "client": AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_API_KEY")), "model": "deepseek/deepseek-r1:free"})
    if os.getenv("GEMINI_API_KEY"): providers.append({"name": "Gemini", "client": AsyncOpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=os.getenv("GEMINI_API_KEY")), "model": "gemini-1.5-flash"})
    if os.getenv("NVIDIA_API_KEY"): providers.append({"name": "NVIDIA", "client": AsyncOpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_API_KEY")), "model": "meta/llama3-70b-instruct"})
    if os.getenv("BAZAARLINK_API_KEY"): providers.append({"name": "BazaarLink", "client": AsyncOpenAI(base_url="https://bazaarlink.ai/api/v1", api_key=os.getenv("BAZAARLINK_API_KEY")), "model": "auto:free"})
    return providers

async def generate_response(messages: list, system_prompt: str) -> str:
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    current_time = time.time()
    providers = get_active_providers()
    active_providers = [p for p in providers if circuit_breaker.get(p["name"], 0) < current_time]

    if not providers: return "⚠️ No AI API keys detected."
    if not active_providers: return "⚠️ Circuit Breaker active. Nodes cooling down."

    for provider in active_providers:
        try:
            res = await asyncio.wait_for(provider["client"].chat.completions.create(model=provider["model"], messages=full_messages, temperature=0.7), timeout=10.0)
            return res.choices[0].message.content
        except Exception as e:
            circuit_breaker[provider['name']] = current_time + 60 
            logger.warning(f"{provider['name']} tripped: {e}")
            continue
    return "⚠️ Network failure."

# ---------------------------------------------------------------------------
# NEW SENSORY & SECURITY COMMANDS
# ---------------------------------------------------------------------------
async def imagine_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Image Synthesis via Pollinations (No API Key Required)"""
    prompt = " ".join(context.args)
    if not prompt: return await update.message.reply_text("Format: /imagine [prompt]")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
    image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=1024&height=1024&nologo=true"
    await update.message.reply_photo(photo=image_url, caption=f"🎨 Rendered: {prompt}")

async def note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Encrypted Vault for Prompts and Configs"""
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    try:
        tag, content = context.args[0], " ".join(context.args[1:])
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO notes (tag, content_crypt) VALUES (?, ?)", (tag.lower(), encrypt_data(content)))
            conn.commit()
        await update.message.reply_text(f"🔒 Secured in vault under tag: `#{tag}`", parse_mode="Markdown")
    except: await update.message.reply_text("Format: /note [tag] [text]")

async def getnote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    tag = context.args[0].lower() if context.args else ""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT content_crypt FROM notes WHERE tag = ? ORDER BY id DESC", (tag,)).fetchall()
    if rows: await update.message.reply_text(f"📂 **#{tag}:**\n" + "\n---\n".join([decrypt_data(r[0]) for r in rows]), parse_mode="Markdown")
    else: await update.message.reply_text("No records found.")

async def purge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Instant Message Deletion Protocol"""
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    if update.message.reply_to_message:
        try: 
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id)
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
        except: await update.message.reply_text("Requires admin deletion rights.")

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Whisper API Voice Recognition"""
    if not os.getenv("GROQ_API_KEY"): return await update.message.reply_text("Audio core offline (Missing Groq Key).")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
    
    file = await context.bot.get_file(update.message.voice.file_id)
    os.makedirs("temp", exist_ok=True)
    file_path = f"temp/{update.message.voice.file_id}.ogg"
    await file.download_to_drive(file_path)
    
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        with open(file_path, "rb") as audio:
            transcription = await client.audio.transcriptions.create(file=("audio.ogg", audio.read()), model="whisper-large-v3")
        user_text = transcription.text
        
        log_memory(update.effective_chat.id, update.effective_user.id, "user", f"[Voice] {user_text}")
        prompt = build_system_prompt(update.effective_user.id, update.effective_user.first_name)
        history = get_chat_history(update.effective_chat.id)
        response = await generate_response(history + [{"role": "user", "content": user_text}], prompt)
        
        log_memory(update.effective_chat.id, update.effective_user.id, "assistant", response)
        await update.message.reply_text(f"🎤 *(Transcribed)*: {user_text}\n\n{response}", parse_mode="Markdown")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

# ---------------------------------------------------------------------------
# INTELLIGENT MESSAGE DISPATCHER & LINK SCANNER
# ---------------------------------------------------------------------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
        
    user, chat, user_text = update.effective_user, update.effective_chat, update.message.text
    
    # Roster Update & Background Logging
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO roster (chat_id, user_id, name) VALUES (?, ?, ?) ON CONFLICT(chat_id, user_id) DO UPDATE SET name = ?", (chat.id, user.id, user.first_name, user.first_name))
        conn.commit()
    log_memory(chat.id, user.id, "user", f"{user.first_name}: {user_text}")

    # Automated Link Scanning
    urls = re.findall(r'(https?://[^\s]+)', user_text)
    if urls and chat.type != "private":
        for url in urls:
            if "http://" in url: # Flag unencrypted traffic
                await update.message.reply_text(f"⚠️ **Security Warning:** Unencrypted HTTP protocol detected in link shared by {user.first_name}.", parse_mode="Markdown")

    is_private = chat.type == "private"
    is_reply_to_bot = bool(update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id)
    is_name_called = bool(re.search(r'\b(jarvis|edwin)\b', user_text, re.IGNORECASE))
    bot_username = (await context.bot.get_me()).username
    is_mentioned = f"@{bot_username}".lower() in user_text.lower() if bot_username else False

    if not is_private and not (is_reply_to_bot or is_name_called or is_mentioned): return

    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    ai_response = await generate_response(get_chat_history(chat.id), build_system_prompt(user.id, user.first_name))
    log_memory(chat.id, user.id, "assistant", ai_response)
    await update.message.reply_text(ai_response)

# ---------------------------------------------------------------------------
# DASHBOARD, TASKS & BASE COMMANDS
# ---------------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return await update.message.reply_text("Monitoring active.")
    kb = [[InlineKeyboardButton("🎯 Active Objectives", callback_data="sys_planner")], [InlineKeyboardButton("🛡️ Security Audit", callback_data="sys_sec")]]
    await update.message.reply_text("🤖 **STARK ADVANCED OS — ULTIMATE CORE**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def announce_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    await context.bot.send_message(chat_id=context.args[0], text=" ".join(context.args[1:]))

async def groupinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = await context.bot.get_chat_member_count(update.effective_chat.id)
    await update.message.reply_text(f"📊 **Chat ID:** `{update.effective_chat.id}`\n• **Members:** {count}", parse_mode="Markdown")

async def scheduled_briefing(context: ContextTypes.DEFAULT_TYPE):
    if not CREATOR_ID: return
    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    expense_summary = ""
    with sqlite3.connect(DB_PATH) as conn:
        if now.weekday() == 0:
            total = conn.execute("SELECT SUM(amount) FROM expenses WHERE timestamp >= datetime('now', '-7 days')").fetchone()[0] or 0.0
            expense_summary = f"\n\n💰 **Weekly Expense:** ₹{total:.2f}"
        
        # Group Health Digest (Friday Report)
        if now.weekday() == 4:
            msgs = conn.execute("SELECT COUNT(*) FROM memory WHERE timestamp >= datetime('now', '-7 days') AND role='user'").fetchone()[0]
            expense_summary += f"\n\n📊 **Group Telemetry:** {msgs} messages logged this week."

    response = await generate_response([{"role": "user", "content": "Morning briefing."}], build_system_prompt(CREATOR_ID, "Abhishek"))
    await context.bot.send_message(chat_id=CREATOR_ID, text=f"🌅 Briefing:\n{response}{expense_summary}", parse_mode="Markdown")

async def post_init(app: Application):
    if CREATOR_ID: await app.bot.send_message(chat_id=CREATOR_ID, text=f"🤖 **Ultimate Core Online**\n• Cascade: {len(get_active_providers())} Nodes\n• Audio/Vision: Engaged\n• Vault: Encrypted", parse_mode="Markdown")

def main():
    db_init()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Kolkata"))
    scheduler.add_job(scheduled_briefing, 'cron', hour=8, minute=0, args=[app])
    scheduler.start()

    cmds = [
        ("start", start_cmd), ("announce", announce_cmd), ("groupinfo", groupinfo_cmd),
        ("imagine", imagine_cmd), ("note", note_cmd), ("getnote", getnote_cmd), ("purge", purge_cmd)
    ]
    for cmd, func in cmds: app.add_handler(CommandHandler(cmd, func))
    
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Ultimate Core Online.")
    app.run_polling()

if __name__ == "__main__":
    main()
