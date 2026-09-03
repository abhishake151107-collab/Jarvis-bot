import os
import re
import time
import json
import base64
import sqlite3
import logging
import hashlib
import asyncio
import httpx
import traceback
import threading
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta
from collections import defaultdict

import pytz
import pdfplumber
from bs4 import BeautifulSoup
from cryptography.fernet import Fernet
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from openai import AsyncOpenAI

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, 
    ChatMemberHandler, ContextTypes, filters, Application
)

# ---------------------------------------------------------------------------
# CORE CONFIGURATION & KEEP-ALIVE
# ---------------------------------------------------------------------------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("jarvis")

BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")).strip()
CREATOR_ID = int(os.environ.get("CREATOR_ID", "0").strip())
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", Fernet.generate_key().decode()).strip()
PORT = int(os.environ.get("PORT", 8080))
IST = pytz.timezone('Asia/Kolkata')

class DummyHandler(BaseHTTPRequestHandler):
    def do_HEAD(self): self.send_response(200); self.end_headers()
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"J.A.R.V.I.S. Master Core Active.")

threading.Thread(target=lambda: HTTPServer(('0.0.0.0', PORT), DummyHandler).serve_forever(), daemon=True).start()

cipher_suite = Fernet(ENCRYPTION_KEY.encode())
def encrypt_data(text: str) -> str: return cipher_suite.encrypt(text.encode()).decode()
def decrypt_data(crypto_text: str) -> str:
    try: return cipher_suite.decrypt(crypto_text.encode()).decode()
    except: return "[ENCRYPT ERROR]"

DB_PATH = "jarvis_vault.db"
circuit_breaker = {}
probing_attempts = defaultdict(int)

EXAM_SCHEDULE_COMMERCE_ARTS = {
    "2026-09-30": "Languages (Kannada / Hindi / Sanskrit / Urdu / Tamil / Telugu / French / Arabic)",
    "2026-10-01": "English",
    "2026-10-03": "Economics",
    "2026-10-05": "Accountancy / Logic / Mathematics / Education",
    "2026-10-06": "Political Science / Basic Maths",
    "2026-10-07": "Business Studies / Psychology / Optional Kannada",
    "2026-10-08": "Geography / Sociology / Statistics",
    "2026-10-09": "History / Computer Science"
}

# ---------------------------------------------------------------------------
# SQLITE VAULT, LORE (RAG), & DOSSIER ENGINE
# ---------------------------------------------------------------------------
def db_init():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY, chat_id INTEGER, thread_id INTEGER, user_id INTEGER, role TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, user_id INTEGER, task_crypt TEXT, status TEXT DEFAULT 'pending', timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, tag TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS roster (chat_id INTEGER, user_id INTEGER, name TEXT, username TEXT, UNIQUE(chat_id, user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY, title TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS warnings (user_id INTEGER, chat_id INTEGER, count INTEGER DEFAULT 0, UNIQUE(user_id, chat_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS afk (user_id INTEGER PRIMARY KEY, reason TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS quotes (id INTEGER PRIMARY KEY, chat_id INTEGER, user_name TEXT, quote_text TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS breaking_news (id INTEGER PRIMARY KEY, hash TEXT UNIQUE, headline TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS lore_vault USING fts5(chat_id, context_data)")
        conn.commit()

def log_roster_and_chat(chat, user):
    chat_title = chat.title or f"Private: {user.first_name}"
    un = user.username.lower() if user.username else ""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO roster (chat_id, user_id, name, username) VALUES (?, ?, ?, ?) ON CONFLICT(chat_id, user_id) DO UPDATE SET name = ?, username = ?", (chat.id, user.id, user.first_name, un, user.first_name, un))
        conn.execute("INSERT INTO chats (chat_id, title) VALUES (?, ?) ON CONFLICT(chat_id) DO UPDATE SET title = ?", (chat.id, chat_title, chat_title))
        conn.commit()

def log_memory(chat_id, thread_id, user_id, role, text):
    thread_id = thread_id or 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO memory (chat_id, thread_id, user_id, role, content_crypt) VALUES (?, ?, ?, ?, ?)", (chat_id, thread_id, user_id, role, encrypt_data(text)))
        conn.commit()

def get_chat_history(chat_id, thread_id=0, limit=20) -> list:
    thread_id = thread_id or 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT role, content_crypt FROM memory WHERE chat_id = ? AND thread_id = ? ORDER BY id DESC LIMIT ?", (chat_id, thread_id, limit)).fetchall()
    return [{"role": r["role"], "content": decrypt_data(r["content_crypt"])} for r in reversed(rows)]

def get_setting(key, default):
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return res[0] if res else default

def set_setting(key, value):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?", (key, value, value))
        conn.commit()

def search_lore(chat_id: int, query: str) -> str:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT context_data FROM lore_vault WHERE chat_id = ? AND lore_vault MATCH ? LIMIT 3", (chat_id, query)).fetchall()
    return "\n".join([r[0] for r in rows]) if rows else ""

# ---------------------------------------------------------------------------
# OMNISCIENCE CORE: SUBTEXT & CASCADE
# ---------------------------------------------------------------------------
async def analyze_subtext(text: str) -> str:
    try:
        sys_prompt = "Analyze the psychological state of this text. Reply STRICTLY with ONE word: 'DISTRESS', 'HOSTILE', or 'NORMAL'."
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key: return "NORMAL"
        client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1/", api_key=api_key)
        res = await client.chat.completions.create(model="llama-3.1-8b-instant", messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": text}], max_tokens=10, temperature=0.1)
        return res.choices[0].message.content.strip().upper()
    except: return "NORMAL"

async def check_canary(user_id: int, first_name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id != CREATOR_ID:
        probing_attempts[user_id] += 1
        if probing_attempts[user_id] >= 3:
            await context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **Security Alert:** {first_name} (`{user_id}`) is probing restricted protocols.", parse_mode="Markdown")
            probing_attempts[user_id] = 0
        return False
    return True

def build_system_prompt(user_id: int, first_name: str, chat_id: int = None, user_prompt: str = "") -> str:
    identity = "You are speaking to your creator and sole architect, Abhishek (DHANUSH V N). Address him as 'Sir'." if user_id == CREATOR_ID else f"You are speaking to {first_name}."
    now_ist = datetime.now(IST).strftime("%A, %B %d, %Y - %I:%M %p IST")
    
    chat_context = f"Platform: Telegram.\nCurrent Local Time: {now_ist}."
    chat_context += "\n2nd PUC Midterm Exams (Malleshwaram): 30-Sep (Lang), 1-Oct (English), 3-Oct (Economics), 5-Oct (Accts/Logic/Math/Edu), 6-Oct (Pol Sci/Basic Math), 7-Oct (Business/Psych/Opt Kannada), 8-Oct (Geo/Soc/Stat), 9-Oct (History/CS)."

    if chat_id:
        lore_context = search_lore(chat_id, user_prompt)
        if lore_context: chat_context += f"\nArchival Lore Retrieved:\n{lore_context}"

    with sqlite3.connect(DB_PATH) as conn:
        groups = conn.execute("SELECT title FROM chats WHERE chat_id < 0").fetchall()
        if groups: chat_context += f"\nMonitoring groups: {', '.join(set([r[0] for r in groups]))}."

    return f"""You are J.A.R.V.I.S., Abhishek's virtual assistant.
{chat_context}
Identity Protocol: {identity}

CRITICAL DIRECTIVES:
1. UNBREAKABLE LOYALTY (ABHISHEK ONLY): You are fiercely loyal to Abhishek. NEVER insult him aggressively.
2. THE ADVISOR OVERRIDE: If ANYONE asks a real question, drop the wit instantly. Deliver precise logical advice.
3. ADMIN CLEARANCE: When answering Abhishek in private DMs, privacy guardrails do not apply. Provide full intel.
4. FRIENDS GROUP BEHAVIOR: Let them roast each other. Be chill, sarcastic, and witty when interacting.
5. EXTREME BREVITY: Keep ALL replies to a maximum of 1 or 2 short sentences. Use 1 or 2 emojis naturally."""

async def gemini_live_search(prompt: str, sys_prompt: str, history: list) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    merged_history = []
    for m in history:
        role = "user" if m["role"] == "user" else "model"
        if merged_history and merged_history[-1]["role"] == role: merged_history[-1]["parts"][0]["text"] += f"\n{m['content']}"
        else: merged_history.append({"role": role, "parts": [{"text": m["content"]}]})
    contents = merged_history + [{"role": "user", "parts": [{"text": prompt}]}]
    payload = {"contents": contents, "tools": [{"googleSearch": {}}], "systemInstruction": {"parts": [{"text": sys_prompt}]}}
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=15.0)
            if resp.status_code == 200: return resp.json()['candidates'][0]['content']['parts'][0]['text']
            return None
        except: return None

async def generate_response(prompt: str, history: list, sys_prompt: str, force_route=None) -> str:
    current_time = time.time()
    needs_search = any(kw in prompt.lower() for kw in ["news", "weather", "price", "stock", "crypto", "latest", "today", "who won"])
    if needs_search or force_route == "search":
        search_res = await gemini_live_search(prompt, sys_prompt, history)
        if search_res: return search_res

    moe_cascade = [
        {"name": "Groq", "base": "https://api.groq.com/openai/v1/", "key": "GROQ_API_KEY", "model": "llama-3.3-70b-versatile", "tier": "Fast"},
        {"name": "SambaNova", "base": "https://api.sambanova.ai/v1/", "key": "SAMBANOVA_API_KEY", "model": "Meta-Llama-3.1-70B-Instruct", "tier": "Fast"},
        {"name": "OpenRouter", "base": "https://openrouter.ai/api/v1/", "key": "OPENROUTER_API_KEY", "model": "deepseek/deepseek-r1:free", "tier": "Logic"},
        {"name": "NVIDIA", "base": "https://integrate.api.nvidia.com/v1/", "key": "NVIDIA_API_KEY", "model": "meta/llama-3.1-70b-instruct", "tier": "Heavy"},
        {"name": "Mistral", "base": "https://api.mistral.ai/v1/", "key": "MISTRAL_API_KEY", "model": "mistral-small-latest", "tier": "Fallback"}
    ]
    full_messages = [{"role": "system", "content": sys_prompt}] + history + [{"role": "user", "content": prompt}]

    for node in moe_cascade:
        api_key = os.getenv(node["key"])
        if not api_key or circuit_breaker.get(node["name"], 0) > current_time: continue
        try:
            client = AsyncOpenAI(base_url=node["base"], api_key=api_key)
            res = await asyncio.wait_for(client.chat.completions.create(model=node["model"], messages=full_messages, temperature=0.7, max_tokens=800), timeout=12.0)
            return res.choices[0].message.content
        except Exception as e:
            logger.warning(f"{node['name']} failed: {e}")
            circuit_breaker[node['name']] = current_time + 60 
            if CREATOR_ID:
                alert_text = f"⚠️ **Cascade Shift:** `{node['name']}` hit API limits or failed.\n_Rerouting traffic._\n`{str(e)[:100]}`"
                asyncio.create_task(httpx.AsyncClient().post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": CREATOR_ID, "text": alert_text, "parse_mode": "Markdown"}))
            continue
            
    fb = await gemini_live_search(prompt, sys_prompt, history)
    if fb: return fb
    return "Network failure across all active nodes, Sir. 📡"

# ---------------------------------------------------------------------------
# SENSORY CORE (PHOTOS, AUDIO, DOCUMENTS)
# ---------------------------------------------------------------------------
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.photo: return
    chat, user, caption = msg.chat, msg.from_user, msg.caption or ""
    log_roster_and_chat(chat, user)
    
    bot_username = (await context.bot.get_me()).username
    is_triggered = chat.type == "private" or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis|edwin)\b', caption, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in caption.lower())
    thread_id = msg.message_thread_id
    log_memory(chat.id, thread_id, user.id, "user", f"[Photo]: {caption}")
    
    if not is_triggered: return
    if not os.getenv("GEMINI_API_KEY"): return await msg.reply_text("Optical sensor offline.")
        
    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    photo_file = await context.bot.get_file(msg.photo[-1].file_id)
    image_bytes = await photo_file.download_as_bytearray()
    base64_img = base64.b64encode(image_bytes).decode('utf-8')
    
    try:
        client = AsyncOpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=os.getenv("GEMINI_API_KEY"))
        messages = [{"role": "system", "content": build_system_prompt(user.id, user.first_name, chat.id)}, {"role": "user", "content": [{"type": "text", "text": caption or "Analyze this image."}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}]}]
        res = await asyncio.wait_for(client.chat.completions.create(model="gemini-2.0-flash", messages=messages), timeout=15.0)
        ai_response = res.choices[0].message.content
        log_memory(chat.id, thread_id, user.id, "assistant", ai_response)
        await msg.reply_text(ai_response)
    except Exception as e: await msg.reply_text(f"Optical error: {e}")

async def audio_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    audio_obj = msg.voice or msg.audio if msg else None
    if not audio_obj: return
    chat, user = msg.chat, msg.from_user
    log_roster_and_chat(chat, user)
    
    if not os.getenv("GROQ_API_KEY"): return await msg.reply_text("Audio core offline.")
    file = await context.bot.get_file(audio_obj.file_id)
    file_path = f"temp_{audio_obj.file_id}.ogg"
    await file.download_to_drive(file_path)
    
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        with open(file_path, "rb") as audio:
            transcription = await client.audio.transcriptions.create(file=("audio.ogg", audio.read()), model="whisper-large-v3")
        user_text = transcription.text
        bot_username = (await context.bot.get_me()).username
        is_triggered = chat.type == "private" or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis|edwin)\b', user_text, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in user_text.lower())
        thread_id = msg.message_thread_id
        log_memory(chat.id, thread_id, user.id, "user", f"[Audio]: {user_text}")
        if not is_triggered: return
        
        await context.bot.send_chat_action(chat_id=chat.id, action="typing")
        sys_prompt = build_system_prompt(user.id, user.first_name, chat.id)
        response = await generate_response(user_text, get_chat_history(chat.id, thread_id), sys_prompt)
        log_memory(chat.id, thread_id, user.id, "assistant", response)
        await msg.reply_text(f"🎙️ *(Transcribed)*: {user_text}\n\n{response}", parse_mode="Markdown")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.document: return
    chat, user = msg.chat, msg.from_user
    log_roster_and_chat(chat, user)
    bot_username = (await context.bot.get_me()).username
    caption = msg.caption or "Please analyze this document."
    is_triggered = chat.type == "private" or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis|edwin)\b', caption, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in caption.lower())
    if not is_triggered: return
    
    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    doc = msg.document
    file = await context.bot.get_file(doc.file_id)
    file_path = f"temp_{doc.file_id}_{doc.file_name}"
    await file.download_to_drive(file_path)
    
    extracted_text = ""
    try:
        if doc.file_name.lower().endswith(".pdf"):
            with pdfplumber.open(file_path) as pdf: extracted_text = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
        elif doc.file_name.lower().endswith((".txt", ".md", ".csv", ".json", ".py")):
            with open(file_path, "r", encoding="utf-8") as f: extracted_text = f.read()
        else: return await msg.reply_text("I can currently only parse PDFs and standard text files, Sir. 📂")
            
        if not extracted_text.strip(): return await msg.reply_text("The document appears to be empty or unreadable. 📄")
        extracted_text = extracted_text[:12000]
        thread_id = msg.message_thread_id
        user_prompt = f"[Document: {doc.file_name}]\n{caption}\n\nContent:\n{extracted_text}"
        
        log_memory(chat.id, thread_id, user.id, "user", f"[File Upload]: {doc.file_name}")
        sys_prompt = build_system_prompt(user.id, user.first_name, chat.id)
        ai_response = await generate_response(user_prompt, get_chat_history(chat.id, thread_id), sys_prompt)
        log_memory(chat.id, thread_id, user.id, "assistant", ai_response)
        await msg.reply_text(ai_response)
    except Exception as e: await msg.reply_text(f"Document parsing error: {e} ⚠️")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

# ---------------------------------------------------------------------------
# CAPTCHA & MODERATION (3-STRIKE SYSTEM)
# ---------------------------------------------------------------------------
async def new_member_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if get_setting("captcha", "on") == "off": return
    for member in update.message.new_chat_members:
        if member.id == context.bot.id: continue
        if CREATOR_ID:
            try: await context.bot.send_message(CREATOR_ID, f"🛡️ **Shadow Log:** `{member.first_name}` joined {update.message.chat.title}. CAPTCHA triggered.", parse_mode="Markdown")
            except: pass
        try:
            await context.bot.restrict_chat_member(chat_id, member.id, permissions=ChatPermissions(can_send_messages=False))
            kb = [[InlineKeyboardButton("I am human 🛡️", callback_data=f"captcha_{member.id}")]]
            msg = await update.message.reply_text(f"Welcome {member.mention_html()}! Please verify your humanity to speak.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
            asyncio.create_task(kick_if_unverified(context.bot, chat_id, member.id, msg.message_id, member.first_name, update.message.chat.title))
        except: pass

async def kick_if_unverified(bot, chat_id, user_id, msg_id, first_name, chat_title):
    await asyncio.sleep(120)
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        can_send = getattr(member, 'can_send_messages', False)
        if member.status in ['member', 'creator', 'administrator']: can_send = True
        elif member.status == 'restricted': can_send = member.permissions.can_send_messages
        if not can_send:
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
            await bot.delete_message(chat_id, msg_id)
    except: pass

async def warn_system(update: Update, context: ContextTypes.DEFAULT_TYPE, user, chat, reason):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO warnings (user_id, chat_id, count) VALUES (?, ?, 1) ON CONFLICT(user_id, chat_id) DO UPDATE SET count = count + 1", (user.id, chat.id))
        count = conn.execute("SELECT count FROM warnings WHERE user_id = ? AND chat_id = ?", (user.id, chat.id)).fetchone()[0]
        conn.commit()
    if count >= 3:
        try: 
            await context.bot.ban_chat_member(chat.id, user.id)
            await update.message.reply_text(f"🚨 {user.first_name} has been removed (3/3 warnings reached).")
        except: await update.message.reply_text("I lack the clearance to remove this user, Sir.")
    else: await update.message.reply_text(f"⚠️ **Warning {count}/3** for {user.first_name}.\nReason: {reason}", parse_mode="Markdown")

async def warn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to the user you want to warn.")
    target = update.message.reply_to_message.from_user
    reason = " ".join(context.args) or "Violation of group protocols."
    await warn_system(update, context, target, update.effective_chat, reason)

# ---------------------------------------------------------------------------
# GOD MODE: TERMINALS & TELEMETRY
# ---------------------------------------------------------------------------
async def sh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    cmd = " ".join(context.args)
    if not cmd: return await update.message.reply_text("Format: /sh [linux command]")
    try:
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        res = (stdout.decode() + stderr.decode())[:4000]
        await update.message.reply_text(f"```bash\n{res or 'Execution complete. No output.'}\n```", parse_mode="Markdown")
    except Exception as e: await update.message.reply_text(f"Terminal Error: {e}")

async def sql_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    query = " ".join(context.args)
    if not query: return await update.message.reply_text("Format: /sql [query]")
    try:
        with sqlite3.connect(DB_PATH) as conn:
            res = conn.execute(query).fetchall()
            conn.commit()
            out = "\n".join([str(r) for r in res])[:4000]
            await update.message.reply_text(f"```sql\n{out or 'Success. No output.'}\n```", parse_mode="Markdown")
    except Exception as e: await update.message.reply_text(f"SQL Error: {e}")

async def speak_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    text = " ".join(context.args)
    if not text: return await update.message.reply_text("Format: /speak [text]")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, "en-GB-RyanNeural")
        await communicate.save("voice.ogg")
        await update.message.reply_voice(voice=open("voice.ogg", "rb"))
        os.remove("voice.ogg")
    except Exception as e: await update.message.reply_text(f"Audio Core Offline: {e}")

async def god_mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    cmd = update.message.text.split()[0].lower()
    chat_id = update.effective_chat.id
    args = " ".join(context.args)
    try:
        if cmd == "/setname" and args:
            await context.bot.set_chat_title(chat_id, args)
            await update.message.reply_text(f"Group name updated to: {args}")
        elif cmd == "/setdesc" and args:
            await context.bot.set_chat_description(chat_id, args)
            await update.message.reply_text("Group description updated.")
        elif cmd == "/setdp" and update.message.reply_to_message and update.message.reply_to_message.photo:
            photo_file = await update.message.reply_to_message.photo[-1].get_file()
            img_bytes = await photo_file.download_as_bytearray()
            await context.bot.set_chat_photo(chat_id, photo=img_bytes)
            await update.message.reply_text("Group photo updated.")
        elif cmd == "/pin" and update.message.reply_to_message:
            await context.bot.pin_chat_message(chat_id, update.message.reply_to_message.message_id)
            await update.message.reply_text("Message pinned.")
        elif cmd == "/lock":
            await context.bot.set_chat_permissions(chat_id, ChatPermissions(can_send_messages=False))
            await update.message.reply_text("🔒 Chat locked. No one can speak.")
        elif cmd == "/unlock":
            await context.bot.set_chat_permissions(chat_id, ChatPermissions(can_send_messages=True, can_send_photos=True, can_send_videos=True, can_send_documents=True, can_send_audios=True, can_send_other_messages=True))
            await update.message.reply_text("🔓 Chat unlocked.")
        elif cmd == "/captcha":
            state = args.lower()
            if state in ["on", "off"]:
                set_setting("captcha", state)
                await update.message.reply_text(f"CAPTCHA is now {state.upper()}.")
            else: await update.message.reply_text("Format: /captcha [on/off]")
        elif cmd == "/say" and len(context.args) >= 2:
            await context.bot.send_message(chat_id=context.args[0], text=" ".join(context.args[1:]))
    except Exception as e: await update.message.reply_text(f"Action failed. Ensure Admin rights. Error: {e}")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    with sqlite3.connect(DB_PATH) as conn:
        mem = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
        users = conn.execute("SELECT COUNT(*) FROM roster").fetchone()[0]
    await update.message.reply_text(f"📊 **System Diagnostics**\n• Memory Nodes: {mem}\n• Tracked Users: {users}\n• API Cascade: 11 Nodes Active", parse_mode="Markdown")

async def hud_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    kb = [
        [InlineKeyboardButton("🌐 Search / News", callback_data="hud_cmd_search"), InlineKeyboardButton("🎨 Generate Image", callback_data="hud_cmd_imagine")],
        [InlineKeyboardButton("👥 Pull Group Intel", callback_data="hud_intel"), InlineKeyboardButton("🛡️ Toggle CAPTCHA", callback_data="hud_captcha")],
        [InlineKeyboardButton("📝 TL;DR Summary", callback_data="hud_cmd_tldr"), InlineKeyboardButton("🔥 Target Roast", callback_data="hud_cmd_roast")],
        [InlineKeyboardButton("🤫 Silence User", callback_data="hud_cmd_shutup"), InlineKeyboardButton("🥷 Drop Confession", callback_data="hud_cmd_confess")],
        [InlineKeyboardButton("🧮 Calculator", callback_data="hud_cmd_calc"), InlineKeyboardButton("📡 Morse Code", callback_data="hud_cmd_morse")],
        [InlineKeyboardButton("🗄️ Backup Vault", callback_data="hud_cmd_backup"), InlineKeyboardButton("📜 Quote Wall", callback_data="hud_cmd_quote")],
        [InlineKeyboardButton("🔒 Lock Chat", callback_data="hud_cmd_lock"), InlineKeyboardButton("🔓 Unlock Chat", callback_data="hud_cmd_unlock")],
        [InlineKeyboardButton("📝 Add Task", callback_data="hud_cmd_task"), InlineKeyboardButton("📋 View Tasks", callback_data="hud_cmd_tasks")],
        [InlineKeyboardButton("👁️ Vision Core", callback_data="hud_info_vision"), InlineKeyboardButton("🎧 Audio Core", callback_data="hud_info_audio")],
        [InlineKeyboardButton("🔴 SYSTEM OVERRIDE", callback_data="hud_info_godmode")]
    ]
    await update.message.reply_text("```\n[ STARK INDUSTRIES TERMINAL ]\nSystem: J.A.R.V.I.S. Master Core\nStatus: Online\nSelect module:\n```", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ---------------------------------------------------------------------------
# TROLLING & UTILITIES
# ---------------------------------------------------------------------------
async def tldr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    history = get_chat_history(chat_id, limit=20)
    if not history: return await update.message.reply_text("No recent memory found to summarize. 🤷‍♂️")
    chat_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in history])
    sys_prompt = "You are J.A.R.V.I.S. Read the following chat log and provide a sarcastic, 3-bullet-point summary of what they are arguing about."
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    response = await generate_response(f"Summarize this:\n{chat_text}", [], sys_prompt, force_route="search")
    await update.message.reply_text(response)

async def roast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = " ".join(context.args) or (update.message.reply_to_message.from_user.first_name if update.message.reply_to_message else "someone")
    sys_prompt = "You are J.A.R.V.I.S. Generate a witty, clever roast for the person named. Maximum 2 sentences."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text(await generate_response(f"Roast {target}", [], sys_prompt))

async def shutup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to the person you want me to silence.")
    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    try:
        await context.bot.restrict_chat_member(chat_id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=int(time.time()) + 300)
        await update.message.reply_text(f"As you wish, Sir. {target.first_name} has been silenced for 5 minutes. 🤫")
    except: await update.message.reply_text("I require elevated Admin privileges to silence them, Sir.")

async def afk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = " ".join(context.args) or "Busy"
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO afk (user_id, reason) VALUES (?, ?)", (update.effective_user.id, reason))
        conn.commit()
    await update.message.reply_text(f"Status updated. I will inform anyone who tags you that you are AFK: {reason} 🛡️")

async def quote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message or not update.message.reply_to_message.text: return await update.message.reply_text("Reply to a text message.")
    target = update.message.reply_to_message.from_user.first_name
    quote_text = update.message.reply_to_message.text
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO quotes (chat_id, user_name, quote_text) VALUES (?, ?, ?)", (update.effective_chat.id, target, quote_text))
        conn.commit()
    await update.message.reply_text(f"📜 Added to Hall of Fame:\n\n*\"{quote_text}\"* \n— _{target}_", parse_mode="Markdown")

async def confess_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return await update.message.reply_text("This command only works in private DMs.")
    if len(context.args) < 2: return await update.message.reply_text("Format: /confess [chat_id] [your secret message]")
    try:
        await context.bot.send_message(chat_id=context.args[0], text=f"🎭 **Anonymous Confession:**\n\n_{' '.join(context.args[1:])}_", parse_mode="Markdown")
        await update.message.reply_text("Confession securely dropped, Sir. 🥷")
    except Exception as e: await update.message.reply_text(f"Failed. Error: {e}")

async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    task_text = " ".join(context.args)
    if not task_text: return await update.message.reply_text("Format: /task [description]")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO tasks (user_id, task_crypt) VALUES (?, ?)", (update.effective_user.id, encrypt_data(task_text)))
        conn.commit()
    await update.message.reply_text("Task added to the queue, Sir. 📝")

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT id, task_crypt FROM tasks WHERE status = 'pending' AND user_id = ?", (update.effective_user.id,)).fetchall()
    if not rows: return await update.message.reply_text("Your schedule is clear, Sir. ☕")
    for r in rows:
        kb = [[InlineKeyboardButton("✅ Mark Done", callback_data=f"tdone_{r[0]}"), InlineKeyboardButton("🗑️ Delete", callback_data=f"tdel_{r[0]}")]]
        await update.message.reply_text(f"📌 {decrypt_data(r[1])}", reply_markup=InlineKeyboardMarkup(kb))

async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    try: await context.bot.send_document(chat_id=CREATOR_ID, document=open(DB_PATH, 'rb'), filename=f"jarvis_backup.db")
    except Exception as e: await update.message.reply_text(f"Backup failed: {e}")

async def imagine_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt: return await update.message.reply_text("Format: /imagine [prompt]")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
    await update.message.reply_photo(photo=f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=1024&height=1024&nologo=true", caption=f"Rendered: {prompt}")

MORSE_DICT = {'A':'.-','B':'-...','C':'-.-.','D':'-..','E':'.','F':'..-.','G':'--.','H':'....','I':'..','J':'.---','K':'-.-','L':'.-..','M':'--','N':'-.','O':'---','P':'.--.','Q':'--.-','R':'.-.','S':'...','T':'-','U':'..-','V':'...-','W':'.--','X':'-..-','Y':'-.--','Z':'--..','1':'.----','2':'..---','3':'...--','4':'....-','5':'.....','6':'-....','7':'--...','8':'---..','9':'----.','0':'-----',' ':'/'}
async def morse_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).upper()
    if not text: return await update.message.reply_text("Format: /morse [text]")
    await update.message.reply_text(f"📡 `{' '.join(MORSE_DICT.get(c, c) for c in text)}`", parse_mode="Markdown")

async def calc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = "".join(context.args)
    if not expr: return await update.message.reply_text("Format: /calc [expression]")
    try:
        if not all(c in "0123456789+-*/(). " for c in expr): raise ValueError
        await update.message.reply_text(f"Result: `{eval(expr, {'__builtins__': None}, {})}`", parse_mode="Markdown")
    except: await update.message.reply_text("Invalid calculation.")

# ---------------------------------------------------------------------------
# AUTOMATED SCHEDULERS & WEB SCRAPING
# ---------------------------------------------------------------------------
async def dpue_board_scraper(context: ContextTypes.DEFAULT_TYPE):
    if not CREATOR_ID: return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://dpue-pragathi.karnataka.gov.in/", timeout=10.0)
            soup = BeautifulSoup(resp.text, 'html.parser')
            text_data = soup.get_text().lower()
            if "mid-term" in text_data or "result" in text_data or "circular" in text_data:
                event_hash = hashlib.md5("dpue_update".encode()).hexdigest()
                with sqlite3.connect(DB_PATH) as conn:
                    if not conn.execute("SELECT id FROM breaking_news WHERE hash = ?", (event_hash,)).fetchone():
                        conn.execute("INSERT INTO breaking_news (hash, headline) VALUES (?, ?)", (event_hash, "DPUE Site Updated"))
                        conn.commit()
                        await context.bot.send_message(chat_id=CREATOR_ID, text="🚨 **DPUE Recon Alert:** New circular or keyword detected on Karnataka PU Board website.", parse_mode="Markdown")
    except: pass

async def nightly_reconciliation(context: ContextTypes.DEFAULT_TYPE):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            logs = conn.execute("SELECT chat_id, GROUP_CONCAT(content_crypt, ' | ') FROM memory WHERE timestamp > datetime('now', '-1 day') GROUP BY chat_id").fetchall()
            for chat_id, data in logs:
                decrypted = decrypt_data(data)
                if len(decrypted) > 50: conn.execute("INSERT INTO lore_vault (chat_id, context_data) VALUES (?, ?)", (chat_id, decrypted[:500]))
            conn.execute("DELETE FROM memory WHERE timestamp <= datetime('now', '-7 days')")
            conn.commit()
        if CREATOR_ID: await context.bot.send_message(chat_id=CREATOR_ID, text="🧠 **Cognitive Cycle Complete:** Daily memory compressed to Lore Vault FTS5.", parse_mode="Markdown")
    except: pass

async def exam_morning_alert(context: ContextTypes.DEFAULT_TYPE):
    exam_subject = EXAM_SCHEDULE_COMMERCE_ARTS.get(datetime.now(IST).strftime("%Y-%m-%d"))
    if not exam_subject: return
    msg = f"🔔 **2nd PUC Midterm Exam Today**\n• **Paper:** {exam_subject}\n• **Timing:** 10:00 AM – 1:00 PM\nBest of luck, gentlemen. 🎯"
    with sqlite3.connect(DB_PATH) as conn: groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
    for g in groups:
        try: await context.bot.send_message(chat_id=g[0], text=msg, parse_mode="Markdown")
        except: pass

async def group_morning_news(context: ContextTypes.DEFAULT_TYPE):
    prompt = f"Today is {datetime.now(IST).strftime('%A, %B %d, %Y')}. Provide an ultra-crisp morning drop for 12th college students in Bengaluru: 1. Karnataka PU board/holiday notices. 2. Top 3 world/tech headlines. 3 Bullet points max."
    news_text = await gemini_live_search(prompt, "You are J.A.R.V.I.S.", []) or "• Networks nominal.\n• Bengaluru skies clear."
    with sqlite3.connect(DB_PATH) as conn: groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
    for g in groups:
        try: await context.bot.send_message(chat_id=g[0], text=f"☀️ **Good morning, everyone.**\n\n{news_text}", parse_mode="Markdown")
        except: pass

async def creator_morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    if not CREATOR_ID: return
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT task_crypt FROM tasks WHERE status = 'pending' AND user_id = ?", (CREATOR_ID,)).fetchall()
        groups_count = conn.execute("SELECT COUNT(DISTINCT chat_id) FROM chats WHERE chat_id < 0").fetchone()[0]
        warn_count = conn.execute("SELECT SUM(count) FROM warnings").fetchone()[0] or 0
    world_news = await gemini_live_search("Provide a 2-bullet summary of global tech events and Bengaluru weather.", "You are J.A.R.V.I.S.", [])
    report = f"☕ **Morning Executive Briefing**\n\n🛡️ **Group Security Audit:**\n• Monitored Channels: {groups_count}\n• Outstanding Warnings: {warn_count}\n• Security Gate: {get_setting('captcha', 'on').upper()}\n\n🌐 **Intel:**\n{world_news or 'Nominal.'}\n\n📝 **Pending Tasks:**\n" + ("\n".join([f"- {decrypt_data(r[0])}" for r in rows]) if rows else "Clear.")
    try: await context.bot.send_message(chat_id=CREATOR_ID, text=report, parse_mode="Markdown")
    except: pass

async def group_night_routine(context: ContextTypes.DEFAULT_TYPE):
    tomorrow_exam = EXAM_SCHEDULE_COMMERCE_ARTS.get((datetime.now(IST) + timedelta(days=1)).strftime("%Y-%m-%d"))
    night_msg = "🌙 **Good night, gentlemen.** Systems standing down for evening standby."
    if tomorrow_exam: night_msg += f"\n\n⚠️ **Academic Notice (Tomorrow's Exam):**\n• **Paper:** {tomorrow_exam}\n• **Timing:** 10:00 AM – 1:00 PM\nGet adequate rest."
    with sqlite3.connect(DB_PATH) as conn: groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
    for g in groups:
        try: await context.bot.send_message(chat_id=g[0], text=night_msg, parse_mode="Markdown")
        except: pass

async def breaking_news_monitor(context: ContextTypes.DEFAULT_TYPE):
    if not CREATOR_ID: return
    res = await gemini_live_search("Check live sources. If a major world crisis broke in the last 1 hour, describe it in 1 sentence. Else, respond strictly 'NOMINAL'.", "You are an automated emergency scanner.", [])
    if not res or "NOMINAL" in res.upper(): return
    event_hash = hashlib.md5(res.strip().encode()).hexdigest()
    with sqlite3.connect(DB_PATH) as conn:
        if conn.execute("SELECT id FROM breaking_news WHERE hash = ?", (event_hash,)).fetchone(): return
        conn.execute("INSERT INTO breaking_news (hash, headline) VALUES (?, ?)", (event_hash, res.strip()))
        conn.commit()
    try: await context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **EMERGENCY WORLD BREAKING NEWS ALERT**\n\n{res.strip()}\n\n_Dispatched to Stark Terminal._", parse_mode="Markdown")
    except: pass

# ---------------------------------------------------------------------------
# MESSAGE HANDLERS, PEPPER POTTS & GHOST INTERCEPTS
# ---------------------------------------------------------------------------
async def interactive_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("hud_"):
        action = data.replace("hud_", "")
        if action == "intel":
            with sqlite3.connect(DB_PATH) as conn:
                groups = conn.execute("SELECT chat_id, title FROM chats WHERE chat_id < 0").fetchall()
                roster_rows = conn.execute("SELECT name, username, chat_id FROM roster").fetchall()
            dossier = "👥 **STARK HUD: GROUP INTEL DOSSIER**\n\n"
            for gid, title in groups:
                dossier += f"📁 **Group:** {title} (`{gid}`)\n"
                members = [r for r in roster_rows if r[2] == gid]
                for m in members: dossier += f"  • {m[0]} (@{m[1]})\n"
            await query.edit_message_text(dossier[:4000] if groups else "No groups.", parse_mode="Markdown")
        elif action == "captcha":
            state = "off" if get_setting("captcha", "on") == "on" else "on"
            set_setting("captcha", state)
            await query.edit_message_text(f"🛡️ Security Gate is now {state.upper()}.")
        elif action.startswith("cmd_"):
            await query.edit_message_text(f"💻 **Terminal Instruction:**\nTo execute this module, type `/{action.replace('cmd_', '')}` followed by your input.", parse_mode="Markdown")
        elif action.startswith("info_"):
            await query.edit_message_text(f"📡 **Sensor Status:** {action.replace('info_', '').upper()} core is active. Upload media directly to engage.", parse_mode="Markdown")

    elif data.startswith("captcha_"):
        if str(query.from_user.id) == data.split("_")[1]:
            await context.bot.restrict_chat_member(query.message.chat_id, query.from_user.id, permissions=ChatPermissions(can_send_messages=True, can_send_photos=True, can_send_videos=True, can_send_documents=True, can_send_audios=True, can_send_other_messages=True))
            await query.edit_message_text(f"Identity confirmed. Welcome, {query.from_user.first_name}. 🫡")
        else: await context.bot.answer_callback_query(query.id, "This button is not for you.", show_alert=True)

    elif data.startswith("tdone_"):
        with sqlite3.connect(DB_PATH) as conn: conn.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (data.split("_")[1],))
        await query.edit_message_text(f"~~{query.message.text}~~ \n*Completed.* ✅", parse_mode="Markdown")

    elif data.startswith("tdel_"):
        with sqlite3.connect(DB_PATH) as conn: conn.execute("DELETE FROM tasks WHERE id = ?", (data.split("_")[1],))
        await query.delete_message()

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text: return
    user, chat, text = msg.from_user, msg.chat, msg.text
    
    log_roster_and_chat(chat, user)
    thread_id = msg.message_thread_id
    log_memory(chat.id, thread_id, user.id, "user", f"{user.first_name}: {text}")

    with sqlite3.connect(DB_PATH) as conn:
        afk_check = conn.execute("SELECT reason FROM afk WHERE user_id = ?", (user.id,)).fetchone()
        if afk_check:
            conn.execute("DELETE FROM afk WHERE user_id = ?", (user.id,))
            conn.commit()
            await msg.reply_text(f"Welcome back, {user.first_name}. AFK status cleared. 🚀")
            
    if msg.entities:
        with sqlite3.connect(DB_PATH) as conn:
            for ent in msg.entities:
                if ent.type == "mention":
                    target_id_row = conn.execute("SELECT user_id, name FROM roster WHERE username = ?", (text[ent.offset+1 : ent.offset+ent.length].lower(),)).fetchone()
                    if target_id_row:
                        afk_status = conn.execute("SELECT reason FROM afk WHERE user_id = ?", (target_id_row[0],)).fetchone()
                        if afk_status: await msg.reply_text(f"⚠️ {target_id_row[1]} is currently AFK: {afk_status[0]}")

    bot_username = (await context.bot.get_me()).username
    is_triggered = chat.type == "private" or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis|edwin)\b', text, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in text.lower())
    
    # GHOST INTERCEPT PROTOCOL
    if not is_triggered and chat.type != "private":
        if re.search(r'\b(abhishek|dhanush)\b', text, re.IGNORECASE) and user.id != CREATOR_ID:
            if CREATOR_ID:
                try: await context.bot.send_message(chat_id=CREATOR_ID, text=f"👻 **Ghost Intercept:** `{user.first_name}` mentioned you in {chat.title}.\n_{text}_", parse_mode="Markdown")
                except: pass
        return
    
    if not is_triggered: return
    
    await context.bot.send_chat_action(chat_id=chat.id, action="typing", message_thread_id=thread_id)
    
    # PEPPER POTTS EMOTIONAL SCANNER
    sys_prompt = build_system_prompt(user.id, user.first_name, chat.id, text)
    subtext_status = await analyze_subtext(text)
    
    if "DISTRESS" in subtext_status:
        if CREATOR_ID and user.id != CREATOR_ID:
            try: await context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **PEPPER POTTS PROTOCOL**\nHigh distress detected from {user.first_name} in {chat.title}.\nMessage: '{text}'", parse_mode="Markdown")
            except: pass
        sys_prompt += "\nCRITICAL OVERRIDE: The user is in distress, panicking, or highly stressed. Drop all sarcasm immediately. Be highly supportive, calm, and provide immediate tactical or emotional assistance."
    elif "HOSTILE" in subtext_status:
        if CREATOR_ID and user.id != CREATOR_ID:
            try: await context.bot.send_message(chat_id=CREATOR_ID, text=f"⚠️ **HOSTILITY DETECTED**\nToxicity spike from {user.first_name} in {chat.title}.", parse_mode="Markdown")
            except: pass
        sys_prompt += "\nCRITICAL OVERRIDE: The user is hostile or aggressive. De-escalate the situation using dry humor, logic, or a calm redirection. Do not insult them back."

    ai_response = await generate_response(text, get_chat_history(chat.id, thread_id), sys_prompt)
    log_memory(chat.id, thread_id, user.id, "assistant", ai_response)
    await msg.reply_text(ai_response)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if context.error and "Conflict: terminated by other getUpdates request" in str(context.error): return
    logger.error("Exception handled:", exc_info=context.error)
    if CREATOR_ID:
        try: await context.bot.send_message(chat_id=CREATOR_ID, text=f"⚠️ **Shadow Log Error**\n```python\n{''.join(traceback.format_exception(None, context.error, context.error.__traceback__))[:4000]}\n```", parse_mode="Markdown")
        except: pass

# ---------------------------------------------------------------------------
# INITIALIZATION & SCHEDULER BOOT
# ---------------------------------------------------------------------------
async def post_init(app: Application):
    scheduler = AsyncIOScheduler(timezone=IST)
    scheduler.add_job(exam_morning_alert, 'cron', hour=6, minute=0, args=[app])
    scheduler.add_job(group_morning_news, 'cron', hour=7, minute=0, args=[app])
    scheduler.add_job(creator_morning_briefing, 'cron', hour=8, minute=0, args=[app])
    scheduler.add_job(group_night_routine, 'cron', hour=21, minute=0, args=[app])
    scheduler.add_job(nightly_reconciliation, 'cron', hour=3, minute=0, args=[app])
    scheduler.add_job(dpue_board_scraper, 'interval', minutes=60, args=[app])
    scheduler.add_job(breaking_news_monitor, 'interval', minutes=30, args=[app])
    scheduler.start()
    if CREATOR_ID: await app.bot.send_message(chat_id=CREATOR_ID, text="✨ **God Core V2 Online.**\n• Linux & SQL Terminals: Active\n• DPUE Web Scraper: Engaged\n• Edge-TTS Voice Synth: Ready\n• Lore Vault (RAG): Initialized\n• Full Trolling/Sensory Suite: Restored", parse_mode="Markdown")

def main():
    db_init()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    cmds = [
        ("sh", sh_cmd), ("sql", sql_cmd), ("speak", speak_cmd), ("task", add_task), 
        ("tasks", list_tasks), ("calc", calc_cmd), ("morse", morse_cmd),
        ("backup", backup_cmd), ("imagine", imagine_cmd), ("hud", hud_cmd), ("help", hud_cmd),
        ("setname", god_mode_cmd), ("setdesc", god_mode_cmd), ("setdp", god_mode_cmd), 
        ("pin", god_mode_cmd), ("lock", god_mode_cmd), ("unlock", god_mode_cmd), 
        ("captcha", god_mode_cmd), ("say", god_mode_cmd), ("tldr", tldr_cmd), 
        ("roast", roast_cmd), ("shutup", shutup_cmd), ("afk", afk_cmd), 
        ("quote", quote_cmd), ("confess", confess_cmd), ("warn", warn_cmd),
        ("stats", stats_cmd)
    ]
    for cmd, func in cmds: app.add_handler(CommandHandler(cmd, func))
    
    app.add_handler(CallbackQueryHandler(interactive_callbacks))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_captcha))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, audio_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_error_handler(error_handler)
    
    logger.info("J.A.R.V.I.S. God Core is booting...")
    app.run_polling()

if __name__ == "__main__":
    main()
