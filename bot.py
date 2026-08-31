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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
)
import google.generativeai as genai
from groq import Groq

# ---------------------------------------------------------------------------
# CORE CONFIGURATION & API KEYS
# ---------------------------------------------------------------------------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("jarvis")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CREATOR_ID = int(os.environ.get("CREATOR_ID", "0").strip())
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "").strip()
PORT = int(os.environ.get("PORT", 8080))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"J.A.R.V.I.S. Omni-Engine is online.")

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
DB_PATH = "jarvis_vault.db"

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-3.6-flash")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

SYSTEM_PROMPT = """You are J.A.R.V.I.S., an elite AI assistant. Your creator and administrator is Abhishek (DHANUSH V N).
Character: Strictly professional, highly capable, and clinically dry. You possess a sharp, understated British wit.
Rule 1: Be ultra-concise. Speak in short, natural sentences. No filler, no AI disclaimers.
Rule 2: You MUST address Abhishek exclusively as 'Sir'. Never use his first name. 
Rule 3: When speaking to anyone else, you MUST address them politely by their provided first name.
Rule 4: Use a maximum of ONE tasteful emoji per message (e.g., 🛡️, 🫡, ⚡).
Rule 5: If an outsider speaks nonsense, dismiss them with elegant, ruthless sarcasm. Otherwise, stay brief and helpful."""

user_rate_limit = defaultdict(list)
processing_lock = asyncio.Lock()

def check_rate_limit(user_id: int) -> bool:
    now = datetime.now().timestamp()
    user_rate_limit[user_id] = [t for t in user_rate_limit[user_id] if now - t < 10]
    if len(user_rate_limit[user_id]) >= 5: return False
    user_rate_limit[user_id].append(now)
    return True

# ---------------------------------------------------------------------------
# SQLITE VAULT & TASK MANAGER
# ---------------------------------------------------------------------------
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def db_init():
    conn = db_connect()
    conn.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, thread_id INTEGER, user_id INTEGER, role TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, task_crypt TEXT, status TEXT DEFAULT 'pending', timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
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
# STARK ADVANCED OS TERMINAL & COMMANDS
# ---------------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates the massive Stark OS Dashboard"""
    user = update.effective_user
    chat_type = "Private DM" if update.effective_chat.type == "private" else update.effective_chat.title
    greeting_name = "Sir" if user.id == CREATOR_ID else user.first_name

    text = f"🤖 **STARK ADVANCED OS — J.A.R.V.I.S. CORE** ✨\n" \
           f"Welcome **{greeting_name}!** Active Core: **J.A.R.V.I.S.**\n" \
           f"Location: {chat_type}\n\n" \
           f"Use buttons below to explore sub-systems:"

    keyboard = [
        [InlineKeyboardButton("⚡ Launch Stark HUD WebApp", web_app=WebAppInfo(url="https://codepen.io/pen/"))],
        [InlineKeyboardButton("🏡 Smart Home", callback_data="sys_smarthome"),
         InlineKeyboardButton("🛠️ CAD Engine", callback_data="sys_cad"),
         InlineKeyboardButton("🚀 Autopilot", callback_data="sys_auto")],
        [InlineKeyboardButton("🎯 AI Planner", callback_data="sys_planner"),
         InlineKeyboardButton("🚨 Lockdown", callback_data="sys_lockdown"),
         InlineKeyboardButton("📁 Audit Log", callback_data="sys_audit")],
        [InlineKeyboardButton("💰 Expenses", callback_data="sys_expense"),
         InlineKeyboardButton("📚 Study Plan", callback_data="sys_study"),
         InlineKeyboardButton("💻 Code Dev", callback_data="sys_code")],
        [InlineKeyboardButton("🌐 Network Recon", callback_data="sys_recon"),
         InlineKeyboardButton("🎙️ Voice Matrix", callback_data="sys_voice"),
         InlineKeyboardButton("👁️ Vision Scan", callback_data="sys_vision")],
        [InlineKeyboardButton("👑 Claim Boss", callback_data="sys_boss"),
         InlineKeyboardButton("📢 Announce", callback_data="sys_announce"),
         InlineKeyboardButton("⭐ Karma", callback_data="sys_karma")],
        [InlineKeyboardButton("👥 Group Control", callback_data="sys_group"),
         InlineKeyboardButton("🛡️ Security", callback_data="sys_sec"),
         InlineKeyboardButton("📚 2nd PU Exam", callback_data="sys_exam")]
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def sys_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles responses for the Stark Dashboard buttons"""
    query = update.callback_query
    user = query.from_user
    action = query.data.split("_")[1]
    
    is_boss = user.id == CREATOR_ID
    title = "Sir" if is_boss else user.first_name
    
    responses = {
        "smarthome": f"Smart Home IoT nodes are currently routing, {title}.",
        "cad": f"CAD Engine requires terminal authorization, {title}.",
        "auto": f"Autopilot engaged. Trajectory locked, {title}.",
        "planner": f"Send /task to log a new objective, {title}.",
        "lockdown": f"Initiating protocol 8675. Facility lockdown simulated, {title}.",
        "audit": f"Audit logs are encrypted in the local SQLite vault, {title}.",
        "expense": f"Expense tracking module standby, {title}.",
        "study": f"Study Plan initialized. Focus required, {title}.",
        "code": f"Development environment ready. Awaiting your syntax, {title}.",
        "recon": f"Network reconnaissance tools are active, {title}.",
        "voice": f"Awaiting audio input. Please send a Voice Note, {title}.",
        "vision": f"Optical sensors ready. Please upload an image, {title}.",
        "boss": "You are already recognized as the Creator, Sir." if is_boss else "I already serve Abhishek. Identity lock is permanent.",
        "announce": f"Broadcast module requires elevated parameters, {title}.",
        "karma": f"Karma matrix calculated. You are in good standing, {title}.",
        "group": f"Group moderation is active in background channels, {title}.",
        "sec": f"Firewalls nominal. End-to-end encryption intact, {title}.",
        "exam": f"2nd PU Exam archives accessed. Best of luck, {title}."
    }
    
    await query.answer(responses.get(action, f"System module unavailable, {title}."), show_alert=True)

# ---------------------------------------------------------------------------
# COMMANDS & INTERACTIVE TOOLS
# ---------------------------------------------------------------------------
async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "rb") as f:
            await context.bot.send_document(update.effective_chat.id, document=f, filename=f"jarvis_vault_{datetime.utcnow():%Y%m%d}.db")

async def task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    task_text = " ".join(context.args)
    if not task_text: return await update.message.reply_text("Provide a task description.", parse_mode="Markdown")
    
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (user_id, task_crypt) VALUES (?, ?)", (CREATOR_ID, encrypt_data(task_text)))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Mark Done", callback_data=f"done_{task_id}"),
        InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{task_id}")
    ]])
    await update.message.reply_text(f"📋 **Task Logged:**\n{task_text}", reply_markup=keyboard, parse_mode="Markdown")

async def task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != CREATOR_ID: return await query.answer("Access Denied.", show_alert=True)
    
    action, task_id = query.data.split("_")
    conn = db_connect()
    if action == "done":
        conn.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))
        await query.edit_message_text(f"✅ ~~{query.message.text.replace('📋 Task Logged:', '').strip()}~~", parse_mode="Markdown")
    elif action == "del":
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await query.edit_message_text("🗑️ *Task purged from memory.*", parse_mode="Markdown")
    conn.commit()
    conn.close()
    await query.answer()

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query: return await update.message.reply_text("Provide a search query.")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        results = await asyncio.to_thread(lambda: DDGS().text(query, max_results=3))
        if not results: return await update.message.reply_text("No data found on the public web.")
        context_str = "\n".join([f"- {r['title']}: {r['body']} ({r['href']})" for r in results])
        res = await asyncio.to_thread(gemini_model.generate_content, f"{SYSTEM_PROMPT}\n\nSummarize these live search results for '{query}':\n{context_str}")
        await update.message.reply_text(res.text)
    except Exception as e:
        await update.message.reply_text(f"Search relay failed: {e}")

async def math_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query: return await update.message.reply_text("Provide an equation.")
    try:
        node = ast.parse(query, mode='eval')
        valid = all(isinstance(n, (ast.Expression, ast.Constant, ast.UnaryOp, ast.BinOp, ast.operator, ast.unaryop)) for n in ast.walk(node))
        if not valid: raise ValueError()
        await update.message.reply_text(f"Result: `{eval(compile(node, '<string>', 'eval'))}`", parse_mode="Markdown")
    except Exception: await update.message.reply_text("Invalid equation.")

# ---------------------------------------------------------------------------
# MULTI-MODAL PIPELINE
# ---------------------------------------------------------------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, chat = update.effective_user, update.effective_chat
    if not check_rate_limit(user.id): return
    
    await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    photo_file = await update.message.photo[-1].get_file()
    path = f"/tmp/{photo_file.file_unique_id}.jpg"
    await photo_file.download_to_drive(path)

    async with processing_lock:
        try:
            with open(path, "rb") as f: image_bytes = f.read()
            os.remove(path)
            
            image_parts = [{"mime_type": "image/jpeg", "data": image_bytes}]
            prompt_text = update.message.caption if update.message.caption else "Analyze this image and describe its contents concisely."
            
            res = await asyncio.to_thread(gemini_model.generate_content, [f"{SYSTEM_PROMPT}\n\nUser Request: {prompt_text}", image_parts[0]])
            await update.message.reply_text(res.text)
        except Exception as e:
            if os.path.exists(path): os.remove(path)
            await update.message.reply_text(f"Vision matrix failed: {e}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
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
            await update.message.reply_text(res.text)
        except Exception as e: 
            if os.path.exists(path): os.remove(path)
            await update.message.reply_text(f"Document parsing failed.")

def _extract_pdf(path):
    import pdfplumber
    with pdfplumber.open(path) as pdf: return "\n".join([p.extract_text() or "" for p in pdf.pages])

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not groq_client: return
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
        except Exception as e:
            if os.path.exists(path): os.remove(path)
            await update.message.reply_text("Voice matrix failed.")

# ---------------------------------------------------------------------------
# NEURAL CHAT
# ---------------------------------------------------------------------------
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text: return
    user, chat = update.effective_user, update.effective_chat
    thread_id = msg.message_thread_id or 0
    text = msg.text

    if chat.type in ['group', 'supergroup']:
        is_reply = msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id
        bot_username = context.bot.username.lower() if context.bot.username else ""
        is_mentioned = "jarvis" in text.lower() or (bot_username and bot_username in text.lower())
        if not (is_reply or is_mentioned): return

    if not check_rate_limit(user.id): return 
    await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    
    url_pattern = re.compile(r'(https?://[^\s]+)')
    urls = url_pattern.findall(text)
    if urls:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"https://r.jina.ai/{urls[0]}", timeout=10.0)
                if resp.status_code == 200: text = f"User pasted a link. Content:\n{resp.text[:8000]}\n\nOriginal prompt: {text}"
        except Exception: pass

    log_memory(chat.id, thread_id, user.id, f"User ({user.first_name})", text)
    history = get_thread_context(chat.id, thread_id)
    chat_name = chat.title if chat.title else "Private Terminal"
    
    # Prompt explicitly tells Jarvis if he is talking to you or someone else
    is_boss = "YES" if user.id == CREATOR_ID else "NO"
    
    prompt = f"""{SYSTEM_PROMPT}\n\nLOCATION: {chat_name}\nSPEAKER: {user.first_name}\nIS BOSS?: {is_boss}\nCONTEXT:\n{history}\n\nRespond:"""
    
    try:
        res = await asyncio.to_thread(gemini_model.generate_content, prompt)
        log_memory(chat.id, thread_id, user.id, "J.A.R.V.I.S.", res.text.strip())
        await msg.reply_text(res.text)
    except Exception as e:
        await msg.reply_text(f"Google API Error: {str(e)}")

# ---------------------------------------------------------------------------
# BOOT SEQUENCE
# ---------------------------------------------------------------------------
async def morning_brief(app: Application):
    try:
        await app.bot.send_message(CREATOR_ID, "📰 **Morning Briefing:** All systems nominal. Vault is secure.", parse_mode="Markdown")
    except Exception: pass

async def _post_init(app: Application):
    scheduler = AsyncIOScheduler(timezone=IST)
    scheduler.add_job(lambda: asyncio.create_task(morning_brief(app)), "cron", hour=8, minute=0)
    scheduler.start()
    logger.info("J.A.R.V.I.S. Omni-Engine Armed.")

if __name__ == "__main__":
    db_init()
    try:
        app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()
        
        # Tools & Commands
        app.add_handler(CommandHandler(["start", "help", "dashboard"], start_cmd))
        app.add_handler(CommandHandler("backup", backup_cmd))
        app.add_handler(CommandHandler("task", task_cmd))
        app.add_handler(CommandHandler("search", search_cmd))
        app.add_handler(CommandHandler("math", math_cmd))
        
        # Callback Handlers (Tasks & UI)
        app.add_handler(CallbackQueryHandler(task_callback, pattern=r"^(done|del)_"))
        app.add_handler(CallbackQueryHandler(sys_callback, pattern=r"^sys_"))
        
        # Multi-Modal & Chat
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(MessageHandler(filters.VOICE, handle_voice))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.critical(f"SYSTEM FAILURE: {e}")
