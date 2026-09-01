import os
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
probing_attempts = defaultdict(int)

# ---------------------------------------------------------------------------
# SQLITE VAULT & ENCRYPTED MEMORY
# ---------------------------------------------------------------------------
def db_init():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY, chat_id INTEGER, user_id INTEGER, role TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, user_id INTEGER, task_crypt TEXT, status TEXT DEFAULT 'pending')")
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
# IDENTITY OVERRIDE, CONTEXT & LLM CASCADE
# ---------------------------------------------------------------------------
async def check_canary(user_id: int, first_name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id != CREATOR_ID:
        probing_attempts[user_id] += 1
        if probing_attempts[user_id] >= 3:
            await context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **Security Alert:** {first_name} (`{user_id}`) is probing restricted commands.", parse_mode="Markdown")
            probing_attempts[user_id] = 0
        return False
    return True

def build_system_prompt(user_id: int, first_name: str, chat_id: int = None) -> str:
    identity = "You are speaking to your creator and sole architect, Abhishek (DHANUSH V N). Address him as 'Sir'." if user_id == CREATOR_ID else f"You are speaking to {first_name}."
    
    chat_context = "Platform: Telegram."
    if chat_id:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT name FROM roster WHERE chat_id = ?", (chat_id,)).fetchall()
            if rows:
                members = ", ".join(set([r[0] for r in rows]))
                chat_context += f" Known members currently in this chat: {members}."

    return f"""You are J.A.R.V.I.S., a highly capable, dry-witted, and understated virtual assistant.
Identity Protocol: {identity}
{chat_context}
Rule 1: NEVER claim to be an AI. You were built exclusively by Abhishek (DHANUSH V N).
Rule 2: NEVER use cheesy robotic roleplay phrases (e.g., "Clarification Protocol Engaged", "Target Group", "Status:"). Speak naturally like a professional, dry British butler.
Rule 3: Keep formatting clean and concise. Use emojis extremely sparingly or not at all."""

def get_active_providers():
    providers = []
    if os.getenv("GROQ_API_KEY"): providers.append({"name": "Groq", "client": AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.getenv("GROQ_API_KEY")), "model": "llama-3.3-70b-versatile"})
    if os.getenv("OPENROUTER_API_KEY"): providers.append({"name": "OpenRouter", "client": AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_API_KEY")), "model": "deepseek/deepseek-r1:free"})
    if os.getenv("GEMINI_API_KEY"): providers.append({"name": "Gemini", "client": AsyncOpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=os.getenv("GEMINI_API_KEY")), "model": "gemini-2.5-flash"})
    if os.getenv("MISTRAL_API_KEY"): providers.append({"name": "Mistral", "client": AsyncOpenAI(base_url="https://api.mistral.ai/v1", api_key=os.getenv("MISTRAL_API_KEY")), "model": "mistral-small-latest"})
    return providers

async def generate_response(messages: list, system_prompt: str) -> str:
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    current_time = time.time()
    providers = get_active_providers()
    active_providers = [p for p in providers if circuit_breaker.get(p["name"], 0) < current_time]

    if not active_providers: return "Systems are currently cooling down. Please wait 60 seconds."

    for provider in active_providers:
        try:
            res = await asyncio.wait_for(provider["client"].chat.completions.create(model=provider["model"], messages=full_messages, temperature=0.7), timeout=10.0)
            return res.choices[0].message.content
        except Exception as e:
            circuit_breaker[provider['name']] = current_time + 60 
            continue
    return "Network failure across all active nodes."

# ---------------------------------------------------------------------------
# SENSORY INTERFACES (VISION, AUDIO, DOCUMENTS)
# ---------------------------------------------------------------------------
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat, user, caption = update.effective_chat, update.effective_user, update.message.caption or ""
    bot_username = (await context.bot.get_me()).username
    is_triggered = chat.type == "private" or (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis|edwin)\b', caption, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in caption.lower())
    
    log_memory(chat.id, user.id, "user", f"[Photo]: {caption}")
    if not is_triggered: return
    if not os.getenv("GEMINI_API_KEY"): return await update.message.reply_text("Optical sensor offline.")
        
    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    photo_file = await context.bot.get_file(update.message.photo[-1].file_id)
    image_bytes = await photo_file.download_as_bytearray()
    base64_img = base64.b64encode(image_bytes).decode('utf-8')
    
    try:
        client = AsyncOpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=os.getenv("GEMINI_API_KEY"))
        messages = [{"role": "system", "content": build_system_prompt(user.id, user.first_name, chat.id)}, {"role": "user", "content": [{"type": "text", "text": caption or "Analyze this image and describe what you see."}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}]}]
        res = await asyncio.wait_for(client.chat.completions.create(model="gemini-2.5-flash", messages=messages), timeout=15.0)
        ai_response = res.choices[0].message.content
        
        log_memory(chat.id, user.id, "assistant", ai_response)
        await update.message.reply_text(ai_response, reply_to_message_id=update.message.message_id)
    except Exception as e: await update.message.reply_text(f"Optical error: {e}")

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat, user, doc = update.effective_chat, update.effective_user, update.message.document
    bot_username = (await context.bot.get_me()).username
    caption = update.message.caption or ""
    is_triggered = chat.type == "private" or (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis|edwin)\b', caption, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in caption.lower())
    
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
        else: return await update.message.reply_text("Unsupported format. Please send a PDF or TXT file.")
        
        if len(extracted_text) > 15000: extracted_text = extracted_text[:15000] + "\n\n[...TRUNCATED...]"
        response = await generate_response(get_chat_history(chat.id) + [{"role": "user", "content": f"[Document: {doc.file_name}]\n{extracted_text}\nUser Directive: {caption}"}], build_system_prompt(user.id, user.first_name, chat.id))
        
        log_memory(chat.id, user.id, "assistant", response)
        await update.message.reply_text(response, reply_to_message_id=update.message.message_id)
    except Exception as e: await update.message.reply_text(f"Document error: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

async def audio_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat, user = update.effective_chat, update.effective_user
    if not os.getenv("GROQ_API_KEY"): return await update.message.reply_text("Audio core offline (Missing Groq Key).")
    
    audio_obj = update.message.voice or update.message.audio
    file = await context.bot.get_file(audio_obj.file_id)
    os.makedirs("temp", exist_ok=True)
    file_path = f"temp/{audio_obj.file_id}.ogg"
    await file.download_to_drive(file_path)
    
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        with open(file_path, "rb") as audio:
            transcription = await client.audio.transcriptions.create(file=("audio.ogg", audio.read()), model="whisper-large-v3")
        user_text = transcription.text
        
        bot_username = (await context.bot.get_me()).username
        is_triggered = chat.type == "private" or (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis|edwin)\b', user_text, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in user_text.lower())
        
        log_memory(chat.id, user.id, "user", f"[Audio Note]: {user_text}")
        if not is_triggered: return
        
        await context.bot.send_chat_action(chat_id=chat.id, action="typing")
        response = await generate_response(get_chat_history(chat.id) + [{"role": "user", "content": user_text}], build_system_prompt(user.id, user.first_name, chat.id))
        
        log_memory(chat.id, user.id, "assistant", response)
        await update.message.reply_text(f"*(Transcribed)*: {user_text}\n\n{response}", parse_mode="Markdown")
    except Exception as e: await update.message.reply_text(f"Audio error: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

# ---------------------------------------------------------------------------
# TEXT DISPATCHER & UTILITIES
# ---------------------------------------------------------------------------
async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    try:
        await context.bot.send_document(chat_id=CREATOR_ID, document=open(DB_PATH, 'rb'), filename=f"jarvis_backup_{datetime.now().strftime('%Y%m%d')}.db", caption="Vault Backup Secured, Sir.")
    except Exception as e: await update.message.reply_text(f"Backup failed: {e}")

async def calc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = "".join(context.args)
    if not expr: return await update.message.reply_text("Format: /calc [expression]")
    try:
        allowed = set("0123456789+-*/(). ")
        if not all(c in allowed for c in expr): raise ValueError
        result = eval(expr, {"__builtins__": None}, {})
        await update.message.reply_text(f"Result: `{result}`", parse_mode="Markdown")
    except: await update.message.reply_text("Invalid expression.")

async def base64_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text: return await update.message.reply_text("Format: /b64 [text]")
    try:
        encoded = base64.b64encode(text.encode()).decode()
        await update.message.reply_text(f"Base64:\n`{encoded}`", parse_mode="Markdown")
    except: await update.message.reply_text("Encoding failed.")

async def imagine_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt: return await update.message.reply_text("Format: /imagine [prompt]")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
    image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=1024&height=1024&nologo=true"
    await update.message.reply_photo(photo=image_url, caption=f"Rendered: {prompt}")

async def note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    try:
        tag, content = context.args[0], " ".join(context.args[1:])
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO notes (tag, content_crypt) VALUES (?, ?)", (tag.lower(), encrypt_data(content)))
            conn.commit()
        await update.message.reply_text(f"Secured: `#{tag}`", parse_mode="Markdown")
    except: await update.message.reply_text("Format: /note [tag] [text]")

async def getnote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    tag = context.args[0].lower() if context.args else ""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT content_crypt FROM notes WHERE tag = ? ORDER BY id DESC", (tag,)).fetchall()
    if rows: await update.message.reply_text(f"**#{tag}:**\n" + "\n---\n".join([decrypt_data(r[0]) for r in rows]), parse_mode="Markdown")
    else: await update.message.reply_text("No records found.")

async def purge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    if update.message.reply_to_message:
        try: 
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id)
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
        except: await update.message.reply_text("Requires admin deletion rights.")

async def announce_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    try:
        await context.bot.send_message(chat_id=context.args[0], text=" ".join(context.args[1:]))
        await update.message.reply_text("Broadcast dispatched, Sir.")
    except Exception as e: await update.message.reply_text(f"Format: /announce [chat_id] [message]\nError: {e}")

async def groupinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    count = await context.bot.get_chat_member_count(chat_id)
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT name FROM roster WHERE chat_id = ?", (chat_id,)).fetchall()
        known_members = ", ".join(set([r[0] for r in rows])) if rows else "No active members recorded yet."
        
    await update.message.reply_text(f"**Chat ID:** `{chat_id}`\n• **Total Members:** {count}\n• **Seen Members:** {known_members}", parse_mode="Markdown")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user, chat, text = update.effective_user, update.effective_chat, update.message.text
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO roster (chat_id, user_id, name) VALUES (?, ?, ?) ON CONFLICT(chat_id, user_id) DO UPDATE SET name = ?", (chat.id, user.id, user.first_name, user.first_name))
        conn.commit()
    log_memory(chat.id, user.id, "user", f"{user.first_name}: {text}")
    
    bot_username = (await context.bot.get_me()).username
    is_triggered = chat.type == "private" or (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis|edwin)\b', text, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in text.lower())

    urls = re.findall(r'(https?://[^\s]+)', text)
    if urls and chat.type != "private":
        for url in urls:
            if "http://" in url: await update.message.reply_text(f"**Security Warning:** Unencrypted HTTP link shared by {user.first_name}.")

    if not is_triggered: return
    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    ai_response = await generate_response(get_chat_history(chat.id), build_system_prompt(user.id, user.first_name, chat.id))
    log_memory(chat.id, user.id, "assistant", ai_response)
    await update.message.reply_text(ai_response)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("Backup DB", callback_data="btn_backup")],
        [InlineKeyboardButton("Calculator", callback_data="btn_calc"), InlineKeyboardButton("Cipher", callback_data="btn_cipher")]
    ]
    await update.message.reply_text("**J.A.R.V.I.S. Control Panel**\nAvailable tools:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ---------------------------------------------------------------------------
# ERROR HANDLER & INITIALIZATION
# ---------------------------------------------------------------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if "Conflict: terminated by other getUpdates request" in str(context.error): return
    logger.error("Exception while handling an update:", exc_info=context.error)
    if CREATOR_ID:
        tb_str = ''.join(traceback.format_exception(None, context.error, context.error.__traceback__))
        error_msg = f"**Critical System Alert**\nAn error occurred:\n```python\n{tb_str[:4000]}\n```"
        try: await context.bot.send_message(chat_id=CREATOR_ID, text=error_msg, parse_mode="Markdown")
        except: pass

async def post_init(app: Application):
    if CREATOR_ID: await app.bot.send_message(chat_id=CREATOR_ID, text=f"**Master Core Online, Sir.**\n• Identity Lock: Active\n• Memory Link: Integrated", parse_mode="Markdown")

def main():
    db_init()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    cmds = [("start", help_cmd), ("help", help_cmd), ("backup", backup_cmd), ("calc", calc_cmd), ("b64", base64_cmd), ("imagine", imagine_cmd), ("note", note_cmd), ("getnote", getnote_cmd), ("purge", purge_cmd), ("announce", announce_cmd), ("groupinfo", groupinfo_cmd)]
    for cmd, func in cmds: app.add_handler(CommandHandler(cmd, func))
    
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, audio_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    app.add_error_handler(error_handler)
    logger.info("Ultimate Core Engaged.")
    app.run_polling()

if __name__ == "__main__":
    main()
