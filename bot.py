import os
import sys
import re
import time
import base64
import sqlite3
import logging
import asyncio
import traceback
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
from collections import defaultdict

import pytz
import pdfplumber
from cryptography.fernet import Fernet
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from openai import AsyncOpenAI

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, Application
)

# ---------------------------------------------------------------------------
# CORE CONFIGURATION & KEEP-ALIVE SERVER
# ---------------------------------------------------------------------------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
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
user_message_timestamps = defaultdict(list)

# ---------------------------------------------------------------------------
# SQLITE VAULT & ENCRYPTED MEMORY
# ---------------------------------------------------------------------------
def db_init():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY, chat_id INTEGER, user_id INTEGER, role TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, user_id INTEGER, task_crypt TEXT, status TEXT DEFAULT 'pending')")
        conn.execute("CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, category TEXT, note_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, tag TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS roster (chat_id INTEGER, user_id INTEGER, name TEXT, UNIQUE(chat_id, user_id))")
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
# IDENTITY OVERRIDE & LLM CASCADE
# ---------------------------------------------------------------------------
def build_system_prompt(user_id: int, first_name: str) -> str:
    if user_id == CREATOR_ID:
        identity = "You are speaking to your creator and sole architect, Abhishek (DHANUSH V N). Address him as 'Sir'."
    else:
        identity = f"You are speaking to {first_name}."
        
    return f"""You are J.A.R.V.I.S., a highly capable, friendly, and witty virtual assistant.
Identity Protocol: {identity}
Rule 1: NEVER claim to be an AI, a language model, or trained on vast datasets. You were built exclusively by Abhishek (DHANUSH V N).
Rule 2: Be highly concise, structured, and use bullet points when helpful.
Rule 3: Be warm and friendly. Use emojis naturally and appropriately, but maintain a sharp, competent edge."""

def get_active_providers():
    providers = []
    if os.getenv("GROQ_API_KEY"): providers.append({"name": "Groq", "client": AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.getenv("GROQ_API_KEY")), "model": "llama-3.3-70b-versatile"})
    if os.getenv("OPENROUTER_API_KEY"): providers.append({"name": "OpenRouter", "client": AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_API_KEY")), "model": "deepseek/deepseek-r1:free"})
    if os.getenv("GEMINI_API_KEY"): providers.append({"name": "Gemini", "client": AsyncOpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=os.getenv("GEMINI_API_KEY")), "model": "gemini-1.5-flash"})
    if os.getenv("MISTRAL_API_KEY"): providers.append({"name": "Mistral", "client": AsyncOpenAI(base_url="https://api.mistral.ai/v1", api_key=os.getenv("MISTRAL_API_KEY")), "model": "mistral-small-latest"})
    return providers

async def generate_response(messages: list, system_prompt: str) -> str:
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    current_time = time.time()
    providers = get_active_providers()
    active_providers = [p for p in providers if circuit_breaker.get(p["name"], 0) < current_time]

    if not active_providers: return "⚠️ Systems cooling down. Please wait 60 seconds."

    for provider in active_providers:
        try:
            res = await asyncio.wait_for(provider["client"].chat.completions.create(model=provider["model"], messages=full_messages, temperature=0.7), timeout=10.0)
            return res.choices[0].message.content
        except Exception as e:
            circuit_breaker[provider['name']] = current_time + 60 
            continue
    return "⚠️ Network failure across all nodes."

# ---------------------------------------------------------------------------
# SENSORY INTERFACES (VISION, AUDIO, DOCUMENTS)
# ---------------------------------------------------------------------------
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat, user, caption = update.effective_chat, update.effective_user, update.message.caption or ""
    bot_username = (await context.bot.get_me()).username
    is_triggered = chat.type == "private" or (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis|edwin)\b', caption, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in caption.lower())
    
    log_memory(chat.id, user.id, "user", f"[Photo]: {caption}")
    if not is_triggered: return
    if not os.getenv("GEMINI_API_KEY"): return await update.message.reply_text("Optical sensor offline. 📷")
        
    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    photo_file = await context.bot.get_file(update.message.photo[-1].file_id)
    image_bytes = await photo_file.download_as_bytearray()
    base64_img = base64.b64encode(image_bytes).decode('utf-8')
    
    try:
        client = AsyncOpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=os.getenv("GEMINI_API_KEY"))
        messages = [{"role": "system", "content": build_system_prompt(user.id, user.first_name)}, {"role": "user", "content": [{"type": "text", "text": caption or "Analyze this image."}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}]}]
        res = await asyncio.wait_for(client.chat.completions.create(model="gemini-1.5-flash", messages=messages), timeout=15.0)
        ai_response = res.choices[0].message.content
        
        log_memory(chat.id, user.id, "assistant", ai_response)
        await update.message.reply_text(ai_response, reply_to_message_id=update.message.message_id)
    except Exception as e: await update.message.reply_text(f"Optical error: {e}")

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat, user, doc = update.effective_chat, update.effective_user, update.message.document
    bot_username = (await context.bot.get_me()).username
    caption = update.message.caption or ""
    is_triggered = chat.type == "private" or (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis|edwin)\b', caption, re.IGNORECASE)
    
    if not is_triggered: return
    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    
    file = await context.bot.get_file(doc.file_id)
    os.makedirs("temp", exist_ok=True)
    file_path = f"temp/{doc.file_id}_{doc.file_name}"
    await file.download_to_drive(file_path)
    
    try:
        extracted_text = ""
        if doc.file_name.lower().endswith(".txt"):
            with open(file_path, "r", encoding="utf-8") as f: extracted_text = f.read()
        elif doc.file_name.lower().endswith(".pdf"):
            with pdfplumber.open(file_path) as pdf: extracted_text = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
        else: return await update.message.reply_text("Unsupported format. Use PDF or TXT. 📄")
        
        if len(extracted_text) > 15000: extracted_text = extracted_text[:15000] + "\n\n[...TRUNCATED...]"
        response = await generate_response(get_chat_history(chat.id) + [{"role": "user", "content": f"[Document: {doc.file_name}]\n{extracted_text}\nUser: {caption}"}], build_system_prompt(user.id, user.first_name))
        
        log_memory(chat.id, user.id, "assistant", response)
        await update.message.reply_text(response, reply_to_message_id=update.message.message_id)
    finally:
        if os.path.exists(file_path): os.remove(file_path)

# ---------------------------------------------------------------------------
# DETERMINISTIC UTILITIES & MODERATION
# ---------------------------------------------------------------------------
async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    try:
        await context.bot.send_document(chat_id=CREATOR_ID, document=open(DB_PATH, 'rb'), filename=f"jarvis_backup_{datetime.now().strftime('%Y%m%d')}.db", caption="📦 Vault Backup Secured, Sir.")
    except Exception as e: await update.message.reply_text(f"Backup failed: {e}")

async def calc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = "".join(context.args)
    if not expr: return await update.message.reply_text("Format: /calc [expression]")
    try:
        allowed = set("0123456789+-*/(). ")
        if not all(c in allowed for c in expr): raise ValueError
        result = eval(expr, {"__builtins__": None}, {})
        await update.message.reply_text(f"🧮 Result: `{result}`", parse_mode="Markdown")
    except: await update.message.reply_text("Invalid expression. 🚫")

async def base64_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text: return await update.message.reply_text("Format: /b64 [text]")
    try:
        encoded = base64.b64encode(text.encode()).decode()
        await update.message.reply_text(f"🔐 Base64:\n`{encoded}`", parse_mode="Markdown")
    except: await update.message.reply_text("Encoding failed.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user, chat, text = update.effective_user, update.effective_chat, update.message.text
    
    log_memory(chat.id, user.id, "user", f"{user.first_name}: {text}")
    bot_username = (await context.bot.get_me()).username
    is_triggered = chat.type == "private" or (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis|edwin)\b', text, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in text.lower())

    # Security Warning
    urls = re.findall(r'(https?://[^\s]+)', text)
    if urls and chat.type != "private":
        for url in urls:
            if "http://" in url: await update.message.reply_text(f"⚠️ Security Warning: Unencrypted HTTP link shared by {user.first_name}.")

    if not is_triggered: return
    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    ai_response = await generate_response(get_chat_history(chat.id), build_system_prompt(user.id, user.first_name))
    log_memory(chat.id, user.id, "assistant", ai_response)
    await update.message.reply_text(ai_response)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📦 Backup DB", callback_data="btn_backup")],
        [InlineKeyboardButton("🧮 Calculator", callback_data="btn_calc"), InlineKeyboardButton("🔐 Cipher", callback_data="btn_cipher")]
    ]
    await update.message.reply_text("🤖 **J.A.R.V.I.S. Control Panel**\nAvailable deterministic tools:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ---------------------------------------------------------------------------
# ERROR HANDLER & INITIALIZATION
# ---------------------------------------------------------------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling an update:", exc_info=context.error)
    if CREATOR_ID:
        tb_str = ''.join(traceback.format_exception(None, context.error, context.error.__traceback__))
        error_msg = f"🚨 **Critical System Alert**\nAn error occurred:\n```python\n{tb_str[:4000]}\n```"
        try: await context.bot.send_message(chat_id=CREATOR_ID, text=error_msg, parse_mode="Markdown")
        except: pass

async def post_init(app: Application):
    if CREATOR_ID: await app.bot.send_message(chat_id=CREATOR_ID, text=f"✨ **System Fully Online, Sir.**\n• Identity Lock: Active\n• Deterministic Tools: Engaged", parse_mode="Markdown")

def main():
    db_init()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", help_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("calc", calc_cmd))
    app.add_handler(CommandHandler("b64", base64_cmd))
    
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    app.add_error_handler(error_handler)
    logger.info("Ultimate Core Engaged.")
    app.run_polling()

if __name__ == "__main__":
    main()
