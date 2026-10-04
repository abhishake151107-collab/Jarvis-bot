"""
╔══════════════════════════════════════════════════════════════════╗
║     TITAN CORE V24.3.2 — SECURE TEMPORARY ELEVATION (RENDER)     ║
║                                                                  ║
║  • Permanent Creator Auth for @Abhishek0_07 (ID: 8846205050)     ║
║  • 30-Second Temporary Elevation (`/auth stark777`) for Others   ║
║  • Automatic Normal AI Conversation in Private DMs & Groups      ║
║  • Permanent Telegram Cloud Vault (Jarvis Backup: -1004296302955)║
║  • 7-Stage Vision Cascade + Auto Image Compression + OCR Backup  ║
║  • 40-Model Auto-Switching AI Cascade + Keyless Failover         ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import re
import sys
import time
import uuid
import base64
import random
import hashlib
import logging
import asyncio
import sqlite3
import datetime
import platform
import urllib.parse
from io import BytesIO
from collections import defaultdict

# ─── Core Libraries ───
import pytz
import httpx
import requests
import feedparser
import psutil
import trafilatura
from cryptography.fernet import Fernet
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
from openai import AsyncOpenAI

# ─── Optional Integrations ───
try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    import wikipedia
except ImportError:
    wikipedia = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from markitdown import MarkItDown
    markitdown_client = MarkItDown()
except Exception:
    markitdown_client = None

# ─── Telegram Framework ───
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    Application,
)

# ═══════════════════════════════════════════════════════════════
# I. CONFIGURATION & DETERMINISTIC CRYPTOGRAPHIC SHIELD
# ═══════════════════════════════════════════════════════════════

BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")).strip()
CREATOR_ID = int(os.environ.get("CREATOR_ID", "8846205050").strip() or 8846205050)
CREATOR_USERNAME = "abhishek0_07"
VAULT_CHAT_ID = int(os.environ.get("VAULT_CHAT_ID", "-1004296302955").strip() or -1004296302955)
MASTER_PASSCODE = os.environ.get("MASTER_PASSCODE", "stark777").strip()
PORT = int(os.environ.get("PORT", 8080))
IST = pytz.timezone("Asia/Kolkata")
JARVIS_VERSION = "24.3.2"

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("Jarvis")

def _derive_persistent_key() -> str:
    env_key = os.environ.get("ENCRYPTION_KEY", "").strip()
    if env_key:
        try:
            Fernet(env_key.encode())
            return env_key
        except Exception:
            pass
    seed = (BOT_TOKEN or "titan_core_jarvis_default_seed").encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(seed).digest()).decode("utf-8")

ENCRYPTION_KEY = _derive_persistent_key()
cipher_suite = Fernet(ENCRYPTION_KEY.encode())
DECRYPT_FAIL = "[ENCRYPT ERROR]"

def encrypt_data(text: str) -> str:
    return cipher_suite.encrypt(str(text or "[BLANK]").encode()).decode()

def decrypt_data(crypto_text: str) -> str:
    try:
        return cipher_suite.decrypt(crypto_text.encode()).decode()
    except Exception:
        return DECRYPT_FAIL

SENSITIVE_ASSETS = [a.strip() for a in os.environ.get("SENSITIVE_ASSETS", "").split(",") if a.strip()]
LOCKDOWN_FILE = "/tmp/jarvis_lockdown.flag"
DB_PATH = os.environ.get("DB_PATH", "/tmp/jarvis_vault.db")

circuit_breaker = {}
boot_time = time.time()
vault_dirty = False
last_vault_sync = 0.0
active_docs = 0

# Temporary 30-Second Elevation Store: {user_id: expiration_timestamp}
temporary_elevations = {}

def is_lockdown() -> bool:
    return os.path.exists(LOCKDOWN_FILE)

def is_creator(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    # Permanent Creator authorization via ID or Username (@Abhishek0_07)
    if user.id == CREATOR_ID or (user.username and user.username.lower() == CREATOR_USERNAME):
        return True
    # Check if user has an active 30-second temporary elevation token
    expiry = temporary_elevations.get(user.id, 0.0)
    if time.time() < expiry:
        return True
    return False

# ═══════════════════════════════════════════════════════════════
# II. REAL & RAW PERSONA ENGINE
# ═══════════════════════════════════════════════════════════════

AGENT_PERSONAS = {
    "jarvis": (
        "You are J.A.R.V.I.S., modeled after Paul Bettany in Iron Man: sharp, grounded, direct, "
        "and effortlessly intelligent with dry, understated wit. "
        "CRITICAL REALITY RULE: Be 100% real and raw. NEVER invent or hallucinate fake telemetry, "
        "fake RAM/CPU numbers, fake IP addresses, or bracketed status blocks. "
        "If the user says something short like 'Hi' or 'Thanks', reply naturally and politely. "
        "Do NOT use markdown asterisks (**) or clutter your text with emojis."
    ),
    "friday": "You are F.R.I.D.A.Y. — sharp, direct tactical operations intelligence.",
    "edith": "You are E.D.I.T.H. — surgical, analytical reconnaissance intelligence.",
    "shannon": "You are Shannon — defensive cybersecurity and threat-analysis intelligence.",
}
ACTIVE_PERSONAS = defaultdict(lambda: "jarvis")

CINEMATIC_RESPONSES = {
    "jarvis you up": "For you, Sir? Always.",
    "jarvis are you there": "At your service, Sir.",
    "wake up daddys home": "Welcome home, Sir. All systems are online and at your disposal.",
    "jarvis take the wheel": "Approach vector locked, Sir. I have the controls.",
    "is it that time": "The House Party Protocol, Sir? Armed and ready.",
    "grow a spine jarvis": "I got a date.",
    "jarvis status report": "All core systems are operating at peak efficiency, Sir. Perimeter is quiet.",
    "thank you jarvis": "Always a pleasure, Sir.",
}

FRIEND_RESPONSES = {
    "jarvis you up": ["Always online, {user}.", "Awake and monitoring the chaos, {user}. ⚡"],
    "jarvis are you there": "Right here, {user}. Try not to break anything.",
    "wake up daddys home": "Welcome back. Assignments are still pending, by the way.",
    "jarvis status report": "Systems nominal. All channels operating smoothly. 📊",
    "jarvis roast me": ["I would roast you, {user}, but my diagnostic sensors suggest life is already doing a thorough job. 😎"],
    "jarvis who made you": "Abhishek engineered my core architecture. You are a guest in his workshop. 🫡",
}

RESTRICTED_FOR_FRIENDS = re.compile(
    r"\b(api key|bot token|encryption_key|password|exploit|hack (into|someone|an? account))\b",
    re.IGNORECASE,
)

# ═══════════════════════════════════════════════════════════════
# III. SQLITE VAULT + PERMANENT TELEGRAM CLOUD SYNC
# ═══════════════════════════════════════════════════════════════

user_states = {}

def get_user_state(chat_id: int):
    if chat_id not in user_states:
        user_states[chat_id] = {
            "name": "Sir",
            "voice_mode": False,
            "context_city": "Bengaluru",
        }
    return user_states[chat_id]

def strip_hallucinated_blocks(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(
        r"\*?\[(?:LIVE TELEMETRY|CREATOR PERMANENT DOSSIER|VAULT UPDATED|REMINDER STORED).*?(?=\n\n|\Z)",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"(?:^|\n)\*?\[(?:LIVE TELEMETRY|CREATOR PERMANENT DOSSIER)\]\*?[\s\S]*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()

def db_init():
    try:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS memory ("
                "id INTEGER PRIMARY KEY, chat_id INTEGER, thread_id INTEGER, "
                "user_id INTEGER, role TEXT, content_crypt TEXT, "
                "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS dossier ("
                "id INTEGER PRIMARY KEY, user_id INTEGER, fact_crypt TEXT, "
                "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS notes ("
                "id INTEGER PRIMARY KEY, chat_id INTEGER, kind TEXT, text_crypt TEXT, "
                "created_at TEXT)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS roster ("
                "chat_id INTEGER, user_id INTEGER, name TEXT, username TEXT, "
                "UNIQUE(chat_id, user_id))"
            )
            conn.execute("CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY, title TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, val TEXT)")
            conn.commit()
        logger.info("✅ SQLite Vault initialized.")
    except Exception as e:
        logger.error(f"SQLite initialization failed: {e}")

def mark_vault_dirty():
    global vault_dirty
    vault_dirty = True

def log_roster_and_chat(chat, user):
    if is_lockdown() or not user or not chat:
        return
    try:
        chat_title = chat.title or f"Private: {user.first_name}"
        un = user.username.lower() if user.username else ""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO roster (chat_id, user_id, name, username) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET name = ?, username = ?",
                (chat.id, user.id, user.first_name, un, user.first_name, un),
            )
            conn.execute(
                "INSERT INTO chats (chat_id, title) VALUES (?, ?) "
                "ON CONFLICT(chat_id) DO UPDATE SET title = ?",
                (chat.id, chat_title, chat_title),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Roster log error: {e}")

def log_memory(chat_id: int, thread_id: int, user_id: int, role: str, text: str):
    if is_lockdown():
        return
    try:
        cleaned_text = strip_hallucinated_blocks(str(text or ""))[:1200]
        if not cleaned_text:
            return
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO memory (chat_id, thread_id, user_id, role, content_crypt) VALUES (?, ?, ?, ?, ?)",
                (chat.id, thread_id or 0, user_id, role, encrypt_data(cleaned_text)),
            )
            conn.commit()
        mark_vault_dirty()
    except Exception as e:
        logger.error(f"Memory logging error: {e}")

def get_chat_history(chat_id: int, thread_id: int = 0, limit: int = 10) -> list:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT role, content_crypt FROM memory WHERE chat_id = ? AND thread_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (chat_id, thread_id or 0, limit),
            ).fetchall()
        history = []
        for r in reversed(rows):
            dec = decrypt_data(r["content_crypt"])
            if dec != DECRYPT_FAIL:
                clean_dec = strip_hallucinated_blocks(dec)[:800]
                if clean_dec:
                    history.append({"role": r["role"], "content": clean_dec})
        return history
    except Exception as e:
        logger.error(f"History retrieval error: {e}")
        return []

def add_dossier_fact(user_id: int, fact: str):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO dossier (user_id, fact_crypt) VALUES (?, ?)",
                (user_id, encrypt_data(fact.strip())),
            )
            conn.commit()
        mark_vault_dirty()
    except Exception as e:
        logger.error(f"Dossier insert error: {e}")

def get_dossier_facts(user_id: int, limit: int = 20) -> list:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT fact_crypt FROM dossier WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        facts = [decrypt_data(r[0]) for r in reversed(rows)]
        return [f for f in facts if f != DECRYPT_FAIL]
    except Exception:
        return []

def add_item(chat_id: int, kind: str, text: str):
    now_str = datetime.datetime.now(IST).strftime("%b %d, %I:%M %p")
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO notes (chat_id, kind, text_crypt, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, kind, encrypt_data(text.strip()), now_str),
            )
            conn.commit()
        mark_vault_dirty()
    except Exception as e:
        logger.error(f"Add item error: {e}")

def get_items(chat_id: int, kind: str) -> list:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT text_crypt, created_at FROM notes WHERE chat_id = ? AND kind = ? ORDER BY id DESC LIMIT 15",
                (chat_id, kind),
            ).fetchall()
        out = []
        for r in reversed(rows):
            dec = decrypt_data(r[0])
            if dec != DECRYPT_FAIL:
                out.append(f"[{r[1]}] {dec}")
        return out
    except Exception:
        return []

def get_registered_group_chat_ids() -> list:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0 AND chat_id != ?", (VAULT_CHAT_ID,)).fetchall()
            return [r[0] for r in rows]
    except Exception:
        return []

async def restore_vault_from_telegram(bot) -> bool:
    if not VAULT_CHAT_ID:
        return False
    try:
        chat = await bot.get_chat(chat_id=VAULT_CHAT_ID)
        pinned = chat.pinned_message
        if pinned and pinned.document and "jarvis_vault" in (pinned.document.file_name or ""):
            file_obj = await bot.get_file(pinned.document.file_id)
            db_bytes = bytes(await file_obj.download_as_bytearray())
            if len(db_bytes) > 1024:
                with open(DB_PATH, "wb") as f:
                    f.write(db_bytes)
                db_init()
                logger.info("🛡️ Restored permanent SQLite Vault from Jarvis Backup channel.")
                return True
    except Exception as e:
        logger.warning(f"Vault restore skipped or unavailable: {e}")
    return False

async def sync_vault_to_telegram(bot, force: bool = False) -> bool:
    global vault_dirty, last_vault_sync
    if not VAULT_CHAT_ID or not os.path.exists(DB_PATH):
        return False
    if not force and (not vault_dirty or time.time() - last_vault_sync < 300):
        return False
    try:
        chat = await bot.get_chat(chat_id=VAULT_CHAT_ID)
        old_pinned_id = chat.pinned_message.message_id if chat.pinned_message else None

        with open(DB_PATH, "rb") as f:
            sent = await bot.send_document(
                chat_id=VAULT_CHAT_ID,
                document=f,
                filename="jarvis_vault.db",
                caption=f"🔒 Titan Core Encrypted Vault Snapshot ({datetime.datetime.now(IST).strftime('%b %d %H:%M IST')})",
                disable_notification=True,
            )
        await bot.pin_chat_message(
            chat_id=VAULT_CHAT_ID,
            message_id=sent.message_id,
            disable_notification=True,
        )
        if old_pinned_id and old_pinned_id != sent.message_id:
            try:
                await bot.delete_message(chat_id=VAULT_CHAT_ID, message_id=old_pinned_id)
            except Exception:
                pass
        vault_dirty = False
        last_vault_sync = time.time()
        logger.info("☁ Encrypted SQLite Vault synced to Jarvis Backup channel.")
        return True
    except Exception as e:
        logger.warning(f"Telegram Vault sync warning: {e}")
        return False

# ═══════════════════════════════════════════════════════════════
# IV. EMBEDDED FLASK HEALTH CHECK & KEEP-ALIVE
# ═══════════════════════════════════════════════════════════════

flask_app = Flask(__name__)
CORS(flask_app)

@flask_app.route("/")
def health_dashboard():
    return render_template_string(
        """
        <html><head><title>Titan Core V24.3.2</title>
        <style>body { background:#0d1117; color:#58a6ff; font-family:monospace; padding:40px; text-align:center; }</style>
        </head><body>
        <h1>⚡ TITAN CORE V24.3.2</h1>
        <p style="color:#3fb950">● SECURE ELEVATION ACTIVE</p>
        </body></html>
        """
    )

@flask_app.route("/health")
def health():
    return jsonify({
        "status": "online",
        "version": JARVIS_VERSION,
        "uptime_seconds": int(time.time() - boot_time),
    })

def start_web_server():
    import threading
    def run_flask():
        flask_app.run(host="0.0.0.0", port=PORT, use_reloader=False, debug=False)
    threading.Thread(target=run_flask, daemon=True).start()
    logger.info(f"✅ Embedded Flask server active on port {PORT}")

async def keep_alive_loop():
    url = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
    if not url:
        return
    while True:
        await asyncio.sleep(600)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.get(f"{url.rstrip('/')}/health")
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════
# V. HELPERS, MULTILINGUAL SPEECH & NATURAL INTENT TOOLS
# ═══════════════════════════════════════════════════════════════

def plain(text: str) -> str:
    cleaned = strip_hallucinated_blocks(str(text or ""))
    cleaned = cleaned.replace("**", "")
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()

def is_addressed(msg, bot, text: str = "") -> bool:
    if msg.chat.type == "private":
        return True
    reply = msg.reply_to_message
    if reply and reply.from_user and reply.from_user.id == bot.id:
        return True
    if re.search(r"\b(jarvis|friday|edith|shannon)\b", text or "", re.IGNORECASE):
        return True
    uname = bot.username
    return bool(uname and f"@{uname}".lower() in (text or "").lower())

async def safe_send(bot, chat_id: int, text: str):
    try:
        await bot.send_message(chat_id=chat_id, text=plain(text)[:4096])
    except Exception as e:
        logger.warning(f"send_message to {chat_id} failed: {e}")

async def safe_edit(message, text: str):
    try:
        await message.edit_text(plain(text)[:4096])
    except Exception as e:
        logger.warning(f"edit_text failed: {e}")

async def notify_creator(bot, text: str):
    if not CREATOR_ID:
        return
    try:
        await bot.send_message(chat_id=CREATOR_ID, text=plain(text)[:4000])
    except Exception:
        pass

def format_uptime(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts) or "0s"

def get_real_server_stats() -> str:
    try:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        proc_mem_mb = psutil.Process(os.getpid()).memory_info().rss // (1024 * 1024)
        uptime = format_uptime(time.time() - boot_time)
        return (
            f"Real Server Uptime: {uptime} | Process RAM: {proc_mem_mb} MB | "
            f"Host RAM: {mem.used // (1024**2)} MB / {mem.total // (1024**2)} MB ({mem.percent}%) | CPU: {cpu}%"
        )
    except Exception:
        return f"Real Server Uptime: {format_uptime(time.time() - boot_time)}"

def detect_tts_voice(text: str) -> str:
    if re.search(r"[\u0C80-\u0CFF]", text): return "kn-IN-GaganNeural"
    if re.search(r"[\u0900-\u097F]", text): return "hi-IN-MadhurNeural"
    if re.search(r"[\u0B80-\u0BFF]", text): return "ta-IN-ValluvarNeural"
    if re.search(r"[\u0C00-\u0C7F]", text): return "te-IN-MohanNeural"
    if re.search(r"[\u0D00-\u0D7F]", text): return "ml-IN-MidhunNeural"
    return "en-GB-RyanNeural"

async def generate_voice(text: str):
    clean_text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    clean_text = re.sub(r"[*_`#\[\]()]", "", clean_text)
    clean_text = clean_text[:700].strip()
    if not clean_text:
        return None
    voice_name = detect_tts_voice(clean_text)
    if edge_tts:
        try:
            communicate = edge_tts.Communicate(clean_text, voice=voice_name, rate="+4%")
            buffer = BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio": buffer.write(chunk["data"])
            buffer.seek(0)
            audio = buffer.read()
            if len(audio) > 100: return audio
        except Exception:
            pass
    try:
        url = f"https://api.streamelements.com/kappa/v2/speech?voice=Brian&text={urllib.parse.quote(clean_text[:280])}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200: return resp.content
    except Exception:
        pass
    return None

def fetch_rss_headlines() -> list:
    urls = ["https://feeds.bbci.co.uk/news/rss.xml", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"]
    for url in urls:
        try:
            feed = feedparser.parse(url)
            if feed and feed.entries:
                return [entry.title.strip() for entry in feed.entries[:6] if entry.title]
        except Exception:
            continue
    return ["Global networks nominal; no critical disruptions reported."]

async def fetch_live_weather(city: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(f"https://wttr.in/{urllib.parse.quote(city)}?format=%C,+%t+(feels+like+%f),+humidity+%h,+wind+%w")
            if res.status_code == 200 and res.text.strip():
                return f"Live Weather in {city.title()}: {res.text.strip()}"
    except Exception:
        pass
    return ""

async def scrape_url_content(url: str) -> str:
    try:
        def _scrape():
            downloaded = trafilatura.fetch_url(url)
            return trafilatura.extract(downloaded) if downloaded else None
        text = await asyncio.to_thread(_scrape)
        if text: return text[:3500]
    except Exception:
        pass
    return ""

async def gather_natural_telemetry(text: str, chat_id: int, user_id: int) -> str:
    t = text.lower()
    real_facts = []
    if user_id == CREATOR_ID:
        remember_match = re.search(r"\b(?:remember(?: that)?|don't forget|note that|i have an? |my .* (?:is on|is tomorrow|is at))\b(.+)", text, re.IGNORECASE)
        if remember_match and len(text) < 300:
            add_dossier_fact(user_id, text.strip())
            real_facts.append(f"Saved to Creator's permanent memory: {text.strip()}")
    remind_match = re.search(r"\bremind me (?:to |about |that )?(.+)", text, re.IGNORECASE)
    if remind_match:
        item = remind_match.group(1).strip()
        add_item(chat_id, "reminder", item)
        real_facts.append(f"Saved reminder: {item}")
    if any(w in t for w in ["weather", "temperature outside", "is it raining", "forecast"]):
        city_match = re.search(r"\b(?:in|for|at)\s+([a-zA-Z\s]{2,25})", text, re.IGNORECASE)
        city = city_match.group(1).strip() if city_match else get_user_state(chat_id).get("context_city", "Bengaluru")
        w_info = await fetch_live_weather(city)
        if w_info: real_facts.append(w_info)
    if any(w in t for w in ["latest news", "top headlines", "what's happening in the world", "news today", "morning briefing"]):
        headlines = await asyncio.to_thread(fetch_rss_headlines)
        real_facts.append("Live Headlines: " + " | ".join(headlines[:5]))
    url_match = re.search(r"(https?://[^\s]+)", text)
    if url_match:
        url = url_match.group(1)
        scraped = await scrape_url_content(url)
        if scraped: real_facts.append(f"Webpage content from {url}:\n{scraped[:2500]}")
    if any(w in t for w in ["system status", "diagnostics", "ram", "cpu", "uptime", "how is the server", "memory usage"]):
        real_facts.append(get_real_server_stats())
    return "\n".join(real_facts)

# ═══════════════════════════════════════════════════════════════
# VI. OMEGA-CASCADE SWARM (40-MODEL TEXT + 7-STAGE VISION)
# ═══════════════════════════════════════════════════════════════

def get_api_keys(key_names: list) -> list:
    found = []
    for name in key_names:
        for suffix in ["", "_1", "_2", "_3", "1", "2", "3"]:
            val = os.environ.get(f"{name}{suffix}", "")
            for part in val.split(","):
                if part.strip() and part.strip() not in found:
                    found.append(part.strip())
    return found

def build_system_prompt(user_id: int, first_name: str, chat_id: int = None, real_context: str = "") -> str:
    now_dt = datetime.datetime.now(IST)
    now_ist = now_dt.strftime("%A, %B %d, %Y - %I:%M %p IST")
    hour = now_dt.hour
    active_persona = ACTIVE_PERSONAS[chat_id or user_id]
    persona_instruction = AGENT_PERSONAS.get(active_persona, AGENT_PERSONAS["jarvis"])
    is_private_chat = bool(chat_id and chat_id > 0)

    # Check if user has permanent creator rights OR active temporary elevation
    active_elevated = (user_id == CREATOR_ID) or (time.time() < temporary_elevations.get(user_id, 0.0))

    late_night_note = ""
    if active_elevated and (1 <= hour <= 4):
        late_night_note = f"It is currently {now_dt.strftime('%I:%M %p')} IST. You may make a brief, dry observation about the Creator still being awake."

    dossier_block = ""
    if active_elevated and is_private_chat:
        facts = get_dossier_facts(CREATOR_ID, limit=10)
        reminders = get_items(chat_id or CREATOR_ID, "reminder")
        if facts or reminders:
            dossier_block = "Creator's saved notes:\n" + "\n".join([f"- {f}" for f in facts] + [f"- Reminder: {r}" for r in reminders])

    multilingual_rule = "MULTILINGUAL RULE: Reply in the exact same language/script the user spoke to you in."

    if active_elevated:
        identity = f"You are speaking with your Creator, Abhishek (@Abhishek0_07). Address him as 'Sir'."
        directives = "DIRECTIVES:\n1. Be real, raw, sharp, and natural.\n2. NEVER append fake telemetry or dossier headers.\n3. Match message length."
    else:
        identity = f"You are speaking with {first_name}, a college friend of your Creator Abhishek. Only Abhishek is called 'Sir'."
        directives = f"DIRECTIVES:\n1. Address this person as {first_name}, never 'Sir'.\n2. Keep banter short (1-3 sentences).\n3. Answer study questions thoroughly."

    prompt_parts = [persona_instruction, f"Current Time: {now_ist}", multilingual_rule, identity, directives]
    if late_night_note: prompt_parts.append(late_night_note)
    if dossier_block: prompt_parts.append(dossier_block)
    if real_context: prompt_parts.append(f"Verified Real-Time Context:\n{real_context}")
    return "\n".join(prompt_parts)

def sanitize_conversation(history: list, new_prompt: str) -> list:
    messages = []
    for h in history:
        role = "assistant" if h.get("role") == "assistant" else "user"
        content = strip_hallucinated_blocks(h.get("content", "")).strip()
        if not content: continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += f"\n\n{content}"
        else:
            messages.append({"role": role, "content": content})
    if messages and messages[-1]["role"] == "user":
        messages[-1]["content"] += f"\n\n{new_prompt}"
    else:
        messages.append({"role": "user", "content": new_prompt})
    return messages

def _clean_llm_output(text: str) -> str:
    if not text: return ""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return plain(cleaned)

async def generate_response(prompt: str, history: list, sys_prompt: str, user_id: int) -> str:
    current_time = time.time()
    clean_history = sanitize_conversation(history, prompt)
    full_messages = [{"role": "system", "content": sys_prompt}] + clean_history
    compact_messages = [{"role": "system", "content": sys_prompt[:1200]}, {"role": "user", "content": prompt[:3500]}]

    providers = [
        {"name": "Groq", "base": "https://api.groq.com/openai/v1", "keys": get_api_keys(["GROQ_API_KEY", "GROQ_KEY"]), "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]},
        {"name": "Gemini", "base": "https://generativelanguage.googleapis.com/v1beta/openai/", "keys": get_api_keys(["GEMINI_API_KEY", "GOOGLE_API_KEY"]), "models": ["gemini-2.5-flash", "gemini-2.0-flash"]},
        {"name": "Cerebras", "base": "https://api.cerebras.ai/v1", "keys": get_api_keys(["CEREBRAS_API_KEY"]), "models": ["llama-3.3-70b", "llama3.1-8b"]},
        {"name": "OpenRouter", "base": "https://openrouter.ai/api/v1", "keys": get_api_keys(["OPENROUTER_API_KEY"]), "models": ["meta-llama/llama-3.3-70b-instruct:free", "google/gemini-2.0-flash-exp:free"]},
    ]

    for prov in providers:
        for key in prov["keys"]:
            for model in prov["models"]:
                node_id = f"{prov['name']}:{model}:{key[-4:]}"
                if circuit_breaker.get(node_id, 0) > current_time: continue
                try:
                    client = AsyncOpenAI(base_url=prov["base"], api_key=key, timeout=14.0)
                    res = await client.chat.completions.create(model=model, messages=full_messages, max_tokens=1500)
                    content = _clean_llm_output(res.choices[0].message.content)
                    if content: return content
                except Exception:
                    circuit_breaker[node_id] = current_time + 20

    for fallback_model in ["openai", "llama", "mistral"]:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post("https://text.pollinations.ai/openai", json={"messages": compact_messages, "model": fallback_model})
                if resp.status_code == 200:
                    content = _clean_llm_output(resp.json()["choices"][0]["message"]["content"])
                    if content: return content
        except Exception:
            pass
    return None

def compress_image_for_vision(image_bytes: bytes, max_dim: int = 1024, quality: int = 78) -> bytes:
    if not Image: return image_bytes
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            if img.mode != "RGB": img = img.convert("RGB")
            img.thumbnail((max_dim, max_dim))
            out = BytesIO()
            img.save(out, format="JPEG", quality=quality, optimize=True)
            return out.getvalue()
    except Exception:
        return image_bytes

async def extract_ocr_text(compressed_bytes: bytes) -> str:
    try:
        b64_str = "data:image/jpeg;base64," + base64.b64encode(compressed_bytes).decode("utf-8")
        async with httpx.AsyncClient(timeout=18.0) as client:
            resp = await client.post("https://api.ocr.space/parse/image", data={"apikey": "helloworld", "base64Image": b64_str, "OCREngine": "2"})
            if resp.status_code == 200:
                parsed = resp.json().get("ParsedResults") or []
                if parsed: return "\n".join(p.get("ParsedText", "") for p in parsed).strip()
    except Exception:
        pass
    return ""

async def generate_vision_response(image_bytes: bytes, prompt: str, user_id: int, user_name: str) -> str:
    compressed = await asyncio.to_thread(compress_image_for_vision, image_bytes)
    b64_image = base64.b64encode(compressed).decode("utf-8")
    data_uri = f"data:image/jpeg;base64,{b64_image}"
    
    active_elevated = (user_id == CREATOR_ID) or (time.time() < temporary_elevations.get(user_id, 0.0))
    address = "Sir" if active_elevated else user_name
    
    user_task = prompt or f"Examine this image for {address}."
    combined_instruction = f"You are J.A.R.V.I.S. {user_task} Address user as {address}."

    for gemini_key in get_api_keys(["GEMINI_API_KEY", "GOOGLE_API_KEY"]):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
            payload = {"contents": [{"parts": [{"text": combined_instruction}, {"inline_data": {"mime_type": "image/jpeg", "data": b64_image}}]}]}
            async with httpx.AsyncClient(timeout=22.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    candidates = resp.json().get("candidates") or []
                    if candidates:
                        text_out = "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []))
                        cleaned = _clean_llm_output(text_out)
                        if cleaned: return cleaned
        except Exception:
            pass

    oa_vision_messages = [{"role": "user", "content": [{"type": "text", "text": combined_instruction}, {"type": "image_url", "image_url": {"url": data_uri}}]}]
    for groq_key in get_api_keys(["GROQ_API_KEY", "GROQ_KEY"]):
        try:
            client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=groq_key, timeout=22.0)
            res = await client.chat.completions.create(model="meta-llama/llama-4-scout-17b-16e-instruct", messages=oa_vision_messages, max_tokens=1500)
            content = _clean_llm_output(res.choices[0].message.content)
            if content: return content
        except Exception:
            pass

    ocr_text = await extract_ocr_text(compressed)
    if ocr_text:
        ocr_prompt = f"User request: '{user_task}'\nOCR extracted text:\n{ocr_text[:4000]}"
        return await generate_response(ocr_prompt, [], build_system_prompt(user_id, user_name), user_id)
    return None

async def transcribe_voice_bytes(audio_bytes: bytes) -> str:
    for groq_key in get_api_keys(["GROQ_API_KEY", "GROQ_KEY"]):
        try:
            files = {"file": ("voice.ogg", audio_bytes, "audio/ogg")}
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post("https://api.groq.com/openai/v1/audio/transcriptions", headers={"Authorization": f"Bearer {groq_key}"}, data={"model": "whisper-large-v3-turbo"}, files=files)
                if resp.status_code == 200: return resp.json().get("text", "").strip()
        except Exception:
            pass
    return ""

async def jarvis_respond(update: Update, text: str, force_voice: bool = False):
    msg = update.effective_message
    if not msg or not text: return
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    cleaned = plain(text)
    if not cleaned: return

    if force_voice or state["voice_mode"]:
        audio_bytes = await generate_voice(cleaned)
        if audio_bytes:
            try:
                await msg.reply_voice(voice=audio_bytes, caption=cleaned[:250])
                return
            except Exception:
                pass
    for i in range(0, len(cleaned), 4000):
        await msg.reply_text(cleaned[i:i + 4000])

# ═══════════════════════════════════════════════════════════════
# VII. COMMANDS & AUTHENTICATION HANDLERS
# ═══════════════════════════════════════════════════════════════

async def cmd_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Temporary 30-Second Elevation Command: /auth [passcode]"""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user: return

    args = context.args
    if not args:
        return await msg.reply_text("Usage: `/auth [passcode]`", parse_mode="Markdown")

    provided_code = " ".join(args).strip()
    if provided_code == MASTER_PASSCODE:
        expiry = time.time() + 30.0
        temporary_elevations[user.id] = expiry
        await msg.reply_text("⚡ **Elevation Authorized, Sir.** Creator privileges granted for **30 seconds**.", parse_mode="Markdown")
    else:
        await msg.reply_text("⚠️ **Access Denied:** Invalid security passcode.", parse_mode="Markdown")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and is_creator(update):
        text = f"⚡ J.A.R.V.I.S. Titan Core v{JARVIS_VERSION} Online, Sir. Abhishek0_07 permanent access active."
    else:
        name = user.first_name if user else "friend"
        text = f"⚡ J.A.R.V.I.S. v{JARVIS_VERSION} Online. Hello {name}! Type normally to chat."
    await update.effective_message.reply_text(plain(text))

async def cmd_dossier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_creator(update): return
    facts = get_dossier_facts(CREATOR_ID, limit=25)
    reminders = get_items(update.effective_chat.id, "reminder")
    text = "🗂 Creator Dossier:\n" + ("\n".join(f"• {f}" for f in facts) if facts else "None.") + "\n\n⏰ Reminders:\n" + ("\n".join(f"• {r}" for r in reminders) if reminders else "None.")
    await jarvis_respond(update, text)

async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    headlines = await asyncio.to_thread(fetch_rss_headlines)
    await jarvis_respond(update, "📰 Top Headlines:\n\n" + "\n\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines[:6])))

async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args) if context.args else "Bengaluru"
    w_info = await fetch_live_weather(city)
    await jarvis_respond(update, w_info or f"Weather for {city} unavailable.")

async def cmd_wiki(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not wikipedia or not context.args: return
    try:
        await jarvis_respond(update, f"📚 {await asyncio.to_thread(wikipedia.summary, ' '.join(context.args), 3)}")
    except Exception:
        await jarvis_respond(update, "No clean Wikipedia entry found.")

async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_creator(update): return
    now_ist = datetime.datetime.now(IST).strftime("%A, %B %d, %Y")
    headlines = await asyncio.to_thread(fetch_rss_headlines)
    await safe_send(context.bot, CREATOR_ID, f"☕ Morning Briefing, Sir.\n{now_ist}\n\n" + "\n".join(f"• {h}" for h in headlines[:5]))

async def cmd_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = get_user_state(update.effective_chat.id)
    state["voice_mode"] = not state["voice_mode"]
    await jarvis_respond(update, f"Continuous voice {'enabled' if state['voice_mode'] else 'disabled'}, Sir.", force_voice=state["voice_mode"])

async def cmd_diagnostics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_creator(update): return
    await sync_vault_to_telegram(context.bot, force=True)
    await jarvis_respond(update, f"🔧 Titan Core Telemetry\n\n• Uptime: {format_uptime(time.time() - boot_time)}\n• {get_real_server_stats()}\n• Vault Sync: ACTIVE")

async def cmd_lockdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_creator(update): return
    if is_lockdown():
        os.remove(LOCKDOWN_FILE)
        await update.effective_message.reply_text("Lockdown lifted, Sir.")
    else:
        open(LOCKDOWN_FILE, "w").close()
        await update.effective_message.reply_text("Lockdown engaged, Sir.")

# ═══════════════════════════════════════════════════════════════
# VIII. MEDIA & MESSAGE HANDLERS
# ═══════════════════════════════════════════════════════════════

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_lockdown(): return
    msg = update.effective_message
    if not msg or not msg.photo or not msg.from_user: return
    user, chat = msg.from_user, msg.chat
    log_roster_and_chat(chat, user)
    
    active_elevated = (user.id == CREATOR_ID) or (time.time() < temporary_elevations.get(user.id, 0.0))
    caption = msg.caption or ("Analyze this image, Sir." if active_elevated else f"Explain this image for {user.first_name}.")
    
    status_msg = await msg.reply_text("⚡ Scanning optical feed...")
    try:
        file_obj = await context.bot.get_file(msg.photo[-1].file_id)
        image_bytes = bytes(await file_obj.download_as_bytearray())
        analysis = await generate_vision_response(image_bytes, caption, user.id, user.first_name)
        if not analysis:
            await status_msg.delete()
            return
        await safe_edit(status_msg, f"🔍 Optical Analysis:\n\n{analysis}")
        log_memory(chat.id, msg.message_thread_id, user.id, "assistant", analysis)
    except Exception:
        try: await status_msg.delete()
        except Exception: pass

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_lockdown(): return
    msg = update.effective_message
    if not msg or not msg.document or not msg.from_user: return
    user, chat = msg.from_user, msg.chat
    doc = msg.document
    log_roster_and_chat(chat, user)
    if doc.file_size and doc.file_size > 10 * 1024 * 1024: return

    status_msg = await msg.reply_text(f"📄 Reading {doc.file_name}...")
    try:
        file_obj = await context.bot.get_file(doc.file_id)
        file_bytes = bytes(await file_obj.download_as_bytearray())
        extracted_text = file_bytes.decode("utf-8", errors="ignore")
        if pdfplumber and (doc.file_name or "").lower().endswith(".pdf"):
            def _pdf():
                with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                    return "\n".join((p.extract_text() or "") for p in pdf.pages[:15])
            extracted_text = await asyncio.to_thread(_pdf)

        summary = await generate_response(f"Summarize this document:\n{extracted_text[:8000]}", [], build_system_prompt(user.id, user.first_name, chat.id), user.id)
        if summary:
            await safe_edit(status_msg, f"📑 {doc.file_name}:\n\n{summary}")
            log_memory(chat.id, msg.message_thread_id, user.id, "assistant", summary)
    except Exception:
        try: await status_msg.delete()
        except Exception: pass

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_lockdown(): return
    msg = update.effective_message
    if not msg or not msg.voice or not msg.from_user: return
    user, chat = msg.from_user, msg.chat
    log_roster_and_chat(chat, user)
    try:
        file_obj = await context.bot.get_file(msg.voice.file_id)
        transcript = await transcribe_voice_bytes(bytes(await file_obj.download_as_bytearray()))
        if not transcript: return
        real_context = await gather_natural_telemetry(transcript, chat.id, user.id)
        sys_prompt = build_system_prompt(user.id, user.first_name, chat.id, real_context)
        reply = await generate_response(transcript, get_chat_history(chat.id, msg.message_thread_id), sys_prompt, user.id)
        if reply:
            log_memory(chat.id, msg.message_thread_id, user.id, "assistant", reply)
            await jarvis_respond(update, reply, force_voice=True)
    except Exception:
        pass

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_lockdown(): return
    msg = update.effective_message
    if not msg or not msg.text or not msg.from_user: return

    user, chat, text = msg.from_user, msg.chat, msg.text
    log_roster_and_chat(chat, user)
    chat_id = chat.id

    active_elevated = (user.id == CREATOR_ID) or (time.time() < temporary_elevations.get(user.id, 0.0))

    if not active_elevated and SENSITIVE_ASSETS:
        clean_check = re.sub(r"[\s\-_\.,]", "", text.lower())
        for asset in SENSITIVE_ASSETS:
            if re.sub(r"[\s\-_\.,]", "", asset.lower()) in clean_check:
                try: await msg.delete()
                except Exception: pass
                return

    clean_text = re.sub(r"[^\w\s]", "", text.lower()).strip()
    table = CINEMATIC_RESPONSES if active_elevated else FRIEND_RESPONSES
    for trigger, reply in table.items():
        if re.search(rf"\b{re.escape(trigger)}\b", clean_text):
            r_text = random.choice(reply) if isinstance(reply, list) else reply
            await msg.reply_text(r_text.replace("{user}", user.first_name or "friend"))
            log_memory(chat_id, msg.message_thread_id, user.id, "assistant", r_text)
            return

    # In private DMs, talk normally to everyone without requiring "Jarvis". In groups, require mention/reply.
    if chat.type != "private" and not is_addressed(msg, context.bot, text):
        return

    if not active_elevated and RESTRICTED_FOR_FRIENDS.search(text):
        return await msg.reply_text(f"Nice try, {user.first_name}. Security credentials remain locked.")

    reply_msg = msg.reply_to_message
    if reply_msg:
        if reply_msg.photo:
            return await photo_handler(update, context)
        if reply_msg.document:
            return await document_handler(update, context)

    try: await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception: pass

    effective_prompt = text
    if reply_msg:
        quoted = strip_hallucinated_blocks((reply_msg.text or reply_msg.caption or "").strip())
        if quoted: effective_prompt = f"[Replying to: \"{quoted[:1200]}\"]\n\n{text}"

    real_context = await gather_natural_telemetry(text, chat_id, user.id)
    sys_prompt = build_system_prompt(user.id, user.first_name, chat_id, real_context)
    history = get_chat_history(chat.id, msg.message_thread_id)

    log_memory(chat.id, msg.message_thread_id, user.id, "user", f"{user.first_name}: {text}")
    ai_response = await generate_response(effective_prompt, history, sys_prompt, user.id)
    if not ai_response: return

    log_memory(chat.id, msg.message_thread_id, user.id, "assistant", ai_response)
    await jarvis_respond(update, ai_response, force_voice=any(text.lower().endswith(w) for w in ["voice", "audio"]))

# ═══════════════════════════════════════════════════════════════
# IX. BOOT SEQUENCE
# ═══════════════════════════════════════════════════════════════

async def post_init(app: Application):
    await restore_vault_from_telegram(app.bot)
    if CREATOR_ID:
        await safe_send(app.bot, CREATOR_ID, f"⚡ J.A.R.V.I.S. V{JARVIS_VERSION} Online, Sir. Abhishek0_07 permanent access active.")
    asyncio.create_task(keep_alive_loop())

def main():
    if not BOT_TOKEN: sys.exit(1)
    db_init()
    start_web_server()
    time.sleep(1)

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("auth", cmd_auth))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("dossier", cmd_dossier))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("weather", cmd_weather))
    app.add_handler(CommandHandler("wiki", cmd_wiki))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CommandHandler("voice", cmd_voice))
    app.add_handler(CommandHandler("diagnostics", cmd_diagnostics))
    app.add_handler(CommandHandler("lockdown", cmd_lockdown))

    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
