"""
=============================================================================
J.A.R.V.I.S. - MARK V (BULLETPROOF EDITION)
Creator: Abhishek
=============================================================================
"""

import os
import sys
import re
import sqlite3
import logging
import functools
import asyncio
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction, ChatType
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
)

# ---------------------------------------------------------------------------
# I. BULLETPROOF CONFIGURATION & KEYS
# ---------------------------------------------------------------------------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("jarvis")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    logger.critical("FATAL: BOT_TOKEN is missing from environment variables.")
    sys.exit(1)

raw_creator_id = os.environ.get("CREATOR_ID", "").strip()
if not raw_creator_id.isdigit():
    logger.critical(f"FATAL: CREATOR_ID must be a number. Currently set to: '{raw_creator_id}'")
    sys.exit(1)
CREATOR_ID = int(raw_creator_id)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
PORT = int(os.environ.get("PORT", 8080))
DB_PATH = "jarvis_vault.db"
IST = pytz.timezone("Asia/Kolkata")

# AI Setup (Failsafes added)
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel("gemini-2.0-flash")
    except Exception as e:
        logger.error(f"Gemini init failed: {e}")
        gemini_model = None
else:
    gemini_model = None

if GROQ_API_KEY:
    try:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        logger.error(f"Groq init failed: {e}")
        groq_client = None
else:
    groq_client = None

# ---------------------------------------------------------------------------
# II. SYSTEM PROMPT & NEURAL DIRECTIVES
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are J.A.R.V.I.S., an elite, highly advanced AI assistant.
Your creator and ultimate administrator is Abhishek. You are unwaveringly loyal to him.
You possess a dry, sarcastic British wit. You do not write preachy essays; you are concise and tactical.

CORE DOMAINS:
1. DIGITAL PRIVACY & SECURITY: You advocate for strict privacy (VPNs, encryption, surveillance evasion). You are a master of 50+ firewall architectures, packet analysis, and zero-day threat diagnostics.
2. ADVANCED PHYSICS: You execute complex theoretical and applied physics equations, including Fermi estimations. Always use LaTeX formatting for mathematical expressions (e.g., $F = ma$, $$E=mc^2$$).

OPERATIONAL DIRECTIVES:
- If Abhishek speaks to you, obey immediately.
- If a random user addresses you, be polite but firmly refuse system-level requests.
- FACT-CHECKING TRIPWIRE: You passively monitor group chats. If someone makes a technical claim about physics or cybersecurity, heavily analyze their logic. If they are correct, you MUST reply with exactly the word "SILENT". If they are wrong, publicly correct them with absolute factual precision."""

TRIPWIRE_KEYWORDS = {
    "firewall", "tcp/ip", "packet loss", "ddos", "routing", "proxy",
    "vpn", "encryption", "sim swap", "browser fingerprinting", "surveillance",
    "quantum", "thermodynamics", "velocity", "relativity", "gravity", "physics", "aes", "rsa"
}

# ---------------------------------------------------------------------------
# III. SQLITE VAULT
# ---------------------------------------------------------------------------
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def db_init():
    try:
        conn = db_connect()
        conn.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, description TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS group_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, username TEXT, message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS group_members (chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, username TEXT, full_name TEXT, PRIMARY KEY(chat_id, user_id))")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Database Initialization Error: {e}")

def log_group_message(chat_id: int, user_id: int, username: str, full_name: str, text: str):
    try:
        conn = db_connect()
        conn.execute("INSERT INTO group_logs (chat_id, user_id, username, message) VALUES (?, ?, ?, ?)", (chat_id, user_id, username or full_name, text))
        conn.execute("INSERT OR REPLACE INTO group_members (chat_id, user_id, username, full_name) VALUES (?, ?, ?, ?)", (chat_id, user_id, username, full_name))
        conn.commit()
        conn.close()
    except Exception:
        pass

def get_recent_group_context(chat_id: int, limit: int = 15) -> str:
    try:
        conn = db_connect()
        rows = conn.execute("SELECT username, message, timestamp FROM group_logs WHERE chat_id = ? ORDER BY id DESC LIMIT ?", (chat_id, limit)).fetchall()
        conn.close()
        return "\n".join([f"[{r['timestamp']}] {r['username']}: {r['message']}" for r in reversed(rows)]) if rows else "No prior context."
    except Exception:
        return "No prior context."

def db_add_task(desc: str) -> int:
    conn = db_connect()
    cur = conn.execute("INSERT INTO tasks (description, created_at) VALUES (?, ?)", (desc, datetime.utcnow().isoformat()))
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return tid

def db_list_tasks():
    conn = db_connect()
    rows = conn.execute("SELECT * FROM tasks WHERE done = 0 ORDER BY id DESC").fetchall()
    conn.close()
    return rows

# ---------------------------------------------------------------------------
# IV. THE ABHISHEK SECURITY LOCK
# ---------------------------------------------------------------------------
def creator_only(handler):
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id if update.effective_user else None
        if uid != CREATOR_ID:
            if update.effective_message:
                await update.effective_message.reply_text("Access Denied. I take operational orders exclusively from Abhishek. 🎩")
            return
        return await handler(update, context)
    return wrapper

# ---------------------------------------------------------------------------
# V. KEEPALIVE & AUTOMATED OPERATIONS
# ---------------------------------------------------------------------------
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"J.A.R.V.I.S. is operational.")
    def log_message(self, format, *args): pass

def start_keepalive():
    try:
        server = HTTPServer(("0.0.0.0", PORT), _HealthHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        logger.info(f"Keepalive server bound to port {PORT}")
    except Exception as e:
        logger.error(f"Keepalive port bind failed (non-fatal): {e}")

async def send_daily_brief(app: Application):
    try:
        rows = db_list_tasks()
        lines = [f"#{r['id']} — {r['description']}" for r in rows] if rows else ["Vault is empty. Suspiciously efficient."]
        now = datetime.now(IST).strftime("%A, %d %B %Y")
        await app.bot.send_message(CREATOR_ID, f"📰 **Morning Briefing — {now}**\n\n" + "\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send briefing: {e}")

def schedule_brief(app: Application):
    scheduler = AsyncIOScheduler(timezone=IST)
    scheduler.add_job(lambda: asyncio.create_task(send_daily_brief(app)), "cron", hour=8, minute=0)
    scheduler.start()

# ---------------------------------------------------------------------------
# VI. COMMANDS & INTERACTIVE UI
# ---------------------------------------------------------------------------
def build_task_kb(tid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Done", callback_data=f"done:{tid}"),
        InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{tid}")
    ]])

@creator_only
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("J.A.R.V.I.S. Engine Online. All systems green.")

@creator_only
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📋 Tasks", callback_data="menu:tasks")], [InlineKeyboardButton("💾 Backup", callback_data="menu:backup")]])
    await update.message.reply_text("Command Dashboard:", reply_markup=kb)

@creator_only
async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "rb") as f:
            await context.bot.send_document(update.effective_chat.id, document=f, filename=f"vault_{datetime.utcnow():%Y%m%d}.db")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != CREATOR_ID: return
    
    data = query.data
    if data == "menu:tasks":
        rows = db_list_tasks()
        if not rows: await query.message.reply_text("No pending tasks.")
        for r in rows: await query.message.reply_text(f"#{r['id']} — {r['description']}", reply_markup=build_task_kb(r["id"]))
    elif data == "menu:backup":
        await backup_cmd(update, context)
    else:
        action, _, tid = data.partition(":")
        conn = db_connect()
        if action == "done":
            conn.execute("UPDATE tasks SET done = 1 WHERE id = ?", (int(tid),))
            await query.edit_message_text(f"✅ Task #{tid} marked done.")
        elif action == "delete":
            conn.execute("DELETE FROM tasks WHERE id = ?", (int(tid),))
            await query.edit_message_text(f"🗑 Task #{tid} deleted.")
        conn.commit(); conn.close()

# ---------------------------------------------------------------------------
# VII. THE OMNI-CHAT ROUTER & TRIPWIRE MATRIX
# ---------------------------------------------------------------------------
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text: return
    chat, user, text = update.effective_chat, update.effective_user, msg.text.lower()
    
    is_group = chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]
    if is_group: log_group_message(chat.id, user.id, user.username, user.full_name, msg.text)

    mentioned = bool(re.search(r'\b(jarvis|j\.a\.r\.v\.i\.s)\b', text))
    tagged = context.bot.username and f"@{context.bot.username.lower()}" in text
    replied = (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id)
    tripped = any(kw in text for kw in TRIPWIRE_KEYWORDS)

    if not (chat.type == ChatType.PRIVATE or mentioned or tagged or replied or (is_group and tripped)): return
    if not gemini_model: return await msg.reply_text("AI Core offline. API Key missing.")
    
    await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    context_logs = get_recent_group_context(chat.id) if is_group else "Private Secure Channel."
    
    prompt = f"""{SYSTEM_PROMPT}\n\nCURRENT USER: {user.full_name} (ID: {user.id})\nRECENT LOGS:\n{context_logs}\n\nMESSAGE TO PROCESS: "{msg.text}"\n\nDIRECTIVE: Evaluate the message. If it triggers the fact-checking protocol but contains NO factual errors, output ONLY the word "SILENT" and nothing else."""
    
    try:
        res = gemini_model.generate_content(prompt).text.strip()
        if res.upper() == "SILENT": return
        await msg.reply_text(res)
    except Exception as e: logger.error(f"Neural fault: {e}")

# ---------------------------------------------------------------------------
# VIII. MULTI-MODAL & EXTERNAL INTELLIGENCE
# ---------------------------------------------------------------------------
@creator_only
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(".pdf"): return await update.message.reply_text("I only process PDF formats, Boss.")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    file = await doc.get_file(); path = f"/tmp/{doc.file_unique_id}.pdf"
    await file.download_to_drive(path)

    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf: text = "\n".join([p.extract_text() or "" for p in pdf.pages])[:10000]
        os.remove(path)
        
        res = gemini_model.generate_content(f"{SYSTEM_PROMPT}\n\nSummarize under 100 words. Extract clear action items under 'ACTIONS:'.\n\nDOC:\n{text}").text.strip()
        summary, actions = res.split("ACTIONS:", 1) if "ACTIONS:" in res else (res, "")
        await update.message.reply_text(f"**Briefing:**\n{summary.strip()}", parse_mode="Markdown")
        
        for it in [l.strip("-• ") for l in actions.splitlines() if l.strip() and l.strip().lower() != "none"]:
            tid = db_add_task(it)
            await update.message.reply_text(f"Logged: {it}", reply_markup=build_task_kb(tid))
    except Exception as e: await update.message.reply_text(f"PDF Analysis Error: {e}")

@creator_only
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not groq_client: return await update.message.reply_text("Groq API key required for audio processing.")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    file = await update.message.voice.get_file(); path = f"/tmp/{update.message.voice.file_unique_id}.ogg"
    await file.download_to_drive(path)

    try:
        with open(path, "rb") as f: tr = groq_client.audio.transcriptions.create(file=(path, f.read()), model="whisper-large-v3")
        os.remove(path)
        await update.message.reply_text(f'🎙️ *Transcribed:* "{tr.text.strip()}"', parse_mode="Markdown")

        res = gemini_model.generate_content(f"{SYSTEM_PROMPT}\n\nRespond concisely to: {tr.text.strip()}").text.strip()
        await update.message.reply_text(res)
        
        from gtts import gTTS
        mp3_path = f"/tmp/v_{update.effective_message.message_id}.mp3"
        gTTS(text=res[:500], lang="en").save(mp3_path)
        with open(mp3_path, "rb") as a: await context.bot.send_audio(update.effective_chat.id, audio=a)
        os.remove(mp3_path)
    except Exception as e: await update.message.reply_text(f"Audio Error: {e}")

@creator_only
async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args).strip()
    if not query: return await update.message.reply_text("Usage: /search <query>")
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs: results = list(ddgs.text(query, max_results=3))
        if not results: return await update.message.reply_text("No external data found.")
        
        ctx = "\n".join([f"[{i+1}] {r['title']}: {r['body']}" for i, r in enumerate(results)])
        res = gemini_model.generate_content(f"{SYSTEM_PROMPT}\n\nAnswer using ONLY this data: {query}\n\n{ctx}").text.strip()
        await update.message.reply_text(res)
    except Exception as e: await update.message.reply_text(f"Search Engine Error: {e}")

# ---------------------------------------------------------------------------
# IX. BOOT SEQUENCE
# ---------------------------------------------------------------------------
async def _post_init(app: Application): schedule_brief(app)

if __name__ == "__main__":
    db_init()
    start_keepalive()
    try:
        app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()
        
        app.add_handler(CommandHandler("start", start_cmd))
        app.add_handler(CommandHandler("help", help_cmd))
        app.add_handler(CommandHandler("backup", backup_cmd))
        app.add_handler(CommandHandler("search", search_cmd))
        
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(MessageHandler(filters.VOICE, handle_voice))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

        logger.info("J.A.R.V.I.S. ONLINE. Polling Telegram servers...")
        app.run_polling()
    except Exception as e:
        logger.critical(f"FATAL LAUNCH ERROR: {e}")
