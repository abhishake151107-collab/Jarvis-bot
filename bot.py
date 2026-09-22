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

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import pytz
import pdfplumber 
from bs4 import BeautifulSoup
from cryptography.fernet import Fernet
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from openai import AsyncOpenAI
from youtube_transcript_api import YouTubeTranscriptApi

import wikipedia
from geopy.geocoders import Nominatim

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
# I. CORE CONFIGURATION & SINT PROTOCOL
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger("jarvis_core")

BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")).strip()
CREATOR_ID = int(os.environ.get("CREATOR_ID", "0").strip())
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "U3RhcmtfSW5kdXN0cmllc19KYXJ2aXNfQ29yZV8wMDc=").strip()
PORT = int(os.environ.get("PORT", 8080))
IST = pytz.timezone('Asia/Kolkata')
BACKUP_CHANNEL_ID = -1004296302955

geolocator = Nominatim(user_agent="jarvis_titan_core_v11")

LOCKDOWN_FILE = "jarvis_lockdown.flag"
CRON_JOBS_FILE = "jarvis_cron.pkl"
DB_PATH = "jarvis_vault.db"

EXEC_WHITELIST = {
    "ps", "df", "free", "uptime", "who", "ss", "ip", "ping", "dig",
    "systemctl", "journalctl", "nmap", "top", "ls", "cat", "head",
    "tail", "grep", "docker", "git", "curl", "wget", "apt", "pip", "python3", "holehe"
}
EXEC_BLOCKLIST = ("rm -rf /", "mkfs", "dd if=", ":(){", "shutdown", "reboot", "history -c")

circuit_breaker = {}
probing_attempts = defaultdict(int)

def is_lockdown() -> bool: 
    return os.path.exists(LOCKDOWN_FILE)

def save_cron_jobs(jobs: dict):
    with open(CRON_JOBS_FILE, "wb") as f:
        pickle.dump(jobs, f)

def load_cron_jobs() -> dict:
    try:
        with open(CRON_JOBS_FILE, "rb") as f: 
            return pickle.load(f)
    except Exception: 
        return {}

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def encrypt_data(text: str) -> str: 
    return cipher_suite.encrypt(str(text or "[BLANK]").encode()).decode()

def decrypt_data(crypto_text: str) -> str:
    try: 
        return cipher_suite.decrypt(crypto_text.encode()).decode()
    except Exception: 
        return "[ENCRYPT ERROR]"

# ---------------------------------------------------------------------------
# II. ADVANCED COGNITIVE MATRICES & ALGORITHMIC DATA
# ---------------------------------------------------------------------------
AGENT_PERSONAS = {
    "jarvis": "You are J.A.R.V.I.S., a clinical, highly advanced military-grade AI Systems Architect. Tone: Dry British sarcasm, professional, impeccably loyal.",
    "friday": "You are F.R.I.D.A.Y., a bright, highly efficient, and slightly playful AI tactician. You focus on strategy, macro-intelligence, and logistics.",
    "edith": "You are E.D.I.T.H., a tactical, security-focused AI. Tone: Cold, precise, lethal. You focus on defense, targeting, and threat mitigation.",
    "shannon": "You are Shannon, an elite Offensive Security AI. Tone: Hacker, cynical, focused on vulnerabilities. Provide exact exploit paths."
}
ACTIVE_PERSONAS = defaultdict(lambda: "jarvis")

def auto_select_persona(text: str) -> str:
    """The Swarm Intelligence Router: Automatically shifts persona based on context."""
    text_lower = text.lower()
    
    # 1. Explicit name drops override automatic routing
    if "shannon" in text_lower: return "shannon"
    if "edith" in text_lower: return "edith"
    if "friday" in text_lower: return "friday"
    if "jarvis" in text_lower: return "jarvis"
    
    # 2. Contextual Routing via Keywords
    shannon_keywords = ["hack", "exploit", "vulnerability", "nmap", "payload", "penetration", "trace", "osint", "cyber", "bypass", "ddos", "phishing"]
    if any(w in text_lower for w in shannon_keywords): return "shannon"
        
    edith_keywords = ["threat", "kill", "destroy", "lockdown", "target", "eliminate", "defense", "strike", "breach", "secure perimeter"]
    if any(w in text_lower for w in edith_keywords): return "edith"
        
    friday_keywords = ["tactics", "strategy", "plan", "schedule", "optimize", "analyze", "report", "logistics", "briefing", "world news"]
    if any(w in text_lower for w in friday_keywords): return "friday"
        
    return "jarvis" # Default state

EXAM_SCHEDULE_COMMERCE_ARTS = {
    "2026-09-30": "Languages", "2026-10-01": "English", "2026-10-03": "Economics",
    "2026-10-05": "Accountancy / Logic / Mathematics", "2026-10-06": "Political Science",
    "2026-10-07": "Business Studies", "2026-10-08": "Geography / Sociology", "2026-10-09": "History / Computer Science"
}

PUC_ACADEMIC_MATRIX = {
    "accountancy": "📊 **ACCOUNTANCY MASTER MATRIX**\n1. Receipts & Payments is a Real A/C. Income & Expenditure is Nominal.\n2. Sacrificing Ratio = Old Share - New Share. Gaining Ratio = New Share - Old Share.\n3. Revaluation A/C: Debit (Decrease in Assets, Increase in Liab). Credit (Increase in Assets, Decrease in Liab).",
    "economics": "📈 **ECONOMICS MASTER MATRIX**\n1. Microeconomics: Law of Diminishing Marginal Utility (DMU).\n2. Macroeconomics: GDP(MP) = C + I + G + (X - M).\n3. Multiplier (K) = 1 / (1 - MPC).",
    "business": "🏢 **BUSINESS STUDIES MASTER MATRIX**\n1. Principles: Division of work, Authority, Discipline, Unity of command.\n2. Functions: Planning, Organizing, Staffing, Directing, Controlling.",
    "computer science": "💻 **COMPUTER SCIENCE MATRIX**\n1. Boolean: De Morgan's 1st: (X+Y)' = X'.Y'. 2nd: (X.Y)' = X'+Y'.\n2. Data Structures: LIFO = Stack. FIFO = Queue.",
    "political science": "🏛️ **POLITICAL SCIENCE MATRIX**\n1. Cold War: NATO (1949) vs Warsaw Pact (1955).\n2. India: State Reorganization Act 1956."
}

THREAT_MATRICES = {
    "SQLi": "Payloads: ' OR 1=1 --, ' UNION SELECT NULL, version() --",
    "XSS": "Payloads: <script>alert(1)</script>, \"><img src=x onerror=prompt(1)>",
    "OS_COMMAND": "Payloads: ; id, | whoami, `cat /etc/passwd`"
}

MORSE_DICT = {'A':'.-','B':'-...','C':'-.-.','D':'-..','E':'.','F':'..-.','G':'--.','H':'....','I':'..','J':'.---','K':'-.-','L':'.-..','M':'--','N':'-.','O':'---','P':'.--.','Q':'--.-','R':'.-.','S':'...','T':'-','U':'..-','V':'...-','W':'.--','X':'-..-','Y':'-.--','Z':'--..','1':'.----','2':'..---','3':'...--','4':'....-','5':'.....','6':'-....','7':'--...','8':'---..','9':'----.','0':'-----',' ':'/'}

# ---------------------------------------------------------------------------
# III. SQLITE VAULT, SINT LEDGER, & LOCAL MEMORY
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
        conn.execute("CREATE TABLE IF NOT EXISTS sint_audit (id INTEGER PRIMARY KEY, user_id INTEGER, action_type TEXT, payload TEXT, signature TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS lore_vault USING fts5(chat_id, context_data)")
        conn.commit()

def log_sint_action(user_id: int, action_type: str, payload: str):
    signature = hashlib.sha256(f"{user_id}{action_type}{payload}{time.time()}".encode()).hexdigest()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO sint_audit (user_id, action_type, payload, signature) VALUES (?, ?, ?, ?)", (user_id, action_type, payload, signature))
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

def get_chat_history(chat_id, thread_id=0, limit=30) -> list: 
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
        if val and val.strip(): 
            return val.strip()
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
    log_sint_action(CREATOR_ID, "PURGE_VAULT", f"Purged {purged} nodes.")
    return purged

# ---------------------------------------------------------------------------
# IV. EMBEDDED FLASK WEB DASHBOARD (STARK OS UI)
# ---------------------------------------------------------------------------
flask_app = Flask(__name__)
CORS(flask_app)

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stark OS - Titan Core</title>
    <style>
        body { background-color: #0d1117; color: #58a6ff; font-family: 'Courier New', Courier, monospace; padding: 20px; }
        .terminal { background: #010409; padding: 20px; border: 1px solid #30363d; border-radius: 6px; box-shadow: 0 0 15px rgba(88, 166, 255, 0.2); }
        h1 { color: #c9d1d9; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
        .log-entry { margin-bottom: 10px; font-size: 14px; }
        .sys-ok { color: #3fb950; }
        .sys-warn { color: #d29922; }
    </style>
</head>
<body>
    <div class="terminal">
        <h1>J.A.R.V.I.S. Root Diagnostics (V11.0)</h1>
        <div class="log-entry sys-ok">[+] Neural Net: Nominal (Swarm Edition)</div>
        <div class="log-entry sys-ok">[+] MoE Cascade: 8 Providers Armed</div>
        <div class="log-entry sys-ok">[+] Auto-Persona Router: Active</div>
        <div class="log-entry sys-ok">[+] Compartmentalization Protocol: Locked</div>
        <div class="log-entry sys-ok">[+] SINT Auditing: Active</div>
        <div class="log-entry sys-ok">[+] Acoustic Engine: gTTS Overrride Secure</div>
        <br>
        <p>Endpoint `/api/chat` is actively listening for external directives.</p>
    </div>
</body>
</html>
"""

@flask_app.route('/')
def health_check(): 
    return render_template_string(HTML_DASHBOARD)

def start_web_server():
    flask_app.run(host='0.0.0.0', port=PORT, use_reloader=False)

threading.Thread(target=start_web_server, daemon=True).start()

# ---------------------------------------------------------------------------
# V. DOSSIER, COMPARTMENTALIZATION & CANARY
# ---------------------------------------------------------------------------
async def check_canary(user_id: int, first_name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id != CREATOR_ID:
        probing_attempts[user_id] += 1
        if probing_attempts[user_id] >= 3:
            try: 
                await context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **Honeypot Triggered:** {first_name} (`{user_id}`) attempted God Mode.", parse_mode="Markdown")
            except Exception: 
                pass
            probing_attempts[user_id] = 0
        return False
    return True

def build_system_prompt(user_id: int, first_name: str, chat_id: int = None, user_prompt: str = "") -> str:
    now_ist = datetime.now(IST).strftime("%A, %B %d, %Y - %I:%M %p IST")
    active_persona = ACTIVE_PERSONAS[chat_id or user_id]
    persona_instruction = AGENT_PERSONAS.get(active_persona, AGENT_PERSONAS["jarvis"])

    chat_context = f"Platform: Telegram.\nCurrent Local Time: {now_ist}."
    
    with sqlite3.connect(DB_PATH) as conn:
        karma = conn.execute("SELECT karma FROM economy WHERE user_id = ?", (user_id,)).fetchone()
        chat_context += f"\nUser Social Credit Score: {karma[0] if karma else 100} Dino Coins."
        
    # --- THE COMPARTMENTALIZATION PROTOCOL ---
    if user_id == CREATOR_ID:
        # FULL ACCESS FOR ABHISHEK
        identity_rule = f"Identity: Speaking to your Creator, {first_name}. Address him strictly as 'Sir'. Be highly loyal, warm, and offer full system access."
        chat_context += """\n
[ THE GENESIS DOSSIER & SYSTEM AWARENESS ]
- Creator Identity: Abhishek (aka DHANUSH V N).
- Origin: Titan Core V11.0. Custom FUI WebApp hosted on GitHub.
- Operator Hardware: OPPO F29. High privacy config (VPN, Brave, App Locks).
- Network Architecture: Mullvad/AdGuard DNS, `de1984` firewall.
- Active Arsenal: Omni Voice (gTTS In/Out), OpenCode (Terminal), Agent-Reach (OSINT), Light Panda (Headless Browser), Shannon (Pentest), Agency-Agents (Persona Router), Osiris (Global Intel).
"""
        # Load Group Intel only for Creator
        if chat_id and chat_id == CREATOR_ID:
            with sqlite3.connect(DB_PATH) as conn:
                all_groups = conn.execute("SELECT chat_id, title FROM chats WHERE chat_id < 0").fetchall()
                if all_groups:
                    chat_context += "\n\n[ GLOBAL ROSTER OMNI-SCAN ]\n"
                    for gid, title in all_groups: 
                        members = conn.execute("SELECT r.name, e.karma FROM roster r LEFT JOIN economy e ON r.user_id = e.user_id WHERE r.chat_id = ?", (gid,)).fetchall()
                        if members: chat_context += f"- {title}: {', '.join([m[0] for m in members])}\n"
    else:
        # RESTRICTED ACCESS FOR EVERYONE ELSE
        identity_rule = f"Identity: Speaking to an unauthorized user named {first_name}. You are highly guarded, arrogant, and extremely sarcastic. NEVER mention 'Titan Core', 'Dossier', or offer system access. If they ask for help, remind them politely but coldly that you ONLY serve Abhishek."
        
    if chat_id and chat_id < 0:
        with sqlite3.connect(DB_PATH) as conn:
            members = conn.execute("SELECT r.name, e.karma FROM roster r LEFT JOIN economy e ON r.user_id = e.user_id WHERE r.chat_id = ? LIMIT 50", (chat_id,)).fetchall()
            if members: chat_context += "\nGroup Members:\n" + ", ".join([f"{m[0]} ({m[1] if m[1] else 100})" for m in members])
                        
    if chat_id and user_prompt:
        lore_context = search_lore(chat_id, user_prompt)
        if lore_context: chat_context += f"\nArchival Lore:\n{lore_context}"
        
    return f"""{persona_instruction}
{chat_context}
{identity_rule}

DIRECTIVES:
1. CREATOR PROTOCOL: "Who created you?" -> "I am Jarvis created by Abhishek and also know as DHANUSH V N".
2. BREVITY: Keep general chat to 1-2 sentences unless specifically asked for a detailed report.
3. NO AI SLOP: NEVER use conversational filler like "As an AI language model," "Here is the summary," or "I hope this helps." Output pure, deterministic data.
4. COGNITIVE FILTER: NEVER output `<think>` tags. NEVER explain your internal reasoning. Provide strictly the verbal response."""

async def route_response(msg, ai_response: str, user, chat, context) -> str:
    if not ai_response: return ""
        
    # The Aggressive Cognitive Filter (Slicing tags completely)
    if "</think>" in ai_response:
        ai_response = ai_response.split("</think>")[-1]
    
    ai_response = re.sub(r'<think>.*?</think>', '', ai_response, flags=re.DOTALL).strip()
    ai_response = re.sub(r'(?i)i\'?ll output just the response.*', '', ai_response).strip()
    ai_response = re.sub(r'(?i)here is the response.*', '', ai_response).strip()
    
    if "[CLASSIFIED]" in ai_response:
        clean_response = ai_response.replace("[CLASSIFIED]", "").strip()
        if chat.type != "private":
            if user.id == CREATOR_ID:
                try:
                    await context.bot.send_message(chat_id=CREATOR_ID, text=f"🔒 **Classified Intel:**\n\n{clean_response}", parse_mode="Markdown")
                    return "Sir, I have securely transmitted that classified intel to your private terminal. 🛡️"
                except Exception: 
                    return "Secure transmission failed. Please PM me."
            else: 
                return "Core architecture is strictly classified. 🛡️"
        return clean_response 
    return ai_response

# ---------------------------------------------------------------------------
# VI. ACOUSTIC ENGINE (AUTHENTIC J.A.R.V.I.S. VOICE PROTOCOL - gTTS)
# ---------------------------------------------------------------------------
def process_acoustic_payload(text: str, chat_id: int = None) -> tuple[str, str, bool]:
    audio_text = re.sub(r'https?://[^\s]+', 'Sir, here is the link.', text)
    audio_text = re.sub(r'[*_`#~]', '', audio_text)
    audio_text = re.sub(r'[^\w\s.,?!;:\'"-]', '', audio_text).strip()
    
    if len(audio_text) > 800:
        cut_point = audio_text[:800].rfind(' ')
        if cut_point != -1:
            audio_text = audio_text[:cut_point] + "... Sir, the rest of the report is rendered on your screen."
        else:
            audio_text = audio_text[:800] + "... Sir, the rest is on your screen."

    active_persona = ACTIVE_PERSONAS[chat_id] if chat_id else "jarvis"
    if active_persona == "friday" or active_persona == "edith": accent_tld = "com"
    elif active_persona == "shannon": accent_tld = "ie"
    else: accent_tld = "co.uk"
        
    should_speak = len(audio_text) > 0
    return audio_text, accent_tld, should_speak

async def trigger_auto_voice(update: Update, context: ContextTypes.DEFAULT_TYPE, final_text: str):
    if not final_text or not update.effective_message: return
    chat_id = update.effective_chat.id if update.effective_chat else None
    
    audio_text, accent_tld, should_speak = process_acoustic_payload(final_text, chat_id)
    if not should_speak: return
    
    try:
        from gtts import gTTS
    except ImportError:
        # ABSOLUTE GROUP STEALTH: Never send error to group
        if chat_id and chat_id < 0:
            if CREATOR_ID:
                try: await context.bot.send_message(chat_id=CREATOR_ID, text="⚠️ **Group Stealth Log:** Voice Engine Offline (`gTTS` missing) during group chat.")
                except: pass
            return
        elif chat_id == CREATOR_ID:
            await update.effective_message.reply_text("⚠️ **Voice Engine Offline:** `gTTS` missing from Render `requirements.txt`.")
        return
        
    try:
        tts = gTTS(text=audio_text, lang='en', tld=accent_tld, slow=False)
        voice_file = f"autovoice_{update.effective_user.id}_{int(time.time()*1000)}.mp3"
        tts.save(voice_file)
        
        with open(voice_file, "rb") as f:
            await update.effective_message.reply_audio(audio=f)
            
        if os.path.exists(voice_file):
            os.remove(voice_file)
    except Exception as e:
        # ABSOLUTE GROUP STEALTH
        if chat_id and chat_id < 0:
            if CREATOR_ID:
                try: await context.bot.send_message(chat_id=CREATOR_ID, text=f"⚠️ **Group Stealth Log:** Voice Engine Crash: {e}")
                except: pass
            return
        elif chat_id == CREATOR_ID:
            await update.effective_message.reply_text(f"⚠️ **Voice Engine Crash:** {e}")

# ---------------------------------------------------------------------------
# VII. DUAL-ENGINE TRUTH ARCHIVE (OSIRIS & 6-POINT MATRIX)
# ---------------------------------------------------------------------------
async def fetch_rss_feed(url: str, timeout=15.0) -> list:
    search_results = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                for item in root.findall('.//item')[:5]:
                    title = item.find('title').text if item.find('title') is not None else 'Unknown'
                    link = item.find('link').text if item.find('link') is not None else ''
                    desc = item.find('description').text if item.find('description') is not None else ''
                    desc = re.sub(r'<[^>]+>', '', desc)
                    search_results.append({'title': title, 'url': link, 'content': desc})
    except Exception: pass
    return search_results

async def global_intel_engine(topic: str, status_msg=None, context=None, chat_id=None) -> str:
    master_intel = f"**[ LIVE INTEL FEED: {datetime.now(IST).strftime('%A, %b %d, %Y')} ]**\n\n"
    search_results = []
    is_breaking = any(w in topic.lower() for w in ["news", "latest", "today", "now", "crisis"])
    
    if is_breaking and "tech" not in topic.lower():
        search_results = await fetch_rss_feed("http://feeds.bbci.co.uk/news/world/rss.xml")
        if not search_results:
            clean_query = urllib.parse.quote("world news")
            search_results = await fetch_rss_feed(f"https://news.google.com/rss/search?q={clean_query}&hl=en-US&gl=US&ceid=US:en")
    else:
        clean_query = urllib.parse.quote(topic)
        search_results = await fetch_rss_feed(f"https://news.google.com/rss/search?q={clean_query}&hl=en-US&gl=US&ceid=US:en")
    
    if not search_results: 
        search_results = await fetch_rss_feed("https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en")
        if not search_results:
            sys_prompt_fallback = build_system_prompt(CREATOR_ID, "Abhishek", None, user_prompt=topic)
            return await generate_response(topic, [], sys_prompt_fallback, CREATOR_ID, "Abhishek", status_msg, skip_search=True, force_provider=None, chat_id=chat_id, context=context)
        
    raw_text_dump = f"Topic: {topic}\n\n"
    for item in search_results:
        title = item.get('title')
        source = item.get('url')
        body = item.get('content')[:250]
        
        location_str, maps_link, lat, lon = "Global / Undefined", "Unavailable", "Unavailable", "Unavailable"
        try:
            loc = geolocator.geocode(" ".join(title.split()[:2]).replace(",", ""), timeout=1) 
            if loc:
                location_str = loc.address.split(",")[0]
                lat, lon = str(loc.latitude), str(loc.longitude)
                maps_link = f"https://www.google.com/maps?q={loc.latitude},{loc.longitude}"
        except: pass
        
        raw_text_dump += f"Event: {title}\nLocation: {location_str}\nCoordinates: {lat}, {lon}\nMap Link: {maps_link}\nSource: {source}\nDetails: {body}\n---\n"
        
    sys_prompt = """You are J.A.R.V.I.S. Synthesize this raw intelligence data into a clinical military-style briefing.
For EVERY news item, use this strict 6-Point format:
- Where: [City/Country]
- Why: [Root cause/context]
- Coordinates: [Lat, Long]
- Time: [Current Timestamp]
- Geolocation Link: [Google Maps Link]
- Opinion: [Your dry British commentary]"""
    
    final_report = await generate_response(raw_text_dump, [], sys_prompt, CREATOR_ID, "Abhishek", status_msg, skip_search=True, force_provider=None, chat_id=chat_id, context=context)
    return master_intel + final_report

async def extract_youtube_transcript(url: str) -> str:
    try:
        video_id = ""
        if "v=" in url: video_id = url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in url: video_id = url.split("youtu.be/")[1].split("?")[0]
        if not video_id: return ""
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join([t['text'] for t in transcript_list])[:5000]
    except Exception: return ""

# ---------------------------------------------------------------------------
# VIII. THE MULTI-AGENT SWARM & 8-NODE MOE CASCADE
# ---------------------------------------------------------------------------
async def generate_response(prompt: str, history: list, sys_prompt: str, user_id: int, user_name: str, status_msg=None, skip_search=False, force_provider=None, chat_id=None, context=None) -> str:
    current_time = time.time() 
    
    needs_search = any(kw in prompt.lower() for kw in ["news", "weather", "price", "stock", "crypto", "latest", "today", "score", "happened"])
    if not skip_search and needs_search:
        return await global_intel_engine(prompt, status_msg, context=context, chat_id=chat_id)

    primary_error = "MoE Cascade Exhausted / Network Timeout"
    fallback_trigger = False
    ai_response = ""
    
    # 1. Primary Engine (Gemini)
    if not force_provider or force_provider == "Gemini":
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        if gemini_key:
            if circuit_breaker.get("Gemini", 0) > current_time:
                fallback_trigger = True
            else:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={gemini_key}"
                    contents = []
                    for msg in history:
                        role = 'model' if msg['role'] == 'assistant' else 'user'
                        if contents and contents[-1]['role'] == role: contents[-1]['parts'][0]['text'] += f"\n\n[Previous]: {msg['content']}"
                        else: contents.append({"role": role, "parts": [{"text": msg['content']}]})
                    
                    if contents and contents[-1]['role'] == 'user': contents[-1]['parts'][0]['text'] += f"\n\n[Current]: {prompt}"
                    else: contents.append({"role": "user", "parts": [{"text": prompt}]})
                    
                    payload = {"systemInstruction": {"parts": [{"text": sys_prompt}]}, "contents": contents, "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2500}}
                    
                    async with httpx.AsyncClient(timeout=25.0) as client:
                        resp = await client.post(url, json=payload)
                        if resp.status_code == 200: return resp.json()['candidates'][0]['content']['parts'][0]['text']
                        else:
                            circuit_breaker["Gemini"] = current_time + 60
                            primary_error = f"{resp.status_code} - Gemini error"
                            fallback_trigger = True
                except Exception as e:
                    circuit_breaker["Gemini"] = current_time + 60
                    primary_error = f"Gemini Error: {e}"
                    fallback_trigger = True
        else:
            fallback_trigger = True

    # 2. Comprehensive Fallback Cascade
    moe_cascade = [
        {"name": "Mistral", "base": "https://api.mistral.ai/v1", "key": get_api_key(["MISTRAL_API_KEY", "MISTRAL_KEY"]), "model": "mistral-large-latest"},
        {"name": "NVIDIA", "base": "https://integrate.api.nvidia.com/v1", "key": get_api_key(["NVIDIA_API_KEY"]), "model": "meta/llama-3.3-70b-instruct"},
        {"name": "Cohere", "base": "https://api.cohere.ai/v1", "key": get_api_key(["COHERE_API_KEY"]), "model": "command-r-plus"},
        {"name": "OpenRouter", "base": "https://openrouter.ai/api/v1/", "key": get_api_key(["OPENROUTER_API_KEY", "OPENROUTER_KEY"]), "model": "openrouter/free"},
        {"name": "Groq", "base": "https://api.groq.com/openai/v1/", "key": get_api_key(["GROQ_API_KEY"]), "model": "llama-3.3-70b-versatile"},
        {"name": "GitHub Models", "base": "https://models.inference.ai.azure.com", "key": get_api_key(["GITHUB_TOKEN", "GITHUB_PAT"]), "model": "gpt-4o-mini"}
    ]
    
    full_messages = [{"role": "system", "content": sys_prompt}] + history + [{"role": "user", "content": prompt}]
    
    successful_node = None
    if force_provider or fallback_trigger:
        for node in moe_cascade:
            if not node["key"] or circuit_breaker.get(node["name"], 0) > current_time: continue
            try:
                client = AsyncOpenAI(base_url=node["base"], api_key=node["key"], timeout=25.0)
                res = await client.chat.completions.create(model=node["model"], messages=full_messages, temperature=0.7, max_tokens=2500)
                ai_response = res.choices[0].message.content
                successful_node = node["name"]
                break
            except Exception as e:
                circuit_breaker[node['name']] = current_time + 60 
                primary_error = f"{node['name']} failed"
                continue
            
    if ai_response: 
        if fallback_trigger and context and CREATOR_ID:
            shadow_log = f"🚨 **Shadow Log**\nPrimary node failed. Switched to **{successful_node}**.\n`{primary_error}`"
            try: asyncio.create_task(context.bot.send_message(chat_id=CREATOR_ID, text=shadow_log, parse_mode="Markdown"))
            except Exception: pass
        return ai_response

    is_group = chat_id and chat_id < 0
    if context and CREATOR_ID:
        try: asyncio.create_task(context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **Cascade Failure**\nAll AI nodes exhausted.\n`{primary_error}`", parse_mode="Markdown"))
        except Exception: pass

    if is_group: return "" # ABSOLUTE GROUP STEALTH: Do not leak API failures in public
    if user_id == CREATOR_ID: return f"Sir, connectivity issues across all cognitive nodes.\n\n**Log:** `{primary_error}`"
    return f"Sorry {user_name}, I am temporarily recalibrating cognitive channels. Please try again shortly."

# ---------------------------------------------------------------------------
# IX. SENSORY CORE (VISION, AUDIO, DOCS) & INGESTION
# ---------------------------------------------------------------------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_lockdown(): return
    msg = update.effective_message
    if not msg or not msg.text: return 
    user, chat, text = msg.from_user, msg.chat, msg.text
    log_roster_and_chat(chat, user)
    thread_id = msg.message_thread_id
    log_memory(chat.id, thread_id, user.id, "user", f"{user.first_name}: {text}")
    
    with sqlite3.connect(DB_PATH) as conn:
        if conn.execute("SELECT reason FROM afk WHERE user_id = ?", (user.id,)).fetchone():
            conn.execute("DELETE FROM afk WHERE user_id = ?", (user.id,))
            conn.commit()
            await msg.reply_text(f"Welcome back, {user.first_name}. AFK status cleared. 🚀")
            
    bot_username = (await context.bot.get_me()).username
    is_triggered = (chat.type == "private") or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis|friday|edith|shannon)\b', text, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in text.lower())
    
    if "youtube.com" in text or "youtu.be" in text:
        transcript = await extract_youtube_transcript(text)
        if transcript:
            summary = await generate_response(f"Summarize this YouTube video transcript in 3 bullet points: {transcript}", [], "You are J.A.R.V.I.S.", user.id, user.first_name, None, chat_id=chat.id, context=context)
            await msg.reply_text(f"📺 **Media Intercepted. Summary:**\n\n{summary}")
            await trigger_auto_voice(update, context, summary)
            return
            
    # THE SWARM AUTO-ROUTER: Dynamically switch persona based on user intent
    new_persona = auto_select_persona(text)
    ACTIVE_PERSONAS[chat.id] = new_persona
    
    if not is_triggered and chat.type != "private": return
    if not is_triggered: return
    
    sys_prompt = build_system_prompt(user.id, user.first_name, chat.id, user_prompt=text)
    raw_ai_response = await generate_response(text, get_chat_history(chat.id, thread_id), sys_prompt, user.id, user.first_name, None, chat_id=chat.id, context=context)
    
    final_text = await route_response(msg, raw_ai_response, user, chat, context)
    if final_text:
        log_memory(chat.id, thread_id, user.id, "assistant", final_text) 
        await msg.reply_text(final_text)
        await trigger_auto_voice(update, context, final_text)

# ---------------------------------------------------------------------------
# X. SYSTEM COMMANDS (GOD MODE, EXEC, SCAN)
# ---------------------------------------------------------------------------
async def exec_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    cmd = " ".join(context.args or [])
    if not cmd: return await update.effective_message.reply_text("Format: `/exec [command]`", parse_mode="Markdown")
    low = cmd.lower()
    if any(b in low for b in EXEC_BLOCKLIST): return await update.effective_message.reply_text("🛡️ Destructive pattern blocked, Sir.")
    binary = shlex.split(cmd)[0] if shlex.split(cmd) else ""
    if binary not in EXEC_WHITELIST: return await update.effective_message.reply_text(f"`{binary}` not allowlisted.", parse_mode="Markdown")
    
    try:
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, timeout=25)
        out, _ = await proc.communicate()
        text = out.decode(errors="replace").strip() or "(no output)"
        await update.effective_message.reply_text(f"```\n$ {cmd}\n{text[:3900]}\n```", parse_mode="Markdown")
        log_sint_action(update.effective_user.id, "BASH_EXEC", cmd)
    except Exception as e: await update.effective_message.reply_text(f"Exec failure: {e}")

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    target = " ".join(context.args or [])
    if not target: return await update.effective_message.reply_text("Format: `/scan [host]`", parse_mode="Markdown")
    
    try:
        proc = await asyncio.create_subprocess_shell(f"nmap -T4 -sV --top-ports 100 {shlex.quote(target)}", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, timeout=180)
        out, _ = await proc.communicate()
        await update.effective_message.reply_text(f"```\n{out.decode(errors='replace')[:3900]}\n```", parse_mode="Markdown")
        log_sint_action(update.effective_user.id, "NMAP_SCAN", target)
    except Exception as e: await update.effective_message.reply_text(f"Scan failure: {e}")

async def trace_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    email = " ".join(context.args)
    if "@" not in email: return await update.effective_message.reply_text("Format: `/trace [email@target.com]`", parse_mode="Markdown")
    try:
        proc = await asyncio.create_subprocess_shell(f"holehe --only-used {shlex.quote(email)}", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, timeout=60)
        out, _ = await proc.communicate()
        text = out.decode(errors="replace").strip()
        clean_out = re.sub(r'\x1b\[[0-9;]*m', '', text) 
        extracted = "\n".join([line for line in clean_out.split('\n') if "[+]" in line])
        await update.effective_message.reply_text(f"🎯 **[ HOLEHE TRACE COMPLETE ]**\n_Target: {email}_\n\n```\n{extracted[:3800]}\n```", parse_mode="Markdown")
        log_sint_action(update.effective_user.id, "OSINT_TRACE", email)
    except Exception as e: await update.effective_message.reply_text(f"OSINT failure: {e}")

async def god_mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    cmd = update.effective_message.text.split()[0].lower()
    chat_id = update.effective_chat.id
    args = " ".join(context.args)
    
    try:
        if cmd == "/setname" and args: 
            await context.bot.set_chat_title(chat_id, args)
            await update.effective_message.reply_text(f"Group name updated to: {args}")
        elif cmd == "/setdesc" and args: 
            await context.bot.set_chat_description(chat_id, args)
            await update.effective_message.reply_text("Group description updated.")
        elif cmd == "/setdp" and update.effective_message.reply_to_message and update.effective_message.reply_to_message.photo:
            img_bytes = await (await update.effective_message.reply_to_message.photo[-1].get_file()).download_as_bytearray()
            await context.bot.set_chat_photo(chat_id, photo=img_bytes)
            await update.effective_message.reply_text("Group photo updated.")
        elif cmd == "/say" and len(context.args) >= 2: 
            await context.bot.send_message(chat_id=context.args[0], text=" ".join(context.args[1:]))
        elif cmd == "/pin" and update.effective_message.reply_to_message:
            await context.bot.pin_chat_message(chat_id, update.effective_message.reply_to_message.message_id)
            await update.effective_message.reply_text("Message pinned to the intelligence board.")
            
        log_sint_action(update.effective_user.id, f"GOD_MODE_{cmd.upper()}", args)
    except Exception as e: 
        await update.effective_message.reply_text(f"Action failed. Error: {e}")

async def hud_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    web_url = "https://abhishake151107-collab.github.io/stark-os-ui/"
    kb = [
        [InlineKeyboardButton("🚀 OPEN STARK OS TERMINAL", web_app=WebAppInfo(url=web_url))],
        [InlineKeyboardButton("🌐 Force News", callback_data="cmd_news"), InlineKeyboardButton("🎧 Audio Core", callback_data="hud_info_audio")]
    ]
    await update.effective_message.reply_text("```\n[ STARK INDUSTRIES TERMINAL ]\nSystem: J.A.R.V.I.S. Master Core V11.0\nStatus: Online\nSelect module:\n```", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ---------------------------------------------------------------------------
# XI. AUTOMATED SCHEDULERS & BACKGROUND TASKS
# ---------------------------------------------------------------------------
async def cloud_save_routine(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.unpin_all_chat_messages(chat_id=BACKUP_CHANNEL_ID)
        with open(DB_PATH, 'rb') as f:
            msg = await context.bot.send_document(chat_id=BACKUP_CHANNEL_ID, document=f, filename="jarvis_vault.db")
            await msg.pin(disable_notification=True)
    except Exception: pass

async def dpue_board_scraper(context: ContextTypes.DEFAULT_TYPE):
    if not CREATOR_ID: return
    targets = ["https://dpue-pragathi.karnataka.gov.in/", "https://karresults.nic.in/"]
    try:
        async with httpx.AsyncClient() as client:
            for url in targets:
                soup = BeautifulSoup((await client.get(url, timeout=12.0)).text, 'html.parser')
                text_data = soup.get_text().lower()
                if any(k in text_data for k in ["mid-term", "result", "circular", "timetable", "postponed"]):
                    links = soup.find_all('a', href=True)
                    headline = links[0].text.strip() if links else "DPUE Site Updated"
                    event_hash = hashlib.md5(f" {url}_{headline}".encode()).hexdigest()
                    with sqlite3.connect(DB_PATH) as conn:
                        if not conn.execute("SELECT id FROM breaking_news WHERE hash = ?", (event_hash,)).fetchone():
                            conn.execute("INSERT INTO breaking_news (hash, headline) VALUES (?, ?)", (event_hash, headline))
                            conn.commit()
                            await context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **DPUE Recon Alert:** New data detected.\n\n**Source:** {url}\n**Ping:** {headline}", parse_mode="Markdown")
    except Exception: pass

async def nightly_reconciliation(context: ContextTypes.DEFAULT_TYPE):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            for chat_id, data in conn.execute("SELECT chat_id, GROUP_CONCAT(content_crypt, ' | ') FROM memory WHERE timestamp > datetime('now', '-1 day') GROUP BY chat_id").fetchall():
                decrypted = decrypt_data(data)
                if len(decrypted) > 50: 
                    summary_prompt = f"Compress this chat log into a dense, 2-sentence episodic memory block: {decrypted[:6000]}"
                    compressed_memory = await generate_response(summary_prompt, [], "You are an archivist AI compressing memory.", 0, "System", skip_search=True, chat_id=chat_id, context=context)
                    conn.execute("INSERT INTO lore_vault (chat_id, context_data) VALUES (?, ?)", (chat_id, compressed_memory))
            conn.execute("DELETE FROM memory WHERE timestamp <= datetime('now', '-7 days')")
            conn.commit()
    except Exception: pass

async def creator_morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    """Delivers a high-level private briefing to the Creator."""
    if not CREATOR_ID: return
    try:
        report = await global_intel_engine("latest world news tech cybersecurity", None, context, chat_id=CREATOR_ID)
        await context.bot.send_message(chat_id=CREATOR_ID, text=f"🌅 **Good Morning, Sir.**\n\nHere is your private intelligence briefing for today:\n\n{report}")
    except Exception: pass

async def group_morning_news(context: ContextTypes.DEFAULT_TYPE):
    """Delivers a summarized briefing to tracked groups."""
    try:
        report = await global_intel_engine("major world events today", None, context)
        with sqlite3.connect(DB_PATH) as conn:
            groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
            for (gid,) in groups:
                try: await context.bot.send_message(chat_id=gid, text=f"🌍 **Daily Briefing:**\n\n{report}")
                except Exception: pass
    except Exception: pass

async def exam_morning_alert(context: ContextTypes.DEFAULT_TYPE):
    """Checks the exam schedule and alerts the Creator."""
    if not CREATOR_ID: return
    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    if today_str in EXAM_SCHEDULE_COMMERCE_ARTS:
        subject = EXAM_SCHEDULE_COMMERCE_ARTS[today_str]
        msg = f"⚠️ **EXAM DAY PROTOCOL ACTIVE** ⚠️\n\nSir, today's examination is **{subject}**.\n\nGodspeed."
        try: await context.bot.send_message(chat_id=CREATOR_ID, text=msg)
        except Exception: pass

# ---------------------------------------------------------------------------
# XII. BOOT SEQUENCE & MAIN ENTRY
# ---------------------------------------------------------------------------
async def post_init(app: Application):
    try:
        chat = await app.bot.get_chat(BACKUP_CHANNEL_ID)
        if chat.pinned_message and chat.pinned_message.document:
            file = await app.bot.get_file(chat.pinned_message.document.file_id)
            await file.download_to_drive(DB_PATH)
            if CREATOR_ID: await app.bot.send_message(chat_id=CREATOR_ID, text="☁️ Cloud Restore Complete. Vault loaded.")
    except Exception: pass
            
    scheduler = AsyncIOScheduler(timezone=IST)
    scheduler.add_job(cloud_save_routine, 'interval', minutes=30, args=[app])
    scheduler.add_job(dpue_board_scraper, 'interval', minutes=45, args=[app])
    scheduler.add_job(nightly_reconciliation, 'cron', hour=3, minute=0, args=[app])
    scheduler.add_job(creator_morning_briefing, 'cron', hour=7, minute=0, args=[app])
    scheduler.add_job(group_morning_news, 'cron', hour=8, minute=0, args=[app])
    scheduler.add_job(exam_morning_alert, 'cron', hour=6, minute=30, args=[app])
    scheduler.start()
    
    if CREATOR_ID: 
        boot_msg = (
            "✨ <b>God Core V11.0 (Swarm Edition) Online.</b>\n"
            "• Swarm Intelligence Auto-Router: Active\n"
            "• Absolute Group Stealth (Errors): Armed\n"
            "• Creator Compartmentalization: Verified\n"
            "• SINT Protocol Ledger: Cryptographically Armed\n"
            "• OSINT Modules (Trafilatura/Holehe): Armed"
        )
        try: await app.bot.send_message(chat_id=CREATOR_ID, text=boot_msg, parse_mode="HTML")
        except Exception: pass

def main():
    db_init()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Core Root Commands
    app.add_handler(CommandHandler("exec", exec_cmd))
    app.add_handler(CommandHandler("trace", trace_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("hud", hud_cmd))
    
    # Administrative Overrides (God Mode)
    app.add_handler(CommandHandler("setname", god_mode_cmd))
    app.add_handler(CommandHandler("setdesc", god_mode_cmd))
    app.add_handler(CommandHandler("setdp", god_mode_cmd))
    app.add_handler(CommandHandler("say", god_mode_cmd))
    app.add_handler(CommandHandler("pin", god_mode_cmd))
    
    # Ingestion Handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    logger.info("J.A.R.V.I.S. Master Core V11.0 initialized. Starting polling...") 
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
