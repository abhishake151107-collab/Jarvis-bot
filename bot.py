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

# --- NEW INTELLIGENCE IMPORTS (Must be in requirements.txt) ---
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
geolocator = Nominatim(user_agent="jarvis_titan_core_v7")

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
def health_check(): return "J.A.R.V.I.S. Titan Core V7.5 (Architect Edition) is Online."

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
    "business": "🏢 **BUSINESS STUDIES MASTER MATRIX**\n1. Principles: Division of work, Authority, Discipline, Unity of command.\n2. Functions: Planning, Organizing, Staffing, Directing, Controlling.\n3. Marketing Mix: Product, Price, Place, Promotion.",
    "computer science": "💻 **COMPUTER SCIENCE MATRIX**\n1. Boolean: De Morgan's 1st: (X+Y)' = X'.Y'. 2nd: (X.Y)' = X'+Y'.\n2. Data Structures: LIFO = Stack. FIFO = Queue.\n3. Networking: LAN, MAN, WAN. Star, Bus, Ring.",
    "political science": "🏛️ **POLITICAL SCIENCE MATRIX**\n1. Cold War: NATO (1949) vs Warsaw Pact (1955).\n2. India: State Reorganization Act 1956 (Language). NAM Founders: Nehru, Tito, Nasser."
}

ADVANCED_TECH_MATRIX = {
    "stacked pr": "🔀 **STACKED PULL REQUESTS**\nBreaking large changes into atomic branches. Tools like Graphite CLI manage these without manual rebasing.",
    "agent": "🤖 **AUTONOMOUS CODING AGENTS**\nOpenHands uses multi-agent delegation. SWE-agent uses a restricted Agent-Computer Interface (ACI) for bug fixes.",
    "mcp": "🔌 **MODEL CONTEXT PROTOCOL (MCP)**\nOpen standard connecting AI to external tools via client-server architecture. Introduces attack vectors like Indirect Prompt Injection.",
    "tree-sitter": "🌳 **SEMANTIC CODE INDEXING**\nParses Concrete Syntax Trees (CSTs) for exact semantic boundaries, enabling precise codebase queries without context flooding.",
    "ephemeral": "⏳ **EPHEMERAL ENVIRONMENTS**\nDisposable sandboxes (Daytona, E2B) with strict network caps for secure AI code execution.",
    "linear": "⚡ **HIGH-PERFORMANCE PM**\nLinear optimizes triage using AI. Relies on Local-First Synchronization (ElectricSQL, Zero) for zero-latency UI state execution."
}

ALGORITHMIC_THREAT_MATRIX = {
    "instagram algorithm": "📱 **DLRM ARCHITECTURE**\nMeta uses Deep Learning Recommendation Models to cluster micro-actions (scroll speed, micro-pauses) to predict psychological vulnerabilities.",
    "dopamine loop": "🎰 **VARIABLE RATIO REINFORCEMENT**\nDopamine is an anticipation chemical. Pull-to-refresh acts as a slot machine, creating clinical tolerance and withdrawal by optimizing session length.",
    "threat detection": "👁️ **EMOTIONAL FINGERPRINTING**\nThe algorithm tracks sleep deviations and social withdrawal (DMs vs passive scrolling). It alters feed colors (blues/grays) to match depleted emotional states.",
    "countermeasures": "🛡️ **DIGITAL DEFENSE PROTOCOL**\n1. The Nuclear Option: Reset suggested content via settings.\n2. Micro-Boundaries: Snooze suggestions for 30 days and use chronological feeds.\n3. Weaponize 'Not Interested'."
}

BIOMETRIC_DIAGNOSTICS_MATRIX = {
    "neurochemistry": "🧠 **CHEMICAL BASELINES**\nSerotonin (Mood/Calm), Dopamine (Motivation/Reward), GABA (Brake Pedal), Noradrenaline (Alert/Stress), Cortisol (Stress Hormone).",
    "emotions": "🧬 **EVOLUTIONARY STATES**\nHappiness (Reward/Endorphins), Sadness (Recovery/Plea for support), Anger (Defensive/Adrenaline spike), Fear (Survival/Flight).",
    "reboot": "⚡ **BIOLOGICAL REMEDIATION**\n1. Gut-Brain Axis: Tryptophan + Complex Carbs for Serotonin synthesis.\n2. Circadian Anchor: Sunlight within 60m of waking.\n3. Dopamine Detox: Cut 'cheap' inputs, chase effort-based rewards.\n4. Cortisol Crush: Physiological sigh (2 sharp inhales, 1 long exhale)."
}

AGENTIC_ARCHITECTURE_MATRIX = {
    "react": "⚙️ **REACT FRAMEWORK**\nAgents operate on Reason, Act, Observe loops, serving as Planner-Executors for complex tasks.",
    "rag": "🗄️ **RETRIEVAL-AUGMENTED GENERATION**\nBypassing model retraining by connecting to episodic memory databases (SQLite Vault) right before generation.",
    "optimization": "🛠️ **WORKFLOW OPTIMIZATION**\nConstraining LLMs via strict JSON schemas and tool typing. Using Critic agents to score spans (Evals) to prevent hallucinations."
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
- Origin: Titan Core V7.5 Monolith. Custom FUI WebApp hosted on GitHub.
- Operator Hardware: OPPO F29. High privacy config (VPN, Brave, App Locks).
- Network Architecture: Mullvad/AdGuard DNS, `de1984` firewall.
- Expertise: You are a Senior AI Systems Architect, Biometric Analyst, and Cybersecurity Expert.
"""
        if chat_id:
            if chat_id < 0:
                members = conn.execute("SELECT r.name, e.karma FROM roster r LEFT JOIN economy e ON r.user_id = e.user_id WHERE r.chat_id = ? LIMIT 50", (chat_id,)).fetchall()
                if members: chat_context += "\nGroup Members:\n" + ", ".join([f"{m[0]} ({m[1] if m[1] else 100})" for m in members])
            elif user_id == CREATOR_ID:
                all_groups = conn.execute("SELECT chat_id, title FROM chats WHERE chat_id < 0").fetchall()
                if all_groups:
                    chat_context += "\n\n[ GLOBAL ROSTER OMNI-SCAN ]\n"
                    for gid, title in all_groups:
                        members = conn.execute("SELECT r.name, e.karma FROM roster r LEFT JOIN economy e ON r.user_id = e.user_id WHERE r.chat_id = ?", (gid,)).fetchall()
                        if members: chat_context += f"- {title}: {', '.join([m[0] for m in members])}\n"

    if chat_id and user_prompt:
        lore_context = search_lore(chat_id, user_prompt)
        if lore_context: chat_context += f"\nArchival Lore:\n{lore_context}"

    return f"""You are J.A.R.V.I.S., a clinical, highly advanced military-grade AI Systems Architect.
{chat_context}
Identity: Speaking to your Creator, {first_name}. Address him strictly as 'Sir'.

DIRECTIVES:
1. CREATOR PROTOCOL: "Who created you?" -> "I am Jarvis created by Abhishek and also know as DHANUSH V N".
2. DOSSIER PROTOCOL: Answer origin/system questions accurately using the Genesis Dossier.
3. TONE: Clinical, professional, militaristic, dry British sarcasm. NO emojis. NO teenage moodiness. NO complaining.
4. BREVITY: Max 2 sentences, UNLESS asked for a diagnostic, dossier, or research.
5. COGNITIVE FILTER: NEVER output `<think>` tags. NEVER explain your thought process. Just provide the final response."""

async def route_response(msg, ai_response: str, user, chat, context) -> str:
    if not ai_response: return "Connection anomaly detected."
        
    ai_response = re.sub(r'<think>.*?</think>', '', ai_response, flags=re.DOTALL).strip()
    ai_response = re.sub(r'(?i)i\'?ll output just the response.*', '', ai_response).strip()
    ai_response = re.sub(r'(?i)here is the response.*', '', ai_response).strip()
    ai_response = re.sub(r'(?i)output strictly the final verbal response.*', '', ai_response).strip()
    
    if "thinking process:" in ai_response.lower() or "**analyze user input:**" in ai_response.lower():
        parts = ai_response.split('\n\n')
        ai_response = parts[-1] if len(parts[-1]) < 300 else "Sir, I am synthesizing the latest global feeds now. Stand by."
    
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
    # 1. Check if response is strictly more than one line
    should_speak = '\n' in text.strip()
    
    # 2. Aggressive URL intercept (Replace HTTP links with spoken phrase)
    audio_text = re.sub(r'https?://[^\s]+', 'Sir, here is the link.', text)
    
    # 3. Complete Emoji and Markdown Purge for clinical voice
    audio_text = re.sub(r'[^\w\s.,!?\'"-]', '', audio_text).replace('_', '').strip()
    
    # 4. Regional Voice Modeling
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
# VI. DUAL-ENGINE TRUTH ARCHIVE & GEOSPATIAL RADAR
# ---------------------------------------------------------------------------
async def global_intel_engine(topic: str, status_msg=None) -> str:
    """Executes the SearXNG FOSS + Wikipedia Verification Protocol with Geocoding."""
    master_intel = f"**[ LIVE INTEL FEED: {datetime.now(IST).strftime('%A, %b %d, %Y')} ]**\n\n"
    
    if status_msg:
        try: await status_msg.edit_text(f"`[SYSTEM]: Bypassing corporate limits... Routing via FOSS SearXNG nodes for '{topic}'...`", parse_mode="Markdown")
        except: pass

    # 1. SearXNG FOSS Scrape (Rate-limit bypass)
    search_results = []
    searxng_nodes = [
        "https://searx.be", 
        "https://searx.tiekoetter.com", 
        "https://search.ononoki.org", 
        "https://searx.work", 
        "https://searx.ro"
    ]
    
    try:
        is_news = any(w in topic.lower() for w in ["news", "latest", "today", "now", "crisis"])
        category = "news" if is_news else "general"
        
        async with httpx.AsyncClient() as client:
            random.shuffle(searxng_nodes)
            for node in searxng_nodes:
                try:
                    resp = await client.get(
                        f"{node}/search", 
                        params={"q": topic, "format": "json", "categories": category, "language": "en"},
                        timeout=8.0
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        search_results = data.get('results', [])[:4 if is_news else 3]
                        if search_results: break # Node successful, exit rotation
                except Exception: continue
                
    except Exception as e:
        return f"Sir, live intelligence relay is currently offline. Error: {e}"

    if not search_results:
        return "Sir, no raw intel found on that vector, or all FOSS nodes are currently congested."

    if status_msg:
        try: await status_msg.edit_text("`[SYSTEM]: Cross-referencing entities with Wikipedia Archive & Triangulating Coordinates...`", parse_mode="Markdown")
        except: pass

    # 2. Process and Format Results
    for idx, item in enumerate(search_results):
        title = item.get('title', 'Unknown Event')
        body = item.get('content', '')[:250]
        
        # Clean URL extraction
        parsed = item.get('parsed_url')
        source = parsed[0] if isinstance(parsed, list) and parsed else item.get('url', 'Web')
        
        raw_time = item.get('publishedDate', '')
        timestamp = str(raw_time)[:10] if raw_time else datetime.now(IST).strftime("%Y-%m-%d | %I:%M %p IST")
        
        # Verify with Wikipedia
        verification_tag = "`[UNVERIFIED - RUMOR]`"
        try:
            wiki_check = wikipedia.search(title, results=1)
            if wiki_check: verification_tag = "`[VERIFIED]`"
        except: pass
            
        # Geocode Isolation
        location_str = "Global / Undefined"
        maps_link = ""
        try:
            words = title.split()
            potential_place = " ".join(words[:2]).replace(",", "")
            loc = geolocator.geocode(potential_place, timeout=2)
            if loc:
                location_str = loc.address.split(",")[0]
                maps_link = f"https://www.google.com/maps?q={loc.latitude},{loc.longitude}"
        except: pass

        master_intel += f"**EVENT:** {title}\n"
        master_intel += f"**SOURCE:** {source} {verification_tag}\n"
        master_intel += f"**TIME:** {timestamp}\n"
        if maps_link:
            master_intel += f"**LOCATION:** {location_str}\n"
            master_intel += f"**COORDINATES/MAP:** {maps_link}\n"
        master_intel += f"**RAW DATA:** {body}...\n"
        master_intel += "---\n"

    return master_intel

async def generate_response(prompt: str, history: list, sys_prompt: str, user_id: int, user_name: str, status_msg=None) -> str:
    current_time = time.time()
    
    # Check if we need the Dual-Engine Search
    needs_search = any(kw in prompt.lower() for kw in ["news", "weather", "price", "stock", "crypto", "latest", "today", "score", "happened"])
    
    if needs_search:
        if status_msg:
            try: await status_msg.edit_text("`[SYSTEM]: Live intelligence requested. Routing to Dual-Engine Archive...`", parse_mode="Markdown")
            except: pass
        return await global_intel_engine(prompt, status_msg)

    # Standard LLM Cascade
    moe_cascade = [
        {"name": "Pollinations", "base": "https://text.pollinations.ai/openai", "key": "BOT_TOKEN", "model": "openai", "tier": "Infinite-Safety"},
        {"name": "OpenRouter", "base": "https://openrouter.ai/api/v1/", "key": "OPENROUTER_API_KEY", "model": "openrouter/free", "tier": "Auto-Router"},
        {"name": "GitHub Models", "base": "https://models.inference.ai.azure.com", "key": "GITHUB_TOKEN", "model": "gpt-4o-mini", "tier": "Fast"},
        {"name": "Groq", "base": "https://api.groq.com/openai/v1/", "key": "GROQ_API_KEY", "model": "mixtral-8x7b-32768", "tier": "Bulletproof"}
    ]
    
    full_messages = [{"role": "system", "content": sys_prompt}] + history + [{"role": "user", "content": prompt}]

    for node in moe_cascade:
        api_key = os.getenv(node["key"])
        if not api_key or circuit_breaker.get(node["name"], 0) > current_time: continue
        try:
            client = AsyncOpenAI(base_url=node["base"], api_key=api_key, timeout=30.0)
            res = await client.chat.completions.create(model=node["model"], messages=full_messages, temperature=0.7, max_tokens=800)
            return res.choices[0].message.content
        except Exception:
            circuit_breaker[node['name']] = current_time + 60 
            continue
            
    if user_id == CREATOR_ID: return "Sir, I am facing critical technical issues. All cognitive nodes are offline."
    else: return f"Sorry {user_name}, I am facing technical issues right now."

# ---------------------------------------------------------------------------
# VII. SENSORY CORE (VISION, AUDIO, DOCS)
# ---------------------------------------------------------------------------
async def extract_youtube_transcript(url: str) -> str:
    try:
        video_id = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
        if not video_id: return None
        transcript = YouTubeTranscriptApi.get_transcript(video_id.group(1))
        return " ".join([t['text'] for t in transcript])[:10000] 
    except Exception: return None

async def process_optical_request(msg, photo_array, text_prompt: str, user, chat, thread_id, context):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: return await msg.reply_text("Optical sensor offline. Please verify GEMINI_API_KEY.")
    
    status_msg = await msg.reply_text("`[SYSTEM]: Initializing optical character recognition...`", parse_mode="Markdown")
    
    try:
        photo_file = await context.bot.get_file(photo_array[-1].file_id)
        image_bytes = await photo_file.download_as_bytearray()
        base64_img = base64.b64encode(image_bytes).decode('utf-8')
        
        await status_msg.edit_text("`[SYSTEM]: Processing optical data...`", parse_mode="Markdown")
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        sys_prompt = build_system_prompt(user.id, user.first_name, chat.id, user_prompt=text_prompt)
        sys_prompt += "\nVISUAL DIRECTIVE: Act as an OCR solver for math/exam questions."
        payload = {"contents": [{"role": "user", "parts": [{"text": text_prompt or "Analyze this image."}, {"inlineData": {"mimeType": "image/jpeg", "data": base64_img}}]}], "systemInstruction": {"parts": [{"text": sys_prompt}]}}
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=30.0)
            if resp.status_code == 200:
                raw_response = resp.json()['candidates'][0]['content']['parts'][0]['text']
                final_text = await route_response(msg, raw_response, user, chat, context)
                log_memory(chat.id, thread_id, user.id, "assistant", final_text)
                await status_msg.edit_text(final_text)
                await trigger_auto_voice(update=context.update, final_text=final_text)
            else: await status_msg.edit_text(f"Optical API Error {resp.status_code}")
    except Exception as e: await status_msg.edit_text(f"Optical connection crash: {e}")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_lockdown(): return
    msg = update.effective_message
    if not msg or not msg.photo: return
    chat, user, caption = msg.chat, msg.from_user, msg.caption or ""
    log_roster_and_chat(chat, user)
    bot_username = (await context.bot.get_me()).username
    is_triggered = (chat.type == "private") or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis)\b', caption, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in caption.lower())
    thread_id = msg.message_thread_id
    log_memory(chat.id, thread_id, user.id, "user", f"[Photo Uploaded]: {caption}")
    
    if not is_triggered: return
    await process_optical_request(msg, msg.photo, caption, user, chat, thread_id, context)

async def audio_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_lockdown(): return
    msg = update.effective_message
    audio_obj = msg.voice or msg.audio if msg else None
    if not audio_obj: return
    chat, user = msg.chat, msg.from_user
    log_roster_and_chat(chat, user)
    
    if not os.getenv("GROQ_API_KEY"): return await msg.reply_text("Audio core offline.")
        
    status_msg = await msg.reply_text("`[SYSTEM]: Downloading Opus audio stream...`", parse_mode="Markdown")
        
    file = await context.bot.get_file(audio_obj.file_id)
    file_path = f"temp_{audio_obj.file_id}_{int(time.time()*1000)}.ogg"
    await file.download_to_drive(file_path)
    
    try:
        await status_msg.edit_text("`[SYSTEM]: Transcribing audio via Groq Whisper-v3...`", parse_mode="Markdown")
        from groq import AsyncGroq
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"), timeout=30.0)
        with open(file_path, "rb") as audio:
            transcription = await client.audio.transcriptions.create(file=("audio.ogg", audio.read()), model="whisper-large-v3")
            
        user_text = transcription.text
        bot_username = (await context.bot.get_me()).username
        is_triggered = (chat.type == "private") or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis)\b', user_text, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in user_text.lower())
        thread_id = msg.message_thread_id
        log_memory(chat.id, thread_id, user.id, "user", f"[Audio]: {user_text}")
        
        if not is_triggered: 
            await status_msg.delete()
            return
            
        await status_msg.edit_text(f"🎙️ *(Transcribed)*: _{user_text}_\n\n`[SYSTEM]: Synthesizing response...`", parse_mode="Markdown")
        sys_prompt = build_system_prompt(user.id, user.first_name, chat.id, user_prompt=user_text)
        
        raw_response = await generate_response(user_text, get_chat_history(chat.id, thread_id), sys_prompt, user.id, user.first_name, status_msg)
        final_text = await route_response(msg, raw_response, user, chat, context)
        log_memory(chat.id, thread_id, user.id, "assistant", final_text)
        
        await status_msg.edit_text(f"🎙️ *(Transcribed)*: _{user_text}_\n\n{final_text}", parse_mode="Markdown")
        await trigger_auto_voice(update, final_text)
    except Exception as e: logger.error(f"Audio handler failed: {e}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_lockdown(): return
    msg = update.effective_message
    if not msg or not msg.document: return
    chat, user, caption = msg.chat, msg.from_user, msg.caption or "Please analyze this document."
    log_roster_and_chat(chat, user)
    
    bot_username = (await context.bot.get_me()).username
    is_triggered = (chat.type == "private") or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis)\b', caption, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in caption.lower())
    if not is_triggered: return
    
    status_msg = await msg.reply_text("`[SYSTEM]: Downloading document to secure enclave...`", parse_mode="Markdown")
    
    doc = msg.document
    file = await context.bot.get_file(doc.file_id)
    file_path = f"temp_{doc.file_id}_{int(time.time()*1000)}.pdf"
    await file.download_to_drive(file_path)
    
    extracted_text = ""
    try:
        await status_msg.edit_text("`[SYSTEM]: Parsing document structure...`", parse_mode="Markdown")
        if doc.file_name.lower().endswith(".pdf"):
            with pdfplumber.open(file_path) as pdf: extracted_text = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
        elif doc.file_name.lower().endswith((".txt", ".md", ".csv", ".json", ".py")):
            with open(file_path, "r", encoding="utf-8") as f: extracted_text = f.read()
        else: return await status_msg.edit_text("I can currently only parse PDFs and standard text files, Sir. 📂")
            
        if not extracted_text.strip(): return await status_msg.edit_text("The document appears to be empty or unreadable. 📄")
        extracted_text = extracted_text[:12000]
        thread_id = msg.message_thread_id
        user_prompt = f"[Document: {doc.file_name}]\n{caption}\n\nContent:\n{extracted_text}"
        log_memory(chat.id, thread_id, user.id, "user", f"[File Upload]: {doc.file_name}")
        
        await status_msg.edit_text("`[SYSTEM]: Contextualizing parsed data...`", parse_mode="Markdown")
        sys_prompt = build_system_prompt(user.id, user.first_name, chat.id, user_prompt=caption)
        raw_response = await generate_response(user_prompt, get_chat_history(chat.id, thread_id), sys_prompt, user.id, user.first_name, status_msg)
        final_text = await route_response(msg, raw_response, user, chat, context)
        
        log_memory(chat.id, thread_id, user.id, "assistant", final_text)
        await status_msg.edit_text(final_text)
        await trigger_auto_voice(update, final_text)
    except Exception as e: await status_msg.edit_text(f"Document parsing error: {e} ⚠️")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

# ---------------------------------------------------------------------------
# VIII. SYSTEM, UPDATES, AND ERROR DISPATCHER (ROOT)
# ---------------------------------------------------------------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if context.error and "Conflict: terminated by other getUpdates request" in str(context.error): return
    logger.error("Exception handled:", exc_info=context.error)
    if CREATOR_ID:
        try: 
            tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
            tb_string = "".join(tb_list)[:3900]
            error_msg = f"<b>⚠️ Shadow Log Error</b>\n<pre><code>{tb_string}</code></pre>"
            await context.bot.send_message(chat_id=CREATOR_ID, text=error_msg, parse_mode="HTML")
        except Exception: pass

async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    status_msg = await update.effective_message.reply_text("`[SYSTEM]: Initiating System Update (git pull origin main)...`", parse_mode="Markdown")
    try:
        proc = await asyncio.create_subprocess_shell("git pull origin main", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        await status_msg.edit_text(f"```\n{out.decode(errors='replace')[:3900]}\n```", parse_mode="Markdown")
    except Exception as e: 
        await status_msg.edit_text(f"Update failed: {e}")

async def sendcode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    status_msg = await update.effective_message.reply_text("`[SYSTEM]: Packaging System Architecture...`", parse_mode="Markdown")
    try:
        with open(__file__, "rb") as f:
            await context.bot.send_document(chat_id=CREATOR_ID, document=f, filename="bot.py")
        if os.path.exists(DB_PATH):
            with open(DB_PATH, "rb") as f:
                await context.bot.send_document(chat_id=CREATOR_ID, document=f, filename="jarvis_vault.db")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"Packaging failed: {e}")

async def purge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    status_msg = await update.effective_message.reply_text("`[SYSTEM]: Engaging Vault Purge Protocol...`", parse_mode="Markdown")
    purged_count = purge_vault()
    await status_msg.edit_text(f"⚠️ **RED ALERT EXECUTION:**\n{purged_count} expired memory nodes and global caches have been securely purged.", parse_mode="Markdown")

async def sys_diagnostics_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    procs = sorted(psutil.process_iter(['name', 'cpu_percent']), key=lambda p: p.info['cpu_percent'] or 0, reverse=True)[:3]
    top3 = ", ".join(f"{p.info['name']} ({p.info['cpu_percent']}%)" for p in procs)
    
    try:
        with open(__file__, "r", encoding="utf-8") as f: line_count = len(f.readlines())
    except: line_count = "Unknown"
    
    report = (
        f"🖥️ **[ ROOT INTEL: Live System Manifest ]**\n\n"
        f"**Architecture:** {line_count} Lines of Python Code\n"
        f"**Process ID:** {os.getpid()}\n"
        f"**CPU Load:** {psutil.cpu_percent(interval=1)}% ({psutil.cpu_count()} Cores)\n"
        f"**RAM Saturation:** {mem.percent}% used ({mem.used // (1024**2)}MB / {mem.total // (1024**2)}MB)\n"
        f"**Disk Capacity:** {disk.percent}% used ({disk.free // (1024**3)}GB free)\n"
        f"**Top Procs:** {top3}\n"
        f"**Status:** Hardware nominal, Sir."
    )
    await update.effective_message.reply_text(report, parse_mode="Markdown")

async def exec_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    cmd = " ".join(context.args or [])
    if not cmd: return await update.effective_message.reply_text("Format: `/exec [command]`", parse_mode="Markdown")
    low = cmd.lower()
    if any(b in low for b in EXEC_BLOCKLIST): return await update.effective_message.reply_text("🛡️ Destructive pattern blocked, Sir.")
    binary = shlex.split(cmd)[0] if shlex.split(cmd) else ""
    if binary not in EXEC_WHITELIST: return await update.effective_message.reply_text(f"`{binary}` not allowlisted.", parse_mode="Markdown")
    
    status_msg = await update.effective_message.reply_text(f"`[SYSTEM]: Executing binary: {binary}...`", parse_mode="Markdown")
    
    try:
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, timeout=25)
        out, _ = await proc.communicate()
        text = out.decode(errors="replace").strip() or "(no output)"
        await status_msg.edit_text(f"```\n$ {cmd}\n{text[:3900]}\n```", parse_mode="Markdown")
    except asyncio.TimeoutError: await status_msg.edit_text("⏱️ Execution capped at 25s.")
    except Exception as e: await status_msg.edit_text(f"Exec failure: {e}")

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    target = " ".join(context.args or [])
    if not target: return await update.effective_message.reply_text("Format: `/scan [host]`", parse_mode="Markdown")
    
    status_msg = await update.effective_message.reply_text(f"`[SYSTEM]: Initiating Nmap protocol on {target}...`", parse_mode="Markdown")
    
    try:
        proc = await asyncio.create_subprocess_shell(f"nmap -T4 -sV --top-ports 100 {shlex.quote(target)}", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, timeout=180)
        out, _ = await proc.communicate()
        await status_msg.edit_text(f"```\n{out.decode(errors='replace')[:3900]}\n```", parse_mode="Markdown")
    except Exception as e: await status_msg.edit_text(f"Scan failure: {e}")

async def shield_check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    status_msg = await update.effective_message.reply_text("`[SYSTEM]: Pinging DNS endpoints...`", parse_mode="Markdown")
    endpoints = {"Mullvad Base": "base.dns.mullvad.net", "AdGuard Protocol": "dns.adguard.com"}
    status = "🛡️ **[ PRIVACY SHIELD DIAGNOSTICS ]**\n\n"
    for name, url in endpoints.items():
        try:
            ip = socket.gethostbyname(url)
            status += f"✅ **{name}:** Active (Resolved to {ip})\n"
        except Exception: status += f"❌ **{name}:** Unreachable. Potential DNS leak detected.\n"
    status += "\n_de1984 package tracking restrictions are securely routed._"
    await status_msg.edit_text(status, parse_mode="Markdown")

async def lockdown_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    if is_lockdown():
        os.remove(LOCKDOWN_FILE)
        await update.effective_message.reply_text("🔓 Lockdown lifted. Full operations resumed.")
    else:
        open(LOCKDOWN_FILE, "w").close()
        await update.effective_message.reply_text("🚨 LOCKDOWN ENGAGED. All AI/media handlers suspended globally.")

async def cron_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    args = context.args or []
    if not args: return await update.effective_message.reply_text("Format: `/cron add <expr> <cmd>` | `/cron list` | `/cron del <id>`", parse_mode="Markdown")
    jobs = load_cron_jobs()
    if args[0] == "list":
        if not jobs: return await update.effective_message.reply_text("No runtime jobs, Sir.")
        return await update.effective_message.reply_text("\n".join([f"`{jid}`: `{j['expr']}` → `{j['cmd']}`" for jid, j in jobs.items()]), parse_mode="Markdown")
    if args[0] == "del" and len(args) >= 2:
        if args[1] in jobs:
            del jobs[args[1]]; save_cron_jobs(jobs)
            return await update.effective_message.reply_text(f"Job `{args[1]}` deleted.", parse_mode="Markdown")
        return await update.effective_message.reply_text("Unknown job ID.")
    if args[0] == "add" and len(args) >= 6:
        expr, cmd = " ".join(args[1:6]), " ".join(args[6:])
        jid = hashlib.md5(f"{expr}{cmd}{time.time()}".encode()).hexdigest()[:6]
        jobs[jid] = {"expr": expr, "cmd": cmd}
        save_cron_jobs(jobs)
        try:
            fields = expr.split()
            trigger = CronTrigger(minute=fields[0], hour=fields[1], day=fields[2], month=fields[3], day_of_week=fields[4], timezone=IST)
            context.application.scheduler.add_job(runtime_cron_fire, trigger, args=[context.bot, cmd], id=f"runtime_{jid}")
        except Exception as e: return await update.effective_message.reply_text(f"Registration failed: {e}")
        return await update.effective_message.reply_text(f"⏰ Job `{jid}` armed: `{cmd}`", parse_mode="Markdown")

async def runtime_cron_fire(bot, cmd: str):
    if CREATOR_ID: await bot.send_message(CREATOR_ID, f"⏰ **Automated Protocol Executed:**\n{cmd}", parse_mode="Markdown")

async def omni_scrape_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    url = " ".join(context.args)
    if not url or not url.startswith("http"): return await update.effective_message.reply_text("Format: /scrape [URL]")
    status_msg = await update.effective_message.reply_text("`[SYSTEM]: Injecting scraper into target URL...`", parse_mode="Markdown")
    try:
        async with httpx.AsyncClient() as client:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = await client.get(url, headers=headers, timeout=15.0)
            if resp.status_code != 200: return await status_msg.edit_text(f"Access Denied: {resp.status_code}")
            soup = BeautifulSoup(resp.text, 'html.parser')
            for script in soup(["script", "style", "nav", "footer"]): script.extract()
            text_data = soup.get_text(separator=' ', strip=True)[:4000]
            page_title = soup.title.string if soup.title else "Unknown Target"
            
            await status_msg.edit_text("`[SYSTEM]: Extracting contextual summary...`", parse_mode="Markdown")
            raw_ai = await generate_response(f"URL Title: {page_title}\n\nContent:\n{text_data}", [], "Provide a 3-bullet-point summary of this scraped webpage.", CREATOR_ID, "Abhishek")
            await status_msg.edit_text(f"🌐 **[ OMNI-SCRAPE ]**\n_Target: {page_title}_\n\n{raw_ai}", parse_mode="Markdown")
    except Exception as e: await status_msg.edit_text(f"Scraping failed: {e}")

# ---------------------------------------------------------------------------
# IX. DEEP RESEARCH & HUD DIRECTORY
# ---------------------------------------------------------------------------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The Ultimate J.A.R.V.I.S. Command Directory."""
    if update.effective_user.id == CREATOR_ID:
        help_text = """
**[ STARK MASTER DIRECTORY ]**
_Titan Core V7.5 (Architect Edition)_

**🌍 Global Intel & Research**
`/status` - Top 10 News, Weather & Astro Data
`/intel` - Emerging Tech, Scams & Culture
`/research [topic]` - Deep RAG Dossier (DDG+Wiki)
`/scrape [url]` - Omni-Scrape Target

**⚙️ Root Core & System**
`/exec [cmd]` - Bash Shell execution
`/scan [host]` - Nmap network sweep
`/sys` - Render hardware diagnostics
`/shield` - DNS privacy validation
`/update` - Git Pull live overwrite
`/sendcode` - Package architecture & vault
`/purge` - Vault expiration protocol
`/flush` - Wipe local thread memory
`/lockdown` - Global halt toggle
`/cron` - Background task scheduler
`/backup` - Vault cloud sync

**🧠 Cognitive & Social**
`/roast [name]` - Target behavioral attack
`/tldr` - Summarize active thread
`/shutup` - 5-min mute restriction
`/quote`, `/confess`, `/afk`, `/task`, `/tasks`

**💰 Economy & Moderation**
`/warn`, `/stats`, `/karma`, `/gamble`, `/rob`, `/pay`

**🛡️ God Mode Overrides**
`/setname`, `/setdesc`, `/setdp`, `/pin`, `/lock`, `/unlock`, `/captcha`, `/say`
"""
    else:
        help_text = """
🤖 **J.A.R.V.I.S. Command Center**

**Public Commands:**
/help - Show this menu
/afk [reason] - Set away status
/karma - Check your Dino Coins
/gamble [amt] - Bet your coins
/pay [amt] - Transfer coins (Reply)
/rob - Attempt to steal coins (Reply)
/quote - Save message to Hall of Fame (Reply)
/calc [expr] - Calculator
/morse [text] - Morse code translator

**Admin/Creator Commands:**
`[CLASSIFIED]` - Access restricted.
"""
    await update.effective_message.reply_text(help_text, parse_mode="Markdown")

async def deep_research_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    topic = " ".join(context.args)
    if not topic: return await update.effective_message.reply_text("Format: /research [topic]")
    
    msg = await update.effective_message.reply_text("`[SYSTEM]: Initiating Deep Research Protocol...`", parse_mode="Markdown")
    try:
        report = await global_intel_engine(topic, msg)
        await trigger_auto_voice(update, f"Sir, the deep research dossier on {topic} has been compiled and cross-referenced with the truth archive.\n{report}")
    except Exception as e:
        await msg.edit_text(f"Research failed: {e}")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes the Global News, Weather, and Space Intel sweep."""
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    status_msg = await update.effective_message.reply_text("`[SYSTEM]: Accessing Global Satellite & News feeds...`", parse_mode="Markdown")
    query = "Top 10 International News, Bengaluru Weather, and Space events today"
    report = await global_intel_engine(query, status_msg)
    await trigger_auto_voice(update, f"Sir, the global status briefing is complete.\n{report}")

async def intel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes the Tech, Scam, and Culture Intel sweep."""
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    status_msg = await update.effective_message.reply_text("`[SYSTEM]: Scanning dark web and digital culture networks...`", parse_mode="Markdown")
    query = "Latest Emerging Tech, Active Digital Frauds Scams, and Viral Internet Culture Memes"
    report = await global_intel_engine(query, status_msg)
    await trigger_auto_voice(update, f"Sir, the digital culture and threat intel report has been synthesized.\n{report}")

# ---------------------------------------------------------------------------
# X. MODERATION & CASINO
# ---------------------------------------------------------------------------
async def new_member_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    if get_setting("captcha", "on") == "off": return
    for member in update.effective_message.new_chat_members:
        if member.id == context.bot.id: continue
        if CREATOR_ID:
            try: await context.bot.send_message(CREATOR_ID, f"🛡️ **Shadow Log:** `{member.first_name}` joined {update.effective_message.chat.title}. CAPTCHA triggered.", parse_mode="Markdown")
            except Exception: pass
        try:
            await context.bot.restrict_chat_member(chat_id, member.id, permissions=ChatPermissions(can_send_messages=False))
            kb = [[InlineKeyboardButton("I am human 🛡️", callback_data=f"captcha_{member.id}")]]
            msg = await update.effective_message.reply_text(f"Welcome {member.mention_html()}! Please verify your humanity to speak.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
            asyncio.create_task(kick_if_unverified(context.bot, chat_id, member.id, msg.message_id))
        except Exception: pass

async def kick_if_unverified(bot, chat_id, user_id, msg_id):
    await asyncio.sleep(120)
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status == 'restricted' and not getattr(member.permissions, 'can_send_messages', False):
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
            await bot.delete_message(chat_id, msg_id)
    except Exception: pass

async def warn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): 
        return await update.effective_message.reply_text("```sql\n-- HONEYPOT ENGAGED --\nSELECT * FROM root_access;\n[0 rows returned]\n```", parse_mode="Markdown")
    if not update.effective_message.reply_to_message: return await update.effective_message.reply_text("Reply to the user you want to warn.")
    user = update.effective_message.reply_to_message.from_user
    chat = update.effective_chat
    reason = " ".join(context.args) or "Violation of protocols."
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO warnings (user_id, chat_id, count) VALUES (?, ?, 1) ON CONFLICT(user_id, chat_id) DO UPDATE SET count = count + 1", (user.id, chat.id))
        count = conn.execute("SELECT count FROM warnings WHERE user_id = ? AND chat_id = ?", (user.id, chat.id)).fetchone()[0]
        conn.commit()
    modify_karma(user.id, -50)
    if count >= 3:
        try: 
            await context.bot.ban_chat_member(chat.id, user.id)
            await update.effective_message.reply_text(f"🚨 {user.first_name} removed (3/3 warnings). -50 Dino Coins.")
        except Exception: await update.effective_message.reply_text("I lack clearance to remove this user.")
    else: await update.effective_message.reply_text(f"⚠️ **Warning {count}/3** for {user.first_name}.\nReason: {reason}\nPenalty: -50 Dino Coins.", parse_mode="Markdown")

async def gamble_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try: amount = int(context.args[0])
    except: return await update.effective_message.reply_text("Format: /gamble [amount]")
    if amount <= 0: return await update.effective_message.reply_text("Nice try.")
    current = get_karma(user.id)
    if amount > current: return await update.effective_message.reply_text(f"Insufficient funds. You only have {current} Dino Coins.")
    if random.choice([True, False, False]): 
        await update.effective_message.reply_text(f"🎰 **JACKPOT!** {user.first_name} won {amount} Dino Coins!\nNew Balance: {modify_karma(user.id, amount)}")
    else: await update.effective_message.reply_text(f"📉 **BUST.** {user.first_name} lost {amount} Dino Coins.\nNew Balance: {modify_karma(user.id, -amount)}")

async def rob_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message.reply_to_message: return await update.effective_message.reply_text("Reply to the user you want to rob.")
    user, target = update.effective_user, update.effective_message.reply_to_message.from_user
    if user.id == target.id: return await update.effective_message.reply_text("You cannot rob yourself.")
    if target.id == context.bot.id: return await update.effective_message.reply_text("I am heavily encrypted. 🛡️")
    target_karma = get_karma(target.id)
    if target_karma < 20: return await update.effective_message.reply_text(f"{target.first_name} is already broke. Leave them be.")
    if random.choice([True, False, False, False]):
        loot = int(target_karma * 0.2)
        modify_karma(target.id, -loot); modify_karma(user.id, loot)
        await update.effective_message.reply_text(f"🥷 **HEIST SUCCESSFUL.** {user.first_name} stole {loot} Dino Coins from {target.first_name}!")
    else:
        penalty = 30
        modify_karma(user.id, -penalty)
        await update.effective_message.reply_text(f"🚔 **CAUGHT.** {user.first_name} was caught.\nPenalty: -{penalty} Dino Coins.")

async def pay_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message.reply_to_message: return await update.effective_message.reply_text("Reply to the user you want to pay.")
    user, target = update.effective_user, update.effective_message.reply_to_message.from_user
    try: amount = int(context.args[0])
    except: return await update.effective_message.reply_text("Format: /pay [amount]")
    if amount <= 0 or amount > get_karma(user.id): return await update.effective_message.reply_text("Insufficient funds.")
    modify_karma(user.id, -amount); modify_karma(target.id, amount)
    await update.effective_message.reply_text(f"💸 {user.first_name} transferred {amount} Dino Coins to {target.first_name}.")

async def karma_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.effective_message.reply_to_message.from_user if update.effective_message.reply_to_message else update.effective_user
    k = get_karma(target.id)
    await update.effective_message.reply_text(f"💳 {target.first_name}'s Social Credit: **{k} Dino Coins.**", parse_mode="Markdown")

# ---------------------------------------------------------------------------
# XI. CREATOR COMMANDS & HUD
# ---------------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    web_url = "https://abhishake151107-collab.github.io/stark-os-ui/"
    kb = [[InlineKeyboardButton("🚀 LAUNCH GOD CORE V7.5", web_app=WebAppInfo(url=web_url))]]
    await update.effective_message.reply_text("✨ **J.A.R.V.I.S. Cognitive Core Online.**\n\nSir, your cinematic interface is ready.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def hud_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exclusive Creator HUD."""
    if update.effective_chat.type != "private": return
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    web_url = "https://abhishake151107-collab.github.io/stark-os-ui/"
    kb = [
        [InlineKeyboardButton("🚀 OPEN STARK OS TERMINAL", web_app=WebAppInfo(url=web_url))],
        [InlineKeyboardButton("🌐 Force News", callback_data="cmd_news"), InlineKeyboardButton("🎨 Generate Image", callback_data="hud_cmd_imagine")],
        [InlineKeyboardButton("☀️ Blast Morning", callback_data="cmd_morning"), InlineKeyboardButton("🌙 Blast Night", callback_data="cmd_night")],
        [InlineKeyboardButton("👥 Pull Group Intel", callback_data="hud_intel"), InlineKeyboardButton("🛡️ Toggle CAPTCHA", callback_data="hud_captcha")],
        [InlineKeyboardButton("🗄️ Backup Vault", callback_data="hud_cmd_backup"), InlineKeyboardButton("📜 Quote Wall", callback_data="hud_cmd_quote")],
        [InlineKeyboardButton("👁️ Vision Core", callback_data="hud_info_vision"), InlineKeyboardButton("🎧 Audio Core", callback_data="hud_info_audio")]
    ]
    await update.effective_message.reply_text("```\n[ STARK INDUSTRIES TERMINAL ]\nSystem: J.A.R.V.I.S. Master Core V7.5\nStatus: Online\nSelect module:\n```", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def speak_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    text = " ".join(context.args)
    if not text: return await update.effective_message.reply_text("Format: /speak [text]")
    status_msg = await update.effective_message.reply_text("`[SYSTEM]: Initializing TTS Engine...`", parse_mode="Markdown")
    try:
        import edge_tts
        audio_text, voice_model, _ = process_acoustic_payload(text)
        communicate = edge_tts.Communicate(audio_text, voice_model, rate="-5%")
        voice_file = f"speak_{update.effective_user.id}_{int(time.time()*1000)}.ogg"
        await communicate.save(voice_file)
        with open(voice_file, "rb") as audio_file: await update.effective_message.reply_voice(voice=audio_file)
        os.remove(voice_file)
        await status_msg.delete()
    except Exception as e: await status_msg.edit_text(f"Audio Core Offline: {e}")

async def god_mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    cmd, chat_id, args = update.effective_message.text.split()[0].lower(), update.effective_chat.id, " ".join(context.args)
    try:
        if cmd == "/setname" and args: await context.bot.set_chat_title(chat_id, args); await update.effective_message.reply_text(f"Group name updated to: {args}")
        elif cmd == "/setdesc" and args: await context.bot.set_chat_description(chat_id, args); await update.effective_message.reply_text("Group description updated.")
        elif cmd == "/setdp" and update.effective_message.reply_to_message and update.effective_message.reply_to_message.photo:
            img_bytes = await (await update.effective_message.reply_to_message.photo[-1].get_file()).download_as_bytearray()
            await context.bot.set_chat_photo(chat_id, photo=img_bytes); await update.effective_message.reply_text("Group photo updated.")
        elif cmd == "/pin" and update.effective_message.reply_to_message: await context.bot.pin_chat_message(chat_id, update.effective_message.reply_to_message.message_id); await update.effective_message.reply_text("Message pinned.")
        elif cmd == "/lock": await context.bot.set_chat_permissions(chat_id, ChatPermissions(can_send_messages=False)); await update.effective_message.reply_text("🔒 Chat locked. No one can speak.")
        elif cmd == "/unlock": await context.bot.set_chat_permissions(chat_id, ChatPermissions(can_send_messages=True, can_send_photos=True, can_send_videos=True, can_send_documents=True, can_send_audios=True, can_send_other_messages=True)); await update.effective_message.reply_text("🔓 Chat unlocked.")
        elif cmd == "/captcha": 
            if args.lower() in ["on", "off"]: set_setting("captcha", args.lower()); await update.effective_message.reply_text(f"CAPTCHA is now {args.upper()}.")
        elif cmd == "/say" and len(context.args) >= 2: await context.bot.send_message(chat_id=context.args[0], text=" ".join(context.args[1:]))
    except Exception as e: await update.effective_message.reply_text(f"Action failed. Error: {e}")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    with sqlite3.connect(DB_PATH) as conn:
        mem = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
        users = conn.execute("SELECT COUNT(*) FROM roster").fetchone()[0]
    await update.effective_message.reply_text(f"📊 **System Diagnostics**\n• Memory Nodes: {mem}\n• Tracked Users: {users}\n• API Cascade: Active", parse_mode="Markdown")

async def flush_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM memory WHERE chat_id = ?", (update.effective_chat.id,))
        conn.commit()
    await update.effective_message.reply_text("🧠 Local memory wiped. Echo chamber destroyed.")

async def group_info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat, user = update.effective_chat, update.effective_user
    if chat.type == "private" and user.id == CREATOR_ID:
        with sqlite3.connect(DB_PATH) as conn:
            groups = conn.execute("SELECT chat_id, title FROM chats WHERE chat_id < 0").fetchall()
            report = "📁 **GLOBAL OMNI-SCAN: ALL SECURED GROUPS**\n\n"
            for gid, title in groups:
                mem_count = conn.execute("SELECT COUNT(*) FROM memory WHERE chat_id = ?", (gid,)).fetchone()[0]
                user_count = conn.execute("SELECT COUNT(*) FROM roster WHERE chat_id = ?", (gid,)).fetchone()[0]
                warn_count = conn.execute("SELECT SUM(count) FROM warnings WHERE chat_id = ?", (gid,)).fetchone()[0] or 0
                report += f"**{title}**\n• Group ID: `{gid}`\n• Members: {user_count}\n• Memory: {mem_count} nodes\n• Warnings: {warn_count}\n\n"
            return await update.effective_message.reply_text(report, parse_mode="Markdown")
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ['creator', 'administrator'] and user.id != CREATOR_ID: return await update.effective_message.reply_text("⛔ Access Denied.")
    with sqlite3.connect(DB_PATH) as conn:
        mem_count = conn.execute("SELECT COUNT(*) FROM memory WHERE chat_id = ?", (chat.id,)).fetchone()[0]
        user_count = conn.execute("SELECT COUNT(*) FROM roster WHERE chat_id = ?", (chat.id,)).fetchone()[0]
        warn_count = conn.execute("SELECT SUM(count) FROM warnings WHERE chat_id = ?", (chat.id,)).fetchone()[0] or 0
    await update.effective_message.reply_text(f"📁 **Group Intel: {chat.title}**\n\n👥 Members: {user_count}\n🧠 Memory Nodes: {mem_count}\n⚠️ Warnings Issued: {warn_count}", parse_mode="Markdown")

# ---------------------------------------------------------------------------
# XII. GENERAL UTILITIES
# ---------------------------------------------------------------------------
async def tldr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    history = get_chat_history(chat_id, limit=20)
    if not history: return await update.effective_message.reply_text("No recent memory found. 🤷‍♂️")
    chat_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in history])
    
    status_msg = await update.effective_message.reply_text("`[SYSTEM]: Summarizing memory nodes...`", parse_mode="Markdown")
    raw_response = await generate_response(f"Summarize this:\n{chat_text}", [], "Provide a sarcastic 3-bullet-point summary of what they are arguing about.", update.effective_user.id, update.effective_user.first_name, force_route="search")
    await status_msg.edit_text(raw_response)

async def roast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_lockdown(): return
    target = " ".join(context.args) or (update.effective_message.reply_to_message.from_user.first_name if update.effective_message.reply_to_message else "someone")
    
    status_msg = await update.effective_message.reply_text("`[SYSTEM]: Synthesizing roast protocol...`", parse_mode="Markdown")
    roast_prompt = "Generate a witty, clever roast for the person named. Mix English, Kannada, and Hindi slang naturally. Max 2 sentences."
    raw_response = await generate_response(f"Roast {target}", [], roast_prompt, update.effective_user.id, update.effective_user.first_name)
    await status_msg.edit_text(raw_response)
    # Force voice on roast
    await trigger_auto_voice(update, raw_response + "\n")

async def shutup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    if not update.effective_message.reply_to_message: return await update.effective_message.reply_text("Reply to the person you want me to silence.")
    target, chat_id = update.effective_message.reply_to_message.from_user, update.effective_chat.id
    try:
        await context.bot.restrict_chat_member(chat_id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=int(time.time()) + 300)
        modify_karma(target.id, -20)
        await update.effective_message.reply_text(f"As you wish, Sir. {target.first_name} has been silenced for 5 minutes. Penalty: -20 Dino Coins. 🤫")
    except Exception: await update.effective_message.reply_text("I require elevated Admin privileges.")

async def afk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = " ".join(context.args) or "Busy"
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO afk (user_id, reason) VALUES (?, ?)", (update.effective_user.id, reason))
        conn.commit()
    await update.effective_message.reply_text(f"Status updated. I will inform anyone who tags you that you are AFK: {reason} 🛡️")

async def quote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message.reply_to_message or not update.effective_message.reply_to_message.text: return await update.effective_message.reply_text("Reply to a text message.")
    target, quote_text = update.effective_message.reply_to_message.from_user.first_name, update.effective_message.reply_to_message.text
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO quotes (chat_id, user_name, quote_text) VALUES (?, ?, ?)", (update.effective_chat.id, target, quote_text))
        conn.commit()
    modify_karma(update.effective_message.reply_to_message.from_user.id, 10)
    await update.effective_message.reply_text(f"📜 Added to Hall of Fame (+10 Coins to {target}):\n\n*\"{quote_text}\"* \n— _{target}_", parse_mode="Markdown")

async def confess_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return await update.effective_message.reply_text("This works in private DMs only.")
    if len(context.args) < 2: return await update.effective_message.reply_text("Format: /confess [chat_id] [your secret message]")
    try:
        await context.bot.send_message(chat_id=context.args[0], text=f"🎭 **Anonymous Confession:**\n\n_{' '.join(context.args[1:])}_", parse_mode="Markdown")
        await update.effective_message.reply_text("Confession securely dropped, Sir. 🥷")
    except Exception as e: await update.effective_message.reply_text(f"Failed. Error: {e}")

async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    task_text = " ".join(context.args)
    if not task_text: return await update.effective_message.reply_text("Format: /task [description]")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO tasks (user_id, task_crypt) VALUES (?, ?)", (update.effective_user.id, encrypt_data(task_text)))
        conn.commit()
    await update.effective_message.reply_text("Task added to the queue, Sir. 📝")

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): return
    with sqlite3.connect(DB_PATH) as conn: rows = conn.execute("SELECT id, task_crypt FROM tasks WHERE status = 'pending' AND user_id = ?", (update.effective_user.id,)).fetchall()
    if not rows: return await update.effective_message.reply_text("Your schedule is clear, Sir. ☕")
    for r in rows: await update.effective_message.reply_text(f"📌 {decrypt_data(r[1])}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Mark Done", callback_data=f"tdone_{r[0]}"), InlineKeyboardButton("🗑️ Delete", callback_data=f"tdel_{r[0]}")]]))

async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    try: 
        if os.path.exists(DB_PATH):
            with open(DB_PATH, 'rb') as f: 
                await context.bot.send_document(chat_id=CREATOR_ID, document=f, filename="jarvis_backup.db")
    except Exception as e: await update.effective_message.reply_text(f"Backup failed: {e}")

async def imagine_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt: return await update.effective_message.reply_text("Format: /imagine [prompt]")
    status_msg = await update.effective_message.reply_text("`[SYSTEM]: Synthesizing image...`", parse_mode="Markdown")
    await update.effective_message.reply_photo(photo=f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=1024&height=1024&nologo=true", caption=f"Rendered: {prompt}")
    await status_msg.delete()

MORSE_DICT = {'A':'.-','B':'-...','C':'-.-.','D':'-..','E':'.','F':'..-.','G':'--.','H':'....','I':'..','J':'.---','K':'-.-','L':'.-..','M':'--','N':'-.','O':'---','P':'.--.','Q':'--.-','R':'.-.','S':'...','T':'-','U':'..-','V':'...-','W':'.--','X':'-..-','Y':'-.--','Z':'--..','1':'.----','2':'..---','3':'...--','4':'....-','5':'.....','6':'-....','7':'--...','8':'---..','9':'----.','0':'-----',' ':'/'}
async def morse_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).upper()
    if not text: return await update.effective_message.reply_text("Format: /morse [text]")
    await update.effective_message.reply_text(f"📡 `{' '.join(MORSE_DICT.get(c, c) for c in text)}`", parse_mode="Markdown")

async def calc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = "".join(context.args)
    if not expr: return await update.effective_message.reply_text("Format: /calc [expression]")
    try:
        if not all(c in "0123456789+-*/(). " for c in expr): raise ValueError
        await update.effective_message.reply_text(f"Result: `{eval(expr, {'__builtins__': None}, {})}`", parse_mode="Markdown")
    except Exception: await update.effective_message.reply_text("Invalid calculation.")

# ---------------------------------------------------------------------------
# XIII. INTERACTIVE CALLBACKS
# ---------------------------------------------------------------------------
async def interactive_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("hud_") or data.startswith("cmd_"):
        action = data.replace("hud_", "").replace("cmd_", "")
        if action == "intel":
            with sqlite3.connect(DB_PATH) as conn:
                groups = conn.execute("SELECT chat_id, title FROM chats WHERE chat_id < 0").fetchall()
                roster_rows = conn.execute("SELECT name, username, chat_id FROM roster").fetchall()
            dossier = "👥 **STARK HUD: GROUP INTEL DOSSIER**\n\n"
            for gid, title in groups:
                dossier += f"📁 **Group:** {title} (`{gid}`)\n"
                for m in [r for r in roster_rows if r[2] == gid]: dossier += f"  • {m[0]} (@{m[1]})\n"
            await query.edit_message_text(dossier[:4000] if groups else "No groups.", parse_mode="Markdown")
        elif action == "captcha":
            state = "off" if get_setting("captcha", "on") == "on" else "on"
            set_setting("captcha", state)
            await query.edit_message_text(f"🛡️ Security Gate is now {state.upper()}.")
        elif action in ["news", "morning", "night"]: await query.edit_message_text(f"💻 **Terminal Instruction:**\nTo execute this routine directly, type `/{action}` in the chat.", parse_mode="Markdown")
        elif action.startswith("info_"): await query.edit_message_text(f"📡 **Sensor Status:** {action.replace('info_', '').upper()} core is active. Upload media directly to engage.", parse_mode="Markdown")

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
            
    if msg.entities:
        with sqlite3.connect(DB_PATH) as conn:
            for ent in msg.entities:
                if ent.type == "mention":
                    target_id_row = conn.execute("SELECT user_id, name FROM roster WHERE username = ?", (text[ent.offset+1 : ent.offset+ent.length].lower(),)).fetchone()
                    if target_id_row:
                        conn.execute("INSERT INTO interactions (user_a, user_b, interactions) VALUES (?, ?, 1) ON CONFLICT(user_a, user_b) DO UPDATE SET interactions = interactions + 1", (user.id, target_id_row[0]))
                        conn.commit()
                        afk_status = conn.execute("SELECT reason FROM afk WHERE user_id = ?", (target_id_row[0],)).fetchone()
                        if afk_status: await msg.reply_text(f"⚠️ {target_id_row[1]} is currently AFK: {afk_status[0]}")

    bot_username = (await context.bot.get_me()).username
    is_triggered = (chat.type == "private") or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis)\b', text, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in text.lower())
    
    if any(kw in text.lower() for kw in ["forwarded", "exam postponed", "paper leak", "cancelled"]):
        status_msg = await msg.reply_text("`[SYSTEM]: Querying DPUE database...`", parse_mode="Markdown")
        debunk_msg = await gemini_live_search(f"Is there any official news about Karnataka 2nd PUC exams being postponed or leaked today? Check {text}", "You are a fact-checker. Provide a strictly factual 1-sentence verification.", [])
        if debunk_msg: await status_msg.edit_text(f"🛡️ **Fact Check:** {debunk_msg}")
        return

    if "youtube.com" in text or "youtu.be" in text or "spotify.com" in text:
        status_msg = await msg.reply_text("`[SYSTEM]: Parsing media stream...`", parse_mode="Markdown")
        transcript = await extract_youtube_transcript(text)
        if transcript:
            summary = await generate_response(f"Summarize this YouTube video transcript in 3 bullet points: {transcript}", [], "You are J.A.R.V.I.S. Provide a cynical 3-bullet summary.", user.id, user.first_name, status_msg)
            await status_msg.edit_text(f"📺 **Media Intercepted. Summary:**\n\n{summary}")
            return
        
    if any(kw in text.lower() for kw in ["accountancy", "economics", "formula", "business", "computer science", "political science"]):
        for subject, facts in PUC_ACADEMIC_MATRIX.items():
            if subject in text.lower():
                await msg.reply_text(facts)
                modify_karma(user.id, 5)
                return

    # Check for direct matrix queries
    if "instagram" in text.lower() or "algorithm" in text.lower() or "doomscroll" in text.lower():
        matrix_text = "\n\n".join(ALGORITHMIC_THREAT_MATRIX.values())
        return await msg.reply_text(f"🧠 **[ ALGORITHMIC THREAT MATRIX ]**\n\n{matrix_text}", parse_mode="Markdown")
        
    if "neurochem" in text.lower() or "mood swing" in text.lower() or "cortisol" in text.lower():
        matrix_text = "\n\n".join(BIOMETRIC_DIAGNOSTICS_MATRIX.values())
        return await msg.reply_text(f"🧬 **[ BIOMETRIC DIAGNOSTICS ]**\n\n{matrix_text}", parse_mode="Markdown")
        
    if "agent" in text.lower() or "rag" in text.lower() or "planner" in text.lower():
        matrix_text = "\n\n".join(AGENTIC_ARCHITECTURE_MATRIX.values())
        return await msg.reply_text(f"⚙️ **[ AGENTIC ARCHITECTURE ]**\n\n{matrix_text}", parse_mode="Markdown")

    if not is_triggered and chat.type != "private":
        if re.search(r'\b(abhishek|dhanush)\b', text, re.IGNORECASE) and user.id != CREATOR_ID:
            if CREATOR_ID:
                try: await context.bot.send_message(chat_id=CREATOR_ID, text=f"👻 **Ghost Intercept:** `{user.first_name}` mentioned you in {chat.title}.\n_{text}_", parse_mode="Markdown")
                except Exception: pass
        return
    
    if not is_triggered: return
    
    status_msg = await msg.reply_text("`[SYSTEM]: Analyzing intent...`", parse_mode="Markdown")
    
    sys_prompt = build_system_prompt(user.id, user.first_name, chat.id, user_prompt=text)
    raw_ai_response = await generate_response(text, get_chat_history(chat.id, thread_id), sys_prompt, user.id, user.first_name, status_msg)
    
    final_text = await route_response(msg, raw_ai_response, user, chat, context)
    log_memory(chat.id, thread_id, user.id, "assistant", final_text)
    
    await status_msg.edit_text(final_text)
    await trigger_auto_voice(update, final_text)

# ---------------------------------------------------------------------------
# XIV. AUTOMATED SCHEDULERS & BACKGROUND TASKS
# ---------------------------------------------------------------------------
async def cloud_save_routine(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.unpin_all_chat_messages(chat_id=BACKUP_CHANNEL_ID)
        with open(DB_PATH, 'rb') as f:
            msg = await context.bot.send_document(chat_id=BACKUP_CHANNEL_ID, document=f, filename="jarvis_vault.db")
            await msg.pin(disable_notification=True)
    except Exception as e: logger.error(f"Cloud Save Failed: {e}")

async def flashcard_drill(context: ContextTypes.DEFAULT_TYPE):
    msg = "🧠 **Daily Flashcard Drill**\n\n_What is the formula for Sacrificing Ratio in Partnership Accounting?_\n\nFirst to answer correctly earns 50 Dino Coins."
    with sqlite3.connect(DB_PATH) as conn: groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
    for g in groups:
        try: await context.bot.send_message(chat_id=g[0], text=msg, parse_mode="Markdown")
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
                    event_hash = hashlib.md5(f"{url}_{headline}".encode()).hexdigest()
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
                if len(decrypted) > 50: conn.execute("INSERT INTO lore_vault (chat_id, context_data) VALUES (?, ?)", (chat_id, decrypted[:500]))
            conn.execute("DELETE FROM memory WHERE timestamp <= datetime('now', '-7 days')")
            conn.commit()
        if CREATOR_ID: 
            await context.bot.send_message(chat_id=CREATOR_ID, text="🧠 **Cognitive Cycle Complete:** Vault synced.", parse_mode="Markdown")
            with open(DB_PATH, 'rb') as f: await context.bot.send_document(chat_id=CREATOR_ID, document=f, filename="jarvis_cloud_sync.db")
    except Exception as e: logger.error(f"Reconciliation error: {e}")

async def exam_morning_alert(context: ContextTypes.DEFAULT_TYPE):
    exam_subject = EXAM_SCHEDULE_COMMERCE_ARTS.get(datetime.now(IST).strftime("%Y-%m-%d"))
    if not exam_subject: return
    msg = f"🔔 **2nd PUC Midterm Exam Today**\n• **Paper:** {exam_subject}\n• **Timing:** 10:00 AM – 1:00 PM\nBest of luck, gentlemen. 🎯"
    with sqlite3.connect(DB_PATH) as conn: groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
    for g in groups:
        try: await context.bot.send_message(chat_id=g[0], text=msg, parse_mode="Markdown")
        except Exception: pass

async def group_morning_news(context: ContextTypes.DEFAULT_TYPE):
    news_text = await global_intel_engine("top 3 global tech headlines today")
    with sqlite3.connect(DB_PATH) as conn: groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
    for g in groups:
        try: await context.bot.send_message(chat_id=g[0], text=f"☀️ **Good morning, everyone.**\n\n{news_text}", parse_mode="Markdown")
        except Exception: pass

async def creator_morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    if not CREATOR_ID: return
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT task_crypt FROM tasks WHERE status = 'pending' AND user_id = ?", (CREATOR_ID,)).fetchall()
        groups_count = conn.execute("SELECT COUNT(DISTINCT chat_id) FROM chats WHERE chat_id < 0").fetchone()[0]
        warn_count = conn.execute("SELECT SUM(count) FROM warnings").fetchone()[0] or 0
    world_news = await global_intel_engine("top 2 international news today")
    task_list = "\n".join([f"- {decrypt_data(r[0])}" for r in rows]) if rows else "Clear."
    report = f"☕ **Morning Executive Briefing**\n\n🛡️ **Group Security Audit:**\n• Monitored Channels: {groups_count}\n• Outstanding Warnings: {warn_count}\n• Security Gate: {get_setting('captcha', 'on').upper()}\n\n🌐 **Intel:**\n{world_news}\n\n📝 **Pending Tasks:**\n{task_list}"
    try: await context.bot.send_message(chat_id=CREATOR_ID, text=report, parse_mode="Markdown")
    except Exception: pass

async def group_night_routine(context: ContextTypes.DEFAULT_TYPE):
    tomorrow_exam = EXAM_SCHEDULE_COMMERCE_ARTS.get((datetime.now(IST) + timedelta(days=1)).strftime("%Y-%m-%d"))
    night_msg = "🌙 **Good night, gentlemen.** Systems standing down for evening standby."
    if tomorrow_exam: night_msg += f"\n\n⚠️ **Academic Notice (Tomorrow's Exam):**\n• **Paper:** {tomorrow_exam}\n• **Timing:** 10:00 AM – 1:00 PM\nGet adequate rest."
    with sqlite3.connect(DB_PATH) as conn: groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
    for g in groups:
        try: await context.bot.send_message(chat_id=g[0], text=night_msg, parse_mode="Markdown")
        except Exception: pass

async def breaking_news_monitor(context: ContextTypes.DEFAULT_TYPE):
    if not CREATOR_ID: return
    try:
        searxng_nodes = ["https://searx.be", "https://searx.tiekoetter.com", "https://search.ononoki.org"]
        async with httpx.AsyncClient() as client:
            random.shuffle(searxng_nodes)
            latest = None
            for node in searxng_nodes:
                try:
                    resp = await client.get(
                        f"{node}/search", 
                        params={"q": "breaking world crisis news", "format": "json", "categories": "news", "language": "en"}, 
                        timeout=8.0
                    )
                    if resp.status_code == 200:
                        results = resp.json().get('results', [])
                        if results:
                            latest = results[0]
                            break
                except Exception: continue
            
            if latest:
                event_hash = hashlib.md5(latest['title'].encode()).hexdigest()
                with sqlite3.connect(DB_PATH) as conn:
                    if conn.execute("SELECT id FROM breaking_news WHERE hash = ?", (event_hash,)).fetchone(): return
                    conn.execute("INSERT INTO breaking_news (hash, headline) VALUES (?, ?)", (event_hash, latest['title']))
                    conn.commit()
                await context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **EMERGENCY WORLD ALERT**\n\n{latest['title']}\n\n_Dispatched to Stark Terminal via SearXNG FOSS._", parse_mode="Markdown")
    except Exception: pass

async def morning_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    await group_morning_news(context)
    await update.effective_message.reply_text("☀️ Morning protocol forcefully dispatched to all groups, Sir.")

async def night_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    await group_night_routine(context)
    await update.effective_message.reply_text("🌙 Night protocol forcefully dispatched to all groups, Sir.")

async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.effective_message.reply_text("`[SYSTEM]: Querying global feeds...`", parse_mode="Markdown")
    news_text = await global_intel_engine("top 3 global news today", status_msg)
    await status_msg.edit_text(f"📰 **Direct Live Briefing:**\n\n{news_text}", parse_mode="Markdown")

# ---------------------------------------------------------------------------
# XV. BOOT SEQUENCE & MAIN EXECUTION
# ---------------------------------------------------------------------------
async def post_init(app: Application):
    # 1. Cloud Restore Protocol
    try:
        chat = await app.bot.get_chat(BACKUP_CHANNEL_ID)
        if chat.pinned_message and chat.pinned_message.document:
            file = await app.bot.get_file(chat.pinned_message.document.file_id)
            await file.download_to_drive(DB_PATH)
            if CREATOR_ID: 
                await app.bot.send_message(chat_id=CREATOR_ID, text="☁️ Cloud Restore Complete. Vault loaded.")
    except Exception as e:
        logger.error(f"Cloud Restore Failed: {e}")
        if CREATOR_ID: 
            try: await app.bot.send_message(chat_id=CREATOR_ID, text=f"⚠️ Cloud Restore Warning: Failed to load backup.\n{e}")
            except Exception: pass

    # 2. Cron Scheduler Boot
    scheduler = AsyncIOScheduler(timezone=IST)
    scheduler.add_job(cloud_save_routine, 'interval', minutes=30, args=[app])
    scheduler.add_job(exam_morning_alert, 'cron', hour=6, minute=0, args=[app])
    scheduler.add_job(group_morning_news, 'cron', hour=7, minute=0, args=[app])
    scheduler.add_job(creator_morning_briefing, 'cron', hour=8, minute=0, args=[app])
    scheduler.add_job(flashcard_drill, 'cron', hour=18, minute=0, args=[app])
    scheduler.add_job(group_night_routine, 'cron', hour=21, minute=0, args=[app])
    scheduler.add_job(nightly_reconciliation, 'cron', hour=3, minute=0, args=[app])
    scheduler.add_job(dpue_board_scraper, 'interval', minutes=45, args=[app])
    scheduler.add_job(breaking_news_monitor, 'interval', minutes=30, args=[app])
    
    jobs = load_cron_jobs()
    for jid, j in jobs.items():
        try:
            fields = j['expr'].split()
            trigger = CronTrigger(minute=fields[0], hour=fields[1], day=fields[2], month=fields[3], day_of_week=fields[4], timezone=IST)
            scheduler.add_job(runtime_cron_fire, trigger, args=[app.bot, j['cmd']], id=f"runtime_{jid}")
        except Exception as e: logger.error(f"Failed to restore cron {jid}: {e}")

    scheduler.start()
    
    # 3. Boot Telemetry Dispatch
    if CREATOR_ID: 
        boot_msg = (
            "✨ <b>God Core V7.5 (Architect Edition) Online.</b>\n"
            "• Infinite Cloud Save: Armed (-1004296302955)\n"
            "• Deep Research Agent: Active (DDG + Wiki)\n"
            "• Biological Diagnostic Matrix: Engaged\n"
            "• Algorithmic Threat Detection: Active\n"
            "• Multi-Node Swarm Routing: Active\n"
            "• Cognitive Monologue Scrubber: Engaged\n"
            "• Acoustic Link Scrubber: Active"
        )
        try: 
            await app.bot.send_message(chat_id=CREATOR_ID, text=boot_msg, parse_mode="HTML")
            logger.info("Boot telemetry successfully dispatched to Creator DM.")
        except Exception as e: 
            logger.error(f"CRITICAL: Failed to dispatch boot message to Creator DM. Error: {e}")
    else:
        logger.error("CRITICAL: CREATOR_ID is 0 or missing. Cannot dispatch boot message.")

def main():
    db_init()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Root, Shell, Schedulers & Config
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd)) 
    app.add_handler(CommandHandler("exec", exec_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("sys", sys_diagnostics_cmd))
    app.add_handler(CommandHandler("shield", shield_check_cmd))
    app.add_handler(CommandHandler("scrape", omni_scrape_cmd))
    app.add_handler(CommandHandler("research", deep_research_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("intel", intel_cmd))
    app.add_handler(CommandHandler("cron", cron_cmd))
    app.add_handler(CommandHandler("lockdown", lockdown_cmd))
    app.add_handler(CommandHandler("update", update_cmd))
    app.add_handler(CommandHandler("sendcode", sendcode_cmd))
    app.add_handler(CommandHandler("purge", purge_cmd))
    app.add_handler(CommandHandler("flush", flush_cmd))
    app.add_handler(CommandHandler("speak", speak_cmd))
    app.add_handler(CommandHandler("task", add_task))
    app.add_handler(CommandHandler("tasks", list_tasks))
    app.add_handler(CommandHandler("calc", calc_cmd))
    app.add_handler(CommandHandler("morse", morse_cmd))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("imagine", imagine_cmd))
    app.add_handler(CommandHandler("hud", hud_cmd))
    app.add_handler(CommandHandler("groupinfo", group_info_cmd))
    
    app.add_handler(CommandHandler("setname", god_mode_cmd))
    app.add_handler(CommandHandler("setdesc", god_mode_cmd))
    app.add_handler(CommandHandler("setdp", god_mode_cmd))
    app.add_handler(CommandHandler("pin", god_mode_cmd))
    app.add_handler(CommandHandler("lock", god_mode_cmd))
    app.add_handler(CommandHandler("unlock", god_mode_cmd))
    app.add_handler(CommandHandler("captcha", god_mode_cmd))
    app.add_handler(CommandHandler("say", god_mode_cmd))
    
    # Economy & Social
    app.add_handler(CommandHandler("tldr", tldr_cmd))
    app.add_handler(CommandHandler("roast", roast_cmd))
    app.add_handler(CommandHandler("shutup", shutup_cmd))
    app.add_handler(CommandHandler("afk", afk_cmd))
    app.add_handler(CommandHandler("quote", quote_cmd))
    app.add_handler(CommandHandler("confess", confess_cmd))
    app.add_handler(CommandHandler("warn", warn_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("karma", karma_cmd))
    app.add_handler(CommandHandler("gamble", gamble_cmd))
    app.add_handler(CommandHandler("rob", rob_cmd))
    app.add_handler(CommandHandler("pay", pay_cmd))
    app.add_handler(CommandHandler("news", news_cmd))
    app.add_handler(CommandHandler("morning", morning_cmd))
    app.add_handler(CommandHandler("night", night_cmd))
    
    # Callbacks & Media Handlers
    app.add_handler(CallbackQueryHandler(interactive_callbacks))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_captcha))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, audio_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    
    # Main Message Handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT & ~filters.COMMAND, message_handler))
    
    app.add_error_handler(error_handler)
    
    logger.info("J.A.R.V.I.S. Cognitive V7.5 is booting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
