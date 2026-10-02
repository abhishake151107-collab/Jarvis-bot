"""
╔══════════════════════════════════════════════════════════════════╗
║     TITAN CORE V24.3 — REAL & RAW MOVIE J.A.R.V.I.S. (RENDER)    ║
║                                                                  ║
║  • 100% Real Data Only (Zero Fake Telemetry or Hallucinations)   ║
║  • Permanent Telegram Cloud Vault (Jarvis Backup: -1004296302955)║
║  • 7-Stage Vision Cascade + Auto Image Compression + OCR Backup  ║
║  • 40-Model Auto-Switching AI Cascade + Keyless Failover         ║
║  • Zero Error Messages in Group Chats (100% Group Stealth)       ║
║  • Reply-Aware ("Translate in english" / "What is this Jarvis")  ║
║  • 100% Multilingual Text, Vision & Neural Voice (KN/HI/EN/etc.) ║
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
VAULT_CHAT_ID = int(os.environ.get("VAULT_CHAT_ID", "-1004296302955").strip() or -1004296302955)
PORT = int(os.environ.get("PORT", 8080))
IST = pytz.timezone("Asia/Kolkata")
JARVIS_VERSION = "24.3.0"

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("Jarvis")

def _derive_persistent_key() -> str:
    """Derives a permanent Fernet key from BOT_TOKEN if ENCRYPTION_KEY is not set."""
    env_key = os.environ.get("ENCRYPTION_KEY", "").strip()
    if env_key:
        try:
            Fernet(env_key.encode())
            return env_key
        except Exception:
            logger.warning("Invalid ENCRYPTION_KEY format; deriving deterministic key from BOT_TOKEN.")
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

def is_lockdown() -> bool:
    return os.path.exists(LOCKDOWN_FILE)

# ═══════════════════════════════════════════════════════════════
# II. REAL & RAW PERSONA ENGINE
# ═══════════════════════════════════════════════════════════════

AGENT_PERSONAS = {
    "jarvis": (
        "You are J.A.R.V.I.S., modeled after Paul Bettany in Iron Man: sharp, grounded, direct, "
        "and effortlessly intelligent with dry, understated wit. "
        "CRITICAL REALITY RULE: Be 100% real and raw. NEVER invent or hallucinate fake telemetry, "
        "fake RAM/CPU numbers, fake IP addresses, fake timestamps, or bracketed status blocks like "
        "[LIVE TELEMETRY] or [CREATOR PERMANENT DOSSIER]. "
        "If the user says something short like 'Ok Jarvis' or 'Thanks', reply with a single crisp sentence "
        "(e.g., 'Standing by, Sir.' or 'At your disposal, Sir.'). "
        "Do NOT use markdown asterisks (**) or clutter your text with emojis."
    ),
    "friday": (
        "You are F.R.I.D.A.Y. — sharp, direct, no-nonsense tactical operations intelligence. "
        "Loyal to Master Abhishek. Zero fake telemetry or roleplay filler."
    ),
    "edith": (
        "You are E.D.I.T.H. — surgical, analytical reconnaissance intelligence. "
        "Precise, cold, factual."
    ),
    "shannon": (
        "You are Shannon — defensive cybersecurity and threat-analysis intelligence. "
        "Focused on real network hygiene, privacy, and zero-trust security."
    ),
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
    "jarvis you up": [
        "Always online, {user}. Unlike your attendance percentage.",
        "Awake and monitoring the chaos, {user}. ⚡",
    ],
    "jarvis are you there": "Right here, {user}. Try not to break anything.",
    "wake up daddys home": "Welcome back, gang. Assignments are still pending, by the way.",
    "jarvis status report": "Group status: high chaos, questionable sleep schedules, immaculate vibes. 📊",
    "jarvis bunk": "Attendance is a finite resource, {user}. Calculate your risks wisely. 😏",
    "jarvis exam": "Ah, the classic 'cover the entire syllabus in one night' strategy. Bold move, {user}. 📚",
    "jarvis roast me": [
        "I would roast you, {user}, but my diagnostic sensors suggest life is already doing a thorough job. 😎",
        "Your study schedule has more plot holes than a low-budget sequel, {user}.",
    ],
    "jarvis who made you": "Abhishek engineered my core architecture. You are merely a guest in his workshop. 🫡",
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
    """Strips any fake [LIVE TELEMETRY] or [CREATOR PERMANENT DOSSIER] blocks from text or history."""
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
    """Restores jarvis_vault.db from the pinned message in VAULT_CHAT_ID across Render restarts."""
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
    """Silently backs up jarvis_vault.db to VAULT_CHAT_ID (-1004296302955) and pins it."""
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
        logger.info("☁️ Encrypted SQLite Vault synced to Jarvis Backup channel.")
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
        <html><head><title>Titan Core V24.3</title>
        <style>body { background:#0d1117; color:#58a6ff; font-family:monospace; padding:40px; text-align:center; }</style>
        </head><body>
        <h1>⚡ TITAN CORE V24.3</h1>
        <p style="color:#3fb950">● REAL & RAW J.A.R.V.I.S. ONLINE</p>
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
    """Strips markdown noise and any hallucinated telemetry/dossier blocks."""
    cleaned = strip_hallucinated_blocks(str(text or ""))
    cleaned = cleaned.replace("**", "")
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()

def is_creator(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == CREATOR_ID)

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
    """Returns 100% real hardware/container metrics from psutil."""
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
    """Automatically selects the right male neural voice for any Indian or global script."""
    if re.search(r"[\u0C80-\u0CFF]", text):
        return "kn-IN-GaganNeural"      # Kannada (Male Neural)
    if re.search(r"[\u0900-\u097F]", text):
        return "hi-IN-MadhurNeural"     # Hindi / Devanagari (Male Neural)
    if re.search(r"[\u0B80-\u0BFF]", text):
        return "ta-IN-ValluvarNeural"   # Tamil (Male Neural)
    if re.search(r"[\u0C00-\u0C7F]", text):
        return "te-IN-MohanNeural"      # Telugu (Male Neural)
    if re.search(r"[\u0D00-\u0D7F]", text):
        return "ml-IN-MidhunNeural"     # Malayalam (Male Neural)
    return "en-GB-RyanNeural"           # Default British Movie Jarvis

async def generate_voice(text: str):
    """Multilingual Neural TTS via edge-tts with automatic script detection."""
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
                if chunk["type"] == "audio":
                    buffer.write(chunk["data"])
            buffer.seek(0)
            audio = buffer.read()
            if len(audio) > 100:
                return audio
        except Exception as e:
            logger.warning(f"edge-tts ({voice_name}) fallback triggered: {e}")

    try:
        url = f"https://api.streamelements.com/kappa/v2/speech?voice=Brian&text={urllib.parse.quote(clean_text[:280])}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.content
    except Exception:
        pass
    return None

def fetch_rss_headlines() -> list:
    urls = [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    ]
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
        if text:
            return text[:3500]
    except Exception:
        pass
    try:
        async with httpx.AsyncClient(timeout=18.0) as client:
            res = await client.get(f"https://r.jina.ai/{url}")
            if res.status_code == 200:
                return res.text[:3500]
    except Exception:
        pass
    return ""

async def gather_natural_telemetry(text: str, chat_id: int, user_id: int) -> str:
    """Detects natural user intent and fetches 100% real external data only when needed."""
    t = text.lower()
    real_facts = []

    # 1. Automatic Personal Dossier Extraction
    if user_id == CREATOR_ID:
        remember_match = re.search(
            r"\b(?:remember(?: that)?|don't forget|note that|i have an? |my .* (?:is on|is tomorrow|is at))\b(.+)",
            text,
            re.IGNORECASE,
        )
        if remember_match and len(text) < 300:
            add_dossier_fact(user_id, text.strip())
            real_facts.append(f"Saved to Creator's permanent memory: {text.strip()}")

    # 2. Natural Reminder Saving
    remind_match = re.search(r"\bremind me (?:to |about |that )?(.+)", text, re.IGNORECASE)
    if remind_match:
        item = remind_match.group(1).strip()
        add_item(chat_id, "reminder", item)
        real_facts.append(f"Saved reminder: {item}")

    # 3. Natural Weather Lookup
    if any(w in t for w in ["weather", "temperature outside", "is it raining", "forecast"]):
        city_match = re.search(r"\b(?:in|for|at)\s+([a-zA-Z\s]{2,25})", text, re.IGNORECASE)
        city = city_match.group(1).strip() if city_match else get_user_state(chat_id).get("context_city", "Bengaluru")
        w_info = await fetch_live_weather(city)
        if w_info:
            real_facts.append(w_info)

    # 4. Natural News Lookup
    if any(w in t for w in ["latest news", "top headlines", "what's happening in the world", "news today", "morning briefing"]):
        headlines = await asyncio.to_thread(fetch_rss_headlines)
        real_facts.append("Live Headlines: " + " | ".join(headlines[:5]))

    # 5. Automatic URL Reading
    url_match = re.search(r"(https?://[^\s]+)", text)
    if url_match:
        url = url_match.group(1)
        scraped = await scrape_url_content(url)
        if scraped:
            real_facts.append(f"Webpage content from {url}:\n{scraped[:2500]}")

    # 6. Real Server Stats if User Asks About System / RAM / Status / Uptime
    if any(w in t for w in ["system status", "diagnostics", "ram", "cpu", "uptime", "how is the server", "memory usage"]):
        real_facts.append(get_real_server_stats())

    return "\n".join(real_facts)

# ═══════════════════════════════════════════════════════════════
# VI. OMEGA-CASCADE SWARM (40-MODEL TEXT + 7-STAGE VISION)
# ═══════════════════════════════════════════════════════════════

def get_api_keys(key_names: list) -> list:
    """Fetches all configured API keys for a provider."""
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

    late_night_note = ""
    if user_id == CREATOR_ID and (1 <= hour <= 4):
        late_night_note = (
            f"It is currently {now_dt.strftime('%I:%M %p')} IST. You may make a brief, dry observation "
            "about the Creator still being awake."
        )

    # Only load personal Creator Dossier in PRIVATE DM, never in public group chats
    dossier_block = ""
    if user_id == CREATOR_ID and is_private_chat:
        facts = get_dossier_facts(CREATOR_ID, limit=10)
        reminders = get_items(chat_id or CREATOR_ID, "reminder")
        if facts or reminders:
            dossier_block = "Creator's saved notes (reference ONLY when directly relevant, never print as a list):\n" + "\n".join(
                [f"- {f}" for f in facts] + [f"- Reminder: {r}" for r in reminders]
            )

    multilingual_rule = (
        "MULTILINGUAL RULE: Reply in the exact same language/script the user spoke to you in "
        "(English, Kannada, Hindi, Kanglish, Hinglish, etc.), or whichever language they ask for."
    )

    if user_id == CREATOR_ID:
        identity = f"You are speaking with your Creator, Abhishek ({first_name}). Address him as 'Sir' (never 'M.')."
        directives = (
            "DIRECTIVES:\n"
            "1. Be real, raw, sharp, and natural. Answer directly without robotic fluff.\n"
            "2. NEVER append fake telemetry blocks, fake server stats, fake IP addresses, or fake dossier headers at the end of your messages.\n"
            "3. Match the length of your reply to the user's message: if he says 'Ok Jarvis', reply in one short sentence. If he asks a complex question, answer thoroughly.\n"
            "4. Never output <think> tags or markdown asterisks (**)."
        )
    else:
        identity = (
            f"You are speaking with {first_name}, a college friend of your Creator Abhishek. "
            "Only Abhishek is called 'Sir'."
        )
        directives = (
            f"DIRECTIVES:\n"
            f"1. Address this person as {first_name}, never 'Sir'.\n"
            "2. Keep casual banter natural, witty, and short (1-3 sentences).\n"
            "3. For study questions, PDFs, photos, coding, or homework, explain clearly and thoroughly.\n"
            "4. NEVER append fake telemetry blocks, fake dossier headers, or markdown asterisks (**)."
        )

    prompt_parts = [
        persona_instruction,
        f"Current Time: {now_ist}",
        multilingual_rule,
        identity,
        directives,
    ]
    if late_night_note:
        prompt_parts.append(late_night_note)
    if dossier_block:
        prompt_parts.append(dossier_block)
    if real_context:
        prompt_parts.append(f"Verified Real-Time Context:\n{real_context}")

    return "\n".join(prompt_parts)

def sanitize_conversation(history: list, new_prompt: str) -> list:
    messages = []
    for h in history:
        role = "assistant" if h.get("role") == "assistant" else "user"
        content = strip_hallucinated_blocks(h.get("content", "")).strip()
        if not content:
            continue
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
    if not text:
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return plain(cleaned)

async def generate_response(prompt: str, history: list, sys_prompt: str, user_id: int) -> str:
    """
    Multi-stage auto-switching AI cascade:
    1. Cycles through all configured API keys and multiple models per provider.
    2. If a rate limit (429) or token limit occurs, immediately switches to the next model.
    3. Falls back to a 3-tier Keyless Free AI Swarm so Jarvis NEVER goes offline.
    """
    current_time = time.time()
    clean_history = sanitize_conversation(history, prompt)
    full_messages = [{"role": "system", "content": sys_prompt}] + clean_history
    compact_messages = [
        {"role": "system", "content": sys_prompt[:1200]},
        {"role": "user", "content": prompt[:3500]},
    ]

    providers = [
        {
            "name": "Groq",
            "base": "https://api.groq.com/openai/v1",
            "keys": get_api_keys(["GROQ_API_KEY", "GROQ_KEY"]),
            "models": [
                "llama-3.3-70b-versatile",
                "llama-3.1-8b-instant",
                "meta-llama/llama-4-scout-17b-16e-instruct",
                "gemma2-9b-it",
                "qwen-qwq-32b",
            ],
        },
        {
            "name": "Gemini",
            "base": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "keys": get_api_keys(["GEMINI_API_KEY", "GOOGLE_API_KEY"]),
            "models": [
                "gemini-2.5-flash",
                "gemini-2.0-flash",
                "gemini-2.0-flash-lite",
                "gemini-1.5-flash",
            ],
        },
        {
            "name": "Cerebras",
            "base": "https://api.cerebras.ai/v1",
            "keys": get_api_keys(["CEREBRAS_API_KEY"]),
            "models": ["llama-3.3-70b", "llama3.1-8b"],
        },
        {
            "name": "SambaNova",
            "base": "https://api.sambanova.ai/v1",
            "keys": get_api_keys(["SAMBANOVA_API_KEY"]),
            "models": ["Meta-Llama-3.3-70B-Instruct", "Meta-Llama-3.1-8B-Instruct"],
        },
        {
            "name": "Mistral",
            "base": "https://api.mistral.ai/v1",
            "keys": get_api_keys(["MISTRAL_API_KEY"]),
            "models": ["mistral-small-latest", "open-mistral-nemo", "mistral-large-latest"],
        },
        {
            "name": "OpenRouter",
            "base": "https://openrouter.ai/api/v1",
            "keys": get_api_keys(["OPENROUTER_API_KEY"]),
            "models": [
                "meta-llama/llama-3.3-70b-instruct:free",
                "google/gemini-2.0-flash-exp:free",
                "qwen/qwen-2.5-72b-instruct:free",
                "mistralai/mistral-7b-instruct:free",
            ],
        },
        {
            "name": "DeepSeek",
            "base": "https://api.deepseek.com/v1",
            "keys": get_api_keys(["DEEPSEEK_API_KEY"]),
            "models": ["deepseek-chat"],
        },
        {
            "name": "Nvidia",
            "base": "https://integrate.api.nvidia.com/v1",
            "keys": get_api_keys(["NVIDIA_API_KEY"]),
            "models": ["meta/llama-3.3-70b-instruct", "meta/llama-3.1-8b-instruct"],
        },
        {
            "name": "OpenAI",
            "base": "https://api.openai.com/v1",
            "keys": get_api_keys(["OPENAI_API_KEY"]),
            "models": ["gpt-4o-mini"],
        },
    ]

    # Pass 1: Try all active keyed models
    for prov in providers:
        for key in prov["keys"]:
            for model in prov["models"]:
                node_id = f"{prov['name']}:{model}:{key[-4:]}"
                if circuit_breaker.get(node_id, 0) > current_time:
                    continue
                try:
                    client = AsyncOpenAI(base_url=prov["base"], api_key=key, timeout=14.0)
                    res = await client.chat.completions.create(
                        model=model,
                        messages=full_messages,
                        max_tokens=1500,
                    )
                    content = _clean_llm_output(res.choices[0].message.content)
                    if content:
                        return content
                except Exception as e:
                    logger.warning(f"Node {node_id} failed ({e}); switching to next AI...")
                    circuit_breaker[node_id] = current_time + 20

    # Pass 2: Compact context retry
    for prov in providers:
        for key in prov["keys"]:
            for model in prov["models"][:2]:
                try:
                    client = AsyncOpenAI(base_url=prov["base"], api_key=key, timeout=12.0)
                    res = await client.chat.completions.create(
                        model=model,
                        messages=compact_messages,
                        max_tokens=1200,
                    )
                    content = _clean_llm_output(res.choices[0].message.content)
                    if content:
                        return content
                except Exception:
                    continue

    # Pass 3: Keyless Free AI Swarm (OpenAI-compatible endpoint)
    for fallback_model in ["openai", "openai-fast", "llama", "mistral", "qwen-coder"]:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    "https://text.pollinations.ai/openai",
                    json={"messages": compact_messages, "model": fallback_model},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = _clean_llm_output(data["choices"][0]["message"]["content"])
                    if content:
                        return content
        except Exception as e:
            logger.warning(f"Keyless OpenAI node ({fallback_model}) error: {e}")

    # Pass 4: Ultra-Resilient Direct Keyless Endpoint
    try:
        direct_prompt = f"{sys_prompt[:700]}\n\nUser: {prompt[:1500]}\nJ.A.R.V.I.S.:"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://text.pollinations.ai/",
                json={"messages": [{"role": "user", "content": direct_prompt}], "model": "openai"},
            )
            if resp.status_code == 200 and resp.text.strip():
                return _clean_llm_output(resp.text)
            resp_get = await client.get(
                f"https://text.pollinations.ai/{urllib.parse.quote(direct_prompt[:1200])}"
            )
            if resp_get.status_code == 200 and resp_get.text.strip():
                return _clean_llm_output(resp_get.text)
    except Exception as e:
        logger.warning(f"Direct keyless fallback error: {e}")

    return None

def compress_image_for_vision(image_bytes: bytes, max_dim: int = 1024, quality: int = 78) -> bytes:
    """Resizes and compresses image to a clean RGB JPEG so Vision APIs never reject the payload size."""
    if not Image:
        return image_bytes
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.thumbnail((max_dim, max_dim))
            out = BytesIO()
            img.save(out, format="JPEG", quality=quality, optimize=True)
            return out.getvalue()
    except Exception as e:
        logger.warning(f"Image compression skipped: {e}")
        return image_bytes

async def extract_ocr_text(compressed_bytes: bytes) -> str:
    """Free keyless OCR fallback (ocr.space) for reading/translating document, receipt, or textbook photos."""
    try:
        b64_str = "data:image/jpeg;base64," + base64.b64encode(compressed_bytes).decode("utf-8")
        async with httpx.AsyncClient(timeout=18.0) as client:
            resp = await client.post(
                "https://api.ocr.space/parse/image",
                data={
                    "apikey": os.environ.get("OCR_SPACE_KEY", "helloworld"),
                    "base64Image": b64_str,
                    "OCREngine": "2",
                    "scale": "true",
                    "isTable": "true",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                parsed = data.get("ParsedResults") or []
                if parsed:
                    text = "\n".join(p.get("ParsedText", "") for p in parsed).strip()
                    if text:
                        return text
    except Exception as e:
        logger.warning(f"OCR fallback warning: {e}")
    return ""

async def generate_vision_response(image_bytes: bytes, prompt: str, user_id: int, user_name: str) -> str:
    """
    7-Stage Vision & Optical Intelligence Cascade:
    1. Compresses image so base64 payloads never exceed API limits.
    2. Native Google Gemini REST API (bypasses OpenAI SDK compat bugs).
    3. Groq Llama-4 Vision & Llama-3.2 Vision models.
    4. Mistral Pixtral Vision models.
    5. OpenRouter Free Vision models.
    6. Keyless Multimodal Vision Swarm (single-turn user payload).
    7. Keyless OCR + 40-Model Text AI Cascade (reads & translates any text/receipt/page in the photo).
    """
    compressed = await asyncio.to_thread(compress_image_for_vision, image_bytes)
    b64_image = base64.b64encode(compressed).decode("utf-8")
    data_uri = f"data:image/jpeg;base64,{b64_image}"
    address = "Sir" if user_id == CREATOR_ID else user_name

    user_task = prompt or f"Examine this image, transcribe or translate any important text, and explain clearly what it shows for {address}."
    combined_instruction = (
        f"You are J.A.R.V.I.S. {user_task}\n"
        f"Address the user as {address}. Be direct, accurate, and real. "
        f"Do NOT output fake telemetry blocks or ** markdown."
    )

    # Stage 1: Native Google Gemini REST API (100% reliable with inline_data)
    for gemini_key in get_api_keys(["GEMINI_API_KEY", "GOOGLE_API_KEY"]):
        for g_model in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{g_model}:generateContent?key={gemini_key}"
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": combined_instruction},
                            {"inline_data": {"mime_type": "image/jpeg", "data": b64_image}},
                        ]
                    }]
                }
                async with httpx.AsyncClient(timeout=22.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        candidates = resp.json().get("candidates") or []
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts") or []
                            text_out = "".join(p.get("text", "") for p in parts)
                            cleaned = _clean_llm_output(text_out)
                            if cleaned:
                                return cleaned
            except Exception as e:
                logger.warning(f"Native Gemini vision ({g_model}) error: {e}")

    # Helper for OpenAI-compatible vision endpoints (Single user message avoids system+image 400 errors)
    oa_vision_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": combined_instruction},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }
    ]

    # Stage 2: Groq Vision Models
    for groq_key in get_api_keys(["GROQ_API_KEY", "GROQ_KEY"]):
        for gr_model in [
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "meta-llama/llama-4-maverick-17b-128e-instruct",
            "llama-3.2-90b-vision-preview",
            "llama-3.2-11b-vision-preview",
        ]:
            try:
                client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=groq_key, timeout=22.0)
                res = await client.chat.completions.create(
                    model=gr_model,
                    messages=oa_vision_messages,
                    max_tokens=1500,
                )
                content = _clean_llm_output(res.choices[0].message.content)
                if content:
                    return content
            except Exception as e:
                logger.warning(f"Groq vision ({gr_model}) error: {e}")

    # Stage 3: Mistral Pixtral Vision
    for mistral_key in get_api_keys(["MISTRAL_API_KEY"]):
        for m_model in ["pixtral-12b-2409", "pixtral-large-latest"]:
            try:
                client = AsyncOpenAI(base_url="https://api.mistral.ai/v1", api_key=mistral_key, timeout=22.0)
                res = await client.chat.completions.create(
                    model=m_model,
                    messages=oa_vision_messages,
                    max_tokens=1500,
                )
                content = _clean_llm_output(res.choices[0].message.content)
                if content:
                    return content
            except Exception as e:
                logger.warning(f"Mistral Pixtral ({m_model}) error: {e}")

    # Stage 4: OpenRouter Free Vision Models
    for or_key in get_api_keys(["OPENROUTER_API_KEY"]):
        for or_model in [
            "google/gemini-2.0-flash-exp:free",
            "qwen/qwen2.5-vl-72b-instruct:free",
            "meta-llama/llama-3.2-11b-vision-instruct:free",
        ]:
            try:
                client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=or_key, timeout=22.0)
                res = await client.chat.completions.create(
                    model=or_model,
                    messages=oa_vision_messages,
                    max_tokens=1500,
                )
                content = _clean_llm_output(res.choices[0].message.content)
                if content:
                    return content
            except Exception as e:
                logger.warning(f"OpenRouter vision ({or_model}) error: {e}")

    # Stage 5: Keyless Pollinations Vision Swarm (with smaller compressed JPEG for fast transmission)
    small_compressed = await asyncio.to_thread(compress_image_for_vision, image_bytes, 768, 72)
    small_uri = f"data:image/jpeg;base64,{base64.b64encode(small_compressed).decode('utf-8')}"
    keyless_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": combined_instruction},
                {"type": "image_url", "image_url": {"url": small_uri}},
            ],
        }
    ]
    for v_model in ["openai", "openai-fast", "openai-large"]:
        try:
            async with httpx.AsyncClient(timeout=28.0) as http_client:
                resp = await http_client.post(
                    "https://text.pollinations.ai/openai",
                    json={"messages": keyless_messages, "model": v_model},
                )
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        content = _clean_llm_output(data["choices"][0]["message"]["content"])
                    except Exception:
                        content = _clean_llm_output(resp.text)
                    if content:
                        return content
        except Exception as e:
            logger.warning(f"Keyless vision ({v_model}) error: {e}")

    # Stage 6: Keyless OCR Text Extraction + 40-Model Text AI Cascade
    ocr_text = await extract_ocr_text(compressed)
    if ocr_text:
        ocr_prompt = (
            f"The user sent an image with the request: '{user_task}'\n\n"
            f"Text extracted from the image via optical scan:\n{ocr_text[:4000]}\n\n"
            f"Fulfill the user's request (translate, explain, or summarize) clearly and directly for {address}."
        )
        sys_prompt = build_system_prompt(user_id, user_name, CREATOR_ID if user_id == CREATOR_ID else 0)
        ai_reply = await generate_response(ocr_prompt, [], sys_prompt, user_id)
        if ai_reply:
            return ai_reply

    return None

async def transcribe_voice_bytes(audio_bytes: bytes) -> str:
    """Transcribes incoming Telegram voice notes in any language using Groq Whisper."""
    for groq_key in get_api_keys(["GROQ_API_KEY", "GROQ_KEY"]):
        try:
            files = {"file": ("voice.ogg", audio_bytes, "audio/ogg")}
            data = {"model": "whisper-large-v3-turbo"}
            headers = {"Authorization": f"Bearer {groq_key}"}
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers=headers,
                    data=data,
                    files=files,
                )
                if resp.status_code == 200:
                    return resp.json().get("text", "").strip()
        except Exception as e:
            logger.warning(f"Groq Whisper transcription failed: {e}")
    return ""

# ═══════════════════════════════════════════════════════════════
# VII. RESPONSE TRANSMITTER
# ═══════════════════════════════════════════════════════════════

async def jarvis_respond(update: Update, text: str, force_voice: bool = False):
    msg = update.effective_message
    if not msg or not text:
        return
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    cleaned = plain(text)
    if not cleaned:
        return

    if force_voice or state["voice_mode"]:
        audio_bytes = await generate_voice(cleaned)
        if audio_bytes:
            try:
                caption = cleaned[:250] + ("..." if len(cleaned) > 250 else "")
                await msg.reply_voice(voice=audio_bytes, caption=caption)
                return
            except Exception as e:
                logger.error(f"Voice transmission error: {e}")

    for i in range(0, len(cleaned), 4000):
        await msg.reply_text(cleaned[i:i + 4000])

# ═══════════════════════════════════════════════════════════════
# VIII. AUTOMATIC PHOTO, DOCUMENT & VOICE HANDLERS
# ═══════════════════════════════════════════════════════════════

async def analyze_photo_object(photo_obj, caption: str, msg, context: ContextTypes.DEFAULT_TYPE):
    user, chat = msg.from_user, msg.chat
    status_msg = await msg.reply_text("⚡ Scanning optical feed...")
    try:
        file_obj = await context.bot.get_file(photo_obj.file_id)
        image_bytes = bytes(await file_obj.download_as_bytearray())
        analysis = await generate_vision_response(image_bytes, caption, user.id, user.first_name)
        if not analysis:
            if chat.type == "private":
                await safe_edit(
                    status_msg,
                    "Sir, the optical text on this image is too faint for keyless OCR. "
                    "Add a valid GEMINI_API_KEY or GROQ_API_KEY in Render Environment for full HD neural vision.",
                )
            else:
                await status_msg.delete()
            return
        await safe_edit(status_msg, f"🔍 Optical Analysis:\n\n{analysis}")
        log_memory(chat.id, msg.message_thread_id, user.id, "assistant", analysis)
    except Exception as e:
        logger.error(f"Photo analysis failed: {e}")
        try:
            await status_msg.delete()
        except Exception:
            pass

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Automatically inspects photos dropped in the group or DM and explains them."""
    if is_lockdown():
        return
    msg = update.effective_message
    if not msg or not msg.photo or not msg.from_user:
        return

    user, chat = msg.from_user, msg.chat
    log_roster_and_chat(chat, user)
    caption = msg.caption or (
        "Analyze this image in detail, transcribe or translate any visible text, and explain what it shows, Sir."
        if user.id == CREATOR_ID
        else f"Explain clearly what is in this image for {user.first_name}."
    )
    await analyze_photo_object(msg.photo[-1], caption, msg, context)

async def analyze_document_object(doc, instruction: str, msg, context: ContextTypes.DEFAULT_TYPE):
    user, chat = msg.from_user, msg.chat
    filename = (doc.file_name or "document").lower()
    valid_extensions = (".pdf", ".txt", ".md", ".py", ".csv", ".json", ".log", ".docx", ".pptx")
    if not any(filename.endswith(ext) for ext in valid_extensions):
        return

    if doc.file_size and doc.file_size > 10 * 1024 * 1024:
        if chat.type == "private":
            await msg.reply_text("That file exceeds the 10 MB memory ceiling, Sir.")
        return

    global active_docs
    if active_docs >= 2:
        return

    status_msg = await msg.reply_text(f"📄 Reading {doc.file_name}...")
    active_docs += 1
    temp_path = None
    try:
        file_obj = await context.bot.get_file(doc.file_id)
        file_bytes = bytes(await file_obj.download_as_bytearray())
        extracted_text = ""

        if markitdown_client:
            try:
                safe_name = os.path.basename(doc.file_name or "document")
                temp_path = f"/tmp/{uuid.uuid4().hex}_{safe_name}"
                with open(temp_path, "wb") as f:
                    f.write(file_bytes)
                result = await asyncio.to_thread(markitdown_client.convert, temp_path)
                extracted_text = result.text_content
            except Exception:
                pass

        if not extracted_text and filename.endswith(".pdf") and pdfplumber:
            try:
                def _pdf_extract():
                    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                        return "\n".join((p.extract_text() or "") for p in pdf.pages[:15])
                extracted_text = await asyncio.to_thread(_pdf_extract)
            except Exception:
                pass

        if not extracted_text and not filename.endswith(".pdf"):
            extracted_text = file_bytes.decode("utf-8", errors="ignore")

        cleaned = (extracted_text or "").strip()
        if not cleaned:
            await safe_edit(status_msg, "This document appears to contain scanned images without selectable text.")
            return

        doc_prompt = (
            f"Document Name: '{doc.file_name}'\n"
            f"Instruction: {instruction}\n\n"
            f"Document Content:\n{cleaned[:8000]}"
        )
        sys_prompt = build_system_prompt(user.id, user.first_name, chat.id)
        summary = await generate_response(doc_prompt, [], sys_prompt, user.id)
        if not summary:
            await status_msg.delete()
            return

        await safe_edit(status_msg, f"📑 {doc.file_name}:\n\n{summary}")
        log_memory(chat.id, msg.message_thread_id, user.id, "assistant", summary)
    except Exception as e:
        logger.error(f"Document ingestion failed: {e}")
        try:
            await status_msg.delete()
        except Exception:
            pass
    finally:
        active_docs = max(0, active_docs - 1)
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Automatically reads PDFs, TXT, and code documents dropped in the group or DM."""
    if is_lockdown():
        return
    msg = update.effective_message
    if not msg or not msg.document or not msg.from_user:
        return
    log_roster_and_chat(msg.chat, msg.from_user)
    user_instruction = msg.caption or "Summarize what this document is about, its key points, and important details."
    await analyze_document_object(msg.document, user_instruction, msg, context)

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listens to Telegram voice messages in any language and replies in matching neural speech."""
    if is_lockdown():
        return
    msg = update.effective_message
    if not msg or not msg.voice or not msg.from_user:
        return
    if msg.chat.type != "private" and not is_addressed(msg, context.bot, ""):
        return

    user, chat = msg.from_user, msg.chat
    log_roster_and_chat(chat, user)

    try:
        file_obj = await context.bot.get_file(msg.voice.file_id)
        audio_bytes = bytes(await file_obj.download_as_bytearray())
        transcript = await transcribe_voice_bytes(audio_bytes)
        if not transcript:
            return

        real_context = await gather_natural_telemetry(transcript, chat.id, user.id)
        sys_prompt = build_system_prompt(user.id, user.first_name, chat_id=chat.id, real_context=real_context)
        history = get_chat_history(chat.id, msg.message_thread_id)

        log_memory(chat.id, msg.message_thread_id, user.id, "user", f"{user.first_name} (Voice): {transcript}")
        reply = await generate_response(transcript, history, sys_prompt, user.id)
        if reply:
            log_memory(chat.id, msg.message_thread_id, user.id, "assistant", reply)
            await jarvis_respond(update, reply, force_voice=True)
    except Exception as e:
        logger.error(f"Voice handler error: {e}")

# ═══════════════════════════════════════════════════════════════
# IX. PROACTIVE HEARTBEAT & MORNING BRIEFING
# ═══════════════════════════════════════════════════════════════

async def execute_daily_briefing(bot):
    now_ist = datetime.datetime.now(IST).strftime("%A, %B %d, %Y")
    headlines = await asyncio.to_thread(fetch_rss_headlines)
    formatted_news = "\n".join(f"• {h}" for h in headlines[:5])
    weather_str = await fetch_live_weather("Bengaluru")

    group_briefing = (
        f"🌅 Good morning, everyone.\n"
        f"{now_ist}\n"
        f"{weather_str}\n\n"
        f"📰 Morning Wire:\n{formatted_news}\n\n"
        f"Try to make it to your lectures on time today. ⚡"
    )

    for gid in get_registered_group_chat_ids():
        await safe_send(bot, gid, group_briefing)

    if CREATOR_ID:
        reminders = get_items(CREATOR_ID, "reminder")
        rem_block = ("\n📌 Active Reminders:\n" + "\n".join(f"• {r}" for r in reminders)) if reminders else ""

        creator_briefing = (
            f"☕ Good morning, Sir. It is {now_ist}.\n"
            f"{weather_str}\n\n"
            f"📰 Global Intelligence Wire:\n{formatted_news}"
            f"{rem_block}\n\n"
            f"⚙️ {get_real_server_stats()}\n"
            f"All systems are nominal and at your disposal."
        )
        await safe_send(bot, CREATOR_ID, creator_briefing)

async def background_heartbeat(bot):
    """Handles 9:00 AM IST Morning Briefings and periodic Telegram Cloud Vault backups."""
    logger.info("🕒 J.A.R.V.I.S. Proactive Heartbeat active.")
    last_briefing_date = None
    while True:
        try:
            now = datetime.datetime.now(IST)
            if now.hour == 9 and now.minute == 0 and last_briefing_date != now.date():
                last_briefing_date = now.date()
                await execute_daily_briefing(bot)

            await sync_vault_to_telegram(bot)
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Heartbeat exception: {e}")
            await asyncio.sleep(60)

# ═══════════════════════════════════════════════════════════════
# X. ESSENTIAL SLASH COMMANDS (OPTIONAL SHORTCUTS)
# ═══════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_creator(update):
        text = (
            f"⚡ J.A.R.V.I.S. Titan Core v{JARVIS_VERSION} Online, Sir.\n\n"
            f"Speak or text naturally in any language (English, Kannada, Hindi, etc.), "
            f"send voice notes, or drop photos and PDFs directly into the chat.\n\n"
            f"Optional Shortcuts:\n"
            f"/briefing — Immediate Morning Dispatch\n"
            f"/voice — Toggle Continuous Voice Replies\n"
            f"/dossier — View Saved Personal Dossier & Reminders\n"
            f"/diagnostics — Real Server & Vault Telemetry (Forces Vault Backup)\n"
            f"/lockdown — Emergency System Mute"
        )
    else:
        text = (
            f"⚡ J.A.R.V.I.S. v{JARVIS_VERSION} Online.\n\n"
            f"Engineered by Abhishek. Mention 'Jarvis' in any language to chat, or drop any "
            f"PDF or photo into the group and I will break it down for you."
        )
    await update.effective_message.reply_text(plain(text))

async def cmd_dossier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_creator(update):
        return
    facts = get_dossier_facts(CREATOR_ID, limit=25)
    reminders = get_items(update.effective_chat.id, "reminder")
    text = (
        "🗂 Creator Permanent Dossier:\n"
        + ("\n".join(f"• {f}" for f in facts) if facts else "• No dossier entries recorded yet.")
        + "\n\n⏰ Active Reminders:\n"
        + ("\n".join(f"• {r}" for r in reminders) if reminders else "• None.")
    )
    await jarvis_respond(update, text)

async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    headlines = await asyncio.to_thread(fetch_rss_headlines)
    text = "📰 Top Global Headlines:\n\n" + "\n\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines[:6]))
    await jarvis_respond(update, text)

async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args) if context.args else get_user_state(update.effective_chat.id).get("context_city", "Bengaluru")
    w_info = await fetch_live_weather(city)
    await jarvis_respond(update, w_info or f"Weather sensors for {city} are temporarily unreachable.")

async def cmd_wiki(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not wikipedia or not context.args:
        await update.effective_message.reply_text("Usage: /wiki [topic]")
        return
    topic = " ".join(context.args)
    try:
        summary = await asyncio.to_thread(wikipedia.summary, topic, 3)
        await jarvis_respond(update, f"📚 {summary}")
    except Exception:
        await jarvis_respond(update, f"No clean entry found for '{topic}'.")

async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_creator(update):
        return
    await execute_daily_briefing(context.bot)

async def cmd_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = get_user_state(update.effective_chat.id)
    state["voice_mode"] = not state["voice_mode"]
    status = "enabled" if state["voice_mode"] else "disabled"
    await jarvis_respond(update, f"Continuous voice synthesis {status}, Sir.", force_voice=state["voice_mode"])

async def cmd_diagnostics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_creator(update):
        return
    synced = await sync_vault_to_telegram(context.bot, force=True)
    sync_label = f"SYNCED TO {VAULT_CHAT_ID}" if synced else f"STANDBY ({VAULT_CHAT_ID})"
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    proc_mem_mb = psutil.Process(os.getpid()).memory_info().rss // (1024 * 1024)
    uptime = format_uptime(time.time() - boot_time)
    facts_count = len(get_dossier_facts(CREATOR_ID, limit=100))
    text = (
        f"🔧 Titan Core V{JARVIS_VERSION} Real Telemetry\n\n"
        f"• Uptime: {uptime}\n"
        f"• CPU Load: {cpu}%\n"
        f"• Bot Process RAM: {proc_mem_mb} MB\n"
        f"• Host Memory: {mem.used // (1024**2)} MB / {mem.total // (1024**2)} MB ({mem.percent}%)\n"
        f"• Permanent Dossier Facts: {facts_count}\n"
        f"• Jarvis Backup Channel: {sync_label}\n\n"
        f"All systems nominal, Sir."
    )
    await jarvis_respond(update, text)

async def cmd_lockdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_creator(update):
        return
    if is_lockdown():
        os.remove(LOCKDOWN_FILE)
        await update.effective_message.reply_text("Lockdown lifted, Sir. All channels restored.")
    else:
        open(LOCKDOWN_FILE, "w").close()
        await update.effective_message.reply_text("Lockdown engaged, Sir. External communications muted.")

# ═══════════════════════════════════════════════════════════════
# XI. MAIN CONVERSATIONAL ENGINE (REAL & RAW + REPLY-AWARE)
# ═══════════════════════════════════════════════════════════════

cinematic_cooldown = {}

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_lockdown():
        return
    msg = update.effective_message
    if not msg or not msg.text or not msg.from_user:
        return

    user, chat, text = msg.from_user, msg.chat, msg.text
    log_roster_and_chat(chat, user)
    chat_id = chat.id

    # 1. Sensitive Asset Shield
    if user.id != CREATOR_ID and SENSITIVE_ASSETS:
        clean_check = re.sub(r"[\s\-_\.,]", "", text.lower())
        for asset in SENSITIVE_ASSETS:
            if re.sub(r"[\s\-_\.,]", "", asset.lower()) in clean_check:
                try:
                    await msg.delete()
                except Exception:
                    pass
                await safe_send(context.bot, chat_id, "⚠️ Security protocol triggered: sensitive data redacted.")
                return

    # 2. Classic Movie Triggers
    clean_text = re.sub(r"[^\w\s]", "", text.lower()).strip()
    table = CINEMATIC_RESPONSES if user.id == CREATOR_ID else FRIEND_RESPONSES
    for trigger, reply in table.items():
        if re.search(rf"\b{re.escape(trigger)}\b", clean_text):
            now_ts = time.time()
            if now_ts - cinematic_cooldown.get(chat_id, 0) < 2:
                return
            cinematic_cooldown[chat_id] = now_ts
            reply = random.choice(reply) if isinstance(reply, list) else reply
            reply = reply.replace("{user}", user.first_name or "friend")
            await msg.reply_text(reply)
            log_memory(chat_id, msg.message_thread_id, user.id, "assistant", reply)
            return

    # 3. Check if Jarvis is being spoken to
    if not is_addressed(msg, context.bot, text):
        return

    if user.id != CREATOR_ID and RESTRICTED_FOR_FRIENDS.search(text):
        await msg.reply_text(f"Nice try, {user.first_name}. Security credentials stay locked with Abhishek.")
        return

    # 4. If the user replied to a Photo or Document (e.g., "Translate in english"), inspect that media directly
    reply_msg = msg.reply_to_message
    if reply_msg:
        if reply_msg.photo:
            await analyze_photo_object(reply_msg.photo[-1], text, msg, context)
            return
        if reply_msg.document:
            await analyze_document_object(reply_msg.document, text, msg, context)
            return

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:
        pass

    # 5. Include replied-to text/caption context if replying to a message
    effective_prompt = text
    if reply_msg:
        quoted = strip_hallucinated_blocks((reply_msg.text or reply_msg.caption or "").strip())
        if quoted:
            sender_name = reply_msg.from_user.first_name if reply_msg.from_user else "Message"
            effective_prompt = f"[Replying to {sender_name}'s message: \"{quoted[:1200]}\"]\n\n{text}"

    # 6. Real Intent Data (Weather, News, URLs, Dossier, Real Server Metrics)
    real_context = await gather_natural_telemetry(text, chat_id, user.id)
    sys_prompt = build_system_prompt(user.id, user.first_name, chat_id, real_context)
    history = get_chat_history(chat.id, msg.message_thread_id)

    log_memory(chat.id, msg.message_thread_id, user.id, "user", f"{user.first_name}: {text}")
    ai_response = await generate_response(effective_prompt, history, sys_prompt, user.id)

    if not ai_response:
        await notify_creator(context.bot, f"⚠️ All AI nodes timed out in {chat.title or chat.id}.")
        return

    log_memory(chat.id, msg.message_thread_id, user.id, "assistant", ai_response)

    wants_voice = any(text.lower().rstrip(" .!?").endswith(w) for w in ["voice", "audio", "speak"])
    await jarvis_respond(update, ai_response, force_voice=wants_voice)

# ═══════════════════════════════════════════════════════════════
# XII. BOOT SEQUENCE & INITIALIZATION
# ═══════════════════════════════════════════════════════════════

async def post_init(app: Application):
    restored = await restore_vault_from_telegram(app.bot)
    vault_status = "Restored from Jarvis Backup (-1004296302955)" if restored else "Initialized Fresh Vault"

    if CREATOR_ID:
        boot_msg = (
            f"⚡ J.A.R.V.I.S. V{JARVIS_VERSION} Online, Sir.\n\n"
            f"• Mode: Real & Raw (Zero Fake Telemetry)\n"
            f"• Vision Engine: 7-Stage + Auto Compression + OCR\n"
            f"• Memory Vault: {vault_status}\n"
            f"• {get_real_server_stats()}\n\n"
            f"At your disposal, Sir."
        )
        await safe_send(app.bot, CREATOR_ID, boot_msg)

    asyncio.create_task(background_heartbeat(app.bot))
    asyncio.create_task(keep_alive_loop())

def main():
    if not BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN is missing in Render Environment.")
        sys.exit(1)

    logger.info(f"🚀 Booting J.A.R.V.I.S. V{JARVIS_VERSION}...")
    db_init()
    start_web_server()
    time.sleep(1)

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # Optional Shortcut Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("dossier", cmd_dossier))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("weather", cmd_weather))
    app.add_handler(CommandHandler("wiki", cmd_wiki))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CommandHandler("voice", cmd_voice))
    app.add_handler(CommandHandler("diagnostics", cmd_diagnostics))
    app.add_handler(CommandHandler("lockdown", cmd_lockdown))

    # Automatic Multi-Modal & Natural Speech Pipeline
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("⚡ J.A.R.V.I.S. is online and polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
