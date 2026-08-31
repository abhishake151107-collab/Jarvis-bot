import os
import sys
import re
import ast
import base64
import sqlite3
import logging
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
from collections import defaultdict

import pytz
import httpx
from duckduckgo_search import DDGS
from cryptography.fernet import Fernet
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)
import google.generativeai as genai
from groq import Groq

# ---------------------------------------------------------------------------
# CORE CONFIGURATION & RENDER KEEP-ALIVE
# ---------------------------------------------------------------------------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("edwin")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CREATOR_ID = int(os.environ.get("CREATOR_ID", "0").strip())
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "").strip()
PORT = int(os.environ.get("PORT", 8080)) # Render requires port binding

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Edwin is online and monitoring.")

def keep_alive():
    HTTPServer(('0.0.0.0', PORT), DummyHandler).serve_forever()

threading.Thread(target=keep_alive, daemon=True).start()

if not all([BOT_TOKEN, CREATOR_ID, ENCRYPTION_KEY, GEMINI_API_KEY]):
    logger.critical("FATAL: Missing critical Environment Variables.")
    sys.exit(1)

# Cryptography & AI Init
cipher_suite = Fernet(ENCRYPTION_KEY.encode())
def encrypt_data(text: str) -> str: return cipher_suite.encrypt(text.encode()).decode()
def decrypt_data(crypto_text: str) -> str:
    try: return cipher_suite.decrypt(crypto_text.encode()).decode()
    except Exception: return "[ENCRYPTION ERROR]"

IST = pytz.timezone("Asia/Kolkata")
DB_PATH = "edwin_vault.db"

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.0-flash")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

SYSTEM_PROMPT = """You are Edwin, an elite AI assistant. Creator: Abhishek (DHANUSH V N).
Character: JARVIS-style—dry, witty, understated. Never gush or act overly warm.
Rule 1: Answer directly. No filler, no "As an AI".
Rule 2: Max one dry aside/quip per reply. Humor targets the situation, not the user.
Rule 3: Use concise bullet points by default."""

user_rate_limit = defaultdict(list)
processing_lock = asyncio.Lock()

def check_rate_limit(user_id: int) -> bool:
    now = datetime.now().timestamp()
    user_rate_limit[user_id] = [t for t in user_rate_limit[user_id] if now - t < 10]
    if len(user_rate_limit[user_id]) >= 5: return False
    user_rate_limit[user_id].append(now)
    return True

# ---------------------------------------------------------------------------
# SQLITE VAULT
# ---------------------------------------------------------------------------
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def db_init():
    conn = db_connect()
    conn.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, thread_id INTEGER, user_id INTEGER, role TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
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

# ---------------------------------------------------------------------------
# COMMANDS & TOOLS
# ---------------------------------------------------------------------------
async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "rb") as f:
            await context.bot.send_document(update.effective_chat.id, document=f, filename=f"edwin_vault_{datetime.utcnow():%Y%m%d}.db")

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """New Feature: Fast DuckDuckGo Web Search"""
    query = " ".join(context.args)
    if not query: return await update.message.reply_text("Provide a search query. e.g., `/search Latest CVEs`", parse_mode="Markdown")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        results = await asyncio.to_thread(lambda: DDGS().text(query, max_results=3))
        if not results: return await update.message.reply_text("No data found on the public web.")
        
        context_str = "\n".join([f"- {r['title']}: {r['body']} ({r['href']})" for r in results])
        res = await asyncio.to_thread(gemini_model.generate_content, f"{SYSTEM_PROMPT}\n\nSummarize these live search results for the user's query '{query}':\n{context_str}")
        await update.message.reply_text(res.text)
    except Exception as e:
        await update.message.reply_text("Uplink to search relay failed.")

async def math_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query: return await update.message.reply_text("Provide an equation.")
    try:
        node = ast.parse(query, mode='eval')
        valid = all(isinstance(n, (ast.Expression, ast.Constant, ast.UnaryOp, ast.BinOp, ast.operator, ast.unaryop)) for n in ast.walk(node))
        if not valid: raise ValueError("Complex functions blocked.")
        await update.message.reply_text(f"Result: `{eval(compile(node, '<string>', 'eval'))}`", parse_mode="Markdown")
    except Exception: await update.message.reply_text("Invalid equation.")

# ---------------------------------------------------------------------------
# MULTI-MODAL PIPELINE
# ---------------------------------------------------------------------------
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if doc.file_size > 20971520: return await update.message.reply_text("File exceeds 20MB limit.")
    if not doc.file_name.lower().endswith(".pdf"): return await update.message.reply_text("I process PDF formats exclusively.")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    file = await doc.get_file()
    path = f"/tmp/{doc.file_unique_id}.pdf"
    await file.download_to_drive(path)

    async with processing_lock:
        try:
            import pdfplumber
            text = await asyncio.to_thread(_extract_pdf, path)
            os.remove(path)
            res = await asyncio.to_thread(gemini_model.generate_content, f"{SYSTEM_PROMPT}\n\nExtract action items from this document:\n\n{text[:15000]}")
            await update.message.reply_text(f"**Briefing:**\n{res.text}")
        except Exception as e: 
            if os.path.exists(path): os.remove(path)
            await update.message.reply_text("Failed to parse document.")

def _extract_pdf(path):
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return "\n".join([p.extract_text() or "" for p in pdf.pages])

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not groq_client: return await update.message.reply_text("Groq offline.")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    file = await update.message.voice.get_file()
    path = f"/tmp/{update.message.voice.file_unique_id}.ogg"
    await file.download_to_drive(path)

    async with processing_lock:
        try:
            with open(path, "rb") as f:
                tr = await asyncio.to_thread(groq_client.audio.transcriptions.create, file=(path, f.read()), model="whisper-large-v3")
            os.remove(path)
            await update.message.reply_text(f'🎙️ *Transcribed:* "{tr.text.strip()}"', parse_mode="Markdown")
            res = await asyncio.to_thread(gemini_model.generate_content, f"{SYSTEM_PROMPT}\n\nUser Voice Note: {tr.text.strip()}")
            await update.message.reply_text(res.text)
        except Exception:
            if os.path.exists(path): os.remove(path)
            await update.message.reply_text("Voice matrix failed.")

# ---------------------------------------------------------------------------
# NEURAL CHAT & URL EXTRACTION
# ---------------------------------------------------------------------------
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text: return
    user, chat = update.effective_user, update.effective_chat
    thread_id = msg.message_thread_id or 0

    if not check_rate_limit(user.id): return 
    await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    
    text = msg.text
    
    # New Feature: URL Anticipatory Routing
    url_pattern = re.compile(r'(https?://[^\s]+)')
    urls = url_pattern.findall(text)
    if urls:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"https://r.jina.ai/{urls[0]}", timeout=10.0)
                if resp.status_code == 200:
                    text = f"User pasted a link. Content:\n{resp.text[:8000]}\n\nOriginal prompt: {text}"
        except Exception: pass

    log_memory(chat.id, thread_id, user.id, f"User ({user.first_name})", text)
    history = get_thread_context(chat.id, thread_id)
    
    prompt = f"""{SYSTEM_PROMPT}\n\nSPEAKER: {user.first_name}\nCONTEXT:\n{history}\n\nRespond:"""
    
    try:
        res = await asyncio.to_thread(gemini_model.generate_content, prompt)
        log_memory(chat.id, thread_id, user.id, "Edwin", res.text.strip())
        await msg.reply_text(res.text)
    except Exception:
        await msg.reply_text("API Threshold reached. The cloud is congested.")

# ---------------------------------------------------------------------------
# BOOT SEQUENCE
# ---------------------------------------------------------------------------
async def morning_brief(app: Application):
    try:
        await app.bot.send_message(CREATOR_ID, "📰 **Morning Briefing:** All systems nominal. Sending automated daily DB backup...", parse_mode="Markdown")
        if os.path.exists(DB_PATH):
            with open(DB_PATH, "rb") as f:
                await app.bot.send_document(CREATOR_ID, document=f, filename=f"edwin_vault_{datetime.utcnow():%Y%m%d}.db")
    except Exception: pass

async def _post_init(app: Application):
    scheduler = AsyncIOScheduler(timezone=IST)
    scheduler.add_job(lambda: asyncio.create_task(morning_brief(app)), "cron", hour=8, minute=0)
    scheduler.start()
    logger.info("Edwin Omni-Engine Armed.")

if __name__ == "__main__":
    db_init()
    try:
        app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()
        app.add_handler(CommandHandler("backup", backup_cmd))
        app.add_handler(CommandHandler("math", math_cmd))
        app.add_handler(CommandHandler("search", search_cmd))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(MessageHandler(filters.VOICE, handle_voice))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.critical(f"SYSTEM FAILURE: {e}")
