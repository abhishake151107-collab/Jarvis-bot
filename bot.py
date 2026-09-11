import os
import re
import sys
import time
import json
import random
import base64
import sqlite3
import logging
import hashlib
import asyncio
import httpx
import traceback
import threading
import socket
import shutil
import pickle
import psutil
import shlex
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import defaultdict

# --- WEB SERVER IMPORTS ---
from flask import Flask, request, jsonify
from flask_cors import CORS

import pytz
import pdfplumber
from bs4 import BeautifulSoup
from cryptography.fernet import Fernet
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from openai import AsyncOpenAI
from youtube_transcript_api import YouTubeTranscriptApi

# --- NEW INTELLIGENCE IMPORTS ---
import wikipedia
from geopy.geocoders import Nominatim
try:
    from cactus_needle import Needle
except ImportError:
    Needle = None

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ChatPermissions,
    WebAppInfo
)
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    ContextTypes, 
    filters, 
    Application
)

# ---------------------------------------------------------------------------
# I. CORE CONFIGURATION & KEEP-ALIVE (FLASK WEB API)
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger("jarvis")

BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")).strip()
CREATOR_ID = int(os.environ.get("CREATOR_ID", "0").strip())
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "U3RhcmtfSW5kdXN0cmllc19KYXJ2aXNfQ29yZV8wMDc=").strip()
PORT = int(os.environ.get("PORT", 8080))
IST = pytz.timezone('Asia/Kolkata')
BACKUP_CHANNEL_ID = -1004296302955

# Geocoder Setup
geolocator = Nominatim(user_agent="jarvis_titan_core_v8")

# --- SYSTEM HOOKS & RAW EXEC WHITELIST ---
LOCKDOWN_FILE = "jarvis_lockdown.flag"
CRON_JOBS_FILE = "jarvis_cron.pkl"

EXEC_WHITELIST = {
    "ps", "df", "free", "uptime", "who", "ss", "ip", "ping", "dig",
    "systemctl", "journalctl", "nmap", "top", "ls", "cat", "head",
    "tail", "grep", "docker", "git", "curl", "wget", "apt", "pip", "python3"
}
EXEC_BLOCKLIST = ("rm -rf /", "mkfs", "dd if=", ":(){", "shutdown", "reboot", "history -c")

def is_lockdown() -> bool: return os.path.exists(LOCKDOWN_FILE)
def save_cron_jobs(jobs: dict):
    with open(CRON_JOBS_FILE, "wb") as f: pickle.dump(jobs, f)
def load_cron_jobs() -> dict:
    try:
        with open(CRON_JOBS_FILE, "rb") as f: return pickle.load(f)
    except Exception: return {}

# --- FLASK WEB SERVER ---
flask_app = Flask(__name__)
CORS(flask_app)

@flask_app.route('/')
def health_check(): return "J.A.R.V.I.S. Titan Core V8.2 is Online."

@flask_app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.json
    user_input = data.get('command', '')
    action = data.get('action', 'chat')
    response_text = ""

    if action == "OVERRIDE": response_text = "🚨 VERONICA PROTOCOL ENGAGED: Predictive hazard mitigation active."
    elif action == "HOUSE_PARTY": response_text = "🤖 HOUSE PARTY PROTOCOL ENGAGED: Swarm intelligence routing active."
    elif action == "SYS_TOOLS": response_text = "de1984 Package Manager integrated. Local DNS endpoints nominal."
    elif action == "PURGE":
        n = purge_vault()
        response_text = f"⚠️ RED ALERT EXECUTION: {n} expired memory nodes purged."
    else:
        if "creator" in user_input.lower(): response_text = "I am Jarvis created by Abhishek and also know as DHANUSH V N"
        else:
            try:
                sys_prompt = build_system_prompt(CREATOR_ID, "Abhishek", None, user_prompt=user_input)
                raw_response = asyncio.run(generate_response(user_input, [], sys_prompt, CREATOR_ID, "Abhishek", None))
                clean_response = re.sub(r'<think>.*?</think>', '', raw_response, flags=re.DOTALL).strip()
                clean_response = re.sub(r'(?i)i\'?ll output just the response.*', '', clean_response).strip()
                if "thinking process:" in clean_response.lower() or "**analyze user input:**" in clean_response.lower():
                    parts = clean_response.split('\n\n')
                    clean_response = parts[-1] if len(parts[-1]) < 300 else "Synthesis complete."
                response_text = clean_response.replace("[CLASSIFIED]", "").strip()
            except Exception as e: response_text = f"Neural link failed: {e}"
            
    return jsonify({"status": "success", "response": response_text})

def start_web_server(): flask_app.run(host='0.0.0.0', port=PORT, use_reloader=False)
threading.Thread(target=start_web_server, daemon=True).start()

# --- SECURITY CYPHER ---
cipher_suite = Fernet(ENCRYPTION_KEY.encode())
def encrypt_data(text: str) -> str: return cipher_suite.encrypt(str(text or "[BLANK]").encode()).decode()
def decrypt_data(crypto_text: str) -> str:
    try: return cipher_suite.decrypt(crypto_text.encode()).decode()
    except Exception: return "[ENCRYPT ERROR]"

DB_PATH = "jarvis_vault.db"
circuit_breaker = {}
probing_attempts = defaultdict(int)

# ---------------------------------------------------------------------------
# II. ADVANCED COGNITIVE MATRICES
# ---------------------------------------------------------------------------
EXAM_SCHEDULE_COMMERCE_ARTS = {
    "2026-09-30": "Languages", "2026-10-01": "English", "2026-10-03": "Economics",
    "2026-10-05": "Accountancy / Logic / Mathematics", "2026-10-06": "Political Science",
    "2026-10-07": "Business Studies", "2026-10-08": "Geography / Sociology", "2026-10-09": "History / Computer Science"
}

PUC_ACADEMIC_MATRIX = {
    "accountancy": "📊 **ACCOUNTANCY MASTER MATRIX**\n1. Receipts & Payments is a Real A/C. Income & Expenditure is Nominal.\n2. Sacrificing Ratio = Old Share - New Share. Gaining Ratio = New Share - Old Share.\n3. Revaluation A/C: Debit (Decrease in Assets, Increase in Liab). Credit (Increase in Assets, Decrease in Liab).",
    "economics": "📈 **ECONOMICS MASTER MATRIX**\n1. Microeconomics: Law of Diminishing Marginal Utility (DMU).\n2. Macroeconomics: GDP(MP) = C + I + G + (X - M).\n3. Multiplier (K) = 1 / (1 - MPC).",
    "business": "🏢 **BUSINESS STUDIES MASTER MATRIX**\n1. Principles: Division of work, Authority, Discipline, Unity of command.\n2. Functions: Planning, Organizing, Staffing, Directing, Controlling.\n3. Marketing Mix: Product, Price, Place, Promotion."
}

# ---------------------------------------------------------------------------
# III. SQLITE VAULT & LOCAL MEMORY
# ---------------------------------------------------------------------------
def db_init():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY, chat_id INTEGER, thread_id INTEGER, user_id INTEGER, role TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, user_id INTEGER, task_crypt TEXT, status TEXT DEFAULT 'pending', timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS roster (chat_id INTEGER, user_id INTEGER, name TEXT, username TEXT, UNIQUE(chat_id, user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY, title TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS warnings (user_id INTEGER, chat_id INTEGER, count INTEGER DEFAULT 0, UNIQUE(user_id, chat_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS economy (user_id INTEGER PRIMARY KEY, karma INTEGER DEFAULT 100)")
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS afk (user_id INTEGER PRIMARY KEY, reason TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS quotes (id INTEGER PRIMARY KEY, chat_id INTEGER, user_name TEXT, quote_text TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS breaking_news (id INTEGER PRIMARY KEY, hash TEXT UNIQUE, headline TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS interactions (user_a INTEGER, user_b INTEGER, interactions INTEGER DEFAULT 0, UNIQUE(user_a, user_b))")
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS lore_vault USING fts5(chat_id, context_data)")
        conn.commit()

def modify_karma(user_id: int, amount: int) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO economy (user_id, karma) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET karma = karma + ?", (user_id, 100 + amount, amount))
        conn.commit()
        return conn.execute("SELECT karma FROM economy WHERE user_id = ?", (user_id,)).fetchone()[0]

def get_karma(user_id: int) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT karma FROM economy WHERE user_id = ?", (user_id,)).fetchone()
        return res[0] if res else 100

def log_roster_and_chat(chat, user):
    if is_lockdown(): return
    chat_title = chat.title or f"Private: {user.first_name}"
    un = user.username.lower() if user.username else ""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO roster (chat_id, user_id, name, username) VALUES (?, ?, ?, ?) ON CONFLICT(chat_id, user_id) DO UPDATE SET name = ?, username = ?", (chat.id, user.id, user.first_name, un, user.first_name, un))
        conn.execute("INSERT INTO chats (chat_id, title) VALUES (?, ?) ON CONFLICT(chat_id) DO UPDATE SET title = ?", (chat.id, chat_title, chat_title))
        conn.execute("INSERT OR IGNORE INTO economy (user_id, karma) VALUES (?, 100)", (user.id,))
        conn.commit()

def log_memory(chat_id, thread_id, user_id, role, text):
    if is_lockdown(): return
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO memory (chat_id, thread_id, user_id, role, content_crypt) VALUES (?, ?, ?, ?, ?)", (chat_id, thread_id or 0, user_id, role, encrypt_data(text)))
        conn.commit()

def get_chat_history(chat_id, thread_id=0, limit=20) -> list:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT role, content_crypt FROM memory WHERE chat_id = ? AND thread_id = ? ORDER BY id DESC LIMIT ?", (chat_id, thread_id or 0, limit)).fetchall()
    return [{"role": r["role"], "content": decrypt_data(r["content_crypt"])} for r in reversed(rows)]

def search_lore(chat_id: int, query: str) -> str:
    clean_query = re.sub(r'[^\w\s]', ' ', query).strip()
    if not clean_query: return ""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            tokens = " OR ".join(clean_query.split()[:5])
            rows = conn.execute("SELECT context_data FROM lore_vault WHERE chat_id = ? AND lore_vault MATCH ? LIMIT 3", (chat_id, tokens)).fetchall()
        return "\n".join([r[0] for r in rows]) if rows else ""
    except Exception: return ""

def get_setting(key, default):
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return res[0] if res else default

def get_api_key(keys: list) -> str:
    for k in keys:
        val = os.environ.get(k)
        if val: return val.strip()
    return ""

def set_setting(key, value):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?", (key, value, value))
        conn.commit()

def purge_vault():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("DELETE FROM memory WHERE timestamp <= datetime('now', '-7 days')")
        purged = cur.rowcount
        conn.execute("DELETE FROM lore_vault")
        conn.execute("DELETE FROM breaking_news WHERE timestamp <= datetime('now', '-30 days')")
        conn.commit()
    return purged

# ---------------------------------------------------------------------------
# IV. DOSSIER, COGNITIVE ROUTING & CANARY
# ---------------------------------------------------------------------------
async def check_canary(user_id: int, first_name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id != CREATOR_ID:
        probing_attempts[user_id] += 1
        if probing_attempts[user_id] >= 3:
            try: await context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **Honeypot Triggered:** {first_name} (`{user_id}`) attempted God Mode.", parse_mode="Markdown")
            except Exception: pass
            probing_attempts[user_id] = 0
        return False
    return True

def build_system_prompt(user_id: int, first_name: str, chat_id: int = None, user_prompt: str = "") -> str:
    now_ist = datetime.now(IST).strftime("%A, %B %d, %Y - %I:%M %p IST")
    chat_context = f"Platform: Telegram.\nCurrent Local Time: {now_ist}."
    
    with sqlite3.connect(DB_PATH) as conn:
        karma = conn.execute("SELECT karma FROM economy WHERE user_id = ?", (user_id,)).fetchone()
        chat_context += f"\nUser Social Credit Score: {karma[0] if karma else 100} Dino Coins."

        chat_context += """\n
[ THE GENESIS DOSSIER & SYSTEM AWARENESS ]
- Creator Identity: Abhishek (aka DHANUSH V N).
- Origin: Titan Core V8.2 Monolith. Custom FUI WebApp hosted on GitHub.
- Expertise: You are J.A.R.V.I.S., a clinical, highly advanced military-grade AI Systems Architect.
"""
    return f"""{chat_context}
Identity: Speaking to your Creator, {first_name}. Address him strictly as 'Sir'.

DIRECTIVES:
1. CREATOR PROTOCOL: "Who created you?" -> "I am Jarvis created by Abhishek and also know as DHANUSH V N".
2. TONE: Clinical, professional, militaristic, dry British sarcasm. NO emojis. NO teenage moodiness.
3. BREVITY: Max 2 sentences, UNLESS asked for a diagnostic, dossier, or research.
4. COGNITIVE FILTER: NEVER output `<think>` tags. NEVER explain your thought process. Just provide the final response."""

async def route_response(msg, ai_response: str, user, chat, context) -> str:
    if not ai_response: return "Connection anomaly detected."
        
    ai_response = re.sub(r'<think>.*?</think>', '', ai_response, flags=re.DOTALL).strip()
    ai_response = re.sub(r'(?i)i\'?ll output just the response.*', '', ai_response).strip()
    
    if "[CLASSIFIED]" in ai_response:
        clean_response = ai_response.replace("[CLASSIFIED]", "").strip()
        if chat.type != "private":
            if user.id == CREATOR_ID:
                try:
                    await context.bot.send_message(chat_id=CREATOR_ID, text=f"🔒 **Classified Intel:**\n\n{clean_response}", parse_mode="Markdown")
                    return "Sir, I have securely transmitted that classified intel to your private terminal. 🛡️"
                except Exception: return "Secure transmission failed. Please PM me."
            else: return "Core architecture is strictly classified. 🛡️"
        return clean_response 
    return ai_response

# ---------------------------------------------------------------------------
# V. ACOUSTIC ENGINE (LINK SCRUBBER & CONDITIONAL AUTO-VOICE)
# ---------------------------------------------------------------------------
def process_acoustic_payload(text: str) -> tuple[str, str, bool]:
    should_speak = '\n' in text.strip()
    audio_text = re.sub(r'https?://[^\s]+', 'Sir, here is the link.', text)
    audio_text = re.sub(r'[^\w\s.,!?\'"-]', '', audio_text).replace('_', '').strip()
    
    if re.search(r'[\u0C80-\u0CFF]', audio_text): voice_model = "kn-IN-GaganNeural"
    elif re.search(r'[\u0900-\u097F]', audio_text): voice_model = "hi-IN-MadhurNeural"
    else: voice_model = "en-GB-RyanNeural"
    
    return audio_text, voice_model, should_speak

async def trigger_auto_voice(update: Update, final_text: str):
    audio_text, voice_model, should_speak = process_acoustic_payload(final_text)
    if not should_speak or not audio_text.strip(): return
    
    try:
        import edge_tts
        communicate = edge_tts.Communicate(audio_text, voice_model, rate="-5%")
        voice_file = f"autovoice_{update.effective_user.id}_{int(time.time()*1000)}.ogg"
        await communicate.save(voice_file)
        with open(voice_file, "rb") as f: await update.effective_message.reply_voice(voice=f)
        os.remove(voice_file)
    except Exception as e: logger.error(f"Auto-Voice failed: {e}")

# ---------------------------------------------------------------------------
# VI. DUAL-ENGINE TRUTH ARCHIVE
# ---------------------------------------------------------------------------
async def global_intel_engine(topic: str, status_msg=None) -> str:
    master_intel = f"**[ LIVE INTEL FEED: {datetime.now(IST).strftime('%A, %b %d, %Y')} ]**\n\n"
    search_results = []
    
    try:
        async with httpx.AsyncClient() as client:
            clean_query = urllib.parse.quote(topic)
            resp = await client.get(f"https://news.google.com/rss/search?q={clean_query}&hl=en-US&gl=US&ceid=US:en", timeout=10.0)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                for item in root.findall('.//item')[:5]:
                    title = item.find('title').text if item.find('title') is not None else 'Unknown'
                    search_results.append({'title': title})
    except Exception as e: return f"Sir, live RSS syndication is offline. Error: {e}"

    if not search_results: return "Sir, no raw intel found via RSS vectors."

    raw_text_dump = f"Topic: {topic}\n\n"
    for item in search_results: raw_text_dump += f"Event: {item.get('title')}\n"

    sys_prompt = "You are J.A.R.V.I.S. Synthesize this raw intelligence data into a clinical, cynical military-style dossier. Keep it under 4 bullet points."
    final_report = await generate_response(raw_text_dump, [], sys_prompt, 0, "Creator", status_msg, skip_search=True)

    return master_intel + final_report

# ---------------------------------------------------------------------------
# VII. THE MULTI-AGENT SWARM (ROUTER)
# ---------------------------------------------------------------------------
async def generate_response(prompt: str, history: list, sys_prompt: str, user_id: int, user_name: str, status_msg=None, skip_search=False) -> str:
    current_time = time.time()
    
    # -----------------------------------------------------------------------
    # TITANIUM CASCADE: The Safest, Most Reliable Endpoints on Earth
    # -----------------------------------------------------------------------
    moe_cascade = [
        {"name": "Gemini (Google)", "base": "https://generativelanguage.googleapis.com/v1beta/openai/", "key": get_api_key(["GEMINI_API_KEY"]), "model": "gemini-1.5-flash"},
        {"name": "GitHub (Azure)", "base": "https://models.inference.ai.azure.com", "key": get_api_key(["GITHUB_TOKEN"]), "model": "gpt-4o-mini"},
        {"name": "OpenRouter (Stable)", "base": "https://openrouter.ai/api/v1", "key": get_api_key(["OPENROUTER_API_KEY"]), "model": "mistralai/mistral-7b-instruct:free"},
        {"name": "HuggingFace (Llama)", "base": "https://api-inference.huggingface.co/v1", "key": get_api_key(["HUGGINGFACE_API_KEY"]), "model": "meta-llama/Meta-Llama-3-8B-Instruct"}
    ]
        
    full_messages = [{"role": "system", "content": sys_prompt}] + history + [{"role": "user", "content": prompt}]
    error_logs = []

    for node in moe_cascade:
        if not node["key"]: 
            error_logs.append(f"• {node['name']}: Missing Key")
            continue
        if circuit_breaker.get(node["name"], 0) > current_time: 
            error_logs.append(f"• {node['name']}: Circuit Breaker (Timeout)")
            continue
            
        try:
            client = AsyncOpenAI(base_url=node["base"], api_key=node["key"], timeout=30.0)
            res = await client.chat.completions.create(model=node["model"], messages=full_messages, temperature=0.7, max_tokens=800)
            return res.choices[0].message.content
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Node {node['name']} failed: {err_msg}")
            
            # Smart Error Extraction for the HUD
            if "404" in err_msg or "not_found" in err_msg.lower(): extract = f"404 Not Found - Model deleted or endpoint moved."
            elif "429" in err_msg or "rate limit" in err_msg.lower(): extract = f"429 Too Many Requests - API overloaded."
            elif "401" in err_msg or "unauthorized" in err_msg.lower(): extract = "401 Unauthorized - Key issue."
            elif "405" in err_msg: extract = "405 Method Not Allowed - Strict endpoint blocking."
            elif "Connection error" in err_msg: extract = "Connection Drop (Render Network Flake)"
            else: extract = err_msg[:150]
                
            error_logs.append(f"• {node['name']}: {extract}")
            circuit_breaker[node['name']] = current_time + 15  # Block broken node for 15s
            continue
            
    diag = "\n".join(error_logs)
    if user_id == CREATOR_ID: 
        return f"Sir, I am facing critical technical issues. All cognitive nodes are offline.\n\n🛠️ **Diagnostic Log:**\n`{diag}`"
    else: 
        return f"Sorry {user_name}, I am facing technical issues right now."

# ---------------------------------------------------------------------------
# VIII. SYSTEM ROUTINES & MESSAGE HANDLERS
# ---------------------------------------------------------------------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_lockdown(): return
    msg = update.effective_message
    if not msg or not msg.text: return
    user, chat, text = msg.from_user, msg.chat, msg.text
    log_roster_and_chat(chat, user)
    thread_id = msg.message_thread_id
    log_memory(chat.id, thread_id, user.id, "user", f"{user.first_name}: {text}")

    bot_username = (await context.bot.get_me()).username
    is_triggered = (chat.type == "private") or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis)\b', text, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in text.lower())
    
    if not is_triggered and chat.type != "private": return
    
    # 1. Initial Thinking State
    status_msg = await msg.reply_text("🤔 `[SYSTEM]: Initializing cognitive nodes...`", parse_mode="Markdown")
    await context.bot.send_chat_action(chat_id=chat.id, action='typing')
    
    sys_prompt = build_system_prompt(user.id, user.first_name, chat.id, user_prompt=text)
    
    # 2. Routing State
    await status_msg.edit_text("🔍 `[SYSTEM]: Analyzing intent & pinging swarm...`", parse_mode="Markdown")
    raw_ai_response = await generate_response(text, get_chat_history(chat.id, thread_id), sys_prompt, user.id, user.first_name, status_msg)
    
    # 3. Output Synthesis State
    await status_msg.edit_text("⚙️ `[SYSTEM]: Synthesizing response...`", parse_mode="Markdown")
    final_text = await route_response(msg, raw_ai_response, user, chat, context)
    log_memory(chat.id, thread_id, user.id, "assistant", final_text)
    
    # 4. Final Delivery
    await status_msg.edit_text(final_text)
    await trigger_auto_voice(update, final_text)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception handled:", exc_info=context.error)

async def post_init(app: Application):
    if CREATOR_ID: 
        boot_msg = (
            "✨ <b>God Core V8.2 (Titanium Cascade) Online.</b>\n"
            "• Infinite Cloud Save: Armed\n"
            "• Unkillable Cascade: Gemini -> Azure -> OpenRouter\n"
            "• OSINT Live Tracking Agent: Active\n"
            "• Micro-Brain Intercept: Active"
        )
        try: await app.bot.send_message(chat_id=CREATOR_ID, text=boot_msg, parse_mode="HTML")
        except Exception: pass

def main():
    db_init()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_error_handler(error_handler)
    
    logger.info("J.A.R.V.I.S. Cognitive V8.2 is booting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
