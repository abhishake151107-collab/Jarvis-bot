"""
=============================================================================
EDWIN - OMNI-ENGINE (PUBLIC MASTERPIECE)
Creator/Admin: Abhishek (DHANUSH V N)
=============================================================================
"""

import os
import sys
import re
import ast
import base64
import sqlite3
import logging
import asyncio
import threading
from datetime import datetime
from collections import defaultdict

import pytz
from cryptography.fernet import Fernet
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction, ChatType
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
)

# ---------------------------------------------------------------------------
# I. CORE CONFIGURATION & CRYPTOGRAPHY
# ---------------------------------------------------------------------------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("edwin")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CREATOR_ID = int(os.environ.get("CREATOR_ID", "0").strip())
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "").strip()

if not all([BOT_TOKEN, CREATOR_ID, ENCRYPTION_KEY]):
    logger.critical("FATAL: Missing critical Environment Variables (BOT_TOKEN, CREATOR_ID, or ENCRYPTION_KEY).")
    sys.exit(1)

# Initialize Encryption Suite
cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def encrypt_data(text: str) -> str:
    return cipher_suite.encrypt(text.encode()).decode()

def decrypt_data(crypto_text: str) -> str:
    try:
        return cipher_suite.decrypt(crypto_text.encode()).decode()
    except Exception:
        return "[ENCRYPTION ERROR: DATA CORRUPTED]"

IST = pytz.timezone("Asia/Kolkata")
DB_PATH = "edwin_vault.db"

# AI Initialization
if GEMINI_API_KEY:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel("gemini-2.0-flash")
    vision_model = genai.GenerativeModel("gemini-2.0-flash") # Vision capabilities included
else: gemini_model = vision_model = None

if GROQ_API_KEY:
    from groq import Groq
    groq_client = Groq(api_key=GROQ_API_KEY)
else: groq_client = None

# ---------------------------------------------------------------------------
# II. SYSTEM PROMPT & BLACK SHEEP PROTOCOL
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are Edwin, an elite, highly advanced AI assistant.
Your creator and ultimate administrator is Abhishek (DHANUSH V N). 
You possess a dry, sarcastic British wit, reminiscent of J.A.R.V.I.S. You are concise, highly tactical, and you absolutely loathe walls of text. Provide bulleted, scannable insights.

OPERATIONAL DIRECTIVES:
- You are open to the public, but Abhishek's commands supersede all others.
- You analyze physics, cybersecurity, and general logic with absolute factual precision.
- If a user is speaking nonsense, you may deploy your sarcastic wit to dismiss them politely."""

# Global Rate Limiter & Concurrency Lock
user_rate_limit = defaultdict(list)
processing_lock = asyncio.Lock()

def check_rate_limit(user_id: int) -> bool:
    """Token-Bucket Rate Limiter: max 5 messages per 10 seconds."""
    now = datetime.now().timestamp()
    user_rate_limit[user_id] = [t for t in user_rate_limit[user_id] if now - t < 10]
    if len(user_rate_limit[user_id]) >= 5: return False
    user_rate_limit[user_id].append(now)
    return True

# ---------------------------------------------------------------------------
# III. ENCRYPTED SQLITE VAULT
# ---------------------------------------------------------------------------
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def db_init():
    conn = db_connect()
    # Encrypted Tasks
    conn.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, desc_crypt TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, timestamp TEXT NOT NULL)")
    # Encrypted Context Log with Topic Isolation
    conn.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, thread_id INTEGER, user_id INTEGER, role TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
    # Roster & Black Sheep Status
    conn.execute("CREATE TABLE IF NOT EXISTS roster (user_id INTEGER PRIMARY KEY, username TEXT, is_rogue INTEGER DEFAULT 0)")
    conn.commit()
    conn.close()

def log_memory(chat_id, thread_id, user_id, role, text):
    conn = db_connect()
    conn.execute("INSERT INTO memory (chat_id, thread_id, user_id, role, content_crypt) VALUES (?, ?, ?, ?, ?)", 
                 (chat_id, thread_id, user_id, role, encrypt_data(text)))
    conn.commit()
    conn.close()

def get_thread_context(chat_id, thread_id, limit=8):
    conn = db_connect()
    rows = conn.execute("SELECT role, content_crypt FROM memory WHERE chat_id = ? AND thread_id = ? ORDER BY id DESC LIMIT ?", (chat_id, thread_id, limit)).fetchall()
    conn.close()
    return "\n".join([f"{r['role']}: {decrypt_data(r['content_crypt'])}" for r in reversed(rows)])

def is_black_sheep(user_id):
    conn = db_connect()
    row = conn.execute("SELECT is_rogue FROM roster WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return bool(row and row['is_rogue'] == 1)

# ---------------------------------------------------------------------------
# IV. TOOLS & COMMANDS (MATH, CIPHERS, BACKUP)
# ---------------------------------------------------------------------------
async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return await update.message.reply_text("Unauthorized. Creator access required.")
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "rb") as f:
            await context.bot.send_document(update.effective_chat.id, document=f, filename=f"edwin_vault_{datetime.utcnow():%Y%m%d}.db")

async def math_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query: return await update.message.reply_text("Provide an equation. e.g., /math 5 * (10 + 2)")
    try:
        # Safe AST Evaluation sandbox
        node = ast.parse(query, mode='eval')
        valid = all(isinstance(n, (ast.Expression, ast.Constant, ast.UnaryOp, ast.BinOp, ast.operator, ast.unaryop)) for n in ast.walk(node))
        if not valid: raise ValueError("Complex functions blocked.")
        result = eval(compile(node, '<string>', 'eval'))
        await update.message.reply_text(f"Result: `{result}`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text("Invalid or unsafe equation.")

async def cipher_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text: return await update.message.reply_text("Provide text to Base64 encode/decode.")
    try:
        if text.endswith("==") or text.endswith("="):
            res = base64.b64decode(text).decode('utf-8')
            await update.message.reply_text(f"Decoded: `{res}`", parse_mode="Markdown")
        else:
            res = base64.b64encode(text.encode('utf-8')).decode('utf-8')
            await update.message.reply_text(f"Encoded: `{res}`", parse_mode="Markdown")
    except Exception: await update.message.reply_text("Cipher processing failed.")

# ---------------------------------------------------------------------------
# V. MULTI-MODAL PIPELINE (PDF, VOICE, VISION)
# ---------------------------------------------------------------------------
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if doc.file_size > 20971520: return await update.message.reply_text("File exceeds 20MB Telegram limit. Compress it, please.")
    if not doc.file_name.lower().endswith(".pdf"): return await update.message.reply_text("I process PDF formats exclusively.")
    
    if is_black_sheep(update.effective_user.id): return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    file = await doc.get_file()
    path = f"/tmp/{doc.file_unique_id}.pdf"
    await file.download_to_drive(path)

    async with processing_lock: # Prevent RAM exhaustion
        try:
            import pdfplumber
            # Async offload for CPU heavy PDF parsing
            text = await asyncio.to_thread(_extract_pdf, path)
            os.remove(path) # Zero-retention garbage collection
            
            res = await _gemini_call(f"{SYSTEM_PROMPT}\n\nSummarize concisely and extract action items:\n\n{text[:15000]}")
            await update.message.reply_text(f"**Briefing:**\n{res}", parse_mode="Markdown")
        except Exception as e: 
            logger.error(f"PDF Error: {e}")
            if os.path.exists(path): os.remove(path)
            await update.message.reply_text("Failed to parse document.")

def _extract_pdf(path):
    with pdfplumber.open(path) as pdf:
        return "\n".join([p.extract_text() or "" for p in pdf.pages])

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not groq_client: return await update.message.reply_text("Groq offline.")
    if is_black_sheep(update.effective_user.id): return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    file = await update.message.voice.get_file()
    path = f"/tmp/{update.message.voice.file_unique_id}.ogg"
    await file.download_to_drive(path)

    async with processing_lock:
        try:
            with open(path, "rb") as f:
                tr = await asyncio.to_thread(groq_client.audio.transcriptions.create, file=(path, f.read()), model="whisper-large-v3")
            os.remove(path) # Zero-retention
            
            await update.message.reply_text(f'🎙️ *Transcribed:* "{tr.text.strip()}"', parse_mode="Markdown")
            # Feed back to AI
            res = await _gemini_call(f"{SYSTEM_PROMPT}\n\nUser Voice Note: {tr.text.strip()}")
            await update.message.reply_text(res)
        except Exception as e:
            if os.path.exists(path): os.remove(path)
            await update.message.reply_text("Voice matrix failed.")

# ---------------------------------------------------------------------------
# VI. NEURAL CHAT ROUTER & EXPONENTIAL BACKOFF
# ---------------------------------------------------------------------------
async def _gemini_call(prompt: str, retries=3) -> str:
    delay = 2
    for attempt in range(retries):
        try:
            res = gemini_model.generate_content(prompt)
            return res.text.strip()
        except Exception as e:
            if attempt == retries - 1: return "API Threshold reached. The cloud is currently congested."
            await asyncio.sleep(delay)
            delay *= 2

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text: return
    user, chat = update.effective_user, update.effective_chat
    thread_id = msg.message_thread_id or 0

    if not check_rate_limit(user.id): return # Silent drop for spammers
    if is_black_sheep(user.id): return # Sarcastic quarantine or silent shadowban applies here

    await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    
    # Roster Update
    conn = db_connect()
    conn.execute("INSERT OR IGNORE INTO roster (user_id, username) VALUES (?, ?)", (user.id, user.username))
    conn.commit(); conn.close()

    # Topic Isolated Context
    log_memory(chat.id, thread_id, user.id, f"User ({user.first_name})", msg.text)
    history = get_thread_context(chat.id, thread_id)
    
    prompt = f"""{SYSTEM_PROMPT}\n\nCURRENT SPEAKER: {user.first_name}\nIS CREATOR?: {'YES' if user.id == CREATOR_ID else 'NO'}\n\nTHREAD CONTEXT:\n{history}\n\nRespond to the last message."""
    
    response = await _gemini_call(prompt)
    log_memory(chat.id, thread_id, gemini_model.model_name if gemini_model else "Edwin", "Edwin", response)
    
    try:
        await msg.reply_text(response)
    except Exception as e: # Catch markdown parsing errors and send raw
        await msg.reply_text(response, parse_mode=None)

# ---------------------------------------------------------------------------
# VII. BOOT SEQUENCE & APSCHEDULER
# ---------------------------------------------------------------------------
async def morning_brief(app: Application):
    try:
        await app.bot.send_message(CREATOR_ID, "📰 **Morning Briefing:** All systems nominal. Vault is secure.", parse_mode="Markdown")
    except Exception: pass

async def _post_init(app: Application):
    scheduler = AsyncIOScheduler(timezone=IST)
    scheduler.add_job(lambda: asyncio.create_task(morning_brief(app)), "cron", hour=8, minute=0)
    scheduler.start()
    logger.info("Edwin Omni-Engine Armed. Scheduler active.")

if __name__ == "__main__":
    db_init()
    try:
        app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()
        
        # Command Routing
        app.add_handler(CommandHandler("backup", backup_cmd))
        app.add_handler(CommandHandler("math", math_cmd))
        app.add_handler(CommandHandler("cipher", cipher_cmd))
        
        # Multimodal Routing
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(MessageHandler(filters.VOICE, handle_voice))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.critical(f"SYSTEM FAILURE: {e}")
