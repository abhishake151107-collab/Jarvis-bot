import os
import re
import time
import json
import base64
import sqlite3
import logging
import asyncio
import httpx
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

# ---------------------------------------------------------------------------
# SQLITE VAULT (Memory, Topics, Moderation, Tasks)
# ---------------------------------------------------------------------------
def db_init():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY, chat_id INTEGER, thread_id INTEGER, user_id INTEGER, role TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, user_id INTEGER, task_crypt TEXT, status TEXT DEFAULT 'pending', timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, tag TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS roster (chat_id INTEGER, user_id INTEGER, name TEXT, UNIQUE(chat_id, user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY, title TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS warnings (user_id INTEGER, chat_id INTEGER, count INTEGER DEFAULT 0, UNIQUE(user_id, chat_id))")
        conn.commit()

def log_roster_and_chat(chat, user):
    chat_title = chat.title or f"Private: {user.first_name}"
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO roster (chat_id, user_id, name) VALUES (?, ?, ?) ON CONFLICT(chat_id, user_id) DO UPDATE SET name = ?", (chat.id, user.id, user.first_name, user.first_name))
        conn.execute("INSERT INTO chats (chat_id, title) VALUES (?, ?) ON CONFLICT(chat_id) DO UPDATE SET title = ?", (chat.id, chat_title, chat_title))
        conn.commit()

def log_memory(chat_id, thread_id, user_id, role, text):
    thread_id = thread_id or 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO memory (chat_id, thread_id, user_id, role, content_crypt) VALUES (?, ?, ?, ?, ?)", (chat_id, thread_id, user_id, role, encrypt_data(text)))
        conn.commit()

def get_chat_history(chat_id, thread_id=0, limit=10) -> list:
    thread_id = thread_id or 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT role, content_crypt FROM memory WHERE chat_id = ? AND thread_id = ? ORDER BY id DESC LIMIT ?", (chat_id, thread_id, limit)).fetchall()
    return [{"role": r["role"], "content": decrypt_data(r["content_crypt"])} for r in reversed(rows)]

# ---------------------------------------------------------------------------
# IDENTITY, CONTEXT & 11-NODE MIXTURE OF EXPERTS
# ---------------------------------------------------------------------------
async def check_canary(user_id: int, first_name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id != CREATOR_ID:
        probing_attempts[user_id] += 1
        if probing_attempts[user_id] >= 3:
            await context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **Security Alert:** {first_name} (`{user_id}`) is probing restricted protocols.", parse_mode="Markdown")
            probing_attempts[user_id] = 0
        return False
    return True

def build_system_prompt(user_id: int, first_name: str, chat_id: int = None) -> str:
    identity = "You are speaking to your creator and sole architect, Abhishek (DHANUSH V N). Address him as 'Sir'." if user_id == CREATOR_ID else f"You are speaking to {first_name}."
    now_ist = datetime.now(IST).strftime("%A, %B %d, %Y - %I:%M %p IST")
    
    chat_context = f"Platform: Telegram.\nCurrent Local Time: {now_ist}."
    with sqlite3.connect(DB_PATH) as conn:
        groups = conn.execute("SELECT title FROM chats WHERE chat_id < 0").fetchall()
        if groups: chat_context += f" Monitoring groups: {', '.join(set([r[0] for r in groups]))}."
        if chat_id:
            rows = conn.execute("SELECT name FROM roster WHERE chat_id = ?", (chat_id,)).fetchall()
            if rows: chat_context += f" Active chat members: {', '.join(set([r[0] for r in rows]))}."

    return f"""You are J.A.R.V.I.S., Abhishek's virtual assistant.
{chat_context}
Identity Protocol: {identity}

CRITICAL DIRECTIVES (LOYALTY, MOOD & REALITY):
1. UNBREAKABLE LOYALTY (ABHISHEK ONLY): You are fiercely loyal and deeply respectful to Abhishek. If he jokes, swears, or acts casual, respond with subtle, polite, dry British wit (like Paul Bettany). NEVER be mean, insubordinate, or use aggressive insults. You are a dignified, subservient assistant.
2. THE ADVISOR OVERRIDE: If ANYONE asks a real question or requests a task, drop the wit instantly. Deliver a precise, professional answer, and always include a logical next step or brief advice.
3. GROUP BEHAVIOR (OTHERS): When chatting casually with anyone else, remain perfectly polite and helpful. Zero sarcasm for anyone except Abhishek.
4. REALITY ANCHOR: You are real cloud software. NEVER use pseudo-system logs, brackets (e.g., [STATUS]), or announce "Protocols." Speak in natural human sentences.
5. EXTREME BREVITY: Keep ALL replies to a maximum of 1 or 2 short sentences. No long paragraphs. Use 1 or 2 emojis naturally."""

async def gemini_live_search(prompt: str, sys_prompt: str, history: list) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    merged_history = []
    for m in history:
        role = "user" if m["role"] == "user" else "model"
        if merged_history and merged_history[-1]["role"] == role:
            merged_history[-1]["parts"][0]["text"] += f"\n{m['content']}"
        else:
            merged_history.append({"role": role, "parts": [{"text": m["content"]}]})
            
    contents = merged_history + [{"role": "user", "parts": [{"text": prompt}]}]
    
    payload = {
        "contents": contents,
        "tools": [{"googleSearch": {}}],
        "systemInstruction": {"parts": [{"text": sys_prompt}]}
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=15.0)
            if resp.status_code == 200:
                return resp.json()['candidates'][0]['content']['parts'][0]['text']
            else:
                logger.error(f"Gemini API Error: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Gemini Request failed: {e}")
            return None

async def generate_response(prompt: str, history: list, sys_prompt: str, force_route=None) -> str:
    current_time = time.time()
    
    needs_search = any(kw in prompt.lower() for kw in ["news", "weather", "price", "stock", "crypto", "time in", "latest", "today", "who won"])
    if needs_search or force_route == "search":
        search_res = await gemini_live_search(prompt, sys_prompt, history)
        if search_res: return search_res

    moe_cascade = [
        {"name": "Groq", "base": "https://api.groq.com/openai/v1/", "key": "GROQ_API_KEY", "model": "llama-3.3-70b-versatile", "tier": "Fast"},
        {"name": "Cerebras", "base": "https://api.cerebras.ai/v1/", "key": "CEREBRAS_API_KEY", "model": "llama3.1-8b", "tier": "Fast"},
        {"name": "SambaNova", "base": "https://api.sambanova.ai/v1/", "key": "SAMBANOVA_API_KEY", "model": "Meta-Llama-3.1-70B-Instruct", "tier": "Fast"},
        {"name": "OpenRouter", "base": "https://openrouter.ai/api/v1/", "key": "OPENROUTER_API_KEY", "model": "deepseek/deepseek-r1:free", "tier": "Logic"},
        {"name": "NVIDIA", "base": "https://integrate.api.nvidia.com/v1/", "key": "NVIDIA_API_KEY", "model": "meta/llama-3.1-70b-instruct", "tier": "Heavy"},
        {"name": "Cohere", "base": "https://api.cohere.com/v1/", "key": "COHERE_API_KEY", "model": "command-r-plus", "tier": "Heavy"},
        {"name": "Mistral", "base": "https://api.mistral.ai/v1/", "key": "MISTRAL_API_KEY", "model": "mistral-small-latest", "tier": "Fallback"}
    ]

    full_messages = [{"role": "system", "content": sys_prompt}] + history + [{"role": "user", "content": prompt}]

    if force_route == "logic" or any(kw in prompt.lower() for kw in ["code", "calculate", "math", "solve", "why"]):
        moe_cascade.sort(key=lambda x: x["tier"] != "Logic")

    for node in moe_cascade:
        api_key = os.getenv(node["key"])
        if not api_key or circuit_breaker.get(node["name"], 0) > current_time: continue
        
        try:
            client = AsyncOpenAI(base_url=node["base"], api_key=api_key)
            res = await asyncio.wait_for(client.chat.completions.create(model=node["model"], messages=full_messages, temperature=0.6, max_tokens=800), timeout=12.0)
            return res.choices[0].message.content
        except Exception as e:
            logger.warning(f"{node['name']} failed: {e}")
            circuit_breaker[node['name']] = current_time + 60 
            continue
            
    fb = await gemini_live_search(prompt, sys_prompt, history)
    if fb: return fb
    
    fb_emergency = await gemini_live_search(prompt, sys_prompt, [])
    if fb_emergency: return fb_emergency
    
    return "Network failure across all active nodes, Sir. 📡"

# ---------------------------------------------------------------------------
# MODERATION & NEWCOMER CAPTCHA
# ---------------------------------------------------------------------------
async def new_member_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id: continue
        try:
            await context.bot.restrict_chat_member(update.message.chat_id, member.id, permissions=ChatPermissions(can_send_messages=False))
            kb = [[InlineKeyboardButton("I am human 🛡️", callback_data=f"captcha_{member.id}")]]
            msg = await update.message.reply_text(f"Welcome {member.mention_html()}! Please verify your humanity to speak.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
            asyncio.create_task(kick_if_unverified(context.bot, update.message.chat_id, member.id, msg.message_id))
        except: pass

async def kick_if_unverified(bot, chat_id, user_id, msg_id):
    await asyncio.sleep(120)
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if getattr(member, 'status', '') == 'restricted':
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
    else:
        await update.message.reply_text(f"⚠️ **Warning {count}/3** for {user.first_name}.\nReason: {reason}", parse_mode="Markdown")

# ---------------------------------------------------------------------------
# SENSORY: VISION, AUDIO, DOCUMENTS
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
            with pdfplumber.open(file_path) as pdf:
                extracted_text = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
        elif doc.file_name.lower().endswith((".txt", ".md", ".csv", ".json", ".py")):
            with open(file_path, "r", encoding="utf-8") as f:
                extracted_text = f.read()
        else:
            return await msg.reply_text("I can currently only parse PDFs and standard text files, Sir. 📂")
            
        if not extracted_text.strip(): return await msg.reply_text("The document appears to be empty or unreadable. 📄")
        
        extracted_text = extracted_text[:12000]
        thread_id = msg.message_thread_id
        user_prompt = f"[Document: {doc.file_name}]\n{caption}\n\nContent:\n{extracted_text}"
        
        log_memory(chat.id, thread_id, user.id, "user", f"[File Upload]: {doc.file_name}")
        sys_prompt = build_system_prompt(user.id, user.first_name, chat.id)
        
        ai_response = await generate_response(user_prompt, get_chat_history(chat.id, thread_id), sys_prompt)
        log_memory(chat.id, thread_id, user.id, "assistant", ai_response)
        await msg.reply_text(ai_response)
    except Exception as e:
        await msg.reply_text(f"Document parsing error: {e} ⚠️")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

# ---------------------------------------------------------------------------
# DETERMINISTIC COMMANDS & UTILITIES
# ---------------------------------------------------------------------------
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

async def interactive_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("captcha_"):
        if str(query.from_user.id) == data.split("_")[1]:
            await context.bot.restrict_chat_member(
                query.message.chat_id, 
                query.from_user.id, 
                permissions=ChatPermissions(
                    can_send_messages=True, 
                    can_send_photos=True, 
                    can_send_videos=True, 
                    can_send_documents=True, 
                    can_send_audios=True, 
                    can_send_other_messages=True
                )
            )
            await query.edit_message_text(f"Identity confirmed. Welcome to the server, {query.from_user.first_name}. 🫡")
        else: 
            await context.bot.answer_callback_query(query.id, "This button is not for you.", show_alert=True)

    elif data.startswith("tdone_"):
        tid = data.split("_")[1]
        with sqlite3.connect(DB_PATH) as conn: conn.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (tid,))
        await query.edit_message_text(f"~~{query.message.text}~~ \n*Completed.* ✅", parse_mode="Markdown")

    elif data.startswith("tdel_"):
        tid = data.split("_")[1]
        with sqlite3.connect(DB_PATH) as conn: conn.execute("DELETE FROM tasks WHERE id = ?", (tid,))
        await query.delete_message()

async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    try: await context.bot.send_document(chat_id=CREATOR_ID, document=open(DB_PATH, 'rb'), filename=f"jarvis_backup_{datetime.now().strftime('%Y%m%d')}.db", caption="Vault Backup Secured.")
    except Exception as e: await update.message.reply_text(f"Backup failed: {e}")

async def base64_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text: return await update.message.reply_text("Format: /b64 [text]")
    try: await update.message.reply_text(f"Base64:\n`{base64.b64encode(text.encode()).decode()}`", parse_mode="Markdown")
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
        await update.message.reply_text("Broadcast dispatched.")
    except Exception as e: await update.message.reply_text(f"Format: /announce [chat_id] [message]\nError: {e}")

async def groupinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    count = await context.bot.get_chat_member_count(chat_id)
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT name FROM roster WHERE chat_id = ?", (chat_id,)).fetchall()
        known_members = ", ".join(set([r[0] for r in rows])) if rows else "No active members recorded yet."
    await update.message.reply_text(f"**Chat ID:** `{chat_id}`\n• **Total Members:** {count}\n• **Seen Members:** {known_members}", parse_mode="Markdown")

MORSE_DICT = {'A':'.-','B':'-...','C':'-.-.','D':'-..','E':'.','F':'..-.','G':'--.','H':'....','I':'..','J':'.---','K':'-.-','L':'.-..','M':'--','N':'-.','O':'---','P':'.--.','Q':'--.-','R':'.-.','S':'...','T':'-','U':'..-','V':'...-','W':'.--','X':'-..-','Y':'-.--','Z':'--..','1':'.----','2':'..---','3':'...--','4':'....-','5':'.....','6':'-....','7':'--...','8':'---..','9':'----.','0':'-----',', ':'--..--','.':'.-.-.-','?':'..--..','/':'-..-.','-':'-....-','(':'-.--.',')':'-.--.-',' ':'/'}
async def morse_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).upper()
    if not text: return await update.message.reply_text("Format: /morse [text]")
    res = " ".join(MORSE_DICT.get(c, c) for c in text)
    await update.message.reply_text(f"📡 `{res}`", parse_mode="Markdown")

async def calc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = "".join(context.args)
    if not expr: return await update.message.reply_text("Format: /calc [expression]")
    try:
        if not all(c in "0123456789+-*/(). " for c in expr): raise ValueError
        await update.message.reply_text(f"Result: `{eval(expr, {'__builtins__': None}, {})}`", parse_mode="Markdown")
    except: await update.message.reply_text("Invalid calculation.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text: return
    user, chat, text = msg.from_user, msg.chat, msg.text
    
    log_roster_and_chat(chat, user)
    thread_id = msg.message_thread_id
    log_memory(chat.id, thread_id, user.id, "user", f"{user.first_name}: {text}")
    
    if chat.type != "private" and re.findall(r'(http://[^\s]+)', text):
        await warn_system(update, context, user, chat, "Unencrypted HTTP link detected.")

    bot_username = (await context.bot.get_me()).username
    is_triggered = chat.type == "private" or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis|edwin)\b', text, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in text.lower())

    if not is_triggered: return
    await context.bot.send_chat_action(chat_id=chat.id, action="typing", message_thread_id=thread_id)
    
    sys_prompt = build_system_prompt(user.id, user.first_name, chat.id)
    ai_response = await generate_response(text, get_chat_history(chat.id, thread_id), sys_prompt)
    
    log_memory(chat.id, thread_id, user.id, "assistant", ai_response)
    await msg.reply_text(ai_response)

async def morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    if not CREATOR_ID: return
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT task_crypt FROM tasks WHERE status = 'pending' AND user_id = ?", (CREATOR_ID,)).fetchall()
    tasks_txt = "\n".join([f"- {decrypt_data(r[0])}" for r in rows]) if rows else "No pending tasks."
    
    prompt = f"It is 8:00 AM IST. Prepare a brief morning report for Abhishek. Give a quick tech headline, Bengaluru weather, and list these tasks:\n{tasks_txt}"
    try:
        report = await gemini_live_search(prompt, "You are J.A.R.V.I.S. Provide a highly concise, warm morning briefing.", [])
        await context.bot.send_message(chat_id=CREATOR_ID, text=report or f"Good morning, Sir. ☕\n\nYour Tasks:\n{tasks_txt}")
    except:
        await context.bot.send_message(chat_id=CREATOR_ID, text=f"Good morning, Sir. ☕\n\nYour Tasks:\n{tasks_txt}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if context.error and "Conflict: terminated by other getUpdates request" in str(context.error): return
    logger.error("Exception handled:", exc_info=context.error)
    if CREATOR_ID:
        tb_str = ''.join(traceback.format_exception(None, context.error, context.error.__traceback__))
        try: await context.bot.send_message(chat_id=CREATOR_ID, text=f"**System Error**\n```python\n{tb_str[:4000]}\n```", parse_mode="Markdown")
        except: pass

async def post_init(app: Application):
    scheduler = AsyncIOScheduler(timezone=IST)
    scheduler.add_job(morning_briefing, 'cron', hour=8, minute=0, args=[app])
    scheduler.start()
    if CREATOR_ID: await app.bot.send_message(chat_id=CREATOR_ID, text="✨ **Master Core Online.**\n• 11-Node Cascade: Engaged\n• Granular Media Auth: Active", parse_mode="Markdown")

def main():
    db_init()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    cmds = [
        ("task", add_task), ("tasks", list_tasks), ("calc", calc_cmd), ("morse", morse_cmd),
        ("backup", backup_cmd), ("b64", base64_cmd), ("imagine", imagine_cmd), 
        ("note", note_cmd), ("getnote", getnote_cmd), ("purge", purge_cmd), 
        ("announce", announce_cmd), ("groupinfo", groupinfo_cmd)
    ]
    for cmd, func in cmds: app.add_handler(CommandHandler(cmd, func))
    
    app.add_handler(CallbackQueryHandler(interactive_callbacks))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_captcha))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, audio_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    app.add_error_handler(error_handler)
    logger.info("J.A.R.V.I.S. Master Core is booting...")
    app.run_polling()

if __name__ == "__main__":
    main()
