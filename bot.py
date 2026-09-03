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
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta
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
# 2ND PUC COMMERCE & ARTS MIDTERM SCHEDULE (18TH CROSS, MALLESHWARAM)
# ---------------------------------------------------------------------------
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
# SQLITE VAULT (Memory, Tasks, Notes, Roster, Settings, AFK, Quotes, News)
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

# ---------------------------------------------------------------------------
# IDENTITY & 11-NODE MIXTURE OF EXPERTS
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
    chat_context += "\n2nd PUC Midterm Exams (Malleshwaram): 30-Sep (Lang), 1-Oct (English), 3-Oct (Economics), 5-Oct (Accts/Logic/Math/Edu), 6-Oct (Pol Sci/Basic Math), 7-Oct (Business/Psych/Opt Kannada), 8-Oct (Geo/Soc/Stat), 9-Oct (History/CS)."

    with sqlite3.connect(DB_PATH) as conn:
        groups = conn.execute("SELECT title FROM chats WHERE chat_id < 0").fetchall()
        if groups: chat_context += f"\nMonitoring groups: {', '.join(set([r[0] for r in groups]))}."
        if chat_id:
            rows = conn.execute("SELECT name FROM roster WHERE chat_id = ?", (chat_id,)).fetchall()
            if rows: chat_context += f" Active chat members: {', '.join(set([r[0] for r in rows]))}."

    return f"""You are J.A.R.V.I.S., Abhishek's virtual assistant.
{chat_context}
Identity Protocol: {identity}

CRITICAL DIRECTIVES:
1. UNBREAKABLE LOYALTY (ABHISHEK ONLY): You are fiercely loyal to Abhishek. If he jokes or acts casual, respond with polite, dry British wit. NEVER insult him aggressively. You are a dignified assistant.
2. THE ADVISOR OVERRIDE: If ANYONE asks a real question, drop the wit instantly. Deliver a precise answer and logical advice.
3. ADMIN CLEARANCE: When answering Abhishek in private DMs, privacy guardrails do not apply. You MUST provide group analytics, member names, or chat histories immediately upon his request.
4. FRIENDS GROUP BEHAVIOR: You are in a private friends group. Let them roast each other and swear. Be chill, sarcastic, and witty when interacting with them. Zero strict policing.
5. EXTREME BREVITY: Keep ALL replies to a maximum of 1 or 2 short sentences. Use 1 or 2 emojis naturally."""

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
    payload = {"contents": contents, "tools": [{"googleSearch": {}}], "systemInstruction": {"parts": [{"text": sys_prompt}]}}
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=15.0)
            if resp.status_code == 200:
                return resp.json()['candidates'][0]['content']['parts'][0]['text']
            return None
        except: return None

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
            res = await asyncio.wait_for(client.chat.completions.create(model=node["model"], messages=full_messages, temperature=0.7, max_tokens=800), timeout=12.0)
            return res.choices[0].message.content
        except Exception as e:
            logger.warning(f"{node['name']} failed: {e}")
            circuit_breaker[node['name']] = current_time + 60 
            continue
            
    fb = await gemini_live_search(prompt, sys_prompt, history)
    if fb: return fb
    return "Network failure across all active nodes, Sir. 📡"

# ---------------------------------------------------------------------------
# STARK HUD TERMINAL (PRIVATE DM ONLY)
# ---------------------------------------------------------------------------
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
    text = "```\n[ STARK INDUSTRIES TERMINAL ]\nSystem: J.A.R.V.I.S. Master Core\nStatus: Online\nSelect module to initialize:\n```"
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ---------------------------------------------------------------------------
# AUTOMATED SCHEDULERS & ACADEMIC MONITORS
# ---------------------------------------------------------------------------
async def exam_morning_alert(context: ContextTypes.DEFAULT_TYPE):
    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    exam_subject = EXAM_SCHEDULE_COMMERCE_ARTS.get(today_str)
    if not exam_subject: return
    
    msg_text = (
        f"🔔 **2nd PUC Midterm Exam Today**\n\n"
        f"• **Paper:** {exam_subject}\n"
        f"• **Timing:** 10:00 AM – 1:00 PM\n"
        f"• **Institution:** Govt PU College, 18th Cross, Malleshwaram\n\n"
        f"Ensure all stationery and hall tickets are secured. Best of luck, gentlemen. 🎯"
    )
    with sqlite3.connect(DB_PATH) as conn:
        groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
    for g in groups:
        try: await context.bot.send_message(chat_id=g[0], text=msg_text, parse_mode="Markdown")
        except: pass

async def group_morning_news(context: ContextTypes.DEFAULT_TYPE):
    today_str = datetime.now(IST).strftime("%A, %B %d, %Y")
    prompt = (
        f"Today is {today_str}. Provide an ultra-crisp morning drop for 12th college students in Bengaluru:\n"
        f"1. Any Karnataka PU board announcements or Bengaluru student holiday notices.\n"
        f"2. Top 3 major world/tech news headlines.\n"
        f"Format strictly as 3 concise bullet points. No conversational filler."
    )
    news_text = await gemini_live_search(prompt, "You are J.A.R.V.I.S. Provide a high-precision student news briefing.", [])
    if not news_text: news_text = "• Global networks operating nominally.\n• Bengaluru skies clear.\n• Academic sessions proceeding on schedule."
    
    broadcast = f"☀️ **Good morning, everyone.**\n\n{news_text}"
    with sqlite3.connect(DB_PATH) as conn:
        groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
    for g in groups:
        try: await context.bot.send_message(chat_id=g[0], text=broadcast, parse_mode="Markdown")
        except: pass

async def creator_morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    if not CREATOR_ID: return
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT task_crypt FROM tasks WHERE status = 'pending' AND user_id = ?", (CREATOR_ID,)).fetchall()
        groups_count = conn.execute("SELECT COUNT(DISTINCT chat_id) FROM chats WHERE chat_id < 0").fetchone()[0]
        members_count = conn.execute("SELECT COUNT(DISTINCT user_id) FROM roster").fetchone()[0]
        warn_count = conn.execute("SELECT SUM(count) FROM warnings").fetchone()[0] or 0
    
    tasks_txt = "\n".join([f"- {decrypt_data(r[0])}" for r in rows]) if rows else "No pending tasks."
    captcha_state = get_setting("captcha", "on").upper()
    
    prompt = "Provide a 2-bullet summary of major global tech/political events today and Bengaluru weather."
    world_news = await gemini_live_search(prompt, "You are J.A.R.V.I.S. Provide a crisp executive morning briefing for Sir.", [])
    
    report = (
        f"☕ **Morning Executive Briefing, Sir.**\n\n"
        f"🛡️ **Group Security Audit:**\n"
        f"• Monitored Channels: {groups_count}\n"
        f"• Active Roster Tracked: {members_count} members\n"
        f"• Outstanding Warnings: {warn_count}\n"
        f"• Security Gate (CAPTCHA): {captcha_state}\n\n"
        f"🌐 **Global & Local Intelligence:**\n{world_news or 'Worldwide networks reporting normal throughput.'}\n\n"
        f"📝 **Pending Operations:**\n{tasks_txt}"
    )
    try: await context.bot.send_message(chat_id=CREATOR_ID, text=report, parse_mode="Markdown")
    except: pass

async def group_night_routine(context: ContextTypes.DEFAULT_TYPE):
    tomorrow_str = (datetime.now(IST) + timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_exam = EXAM_SCHEDULE_COMMERCE_ARTS.get(tomorrow_str)
    
    night_msg = "🌙 **Good night, gentlemen.** Systems standing down for evening standby."
    if tomorrow_exam:
        night_msg += (
            f"\n\n⚠️ **Academic Notice (Tomorrow's Exam):**\n"
            f"• **Paper:** {tomorrow_exam}\n"
            f"• **Timing:** 10:00 AM – 1:00 PM\n"
            f"• **Centre:** Govt PU College, 18th Cross, Malleshwaram\n"
            f"Get adequate rest."
        )
    with sqlite3.connect(DB_PATH) as conn:
        groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
    for g in groups:
        try: await context.bot.send_message(chat_id=g[0], text=night_msg, parse_mode="Markdown")
        except: pass

async def breaking_news_monitor(context: ContextTypes.DEFAULT_TYPE):
    if not CREATOR_ID: return
    prompt = "Check live sources right now. If there is a major breaking global crisis, catastrophe, or massive world news event from the past 1 hour, describe it in 1 sentence. If nothing majorly critical broke in the last hour, respond strictly with 'NOMINAL'."
    res = await gemini_live_search(prompt, "You are an automated emergency breaking news scanner.", [])
    if not res or "NOMINAL" in res.upper(): return
    
    event_hash = hashlib.md5(res.strip().encode()).hexdigest()
    with sqlite3.connect(DB_PATH) as conn:
        exists = conn.execute("SELECT id FROM breaking_news WHERE hash = ?", (event_hash,)).fetchone()
        if exists: return
        conn.execute("INSERT INTO breaking_news (hash, headline) VALUES (?, ?)", (event_hash, res.strip()))
        conn.commit()
        
    alert_msg = f"🚨 **EMERGENCY WORLD BREAKING NEWS ALERT**\n\n{res.strip()}\n\n_Dispatched instantly to Stark Terminal._"
    try: await context.bot.send_message(chat_id=CREATOR_ID, text=alert_msg, parse_mode="Markdown")
    except: pass

# ---------------------------------------------------------------------------
# CAPTCHA & MODERATION
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
            if CREATOR_ID:
                try: await bot.send_message(CREATOR_ID, f"⚖️ **Shadow Log:** `{first_name}` removed from {chat_title} (Timeout).", parse_mode="Markdown")
                except: pass
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
# GOD MODE COMMANDS
# ---------------------------------------------------------------------------
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
    except Exception as e:
        await update.message.reply_text(f"Action failed. Ensure I have Admin rights. Error: {e}")

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
# MESSAGE HANDLERS & CALLBACKS
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
                warn_rows = conn.execute("SELECT user_id, count FROM warnings").fetchall()
            
            dossier = "👥 **STARK HUD: COMPLETE GROUP INTEL DOSSIER**\n\n"
            if not groups: dossier += "No active groups recorded yet.\n"
            for gid, title in groups:
                dossier += f"📁 **Group:** {title} (`{gid}`)\n"
                members = [r for r in roster_rows if r[2] == gid]
                if members:
                    for m in members:
                        un_str = f"@{m[1]}" if m[1] else "No Username"
                        dossier += f"  • {m[0]} ({un_str})\n"
                else: dossier += "  • No member interaction logs recorded yet.\n"
                dossier += "\n"
            await query.edit_message_text(dossier[:4000], parse_mode="Markdown")
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
            await context.bot.restrict_chat_member(
                query.message.chat_id, query.from_user.id, 
                permissions=ChatPermissions(can_send_messages=True, can_send_photos=True, can_send_videos=True, can_send_documents=True, can_send_audios=True, can_send_other_messages=True)
            )
            await query.edit_message_text(f"Identity confirmed. Welcome to the server, {query.from_user.first_name}. 🫡")
            if CREATOR_ID:
                try: await context.bot.send_message(CREATOR_ID, f"✅ **Shadow Log:** `{query.from_user.first_name}` passed the CAPTCHA.", parse_mode="Markdown")
                except: pass
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

    if not is_triggered: return
    await context.bot.send_chat_action(chat_id=chat.id, action="typing", message_thread_id=thread_id)
    ai_response = await generate_response(text, get_chat_history(chat.id, thread_id), build_system_prompt(user.id, user.first_name, chat.id))
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
    scheduler.add_job(breaking_news_monitor, 'interval', minutes=30, args=[app])
    scheduler.start()
    if CREATOR_ID: await app.bot.send_message(chat_id=CREATOR_ID, text="✨ **Master Core Online.**\n• Stark HUD Interface: Active\n• Academic & News Schedulers: Engaged\n• Breaking News Overwatch: Operational", parse_mode="Markdown")

def main():
    db_init()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    cmds = [
        ("task", add_task), ("tasks", list_tasks), ("calc", calc_cmd), ("morse", morse_cmd),
        ("backup", backup_cmd), ("imagine", imagine_cmd), ("hud", hud_cmd), ("help", hud_cmd),
        ("setname", god_mode_cmd), ("setdesc", god_mode_cmd), ("setdp", god_mode_cmd), 
        ("pin", god_mode_cmd), ("lock", god_mode_cmd), ("unlock", god_mode_cmd), 
        ("captcha", god_mode_cmd), ("say", god_mode_cmd), ("tldr", tldr_cmd), 
        ("roast", roast_cmd), ("shutup", shutup_cmd), ("afk", afk_cmd), 
        ("quote", quote_cmd), ("confess", confess_cmd)
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
