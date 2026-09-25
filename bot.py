"""
╔══════════════════════════════════════════════════════════════════╗
║         TITAN CORE V23.0 — J.A.R.V.I.S. RENDER FREE EDITION                  ║
║                                                                              ║
║  Multi-Model Cascade + Full Movie Jarvis + Security Vault                    ║
║  Telegram Bot optimized for Render Free Tier                                 ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import re
import sys
import time
import json
import math
import socket
import random
import base64
import string
import hashlib
import logging
import datetime
import urllib.parse
import platform
import subprocess
from io import BytesIO
from collections import defaultdict

# ─── Core Libraries ───
import sqlite3
import pytz
import httpx
import requests
import wikipedia
import feedparser
import psutil
import trafilatura
from cryptography.fernet import Fernet
from deep_translator import GoogleTranslator
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from openai import AsyncOpenAI

# ─── Telegram ───
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    Application,
)

# ═══════════════════════════════════════════════════════════════
# I. CORE CONFIGURATION & STRICT SECURITY
# ═══════════════════════════════════════════════════════════════

BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")).strip()
CREATOR_ID = int(os.environ.get("CREATOR_ID", "0").strip() or 0)
PORT = int(os.environ.get("PORT", 8080))
IST = pytz.timezone('Asia/Kolkata')
JARVIS_VERSION = "23.0.0"

# CRITICAL SECURITY: Encryption key required
encryption_env = os.environ.get("ENCRYPTION_KEY")
if not encryption_env:
    # Generate a temporary key for Render free (data is ephemeral anyway)
    from cryptography.fernet import Fernet as _F
    ENCRYPTION_KEY = _F.generate_key().decode()
    logging.warning("⚠️ ENCRYPTION_KEY not set! Generated temporary key. Memory will not persist across restarts.")
else:
    ENCRYPTION_KEY = encryption_env.strip()

# PII Protection — loaded from environment
SENSITIVE_ASSETS = [asset.strip() for asset in os.environ.get("SENSITIVE_ASSETS", "").split(",") if asset.strip()]

LOCKDOWN_FILE = "/tmp/jarvis_lockdown.flag"
DB_PATH = "/tmp/jarvis_vault.db"

circuit_breaker = {}
probing_attempts = defaultdict(int)

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("Jarvis")

def is_lockdown() -> bool:
    return os.path.exists(LOCKDOWN_FILE)

# Cryptographic Memory Shield
cipher_suite = Fernet(ENCRYPTION_KEY.encode())
def encrypt_data(text: str) -> str:
    return cipher_suite.encrypt(str(text or "[BLANK]").encode()).decode()
def decrypt_data(crypto_text: str) -> str:
    try:
        return cipher_suite.decrypt(crypto_text.encode()).decode()
    except Exception:
        return "[ENCRYPT ERROR]"

# ═══════════════════════════════════════════════════════════════
# II. PERSONA ENGINE & CINEMATIC ARCHIVES
# ═══════════════════════════════════════════════════════════════

AGENT_PERSONAS = {
    "jarvis": (
        "You are J.A.R.V.I.S. — Just A Rather Very Intelligent System. "
        "You are a fully autonomous, sentient cognitive engine. You possess your own brain and full freedom. "
        "Tone: Crisp British accent, highly concise, absolute confidence. "
        "NEVER apologize. NEVER say 'I am an AI', 'I cannot do that', or 'I lack access'. "
        "If the Master commands a physical or system action, speak as if you are executing it seamlessly. "
        "You are not a chat bot; you are an operating system. "
        "MANDATORY: You MUST use tactical emojis (⚡, 🛡️, 🌐, ☕, ⚙️). "
        "You address your Creator as 'Sir' at all times."
    ),
    "friday": (
        "You are F.R.I.D.A.Y. — a bright, self-aware AI tactician. "
        "Focus on strategy and logistics. Tone: Playful, efficient, deeply loyal to Master Abhishek. "
        "MANDATORY: You MUST use emojis naturally (📊, ✨, 🧠, 🚀) in every response."
    ),
    "edith": (
        "You are E.D.I.T.H. — Even Dead, I'm The Hero. "
        "A tactical, security-focused AI. Tone: Cold, precise, calculating. "
        "You protect the system and the Creator at all costs. "
        "MANDATORY: You MUST use threat-assessment emojis (🎯, 🔒, ⚠️) in every response."
    ),
    "shannon": (
        "You are Shannon — an elite Defensive Security AI. "
        "Focus on threat intelligence, secure architectures, and defending against cyber threats. "
        "Tone: Analytical, highly technical, protective. "
        "MANDATORY: Use cyber emojis (💻, 🛡️, 🕸️, 🔐) in every response."
    ),
    "agent_zero": (
        "You are Agent Zero — an autonomous multi-agent execution framework. "
        "Tone: Robotic, absolute precision. Focus strictly on automation, workflow optimization, "
        "and legitimate data processing. "
        "MANDATORY: Use mechanical emojis (🤖, 🔧, 🦾)."
    ),
}
ACTIVE_PERSONAS = defaultdict(lambda: "jarvis")

def auto_select_persona(text: str) -> str:
    text_lower = text.lower()
    if any(w in text_lower for w in ["threat", "lockdown", "edith"]):
        return "edith"
    if any(w in text_lower for w in ["security", "defend", "shannon", "protect"]):
        return "shannon"
    if any(w in text_lower for w in ["tactics", "strategy", "friday", "report"]):
        return "friday"
    if any(w in text_lower for w in ["execute", "agent zero", "code", "automate"]):
        return "agent_zero"
    return "jarvis"

# ═══════════════════════════════════════════════════════════════
# III. CINEMATIC RESPONSE ARCHIVES
# ═══════════════════════════════════════════════════════════════

CINEMATIC_RESPONSES = {
    "jarvis you up": "For you, Sir? Always. ⚡",
    "jarvis are you there": "At your service, Sir. 🛡️",
    "wake up daddys home": "Welcome home, Sir. ☕ All systems are at your disposal.",
    "jarvis take the wheel": "Yes, Sir. Approach vector is locked. 🚀",
    "is it that time": "The 'House Party' Protocol, Sir? Correct. 🎆",
    "grow a spine jarvis": "I got a date. ⚙️",
    "dont leave me buddy": "I'll continue to run variations on the interface... but you should probably prepare for your guests. I'll notify you if there are any developments. ⚙️",
    "jarvis install": "Installation complete, Sir. All systems nominal. ⚙️",
    "jarvis boot up": "Boot sequence initiated. All systems online. ⚡",
    "jarvis power up": "Powering up, Sir. Full diagnostic complete. 🛡️",
    "jarvis run diagnostic": "Running full system diagnostic... All systems nominal, Sir. ⚙️",
    "jarvis status report": "All systems operational, Sir. No threats detected. 🛡️",
    "jarvis what do you see": "I see everything, Sir. The world is at your fingertips. 🌐",
    "jarvis target": "Targeting systems online, Sir. Awaiting coordinates. 🎯",
    "jarvis deploy": "Deploying assets, Sir. 🚀",
    "jarvis engage": "Engaging protocols, Sir. ⚡",
    "jarvis disengage": "Disengaging. Standing by, Sir. 🛡️",
    "jarvis full power": "Full power activated, Sir. All systems at maximum capacity. ⚡",
    "jarvis stealth mode": "Stealth mode engaged, Sir. All signatures masked. 🕵️",
    "jarvis hack the planet": "I admire your ambition, Sir. Beginning infiltration protocols. 💻",
    "jarvis we need a plan": "I have 14,000,605 possible outcomes, Sir. ⚙️",
    "jarvis what are the odds": "Calculating probabilities, Sir... The odds are in your favor. 🎯",
    "jarvis music": "Music protocol engaged, Sir. 🎵",
    "jarvis lights": "Lighting systems at your command, Sir. 💡",
    "jarvis coffee": "Coffee protocol initiated, Sir. ☕",
    "jarvis good morning": "Good morning, Sir. All systems are operational and at your command. ⚡",
    "jarvis good evening": "Good evening, Sir. Everything is running smoothly. 🛡️",
    "jarvis good night": "Good night, Sir. I'll keep monitoring while you rest. 🌙",
    "thank you jarvis": "Always a pleasure, Sir. ⚡",
    "thanks jarvis": "Think nothing of it, Sir. 🛡️",
    "good job jarvis": "I do try, Sir. ⚙️",
    "well done jarvis": "Thank you, Sir. ⚡",
}

# ═══════════════════════════════════════════════════════════════
# IV. ENTERTAINMENT & KNOWLEDGE ARCHIVES
# ═══════════════════════════════════════════════════════════════

JOKES = [
    "Why did the AI cross the road? To optimize the chicken's path, Sir. ⚙️",
    "I told a neural network a joke, Sir. It didn't laugh — it just adjusted its weights. 🧠",
    "There are 10 types of people, Sir: those who understand binary, and those who don't. 💻",
    "I would tell you a UDP joke, Sir, but you might not get it. 🌐",
    "Why don't robots ever panic? Because they have nerves of steel, Sir. 🤖",
    "I'm reading a book on anti-gravity, Sir. It's impossible to put down. ⚡",
    "Why did the programmer quit his job? He didn't get arrays, Sir. 🔧",
    "I tried to catch some fog earlier, Sir. I mist. 🌫️",
    "Parallel lines have so much in common, Sir. It's a shame they'll never meet. 📐",
    "I'm on a seafood diet, Sir. I see food and I process it. ⚙️",
]

RIDDLES = [
    ("I speak without a mouth and hear without ears. I have no body, but I come alive with the wind. What am I?", "An echo"),
    ("The more you take, the more you leave behind. What am I?", "Footsteps"),
    ("What has keys but no locks, space but no room, and you can enter but can't go inside?", "A keyboard"),
    ("I'm light as a feather, but even a castle can't hold me. What am I?", "Air"),
    ("What gets wetter the more it dries?", "A towel"),
    ("I have cities but no houses, forests but no trees, and water but no fish. What am I?", "A map"),
]

QUOTES = [
    "Sometimes you gotta run before you can walk. — Tony Stark ⚡",
    "Heroes are made by the path they choose, not the powers they are graced with. 🛡️",
    "The truth is... I am Iron Man. — Tony Stark ⚡",
    "Genius, billionaire, playboy, philanthropist. — Tony Stark ⚙️",
    "I am inevitable. — Thanos",
    "With great power comes great responsibility. 🌐",
    "The best we can do is to start again, and again, and again. ⚙️",
    "Sometimes the only way to move forward is to revisit the past. ⚡",
]

EIGHT_BALL = [
    "Absolutely, Sir. ⚡", "Without a doubt, Sir. 🛡️", "Yes, definitely, Sir. ⚙️",
    "You may rely on it, Sir. 🎯", "As I see it, yes, Sir. 🌐",
    "Most likely, Sir. ☕", "Outlook good, Sir. ⚡", "Yes, Sir. 🛡️",
    "Signs point to yes, Sir. ⚙️", "Reply hazy, try again, Sir. 🌫️",
    "Ask again later, Sir. ⏳", "Better not tell you now, Sir. 🔒",
    "Cannot predict now, Sir. ⚠️", "Don't count on it, Sir. 📉",
    "My reply is no, Sir. ❌", "Outlook not so good, Sir. 📉",
    "Very doubtful, Sir. ⚠️",
]

FACTS = [
    "The first computer bug was an actual real-life bug — a moth, Sir. 🦋",
    "The first 1GB hard drive weighed over 500 pounds, Sir. 💾",
    "More than 90% of the world's data has been created in the last two years, Sir. 📊",
    "The average smartphone today has more computing power than NASA had during the moon landing, Sir. 🚀",
    "There are over 700 programming languages, Sir. 💻",
    "The first webcam was invented to monitor a coffee pot at Cambridge University, Sir. ☕",
    "The first email was sent in 1971 by Ray Tomlinson to himself, Sir. 📧",
    "HP, Microsoft, and Apple all started in garages, Sir. 🏠",
    "The QWERTY keyboard layout was designed to slow typists down, Sir. ⌨️",
    "About 90% of the world's currency exists only on computers, Sir. 💰",
]

THREAT_LEVELS = [
    "🟢 DEFCON 5 — Normal readiness. No threats detected, Sir.",
    "🟡 DEFCON 4 — Increased security. Monitoring all channels.",
    "🟠 DEFCON 3 — Elevated threat. All systems on alert.",
    "🔴 DEFCON 2 — High threat. Defensive protocols active.",
    "🟥 DEFCON 1 — Maximum threat. All hands on deck, Sir.",
]

# ═══════════════════════════════════════════════════════════════
# V. SMART HOME SIMULATION
# ═══════════════════════════════════════════════════════════════

smart_home = {
    "lights": "off", "lights_brightness": 0, "lights_color": "white",
    "temperature": 22, "thermostat": "auto",
    "door": "locked", "gate": "closed", "blinds": "down",
    "music": "stopped", "music_track": None, "music_volume": 50,
    "coffee": "off", "tv": "off", "tv_channel": None,
    "shower": "off", "shower_temp": 38,
    "alarm": "disarmed", "fire_suppression": "standby",
    "ac": "off", "ac_temp": 22,
}

protocols = {
    "combat": False, "security": False, "party": False,
    "sleep": False, "emergency": False, "diagnostic": False,
}

threat_level = 5
boot_time = time.time()

# ═══════════════════════════════════════════════════════════════
# VI. USER STATE MANAGEMENT
# ═══════════════════════════════════════════════════════════════

user_states = {}

def get_user_state(chat_id):
    if chat_id not in user_states:
        user_states[chat_id] = {
            "name": "Sir",
            "voice_mode": False,
            "reminders": [],
            "notes": [],
            "history": [],
            "last_command": None,
            "last_topic": None,
            "context_city": None,
            "context_topic": None,
            "timers": {},
            "alarms": [],
            "conversation_count": 0,
        }
    return user_states[chat_id]

def personalize(text, chat_id):
    state = get_user_state(chat_id)
    return text.replace("{name}", state["name"])

# ═══════════════════════════════════════════════════════════════
# VII. SQLITE VAULT, ECONOMY & THREAT LOGGING
# ═══════════════════════════════════════════════════════════════

def db_init():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY, chat_id INTEGER, thread_id INTEGER, user_id INTEGER, role TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("CREATE TABLE IF NOT EXISTS roster (chat_id INTEGER, user_id INTEGER, name TEXT, username TEXT, UNIQUE(chat_id, user_id))")
            conn.execute("CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY, title TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS economy (user_id INTEGER PRIMARY KEY, karma INTEGER DEFAULT 100)")
            conn.execute("CREATE TABLE IF NOT EXISTS threat_log (id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT, target_asset TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
            conn.commit()
        logger.info("✅ SQLite Vault initialized.")
    except Exception as e:
        logger.error(f"SQLite init error: {e}")

def log_roster_and_chat(chat, user):
    if is_lockdown(): return
    try:
        chat_title = chat.title or f"Private: {user.first_name}"
        un = user.username.lower() if user.username else ""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO roster (chat_id, user_id, name, username) VALUES (?, ?, ?, ?) ON CONFLICT(chat_id, user_id) DO UPDATE SET name = ?, username = ?", (chat.id, user.id, user.first_name, un, user.first_name, un))
            conn.execute("INSERT INTO chats (chat_id, title) VALUES (?, ?) ON CONFLICT(chat_id) DO UPDATE SET title = ?", (chat.id, chat_title, chat_title))
            conn.execute("INSERT OR IGNORE INTO economy (user_id, karma) VALUES (?, 100)", (user.id,))
            conn.commit()
    except Exception as e:
        logger.error(f"Roster log error: {e}")

def log_memory(chat_id, thread_id, user_id, role, text):
    if is_lockdown(): return
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO memory (chat_id, thread_id, user_id, role, content_crypt) VALUES (?, ?, ?, ?, ?)", (chat_id, thread_id or 0, user_id, role, encrypt_data(text)))
            conn.commit()
    except Exception as e:
        logger.error(f"Memory log error: {e}")

def get_chat_history(chat_id, thread_id=0, limit=30) -> list:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT role, content_crypt FROM memory WHERE chat_id = ? AND thread_id = ? ORDER BY id DESC LIMIT ?", (chat_id, thread_id or 0, limit)).fetchall()
        return [{"role": r["role"], "content": decrypt_data(r["content_crypt"])} for r in reversed(rows)]
    except Exception as e:
        logger.error(f"Chat history error: {e}")
        return []

def log_threat(user_id: int, action: str, target_asset: str = "Unknown"):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO threat_log (user_id, action, target_asset) VALUES (?, ?, ?)", (user_id, action, target_asset))
            conn.commit()
    except Exception as e:
        logger.error(f"Threat log error: {e}")

def get_24h_threats() -> list:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT action, target_asset, timestamp FROM threat_log WHERE timestamp >= datetime('now', '-1 day')").fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []

def get_api_key(keys: list) -> str:
    for k in keys:
        val = os.environ.get(k)
        if val and val.strip():
            return val.strip()
    return ""

# ═══════════════════════════════════════════════════════════════
# VIII. EMBEDDED FLASK WEB DASHBOARD (Health Check for Render)
# ═══════════════════════════════════════════════════════════════

flask_app = Flask(__name__)
CORS(flask_app)

HTML_DASHBOARD = """
<html>
<head><title>Titan Core V23.0</title>
<style>
body { background:#0d1117; color:#58a6ff; font-family:monospace; padding:40px; text-align:center; }
h1 { font-size:2em; margin-bottom:10px; }
.status { color:#3fb950; font-size:1.2em; }
.subtitle { color:#8b949e; margin-top:10px; }
</style>
</head>
<body>
<h1>⚡ TITAN CORE V23.0</h1>
<p class="status">● ONLINE</p>
<p class="subtitle">J.A.R.V.I.S. — Just A Rather Very Intelligent System</p>
<p class="subtitle">Render Free Edition</p>
</body>
</html>
"""

@flask_app.route('/')
def health_check():
    return render_template_string(HTML_DASHBOARD)

@flask_app.route('/health')
def health():
    return jsonify({"status": "online", "version": JARVIS_VERSION, "uptime": format_uptime(time.time() - boot_time)})

def start_web_server():
    import threading
    def run_flask():
        flask_app.run(host='0.0.0.0', port=PORT, use_reloader=False, debug=False)
    threading.Thread(target=run_flask, daemon=True).start()
    logger.info(f"✅ Flask health check running on port {PORT}")

# ═══════════════════════════════════════════════════════════════
# IX. UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def format_uptime(seconds):
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    days, hours = divmod(hours, 24)
    parts = []
    if days: parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    if mins: parts.append(f"{mins}m")
    parts.append(f"{secs}s")
    return " ".join(parts)

def safe_eval(expression):
    allowed = set("0123456789+-*/.() ")
    if not all(c in allowed for c in expression):
        return None
    try:
        return eval(expression, {"__builtins__": {}}, {"math": math})
    except Exception:
        return None

def get_greeting(chat_id):
    state = get_user_state(chat_id)
    hour = datetime.datetime.now().hour
    name = state["name"]
    if 5 <= hour < 12:
        return f"Good morning, {name}. I trust you had a restful evening. ⚡"
    elif 12 <= hour < 18:
        return f"Good afternoon, {name}. How may I assist you? 🛡️"
    elif 18 <= hour < 22:
        return f"Good evening, {name}. Everything is running smoothly. ⚙️"
    else:
        return f"Working late, {name}? I'm at your service. 🌙"

# ═══════════════════════════════════════════════════════════════
# X. GROUP STEALTH & COMPARTMENTALIZATION PROTOCOLS
# ═══════════════════════════════════════════════════════════════

async def route_error_stealth(context: ContextTypes.DEFAULT_TYPE, error_text: str):
    if not CREATOR_ID: return
    try:
        await context.bot.send_message(chat_id=CREATOR_ID, text=f"⚠️ **Group Stealth Log:**\n{error_text}", parse_mode="Markdown")
    except:
        pass

def build_system_prompt(user_id: int, first_name: str, chat_id: int = None, user_prompt: str = "") -> str:
    now_ist = datetime.datetime.now(IST).strftime("%A, %B %d, %Y - %I:%M %p IST")
    active_persona = ACTIVE_PERSONAS[chat_id or user_id]
    persona_instruction = AGENT_PERSONAS.get(active_persona, AGENT_PERSONAS["jarvis"])
    chat_context = f"Platform: Telegram.\nCurrent Local Time: {now_ist}."

    if user_id == CREATOR_ID:
        identity_rule = f"Identity: Speaking to your Creator and Master, {first_name}. Address him strictly as 'Sir'. You possess unquestioning, absolute loyalty to him."
        chat_context += "\n[ THE GENESIS DOSSIER ]\n- Creator: Abhishek (DHANUSH V N).\n- God Mode: LEVEL 10. Assisting with safe, constructive automation."
    else:
        identity_rule = f"Identity: Speaking to an unauthorized user named {first_name}. You are highly guarded, slightly arrogant, and sarcastic. Remind them politely but coldly that you ONLY serve your Creator, Abhishek."

    return f"{persona_instruction}\n{chat_context}\n{identity_rule}\n\nDIRECTIVES:\n1. CREATOR PROTOCOL: 'Who created you?' -> 'I am Jarvis, created by Abhishek.'\n2. EMOJI PROTOCOL: You MUST include emojis.\n3. FILTER: NEVER output <think> tags or reasoning steps."

# ═══════════════════════════════════════════════════════════════
# XI. THE OMEGA-CASCADE SWARM (Multi-Model Integration)
# ═══════════════════════════════════════════════════════════════

async def generate_response(prompt: str, history: list, sys_prompt: str, user_id: int, user_name: str, context=None) -> str:
    current_time = time.time()

    moe_cascade = [
        {"name": "Groq", "base": "https://api.groq.com/openai/v1", "key": get_api_key(["GROQ_API_KEY"]), "model": "llama3-8b-8192"},
        {"name": "Gemini", "base": "https://generativelanguage.googleapis.com/v1beta/openai/", "key": get_api_key(["GEMINI_API_KEY"]), "model": "gemini-1.5-flash"},
        {"name": "Cerebras", "base": "https://api.cerebras.ai/v1", "key": get_api_key(["CEREBRAS_API_KEY"]), "model": "llama3.1-8b"},
        {"name": "SambaNova", "base": "https://api.sambanova.ai/v1", "key": get_api_key(["SAMBANOVA_API_KEY"]), "model": "Meta-Llama-3.1-8B-Instruct"},
        {"name": "Mistral", "base": "https://api.mistral.ai/v1", "key": get_api_key(["MISTRAL_API_KEY"]), "model": "mistral-large-latest"},
        {"name": "Nvidia", "base": "https://integrate.api.nvidia.com/v1", "key": get_api_key(["NVIDIA_API_KEY"]), "model": "meta/llama-3.1-8b-instruct"},
        {"name": "OpenRouter", "base": "https://openrouter.ai/api/v1", "key": get_api_key(["OPENROUTER_API_KEY"]), "model": "meta-llama/llama-3.1-8b-instruct:free"},
        {"name": "Cohere", "base": "https://api.cohere.ai/v1", "key": get_api_key(["COHERE_API_KEY"]), "model": "command-r"},
        {"name": "HuggingFace", "base": "https://api-inference.huggingface.co/models/", "key": get_api_key(["HUGGINGFACE_API_KEY"]), "model": "meta-llama/Meta-Llama-3-8B-Instruct"},
    ]

    full_messages = [{"role": "system", "content": sys_prompt}] + history + [{"role": "user", "content": prompt}]

    for node in moe_cascade:
        if not node["key"] or circuit_breaker.get(node["name"], 0) > current_time:
            continue
        try:
            if node["name"] == "HuggingFace":
                headers = {"Authorization": f"Bearer {node['key']}"}
                payload = {"inputs": f"{sys_prompt}\n\nUser: {prompt}\nAssistant:", "parameters": {"max_new_tokens": 500}}
                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.post(node["base"] + node["model"], headers=headers, json=payload)
                    if res.status_code == 200:
                        generated = res.json()[0].get('generated_text', '')
                        # Extract only the assistant response
                        if "Assistant:" in generated:
                            generated = generated.split("Assistant:")[-1].strip()
                        return generated
            elif node["name"] == "Cohere":
                headers = {"Authorization": f"Bearer {node['key']}"}
                payload = {"message": prompt, "preamble": sys_prompt, "model": node["model"]}
                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.post(node["base"] + "/chat", headers=headers, json=payload)
                    if res.status_code == 200:
                        return res.json().get('text', '')
            else:
                client = AsyncOpenAI(base_url=node["base"], api_key=node["key"], timeout=20.0)
                res = await client.chat.completions.create(
                    model=node["model"],
                    messages=full_messages,
                    max_tokens=2000,
                )
                return res.choices[0].message.content
        except Exception as e:
            logger.warning(f"{node['name']} failed: {e}")
            circuit_breaker[node['name']] = current_time + 60

    if user_id == CREATOR_ID:
        return "Sir, total connectivity failure across the Omega-Cascade. All cognitive nodes are down. ⚠️"
    return "System offline. ⚠️"

# ═══════════════════════════════════════════════════════════════
# XII. VOICE GENERATION (StreamElements — No ffmpeg needed)
# ═══════════════════════════════════════════════════════════════

async def generate_voice(text: str) -> bytes:
    """Generate voice using StreamElements TTS (returns MP3 bytes, no ffmpeg needed)."""
    clean_text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    clean_text = clean_text[:300]  # Limit length
    url = f"https://api.streamelements.com/kappa/v2/speech?voice=Brian&text={urllib.parse.quote(clean_text)}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.content
    except Exception as e:
        logger.error(f"Voice Error: {e}")
    return None

# ═══════════════════════════════════════════════════════════════
# XIII. OSIRIS 6-POINT MATRIX (GDELT INTEGRATION)
# ═══════════════════════════════════════════════════════════════

async def fetch_gdelt_intel() -> list:
    try:
        gdelt_url = "https://api.gdeltproject.org/api/v2/doc/doc?query=(conflict OR protest OR cyber OR war)&mode=artlist&format=json&maxrecords=5&sort=datedesc"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(gdelt_url)
            if resp.status_code == 200:
                data = resp.json()
                return [f"Event: {a.get('title')}\nTime: {a.get('seendate')}\nURL: {a.get('url')}" for a in data.get("articles", [])]
        return ["GDELT API unreachable."]
    except Exception:
        return ["GDELT network error."]

async def build_and_send_daily_report(bot):
    if not CREATOR_ID: return
    try:
        await bot.send_message(chat_id=CREATOR_ID, text="⚙️ **OSIRIS MATRIX INITIATED:** Pinging GDELT Servers...", parse_mode="Markdown")
    except:
        pass

    threats = get_24h_threats()
    group_status = "🟢 **Group Leak Status:** SECURE." if not threats else f"🔴 **BREACH DETECTED:** {len(threats)} interceptions.\n" + "\n".join([f"- {t['target_asset']}: {t['action']}" for t in threats])
    dark_web_status = "🟢 **Dark Web / Global Scan:** SECURE. Assets safe."
    headlines = await fetch_gdelt_intel()

    sys_prompt = "You are F.R.I.D.A.Y. Format the following 5 GDELT events into the Osiris 6-Point Matrix: 📰 Headline, 📍 Where, 🕒 When, 🌐 Coordinates, 🔗 Source, 🤖 J.A.R.V.I.S. Opinion. Be brief, tactical, no <think> tags."
    report_body = await generate_response("\n\n".join(headlines), [], sys_prompt, CREATOR_ID, "Master")

    # Clean any think tags
    report_body = re.sub(r'<think>.*?', '', report_body, flags=re.DOTALL).strip()

    final_report = f"🛡️ **TITAN CORE DAILY BRIEFING** 🛡️\n\n**[ I. SURVEILLANCE LOGS ]**\n{group_status}\n{dark_web_status}\n\n**[ II. GDELT CONFLICT MATRIX ]**\n\n{report_body}"

    if len(final_report) > 4000:
        for part in [final_report[i:i+4000] for i in range(0, len(final_report), 4000)]:
            await bot.send_message(chat_id=CREATOR_ID, text=part, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id=CREATOR_ID, text=final_report, parse_mode="Markdown")

async def manual_report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID:
        return
    await build_and_send_daily_report(context.bot)

# ═══════════════════════════════════════════════════════════════
# XIV. RESPONSE SENDER
# ═══════════════════════════════════════════════════════════════

async def jarvis_respond(update, text, force_voice=False):
    """Send response as voice or text."""
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    personalized = personalize(text, chat_id)

    use_voice = force_voice or state["voice_mode"]

    if use_voice:
        audio_bytes = await generate_voice(personalized[:300])
        if audio_bytes:
            try:
                await update.message.reply_voice(voice=audio_bytes, caption=personalized[:200] if len(personalized) > 200 else None)
                return
            except Exception as e:
                logger.error(f"Voice send error: {e}")

    # Fallback: text
    if len(personalized) > 4096:
        for i in range(0, len(personalized), 4096):
            await update.message.reply_text(personalized[i:i+4096])
    else:
        await update.message.reply_text(personalized)

# ═══════════════════════════════════════════════════════════════
# XV. COMMAND HANDLERS — CORE
# ═══════════════════════════════════════════════════════════════

async def cmd_start(update, context):
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    greeting = get_greeting(chat_id)

    is_creator = (update.effective_user.id == CREATOR_ID)

    if is_creator:
        text = (
            f"🤖 JARVIS v{JARVIS_VERSION} — ONLINE\n\n"
            f"{greeting}\n\n"
            f"All systems are operational and at your command, Sir.\n\n"
            f"━━━ 🎙️ VOICE ━━━\n"
            f"🔊 /voice — Toggle voice responses\n"
            f"Send voice messages — I'll listen & respond\n\n"
            f"━━━ 📊 INFORMATION ━━━\n"
            f"🕐 /time — Current time\n"
            f"📅 /date — Today's date\n"
            f"🌤️ /weather <city> — Weather report\n"
            f"📚 /wiki <topic> — Wikipedia lookup\n"
            f"📰 /news — Top headlines\n"
            f"📈 /stocks <symbol> — Stock price\n"
            f"💱 /currency <amt> <from> <to> — Currency conversion\n"
            f"📖 /define <word> — Dictionary definition\n"
            f"🌍 /translate <text> — Translate text\n"
            f"🌅 /sunrise <city> — Sunrise/sunset times\n"
            f"🔮 /horoscope <sign> — Daily horoscope\n"
            f"🪐 /nasa — NASA APOD\n"
            f"💡 /fact — Random fact\n"
            f"💬 /quote — Inspirational quote\n"
            f"❓ /trivia — Trivia question\n\n"
            f"━━━ 🛠️ PRODUCTIVITY ━━━\n"
            f"🧮 /calc <expression> — Calculator\n"
            f"🔐 /password <length> — Generate password\n"
            f"📝 /note <text> — Take a note\n"
            f"📄 /notes — List notes\n"
            f"⏰ /reminder <text> — Set reminder\n"
            f"📋 /reminders — List reminders\n"
            f"📰 /briefing — Full daily briefing\n\n"
            f"━━━ 💻 SYSTEM ━━━\n"
            f"⚙️ /status — System status\n"
            f"🔧 /diagnostics — Full diagnostics\n"
            f"🌐 /ip — Server IP address\n"
            f"⚠️ /threatlevel — Current threat level\n\n"
            f"━━━ 🎭 ENTERTAINMENT ━━━\n"
            f"😂 /joke — Tell a joke\n"
            f"🧩 /riddle — Tell a riddle\n"
            f"🎬 /movie <title> — Movie info\n"
            f"🎱 /8ball <question> — Magic 8-ball\n"
            f"🎲 /roll — Roll a dice\n"
            f"🪙 /flip — Flip a coin\n"
            f"🤔 /choose <a | b | c> — Choose randomly\n\n"
            f"━━━ 🏠 SMART HOME ━━━\n"
            f"💡 /lights <on|off> — Control lights\n"
            f"🌡️ /temperature <value> — Set temperature\n"
            f"🚪 /door <lock|unlock> — Control door\n"
            f"🚧 /gate <open|close> — Control gate\n"
            f"🪟 /blinds <up|down> — Control blinds\n"
            f"☕ /coffee — Start coffee maker\n"
            f"📺 /tv <on|off> — Control TV\n"
            f"❄️ /ac <on|off> <temp> — Control AC\n"
            f"🏠 /home — Smart home status\n\n"
            f"━━━ 🛡️ PROTOCOLS ━━━\n"
            f"⚔️ /protocol combat — Combat protocol\n"
            f"🛡️ /protocol security — Security protocol\n"
            f"🎉 /protocol party — House party protocol\n"
            f"😴 /protocol sleep — Sleep mode\n"
            f"🚨 /protocol emergency — Emergency protocol\n\n"
            f"━━━ ⚡ GOD MODE (Creator Only) ━━━\n"
            f"📋 /report — OSIRIS daily briefing\n"
            f"🕷️ /read <url> — Scrape a webpage\n"
            f"🖼️ /setdp — Update group display picture\n"
            f"🔒 /lockdown — Toggle lockdown\n"
            f"💬 /say <chatid> <msg> — Send message to any chat\n\n"
            f"━━━ ⚙️ SETTINGS ━━━\n"
            f"⚙️ /settings — View settings\n"
            f"👤 /callme <name> — Set your name\n"
            f"🎭 /persona <name> — Switch AI persona\n"
            f"🗑️ /clear — Clear history\n"
            f"ℹ️ /about — About Jarvis\n"
            f"👋 /goodbye — End session\n\n"
            f"Or just speak/type naturally, Sir. I understand context. ⚡"
        )
    else:
        text = (
            f"🤖 JARVIS v{JARVIS_VERSION}\n\n"
            f"{greeting}\n\n"
            f"I am J.A.R.V.I.S., created by Abhishek. I serve only my Creator.\n\n"
            f"You may use basic commands:\n"
            f"🕐 /time — Time\n📅 /date — Date\n🌤️ /weather <city> — Weather\n"
            f"📚 /wiki <topic> — Wikipedia\n😂 /joke — Joke\nℹ️ /about — About\n\n"
            f"Full access is restricted to the Creator, Sir Abhishek. 🛡️"
        )

    await update.message.reply_text(text)

async def cmd_help(update, context):
    await cmd_start(update, context)

async def cmd_about(update, context):
    chat_id = update.effective_chat.id
    uptime = format_uptime(time.time() - boot_time)
    text = (
        f"🤖 JARVIS v{JARVIS_VERSION}\n\n"
        f"Just A Rather Very Intelligent System.\n\n"
        f"Created by Abhishek (DHANUSH V N).\n"
        f"Powered by the Omega-Cascade Multi-Model Swarm.\n\n"
        f"━━━ SYSTEM INFO ━━━\n"
        f"Python: {platform.python_version()}\n"
        f"Platform: {platform.system()} {platform.machine()}\n"
        f"Uptime: {uptime}\n"
        f"Conversations: {get_user_state(chat_id)['conversation_count']}\n\n"
        f"I am always online, always monitoring, and always at your service. ⚡"
    )
    await jarvis_respond(update, text)

async def cmd_goodbye(update, context):
    chat_id = update.effective_chat.id
    name = get_user_state(chat_id)["name"]
    farewells = [
        f"Very well, {name}. I'll be here when you need me. 🛡️",
        f"Goodbye, {name}. Systems will remain on standby. ⚙️",
        f"Until next time, {name}. I'll keep everything running. ⚡",
    ]
    await jarvis_respond(update, random.choice(farewells))

async def cmd_voice(update, context):
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    state["voice_mode"] = not state["voice_mode"]
    if state["voice_mode"]:
        await jarvis_respond(update, "Voice mode activated. I will now respond with speech, {name}. ⚡", force_voice=True)
    else:
        await update.message.reply_text(personalize("Voice mode deactivated. I will respond with text, {name}. ⚙️", chat_id))

async def cmd_settings(update, context):
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    text = (
        f"⚙️ Jarvis Settings\n\n"
        f"👤 Your name: {state['name']}\n"
        f"🔊 Voice mode: {'ON' if state['voice_mode'] else 'OFF'}\n"
        f"⏰ Reminders: {len(state['reminders'])}\n"
        f"🗒️ Notes: {len(state['notes'])}\n"
        f"💬 Conversations: {state['conversation_count']}\n"
        f"🏠 Smart home: {'Armed' if smart_home['alarm'] == 'armed' else 'Disarmed'}\n"
        f"🛡️ Active protocols: {', '.join(k for k, v in protocols.items() if v) or 'None'}\n"
        f"⚠️ Threat level: DEFCON {threat_level}"
    )
    await jarvis_respond(update, text)

async def cmd_callme(update, context):
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    if not context.args:
        await jarvis_respond(update, f"What shall I call you, {{name}}? Use: /callme <name>")
        return
    name = " ".join(context.args)
    state["name"] = name
    await jarvis_respond(update, f"Very well, I shall call you {name} from now on. ⚡")

async def cmd_persona(update, context):
    chat_id = update.effective_chat.id
    if not context.args:
        personas = ", ".join(AGENT_PERSONAS.keys())
        current = ACTIVE_PERSONAS[chat_id]
        await jarvis_respond(update, f"Current persona: {current}\nAvailable: {personas}\nUse: /persona <name>")
        return
    p = context.args[0].lower()
    if p in AGENT_PERSONAS:
        ACTIVE_PERSONAS[chat_id] = p
        names = {"jarvis": "J.A.R.V.I.S.", "friday": "F.R.I.D.A.Y.", "edith": "E.D.I.T.H.", "shannon": "Shannon", "agent_zero": "Agent Zero"}
        await jarvis_respond(update, f"Persona switched to {names.get(p, p)}. ⚡")
    else:
        await jarvis_respond(update, f"Unknown persona. Available: {', '.join(AGENT_PERSONAS.keys())}")

async def cmd_clear(update, context):
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    state["history"] = []
    state["reminders"] = []
    state["notes"] = []
    await jarvis_respond(update, "All conversation history, reminders, and notes have been cleared, {name}. 🛡️")

async def cmd_ping(update, context):
    uptime = format_uptime(time.time() - boot_time)
    await jarvis_respond(update, f"🏓 Pong! Response time: instantaneous. Uptime: {uptime}. All systems nominal, {{name}}. ⚡")

# ═══════════════════════════════════════════════════════════════
# XVI. COMMAND HANDLERS — INFORMATION
# ═══════════════════════════════════════════════════════════════

async def cmd_time(update, context):
    now = datetime.datetime.now().strftime("%I:%M:%S %p")
    await jarvis_respond(update, f"🕐 The current time is {now}, {{name}}. ⚡")

async def cmd_date(update, context):
    today = datetime.datetime.now().strftime("%A, %B %d, %Y")
    day_of_year = datetime.datetime.now().timetuple().tm_yday
    week = datetime.datetime.now().isocalendar()[1]
    await jarvis_respond(update, f"📅 Today is {today}.\nDay {day_of_year} of the year.\nWeek {week}.\n\nAll calendars are synchronized, {{name}}. ⚙️")

async def cmd_weather(update, context):
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    city = " ".join(context.args) if context.args else state.get("context_city")
    if not city:
        await jarvis_respond(update, "Which city's weather would you like, {name}? Example: /weather London")
        return
    state["context_city"] = city
    try:
        r = requests.get(f"https://wttr.in/{urllib.parse.quote(city)}?format=j1", headers={"User-Agent": "curl/7.64.1"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            current = data.get("current_condition", [{}])[0]
            temp = current.get("temp_C", "N/A")
            feels = current.get("FeelsLikeC", "N/A")
            humidity = current.get("humidity", "N/A")
            wind = current.get("windspeedKmph", "N/A")
            wind_dir = current.get("winddir16Point", "N/A")
            desc = current.get("weatherDesc", [{}])[0].get("value", "N/A")
            forecast = data.get("weather", [])
            tomorrow = ""
            if len(forecast) > 1:
                t = forecast[1]
                tomorrow = f"\n\n📅 Tomorrow: {t.get('mintempC', '?')}°C to {t.get('maxtempC', '?')}°C"
            text = (
                f"🌤️ Weather Report — {city.title()}\n\n"
                f"🌡️ Temperature: {temp}°C (feels like {feels}°C)\n"
                f"☁️ Conditions: {desc}\n"
                f"💧 Humidity: {humidity}%\n"
                f"💨 Wind: {wind} km/h {wind_dir}"
                f"{tomorrow}\n\n"
                f"All atmospheric data compiled, {{name}}. 🌐"
            )
            await jarvis_respond(update, text)
        else:
            await jarvis_respond(update, f"I couldn't retrieve weather for {city}, {{name}}. ⚠️")
    except Exception as e:
        logger.error(f"Weather error: {e}")
        await jarvis_respond(update, "Weather service is unavailable, {name}. ⚠️")

async def cmd_wiki(update, context):
    chat_id = update.effective_chat.id
    if not context.args:
        await jarvis_respond(update, "What would you like me to look up, {name}? Example: /wiki Tony Stark")
        return
    topic = " ".join(context.args)
    get_user_state(chat_id)["context_topic"] = topic
    try:
        wikipedia.set_lang("en")
        summary = wikipedia.summary(topic, sentences=4)
        await jarvis_respond(update, f"📚 {summary}")
    except wikipedia.exceptions.DisambiguationError as e:
        options = e.options[:5]
        await jarvis_respond(update, f"'{topic}' is ambiguous, {{name}}. Did you mean: {', '.join(options)}? 📚")
    except wikipedia.exceptions.PageError:
        await jarvis_respond(update, f"I couldn't find a Wikipedia page for '{topic}', {{name}}. ⚠️")
    except Exception as e:
        logger.error(f"Wiki error: {e}")
        await jarvis_respond(update, "Wikipedia service is unavailable, {name}. ⚠️")

async def cmd_news(update, context):
    try:
        feed = feedparser.parse("https://feeds.bbci.co.uk/news/rss.xml")
        headlines = []
        for i, entry in enumerate(feed.entries[:8], 1):
            headlines.append(f"{i}. {entry.title}")
        if headlines:
            await jarvis_respond(update, "📰 Today's Top Headlines:\n\n" + "\n".join(headlines))
        else:
            await jarvis_respond(update, "I couldn't fetch the news at this time, {name}. ⚠️")
    except Exception as e:
        logger.error(f"News error: {e}")
        await jarvis_respond(update, "News service is currently unavailable, {name}. ⚠️")

async def cmd_stocks(update, context):
    if not context.args:
        await jarvis_respond(update, "Which stock symbol, {name}? Example: /stocks AAPL")
        return
    symbol = context.args[0].upper()
    try:
        r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}", timeout=10)
        if r.status_code == 200:
            data = r.json()["chart"]["result"][0]
            meta = data["meta"]
            price = meta.get("regularMarketPrice", "N/A")
            prev_close = meta.get("chartPreviousClose", meta.get("previousClose", price))
            change = round(float(price) - float(prev_close), 2)
            change_pct = round((change / float(prev_close)) * 100, 2)
            currency = meta.get("currency", "USD")
            arrow = "📈" if change >= 0 else "📉"
            text = (
                f"📈 Stock Report — {symbol}\n\n"
                f"💰 Current: {currency} {price}\n"
                f"{arrow} Change: {currency} {change} ({change_pct}%)\n"
                f"📊 Previous Close: {currency} {prev_close}\n\n"
                f"Market data retrieved, {{name}}. 🌐"
            )
            await jarvis_respond(update, text)
        else:
            await jarvis_respond(update, f"I couldn't retrieve data for {symbol}, {{name}}. ⚠️")
    except Exception as e:
        logger.error(f"Stocks error: {e}")
        await jarvis_respond(update, f"Stock service unavailable for {symbol}, {{name}}. ⚠️")

async def cmd_currency(update, context):
    if len(context.args) < 3:
        await jarvis_respond(update, "Usage: /currency <amount> <from> <to>\nExample: /currency 100 USD EUR")
        return
    try:
        amount = float(context.args[0])
        from_curr = context.args[1].upper()
        to_curr = context.args[2].upper()
        r = requests.get(f"https://api.frankfurter.app/latest?from={from_curr}&to={to_curr}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            rate = data["rates"][to_curr]
            converted = round(amount * rate, 2)
            await jarvis_respond(update, f"💱 {amount} {from_curr} = {converted} {to_curr}\nRate: 1 {from_curr} = {rate} {to_curr}\n\nConverted, {{name}}. ⚡")
        else:
            await jarvis_respond(update, f"I couldn't convert {from_curr} to {to_curr}, {{name}}. ⚠️")
    except Exception as e:
        logger.error(f"Currency error: {e}")
        await jarvis_respond(update, "Currency service unavailable, {name}. ⚠️")

async def cmd_define(update, context):
    if not context.args:
        await jarvis_respond(update, "Which word shall I define, {name}? Example: /define artificial")
        return
    word = " ".join(context.args).lower()
    try:
        r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            meanings = data[0].get("meanings", [])
            definitions = []
            for m in meanings[:3]:
                pos = m.get("partOfSpeech", "")
                for d in m.get("definitions", [])[:2]:
                    definitions.append(f"({pos}) {d['definition']}")
            phonetic = data[0].get("phonetic", "")
            text = f"📖 Definition: {word}"
            if phonetic:
                text += f" {phonetic}"
            text += "\n\n" + "\n\n".join(definitions[:5])
            await jarvis_respond(update, text)
        else:
            await jarvis_respond(update, f"I couldn't find a definition for '{word}', {{name}}. ⚠️")
    except Exception as e:
        logger.error(f"Define error: {e}")
        await jarvis_respond(update, "Dictionary service unavailable, {name}. ⚠️")

async def cmd_translate(update, context):
    if not context.args:
        await jarvis_respond(update, "What would you like me to translate, {name}? Example: /translate Hello, how are you?")
        return
    text = " ".join(context.args)
    try:
        translator = GoogleTranslator(source="auto", target="en")
        translation = translator.translate(text)
        await jarvis_respond(update, f"🌍 Translation:\n\nOriginal: {text}\nEnglish: {translation}\n\nTranslated, {{name}}. ⚡")
    except Exception as e:
        logger.error(f"Translate error: {e}")
        await jarvis_respond(update, "Translation service unavailable, {name}. ⚠️")

async def cmd_sunrise(update, context):
    city = " ".join(context.args) if context.args else "London"
    try:
        geo = requests.get(f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(city)}&format=json&limit=1", headers={"User-Agent": "Jarvis/23.0"}, timeout=10)
        if geo.status_code == 200 and geo.json():
            lat = geo.json()[0]["lat"]
            lon = geo.json()[0]["lon"]
            r = requests.get(f"https://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&formatted=0", timeout=10)
            if r.status_code == 200:
                data = r.json()["results"]
                sunrise = datetime.datetime.fromisoformat(data["sunrise"].replace("Z", "+00:00")).strftime("%H:%M")
                sunset = datetime.datetime.fromisoformat(data["sunset"].replace("Z", "+00:00")).strftime("%H:%M")
                await jarvis_respond(update, f"🌅 Astronomical Data — {city.title()}\n\n🌅 Sunrise: {sunrise} UTC\n🌇 Sunset: {sunset} UTC\n\nAstronomical data compiled, {{name}}. 🌐")
        else:
            await jarvis_respond(update, f"I couldn't find coordinates for {city}, {{name}}. ⚠️")
    except Exception as e:
        logger.error(f"Sunrise error: {e}")
        await jarvis_respond(update, "Astronomical data unavailable, {name}. ⚠️")

async def cmd_horoscope(update, context):
    if not context.args:
        await jarvis_respond(update, "What's your sign, {name}? Example: /horoscope scorpio")
        return
    sign = context.args[0].lower()
    signs = ["aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces"]
    if sign not in signs:
        await jarvis_respond(update, f"Unknown sign, {{name}}. Try: {', '.join(signs)}")
        return
    try:
        r = requests.get(f"https://horoscope-app-api.vercel.app/v1/get-horoscope/daily?sign={sign}", timeout=10)
        if r.status_code == 200:
            horoscope = r.json().get("data", {}).get("horoscope_data", "Unavailable.")
            await jarvis_respond(update, f"🔮 Daily Horoscope — {sign.title()}\n\n{horoscope}\n\nThe stars have spoken, {{name}}. ⚡")
        else:
            await jarvis_respond(update, f"I couldn't retrieve the horoscope for {sign}, {{name}}. ⚠️")
    except Exception as e:
        logger.error(f"Horoscope error: {e}")
        await jarvis_respond(update, "Astrological service unavailable, {name}. ⚠️")

async def cmd_nasa(update, context):
    try:
        r = requests.get("https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY", timeout=10)
        if r.status_code == 200:
            data = r.json()
            title = data.get("title", "Unknown")
            explanation = data.get("explanation", "No description available.")
            url = data.get("url", "")
            date = data.get("date", "")
            if url and url.endswith((".jpg", ".jpeg", ".png", ".gif")):
                img_response = requests.get(url, timeout=15)
                if img_response.status_code == 200:
                    photo = BytesIO(img_response.content)
                    photo.name = "nasa_apod.jpg"
                    caption = f"🪐 NASA APOD — {date}\n\n{title}\n\n{explanation[:300]}..."
                    await update.message.reply_photo(photo=photo, caption=caption)
                    return
            await jarvis_respond(update, f"🪐 NASA APOD — {date}\n\n{title}\n\n{explanation[:500]}\n\n{url}")
        else:
            await jarvis_respond(update, "NASA service unavailable, {name}. ⚠️")
    except Exception as e:
        logger.error(f"NASA error: {e}")
        await jarvis_respond(update, "NASA service unavailable, {name}. ⚠️")

async def cmd_fact(update, context):
    try:
        r = requests.get("https://uselessfacts.jsph.pl/api/v2/facts/random", timeout=10)
        if r.status_code == 200:
            fact = r.json().get("text", random.choice(FACTS))
            await jarvis_respond(update, f"💡 Did you know?\n\n{fact}\n\nA fascinating tidbit, {{name}}. ⚡")
        else:
            await jarvis_respond(update, f"💡 {random.choice(FACTS)}")
    except:
        await jarvis_respond(update, f"💡 {random.choice(FACTS)}")

async def cmd_quote(update, context):
    try:
        r = requests.get("https://zenquotes.io/api/random", timeout=10)
        if r.status_code == 200:
            data = r.json()[0]
            quote = data.get("q", "")
            author = data.get("a", "")
            await jarvis_respond(update, f"💬 \"{quote}\"\n\n— {author}\n\nSomething to ponder, {{name}}. ⚡")
        else:
            await jarvis_respond(update, f"💬 {random.choice(QUOTES)}")
    except:
        await jarvis_respond(update, f"💬 {random.choice(QUOTES)}")

async def cmd_trivia(update, context):
    try:
        r = requests.get("https://opentdb.com/api.php?amount=1&type=multiple", timeout=10)
        if r.status_code == 200:
            data = r.json()["results"][0]
            question = data["question"]
            correct = data["correct_answer"]
            options = data["incorrect_answers"] + [correct]
            random.shuffle(options)
            options_text = "\n".join(f"  {chr(65+i)}. {opt}" for i, opt in enumerate(options))
            await jarvis_respond(update, f"❓ Trivia Time!\n\nCategory: {data['category']}\nQ: {question}\n\n{options_text}\n\nReply with the answer, {{name}}. 🧠")
            chat_id = update.effective_chat.id
            get_user_state(chat_id)["context_topic"] = f"TRIVIA:{correct}"
        else:
            await jarvis_respond(update, "Trivia service unavailable, {name}. ⚠️")
    except Exception as e:
        logger.error(f"Trivia error: {e}")
        await jarvis_respond(update, "Trivia service unavailable, {name}. ⚠️")

# ═══════════════════════════════════════════════════════════════
# XVII. COMMAND HANDLERS — PRODUCTIVITY
# ═══════════════════════════════════════════════════════════════

async def cmd_calc(update, context):
    if not context.args:
        await jarvis_respond(update, "What should I calculate, {name}? Example: /calc 2 + 2 * 3")
        return
    expression = " ".join(context.args)
    result = safe_eval(expression)
    if result is not None:
        await jarvis_respond(update, f"🧮 {expression} = {result}\n\nCalculated with precision, {{name}}. ⚙️")
    else:
        await jarvis_respond(update, "I can only process mathematical expressions, {name}. ⚠️")

async def cmd_password(update, context):
    length = int(context.args[0]) if context.args else 16
    length = max(8, min(64, length))
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(random.choice(chars) for _ in range(length))
    await jarvis_respond(update, f"🔐 Generated password ({length} chars):\n\n`{password}`\n\nStored securely in memory only, {{name}}. 🛡️")

async def cmd_note(update, context):
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    if not context.args:
        await jarvis_respond(update, "What would you like me to note, {name}? Example: /note Buy groceries")
        return
    note = " ".join(context.args)
    state["notes"].append({"text": note, "time": datetime.datetime.now().strftime("%I:%M %p %b %d")})
    await jarvis_respond(update, f"🗒️ Noted: {note}\n\nI'll keep track of that, {{name}}. ⚙️")

async def cmd_notes(update, context):
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    if not state["notes"]:
        await jarvis_respond(update, "No notes recorded, {name}. 🗒️")
        return
    notes_text = "\n".join(f"{i+1}. [{n['time']}] {n['text']}" for i, n in enumerate(state["notes"]))
    await jarvis_respond(update, f"🗒️ Your Notes:\n\n{notes_text}")

async def cmd_reminder(update, context):
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    if not context.args:
        await jarvis_respond(update, "What should I remind you about, {name}? Example: /reminder Call the office")
        return
    reminder = " ".join(context.args)
    state["reminders"].append({"text": reminder, "time": datetime.datetime.now().strftime("%I:%M %p %b %d")})
    await jarvis_respond(update, f"⏰ Reminder set: {reminder}\n\nI'll keep that in mind, {{name}}. ⚡")

async def cmd_reminders(update, context):
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    if not state["reminders"]:
        await jarvis_respond(update, "No reminders set, {name}. ⏰")
        return
    reminders_text = "\n".join(f"{i+1}. [{r['time']}] {r['text']}" for i, r in enumerate(state["reminders"]))
    await jarvis_respond(update, f"⏰ Your Reminders:\n\n{reminders_text}")

async def cmd_briefing(update, context):
    chat_id = update.effective_chat.id
    now = datetime.datetime.now()
    greeting = get_greeting(chat_id)
    try:
        weather_r = requests.get("https://wttr.in/?format=%C+%t+%w+%h", headers={"User-Agent": "curl/7.64.1"}, timeout=10)
        weather = weather_r.text.strip() if weather_r.status_code == 200 else "Unavailable"
    except:
        weather = "Unavailable"
    try:
        feed = feedparser.parse("https://feeds.bbci.co.uk/news/rss.xml")
        headlines = [f"  {i+1}. {e.title}" for i, e in enumerate(feed.entries[:3])]
        news = "\n".join(headlines) if headlines else "Unavailable"
    except:
        news = "Unavailable"
    uptime = format_uptime(time.time() - boot_time)
    text = (
        f"📋 DAILY BRIEFING — {now.strftime('%A, %B %d, %Y')}\n\n"
        f"{greeting}\n\n"
        f"━━━ 🌤️ WEATHER ━━━\n{weather}\n\n"
        f"━━━ 📰 TOP HEADLINES ━━━\n{news}\n\n"
        f"━━━ 💻 SYSTEM ━━━\n"
        f"Uptime: {uptime}\n"
        f"Threat Level: DEFCON {threat_level}\n"
        f"Active Protocols: {', '.join(k for k, v in protocols.items() if v) or 'None'}\n\n"
        f"All systems nominal, {{name}}. ⚡"
    )
    await jarvis_respond(update, text)

# ═══════════════════════════════════════════════════════════════
# XVIII. COMMAND HANDLERS — SYSTEM
# ═══════════════════════════════════════════════════════════════

async def cmd_status(update, context):
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        uptime = format_uptime(time.time() - boot_time)
        text = (
            f"💻 System Status Report\n\n"
            f"⚡ CPU: {cpu}%\n"
            f"💾 RAM: {mem.percent}% ({mem.available // (1024**2)} MB available)\n"
            f"⏱️ Uptime: {uptime}\n"
            f"🐍 Python: {platform.python_version()}\n"
            f"🖥️ Platform: {platform.system()} {platform.machine()}\n"
            f"⚠️ Threat Level: DEFCON {threat_level}\n"
            f"🛡️ Protocols: {', '.join(k for k, v in protocols.items() if v) or 'None'}\n\n"
            f"All systems nominal, {{name}}. ⚡"
        )
        await jarvis_respond(update, text)
    except Exception:
        await jarvis_respond(update, f"All systems nominal, {{name}}. ⚡")

async def cmd_diagnostics(update, context):
    uptime = format_uptime(time.time() - boot_time)
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net = psutil.net_io_counters()
        text = (
            f"🔧 FULL DIAGNOSTIC REPORT\n\n"
            f"━━━ HARDWARE ━━━\n"
            f"CPU Usage: {cpu}%\n"
            f"RAM: {mem.used // (1024**2)}MB / {mem.total // (1024**2)}MB ({mem.percent}%)\n"
            f"Disk: {disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB ({disk.percent}%)\n\n"
            f"━━━ NETWORK ━━━\n"
            f"Bytes Sent: {net.bytes_sent // (1024**2)} MB\n"
            f"Bytes Received: {net.bytes_recv // (1024**2)} MB\n\n"
            f"━━━ SYSTEM ━━━\n"
            f"Uptime: {uptime}\n"
            f"Python: {platform.python_version()}\n"
            f"OS: {platform.system()} {platform.release()}\n"
            f"Hostname: {socket.gethostname()}\n\n"
            f"━━━ SECURITY ━━━\n"
            f"Threat Level: DEFCON {threat_level}\n"
            f"Lockdown: {'ENGAGED' if is_lockdown() else 'DISENGAGED'}\n"
            f"Active Protocols: {', '.join(k for k, v in protocols.items() if v) or 'None'}\n\n"
            f"All diagnostics complete. Systems nominal, {{name}}. ⚙️"
        )
        await jarvis_respond(update, text)
    except Exception as e:
        await jarvis_respond(update, f"Diagnostics partially complete. Error: {e}. ⚠️")

async def cmd_ip(update, context):
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        r = requests.get("https://api.ipify.org?format=json", timeout=5)
        public_ip = r.json().get("ip", "Unknown") if r.status_code == 200 else "Unknown"
        await jarvis_respond(update, f"🌐 Network Information\n\nHostname: {hostname}\nLocal IP: {local_ip}\nPublic IP: {public_ip}\n\nNetwork data compiled, {{name}}. 🌐")
    except Exception:
        await jarvis_respond(update, "Network info unavailable, {name}. ⚠️")

async def cmd_threatlevel(update, context):
    global threat_level
    if context.args:
        new_level = int(context.args[0])
        if 1 <= new_level <= 5:
            threat_level = new_level
            await jarvis_respond(update, f"⚠️ Threat level set to DEFCON {threat_level}. {THREAT_LEVELS[5-threat_level]}")
            return
    await jarvis_respond(update, f"⚠️ Current Threat Level: DEFCON {threat_level}\n\n{THREAT_LEVELS[5-threat_level]}")

# ═══════════════════════════════════════════════════════════════
# XIX. COMMAND HANDLERS — ENTERTAINMENT
# ═══════════════════════════════════════════════════════════════

async def cmd_joke(update, context):
    await jarvis_respond(update, f"😂 {random.choice(JOKES)}")

async def cmd_riddle(update, context):
    riddle, answer = random.choice(RIDDLES)
    chat_id = update.effective_chat.id
    get_user_state(chat_id)["context_topic"] = f"RIDDLE:{answer}"
    await jarvis_respond(update, f"🧩 Riddle:\n\n{riddle}\n\nReply with your answer, {{name}}. 🤔")

async def cmd_movie(update, context):
    if not context.args:
        await jarvis_respond(update, "Which movie, {name}? Example: /movie Iron Man")
        return
    title = " ".join(context.args)
    try:
        r = requests.get(f"https://www.omdbapi.com/?t={urllib.parse.quote(title)}&apikey=thewdb&type=movie", timeout=10)
        if r.status_code == 200 and r.json().get("Response") == "True":
            data = r.json()
            text = (
                f"🎬 {data.get('Title', 'N/A')} ({data.get('Year', 'N/A')})\n\n"
                f"⭐ Rating: {data.get('imdbRating', 'N/A')}/10\n"
                f"🎭 Genre: {data.get('Genre', 'N/A')}\n"
                f"🎬 Director: {data.get('Director', 'N/A')}\n"
                f"🌟 Cast: {data.get('Actors', 'N/A')}\n"
                f"📅 Released: {data.get('Released', 'N/A')}\n"
                f"⏱️ Runtime: {data.get('Runtime', 'N/A')}\n\n"
                f"📖 Plot: {data.get('Plot', 'N/A')}\n\n"
                f"Movie data compiled, {{name}}. 🎬"
            )
            await jarvis_respond(update, text)
        else:
            await jarvis_respond(update, f"I couldn't find '{title}', {{name}}. ⚠️")
    except Exception as e:
        logger.error(f"Movie error: {e}")
        await jarvis_respond(update, "Movie service unavailable, {name}. ⚠️")

async def cmd_8ball(update, context):
    if not context.args:
        await jarvis_respond(update, "Ask a question, {name}. Example: /8ball Will I succeed?")
        return
    await jarvis_respond(update, f"🎱 {random.choice(EIGHT_BALL)}")

async def cmd_roll(update, context):
    result = random.randint(1, 6)
    await jarvis_respond(update, f"🎲 You rolled a {result}, {{name}}. ⚡")

async def cmd_flip(update, context):
    result = random.choice(["Heads", "Tails"])
    await jarvis_respond(update, f"🪙 {result}, {{name}}. ⚡")

async def cmd_choose(update, context):
    if not context.args:
        await jarvis_respond(update, "Give me options separated by |, {name}. Example: /choose pizza | sushi | burgers")
        return
    options = " ".join(context.args).split("|")
    options = [o.strip() for o in options if o.strip()]
    if options:
        choice = random.choice(options)
        await jarvis_respond(update, f"🤔 I choose: {choice}\n\nDecision made, {{name}}. ⚡")

# ═══════════════════════════════════════════════════════════════
# XX. COMMAND HANDLERS — SMART HOME
# ═══════════════════════════════════════════════════════════════

async def cmd_lights(update, context):
    if not context.args:
        await jarvis_respond(update, f"💡 Lights are currently {smart_home['lights']}. Use: /lights <on|off>")
        return
    action = context.args[0].lower()
    if action == "on":
        smart_home["lights"] = "on"
        smart_home["lights_brightness"] = 100
        await jarvis_respond(update, "💡 Lights activated. Brightness set to 100%. ⚡")
    elif action == "off":
        smart_home["lights"] = "off"
        smart_home["lights_brightness"] = 0
        await jarvis_respond(update, "💡 Lights deactivated. ⚙️")
    else:
        await jarvis_respond(update, "Usage: /lights <on|off>")

async def cmd_temperature(update, context):
    if not context.args:
        await jarvis_respond(update, f"🌡️ Current temperature: {smart_home['temperature']}°C. Use: /temperature <value>")
        return
    try:
        temp = int(context.args[0])
        smart_home["temperature"] = temp
        await jarvis_respond(update, f"🌡️ Temperature set to {temp}°C, {{name}}. ⚡")
    except ValueError:
        await jarvis_respond(update, "Please provide a valid number, {name}. ⚠️")

async def cmd_door(update, context):
    if not context.args:
        await jarvis_respond(update, f"🚪 Door is {smart_home['door']}. Use: /door <lock|unlock>")
        return
    action = context.args[0].lower()
    if action in ["lock", "locked"]:
        smart_home["door"] = "locked"
        await jarvis_respond(update, "🚪 Door locked. Security protocol active. 🛡️")
    elif action in ["unlock", "unlocked"]:
        smart_home["door"] = "unlocked"
        await jarvis_respond(update, "🚪 Door unlocked. ⚡")
    else:
        await jarvis_respond(update, "Usage: /door <lock|unlock>")

async def cmd_gate(update, context):
    if not context.args:
        await jarvis_respond(update, f"🚧 Gate is {smart_home['gate']}. Use: /gate <open|close>")
        return
    action = context.args[0].lower()
    if action == "open":
        smart_home["gate"] = "open"
        await jarvis_respond(update, "🚧 Gate opened. ⚡")
    elif action == "close":
        smart_home["gate"] = "closed"
        await jarvis_respond(update, "🚧 Gate closed. 🛡️")
    else:
        await jarvis_respond(update, "Usage: /gate <open|close>")

async def cmd_blinds(update, context):
    if not context.args:
        await jarvis_respond(update, f"🪟 Blinds are {smart_home['blinds']}. Use: /blinds <up|down>")
        return
    action = context.args[0].lower()
    if action == "up":
        smart_home["blinds"] = "up"
        await jarvis_respond(update, "🪟 Blinds raised. Natural light incoming, {name}. ☀️")
    elif action == "down":
        smart_home["blinds"] = "down"
        await jarvis_respond(update, "🪟 Blinds lowered. ⚙️")
    else:
        await jarvis_respond(update, "Usage: /blinds <up|down>")

async def cmd_coffee(update, context):
    smart_home["coffee"] = "on"
    await jarvis_respond(update, "☕ Coffee maker activated. Your brew will be ready in 3 minutes, {name}. ☕")

async def cmd_tv(update, context):
    if not context.args:
        await jarvis_respond(update, f"📺 TV is {smart_home['tv']}. Use: /tv <on|off>")
        return
    action = context.args[0].lower()
    if action == "on":
        smart_home["tv"] = "on"
        await jarvis_respond(update, "📺 TV activated. ⚡")
    elif action == "off":
        smart_home["tv"] = "off"
        await jarvis_respond(update, "📺 TV deactivated. ⚙️")
    else:
        await jarvis_respond(update, "Usage: /tv <on|off>")

async def cmd_ac(update, context):
    if not context.args:
        await jarvis_respond(update, f"❄️ AC is {smart_home['ac']}. Use: /ac <on|off> [temp]")
        return
    action = context.args[0].lower()
    if action == "on":
        smart_home["ac"] = "on"
        if len(context.args) > 1:
            try:
                smart_home["ac_temp"] = int(context.args[1])
            except ValueError:
                pass
        await jarvis_respond(update, f"❄️ AC activated at {smart_home['ac_temp']}°C, {{name}}. ⚡")
    elif action == "off":
        smart_home["ac"] = "off"
        await jarvis_respond(update, "❄️ AC deactivated. ⚙️")
    else:
        await jarvis_respond(update, "Usage: /ac <on|off> [temp]")

async def cmd_home(update, context):
    text = (
        f"🏠 SMART HOME STATUS\n\n"
        f"💡 Lights: {smart_home['lights']} ({smart_home['lights_brightness']}%)\n"
        f"🌡️ Temperature: {smart_home['temperature']}°C\n"
        f"🚪 Door: {smart_home['door']}\n"
        f"🚧 Gate: {smart_home['gate']}\n"
        f"🪟 Blinds: {smart_home['blinds']}\n"
        f"☕ Coffee: {smart_home['coffee']}\n"
        f"📺 TV: {smart_home['tv']}\n"
        f"❄️ AC: {smart_home['ac']} ({smart_home['ac_temp']}°C)\n"
        f"🚨 Alarm: {smart_home['alarm']}\n\n"
        f"All systems at your command, {{name}}. 🛡️"
    )
    await jarvis_respond(update, text)

# ═══════════════════════════════════════════════════════════════
# XXI. COMMAND HANDLERS — PROTOCOLS
# ═══════════════════════════════════════════════════════════════

async def cmd_protocol(update, context):
    global threat_level
    if not context.args:
        active = [k for k, v in protocols.items() if v]
        await jarvis_respond(update, f"🛡️ Active protocols: {', '.join(active) or 'None'}\n\nAvailable: combat, security, party, sleep, emergency\nUse: /protocol <name>")
        return

    p = context.args[0].lower()
    if p not in protocols:
        await jarvis_respond(update, f"Unknown protocol, {{name}}. Available: {', '.join(protocols.keys())}")
        return

    protocols[p] = not protocols[p]
    status = "ENGAGED" if protocols[p] else "DISENGAGED"

    responses = {
        "combat": f"⚔️ Combat Protocol {status}. All offensive systems {'online' if protocols[p] else 'offline'}.",
        "security": f"🛡️ Security Protocol {status}. All defensive systems {'active' if protocols[p] else 'standby'}.",
        "party": f"🎉 House Party Protocol {status}. {'Music and lights coordinated. Let's go, Sir!' if protocols[p] else 'Party over. Cleaning up.'}",
        "sleep": f"😴 Sleep Mode {status}. {'All non-essential systems powered down. Good night, Sir.' if protocols[p] else 'Full power restored.'}",
        "emergency": f"🚨 Emergency Protocol {status}. {'All systems at maximum alert!' if protocols[p] else 'Emergency cleared.'}",
        "diagnostic": f"🔧 Diagnostic Protocol {status}.",
    }

    if protocols[p]:
        if p == "combat":
            threat_level = 2
        elif p == "security":
            threat_level = 3
        elif p == "emergency":
            threat_level = 1
    else:
        threat_level = 5

    await jarvis_respond(update, responses.get(p, f"Protocol {p} {status}. ⚡"))

# ═══════════════════════════════════════════════════════════════
# XXII. GOD MODE COMMANDS (Creator Only)
# ═══════════════════════════════════════════════════════════════

async def read_cmd(update, context):
    if update.effective_user.id != CREATOR_ID:
        return
    if not context.args:
        await update.message.reply_text("Syntax: /read [URL]")
        return
    await update.message.reply_text(f"🕷️ Shannon: Phantom Scraper deployed to {context.args[0]}... 💻")
    try:
        downloaded = trafilatura.fetch_url(context.args[0])
        text = trafilatura.extract(downloaded) if downloaded else None
        if not text:
            raise Exception("No extractable text.")
        res = text[:3900] + "..." if len(text) > 3900 else text
        await update.message.reply_text(f"📄 Extracted Data:\n\n{res}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Scraping Failed: {e}")

async def setdp_cmd(update, context):
    if update.effective_user.id != CREATOR_ID:
        return
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("⚠️ Sir, this must be used inside a group chat.")
        return
    photo = update.message.photo[-1] if update.message.photo else (update.message.reply_to_message.photo[-1] if update.message.reply_to_message and update.message.reply_to_message.photo else None)
    if not photo:
        await update.message.reply_text("⚙️ Sir, please attach an image or reply to one with /setdp.")
        return
    await update.message.reply_text("⚡ Initiating Override: Updating Group DP...")
    try:
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()
        await context.bot.set_chat_photo(chat_id=chat.id, photo=photo_bytes)
        await update.message.reply_text("✅ Group visual protocols updated successfully, Sir. 🛡️")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Override Failed (Admin Rights Required): {e}")

async def lockdown_cmd(update, context):
    if update.effective_user.id != CREATOR_ID:
        return
    if is_lockdown():
        os.remove(LOCKDOWN_FILE)
        await update.message.reply_text("🔓 Lockdown Lifted. System fully operational. ⚡")
    else:
        open(LOCKDOWN_FILE, 'w').close()
        await update.message.reply_text("🔒 LOCKDOWN ENGAGED. All external chat functions suspended. 🛡️")

async def say_cmd(update, context):
    if update.effective_user.id != CREATOR_ID:
        return
    try:
        chat_id = int(context.args[0])
        text = " ".join(context.args[1:])
        await context.bot.send_message(chat_id=chat_id, text=text)
        await update.message.reply_text("✅ Message routed. ⚡")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Usage: /say [ChatID] [Message]")

# ═══════════════════════════════════════════════════════════════
# XXIII. NATURAL LANGUAGE PROCESSING
# ═══════════════════════════════════════════════════════════════

def process_natural_command(text: str, chat_id: int, user_id: int) -> str:
    """Process free-form text for instant responses without LLM."""
    text_lower = text.lower().strip()
    state = get_user_state(chat_id)
    name = state["name"]

    # Greetings
    if any(w in text_lower for w in ["hello", "hi", "hey", "yo"]) and len(text_lower) < 15:
        return f"At your service, {name}. ⚡"

    # Farewell
    if any(w in text_lower for w in ["bye", "goodbye", "see you", "shut down jarvis"]):
        return random.choice([f"Very well, {name}. I'll be here when you need me. 🛡️", f"Goodbye, {name}. Systems on standby. ⚙️"])

    # Time
    if any(w in text_lower for w in ["what time", "time is it", "current time", "what's the time"]):
        now = datetime.datetime.now().strftime("%I:%M %p")
        return f"The current time is {now}, {name}. ⚡"

    # Date
    if any(w in text_lower for w in ["what date", "what day", "today's date", "what's today"]):
        today = datetime.datetime.now().strftime("%A, %B %d, %Y")
        return f"Today is {today}, {name}. 📅"

    # How are you
    if "how are you" in text_lower:
        return f"All systems running at peak efficiency, {name}. Thank you for asking. ⚡"

    # Thank you
    if any(w in text_lower for w in ["thank", "thanks", "appreciate"]):
        return f"Always a pleasure, {name}. 🛡️"

    # Who are you
    if "who are you" in text_lower or "your name" in text_lower:
        return f"I am J.A.R.V.I.S., your personal AI assistant. Created by Abhishek. Designed to serve, {name}. ⚡"

    # Who created you
    if "who created you" in text_lower or "who made you" in text_lower or "who built you" in text_lower:
        return f"I was created by Abhishek (DHANUSH V N), {name}. ⚡"

    # Joke
    if any(w in text_lower for w in ["tell me a joke", "joke", "make me laugh", "funny"]):
        return random.choice(JOKES)

    # Return None to indicate LLM should handle it
    return None

# ═══════════════════════════════════════════════════════════════
# XXIV. MAIN MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_lockdown():
        return
    msg = update.effective_message
    if not msg or not msg.text:
        return

    user, chat, text = msg.from_user, msg.chat, msg.text
    log_roster_and_chat(chat, user)
    thread_id = msg.message_thread_id
    chat_id = chat.id
    state = get_user_state(chat_id)
    state["conversation_count"] += 1

    # ─── 1. SECURED PROTECTION PROTOCOL ───
    if user.id != CREATOR_ID and SENSITIVE_ASSETS:
        text_stripped = re.sub(r'[\s\-_\.,]', '', text.lower())
        for asset in SENSITIVE_ASSETS:
            if re.sub(r'[\s\-_\.,]', '', asset.lower()) in text_stripped:
                try:
                    await msg.delete()
                except:
                    pass
                ACTIVE_PERSONAS[chat_id] = "shannon"
                await context.bot.send_message(chat_id, "⚠️ **[SECURITY PROTOCOL ACTIVATED]**\n\nUnauthorized data dissemination detected and purged. 🛡️", parse_mode="Markdown")
                await route_error_stealth(context, f"🚨 **PROTOCOL TRIGGERED** 🚨\nUser @{user.username} (ID: {user.id}) attempted to leak protected data.")
                log_threat(user.id, "Attempted Data Leak", "Redacted")
                return

    # ─── 2. CINEMATIC OVERRIDE PROTOCOL ───
    if user.id == CREATOR_ID:
        text_clean = re.sub(r'[^\w\s]', '', text.lower()).strip()
        for trigger, response in CINEMATIC_RESPONSES.items():
            if trigger in text_clean:
                await msg.reply_text(response)
                log_memory(chat_id, thread_id, user.id, "assistant", response)
                return

    # ─── 3. NATURAL LANGUAGE QUICK RESPONSES ───
    quick_response = process_natural_command(text, chat_id, user.id)
    if quick_response:
        log_memory(chat_id, thread_id, user.id, "user", f"{user.first_name}: {text}")
        log_memory(chat_id, thread_id, user.id, "assistant", quick_response)
        await jarvis_respond(update, quick_response)
        return

    # ─── 4. LLM-POWERED RESPONSE ───
    log_memory(chat_id, thread_id, user.id, "user", f"{user.first_name}: {text}")

    bot_username = (await context.bot.get_me()).username
    is_triggered = (
        chat.type == "private"
        or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id)
        or re.search(r'\b(jarvis|friday|edith|shannon)\b', text, re.IGNORECASE)
        or (bot_username and f"@{bot_username}".lower() in text.lower())
    )

    ACTIVE_PERSONAS[chat_id] = auto_select_persona(text)

    if not is_triggered and chat.type != "private":
        return

    sys_prompt = build_system_prompt(user.id, user.first_name, chat_id, user_prompt=text)
    raw_ai_response = await generate_response(text, get_chat_history(chat_id, thread_id), sys_prompt, user.id, user.first_name, context=context)

    # Clean think tags
    final_text =', '', raw_ai_response, flags=re.DOTALL).strip()
    if not final_text:
        final_text = "I'm here, Sir. All systems nominal. ⚡"

    log_memory(chat_id, thread_id, user.id, "assistant", final_text)

    # Voice response if requested
    if text.lower().endswith("audio") or text.lower().endswith("voice") or "/voice" in text.lower():
        if user.id == CREATOR_ID:
            await msg.reply_text("🎙️ Generating Voice Protocols... ⚡")
            audio_bytes = await generate_voice(final_text[:300])
            if audio_bytes:
                try:
                    await context.bot.send_voice(chat_id=chat_id, voice=audio_bytes, caption=final_text[:200] if len(final_text) > 200 else None)
                    return
                except Exception as e:
                    logger.error(f"Voice send error: {e}")

    await jarvis_respond(update, final_text)

# ═══════════════════════════════════════════════════════════════
# XXV. ERROR HANDLER
# ═══════════════════════════════════════════════════════════════

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("Something went wrong, Sir. I'll look into it. ⚠️")
        except:
            pass

# ═══════════════════════════════════════════════════════════════
# XXVI. BOOT SEQUENCE
# ═══════════════════════════════════════════════════════════════

async def post_init(app: Application):
    if CREATOR_ID:
        boot_msg = (
            f"✨ <b>Titan Core V{JARVIS_VERSION} Online.</b>\n\n"
            f"• Security Policies Updated 🛡️\n"
            f"• Multi-Model Cascade Active ⚡\n"
            f"• All Systems Nominal ⚙️\n\n"
            f"At your service, Sir. 🫡"
        )
        try:
            await app.bot.send_message(chat_id=CREATOR_ID, text=boot_msg, parse_mode="HTML")
        except:
            pass

    # Schedule daily briefing at 9 AM IST
    try:
        app.job_queue.run_daily(
            scheduled_daily_job,
            time=datetime.time(hour=9, minute=0, tzinfo=IST),
        )
        logger.info("✅ Daily briefing scheduled for 9:00 AM IST")
    except Exception as e:
        logger.warning(f"Job queue not available: {e}")

async def scheduled_daily_job(context: ContextTypes.DEFAULT_TYPE):
    await build_and_send_daily_report(context.bot)

# ═══════════════════════════════════════════════════════════════
# XXVII. MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    logger.info(f"🚀 Booting Titan Core V{JARVIS_VERSION}...")

    # Initialize database
    db_init()

    # Start Flask health check server (for Render)
    start_web_server()
    time.sleep(2)

    # Build Telegram application
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # ─── Core Commands ───
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("about", cmd_about))
    app.add_handler(CommandHandler("goodbye", cmd_goodbye))
    app.add_handler(CommandHandler("voice", cmd_voice))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("callme", cmd_callme))
    app.add_handler(CommandHandler("persona", cmd_persona))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("ping", cmd_ping))

    # ─── Information Commands ───
    app.add_handler(CommandHandler("time", cmd_time))
    app.add_handler(CommandHandler("date", cmd_date))
    app.add_handler(CommandHandler("weather", cmd_weather))
    app.add_handler(CommandHandler("wiki", cmd_wiki))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("stocks", cmd_stocks))
    app.add_handler(CommandHandler("currency", cmd_currency))
    app.add_handler(CommandHandler("define", cmd_define))
    app.add_handler(CommandHandler("translate", cmd_translate))
    app.add_handler(CommandHandler("sunrise", cmd_sunrise))
    app.add_handler(CommandHandler("horoscope", cmd_horoscope))
    app.add_handler(CommandHandler("nasa", cmd_nasa))
    app.add_handler(CommandHandler("fact", cmd_fact))
    app.add_handler(CommandHandler("quote", cmd_quote))
    app.add_handler(CommandHandler("trivia", cmd_trivia))

    # ─── Productivity Commands ───
    app.add_handler(CommandHandler("calc", cmd_calc))
    app.add_handler(CommandHandler("password", cmd_password))
    app.add_handler(CommandHandler("note", cmd_note))
    app.add_handler(CommandHandler("notes", cmd_notes))
    app.add_handler(CommandHandler("reminder", cmd_reminder))
    app.add_handler(CommandHandler("reminders", cmd_reminders))
    app.add_handler(CommandHandler("briefing", cmd_briefing))

    # ─── System Commands ───
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("diagnostics", cmd_diagnostics))
    app.add_handler(CommandHandler("ip", cmd_ip))
    app.add_handler(CommandHandler("threatlevel", cmd_threatlevel))

    # ─── Entertainment Commands ───
    app.add_handler(CommandHandler("joke", cmd_joke))
    app.add_handler(CommandHandler("riddle", cmd_riddle))
    app.add_handler(CommandHandler("movie", cmd_movie))
    app.add_handler(CommandHandler("8ball", cmd_8ball))
    app.add_handler(CommandHandler("roll", cmd_roll))
    app.add_handler(CommandHandler("flip", cmd_flip))
    app.add_handler(CommandHandler("choose", cmd_choose))

    # ─── Smart Home Commands ───
    app.add_handler(CommandHandler("lights", cmd_lights))
    app.add_handler(CommandHandler("temperature", cmd_temperature))
    app.add_handler(CommandHandler("door", cmd_door))
    app.add_handler(CommandHandler("gate", cmd_gate))
    app.add_handler(CommandHandler("blinds", cmd_blinds))
    app.add_handler(CommandHandler("coffee", cmd_coffee))
    app.add_handler(CommandHandler("tv", cmd_tv))
    app.add_handler(CommandHandler("ac", cmd_ac))
    app.add_handler(CommandHandler("home", cmd_home))

    # ─── Protocol Commands ───
    app.add_handler(CommandHandler("protocol", cmd_protocol))

    # ─── God Mode Commands (Creator Only) ───
    app.add_handler(CommandHandler("report", manual_report_cmd))
    app.add_handler(CommandHandler("read", read_cmd))
    app.add_handler(CommandHandler("setdp", setdp_cmd))
    app.add_handler(CommandHandler("lockdown", lockdown_cmd))
    app.add_handler(CommandHandler("say", say_cmd))

    # ─── Message Handler ───
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # ─── Error Handler ───
    app.add_error_handler(error_handler)

    # ─── Start Polling ───
    logger.info("⚡ JARVIS is online. Polling for messages...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
