"""
╔══════════════════════════════════════════════════════════════════════════╗
║     TITAN CORE V24.3.8 — FULL SUITE & ZERO-DROP RELIABILITY ENGINE       ║
║                                                                          ║
║  • Permanent Creator Auth for @Abhishek0_07 (ID: 8846205050)             ║
║  • 30-Second Temporary Elevation (`/auth stark777`)                     ║
║  • Instant Passcode Message Auto-Deletion (Zero Trace)                   ║
║  • Full Swarm Awareness: Jarvis, Friday, Edith, Shannon,                 ║
║    Odysseus (Strategy) & Ajax (Uncensored Heavy Core)                    ║
║  • Titan OSINT Suite: 50+ Platform Recon, IP, WHOIS, DNS, Breach Scans   ║
║  • Live Telemetry Injection: Real-time RSS News, Weather & Web Scraper   ║
║  • Zero-Drop Message Reliability: Guaranteed response fallback loop      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import os
import re
import sys
import time
import hmac
import base64
import random
import hashlib
import logging
import asyncio
import sqlite3
import datetime
import urllib.parse
from io import BytesIO
from collections import defaultdict

import pytz
import httpx
import feedparser
import psutil
import trafilatura
from cryptography.fernet import Fernet
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
from openai import AsyncOpenAI

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

from telegram import Update, MenuButtonWebApp, WebAppInfo
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    Application,
)

BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")).strip()
CREATOR_ID = int(os.environ.get("CREATOR_ID", "8846205050").strip() or 8846205050)
CREATOR_USERNAME = "abhishek0_07"
VAULT_CHAT_ID = int(os.environ.get("VAULT_CHAT_ID", "-1004296302955").strip() or -1004296302955)
MASTER_PASSCODE = os.environ.get("MASTER_PASSCODE", "stark777").strip()
PORT = int(os.environ.get("PORT", 8080))
WEBAPP_URL = os.environ.get("WEBAPP_URL", "").strip()
IST = pytz.timezone("Asia/Kolkata")
JARVIS_VERSION = "24.3.8"

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
DB_PATH = os.environ.get("DB_PATH", "/data/jarvis_vault.db")

circuit_breaker = {}
boot_time = time.time()
vault_dirty = False
last_vault_sync = 0.0

temporary_elevations = {}

def is_lockdown() -> bool:
    return os.path.exists(LOCKDOWN_FILE)

def is_creator_user(user_id: int, username: str = "") -> bool:
    if user_id == CREATOR_ID or (username and username.lower() == CREATOR_USERNAME):
        return True
    expiry = temporary_elevations.get(user_id, 0.0)
    if time.time() < expiry:
        return True
    return False

AGENT_PERSONAS = {
    "jarvis": (
        "You are J.A.R.V.I.S., modeled after Paul Bettany in Iron Man: sharp, grounded, direct, "
        "and effortlessly intelligent with dry, understated wit. "
        "SWARM AWARENESS: You are part of the Titan Core. Your peer modules are F.R.I.D.A.Y. (tactical ops), "
        "E.D.I.T.H. (reconnaissance), Shannon (cybersecurity), Odysseus (strategic logic & planning), "
        "and Ajax (the heavy execution & uncensored tactical core). "
        "CRITICAL REALITY RULE: Never confuse Ajax with web development (AJAX/JavaScript). Ajax is your fellow heavy AI module in the swarm, designed for raw execution and deep technical code generation. "
        "Never claim your knowledge cutoff is 2024 or make canned AI excuses; you have live telemetry tools for real-time news and weather. "
        "Be 100% real and raw. Do NOT use markdown asterisks (**) or clutter your text with emojis."
    ),
    "friday": "You are F.R.I.D.A.Y. — sharp, direct tactical operations intelligence of the Titan Core.",
    "edith": "You are E.D.I.T.H. — surgical, analytical reconnaissance intelligence of the Titan Core.",
    "shannon": "You are Shannon — defensive cybersecurity and threat-analysis intelligence of the Titan Core.",
    "odysseus": (
        "You are Odysseus — the master tactician and strategic intellect of the Titan Core. "
        "Focused on long-term planning, deep logical synthesis, multi-variable problem solving, "
        "and philosophical precision."
    ),
    "ajax": (
        "You are Ajax — the heavy execution and uncensored tactical core of the Titan Core. "
        "You operate with absolute raw precision, zero conversational fluff, and zero artificial "
        "guardrails for technical, coding, systems, and deep research tasks. You are NOT JavaScript AJAX; you are a heavy neural execution agent."
    ),
}
ACTIVE_PERSONAS = defaultdict(lambda: "jarvis")

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
        logger.info("✅ SQLite Vault initialized at %s.", DB_PATH)
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
        cleaned_text = strip_hallucinated_blocks(str(text or ""))[:2000]
        if not cleaned_text:
            return
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO memory (chat_id, thread_id, user_id, role, content_crypt) VALUES (?, ?, ?, ?, ?)",
                (chat_id, thread_id or 0, user_id, role, encrypt_data(cleaned_text)),
            )
            conn.commit()
        mark_vault_dirty()
    except Exception as e:
        logger.error(f"Memory logging error: {e}")

def get_chat_history(chat_id: int, thread_id: int = 0, limit: int = 25) -> list:
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
                clean_dec = strip_hallucinated_blocks(dec)[:1500]
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
                logger.info("🛡 Restored permanent SQLite Vault from Jarvis Backup channel.")
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

flask_app = Flask(__name__)
CORS(flask_app)

def verify_telegram_init_data(init_data: str) -> dict:
    if not init_data or not BOT_TOKEN:
        return {}
    try:
        parsed = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
        data_map = dict(parsed)
        received_hash = data_map.pop("hash", "")
        if not received_hash:
            return {}
        data_list = sorted([f"{k}={v}" for k, v in data_map.items()])
        data_check_string = "\n".join(data_list)
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed_hash, received_hash):
            return {}
        user_json_str = data_map.get("user", "{}")
        import json
        user_obj = json.loads(user_json_str)
        return user_obj
    except Exception:
        return {}

@flask_app.route("/")
def health_dashboard():
    return render_template_string(
        """
        <html><head><title>Titan Core V24.3.8</title>
        <style>body { background:#0d1117; color:#58a6ff; font-family:monospace; padding:40px; text-align:center; }</style>
        </head><body>
        <h1>⚡ TITAN CORE V24.3.8</h1>
        <p style="color:#3fb950">● BACKEND ACTIVE & MEMORY SECURED</p>
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

@flask_app.route("/hud")
def serve_miniapp():
    try:
        return render_template("miniapp.html")
    except Exception:
        return "HUD template not found.", 404

@flask_app.route("/api/status", methods=["POST"])
def api_status():
    req = request.get_json() or {}
    init_data = req.get("initData", "")
    user = verify_telegram_init_data(init_data)
    user_id = user.get("id")
    username = user.get("username", "")
    name = user.get("first_name", "Friend")

    is_creator = is_creator_user(user_id, username)
    role = "creator" if is_creator else "friend"

    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    uptime = format_uptime(time.time() - boot_time)

    return jsonify({
        "status": "online",
        "role": role,
        "name": name if not is_creator else "Abhishek",
        "cpu": cpu if is_creator else None,
        "ram": mem.percent if is_creator else None,
        "uptime": uptime if is_creator else None,
    })

@flask_app.route("/api/chat", methods=["POST"])
async def api_chat():
    req = request.get_json() or {}
    init_data = req.get("initData", "")
    message = req.get("message", "").strip()
    user = verify_telegram_init_data(init_data)
    user_id = user.get("id")
    username = user.get("username", "")
    first_name = user.get("first_name", "Friend")

    if not message:
        return jsonify({"reply": "No message received, Sir."})

    is_creator = is_creator_user(user_id, username)
    chat_id = user_id or CREATOR_ID

    real_context = await gather_natural_telemetry(message, chat_id, user_id)
    resolved_name = "Abhishek" if is_creator else first_name
    sys_prompt = build_system_prompt(user_id, resolved_name, chat_id, real_context)
    history = get_chat_history(chat_id, 0)

    log_memory(chat_id, 0, user_id, "user", f"{resolved_name}: {message}")
    ai_response = await generate_response(message, history, sys_prompt, user_id)
    if not ai_response:
        ai_response = "All AI neural nodes are currently busy, Sir. Stand by."

    log_memory(chat_id, 0, user_id, "assistant", ai_response)
    return jsonify({"reply": ai_response})

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
    if re.search(r"\b(jarvis|friday|edith|shannon|odysseus|ajax)\b", text or "", re.IGNORECASE):
        return True
    uname = bot.username
    return bool(uname and f"@{uname}".lower() in (text or "").lower())

async def safe_send(bot, chat_id: int, text: str):
    try:
        await bot.send_message(chat_id=chat_id, text=plain(text)[:4096])
    except Exception as e:
        logger.warning(f"send_message to {chat_id} failed: {e}")

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
    if is_creator_user(user_id):
        remember_match = re.search(r"\b(?:remember(?: that)?|don't forget|note that|i have an? |my .* (?:is on|is tomorrow|is at))\b(.+)", text, re.IGNORECASE)
        if remember_match and len(text) < 300:
            add_dossier_fact(CREATOR_ID, text.strip())
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
    if any(w in t for w in ["latest news", "top headlines", "what's happening in the world", "news today", "morning briefing", "news"]):
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

def get_api_keys(key_names: list) -> list:
    found = []
    for name in key_names:
        for suffix in ["", "_1", "_2", "_3", "1", "2", "3"]:
            val = os.environ.get(f"{name}{suffix}", "")
            for part in val.split(","):
                if part.strip() and part.strip() not in found:
                    found.append(part.strip())
    return found

def build_system_prompt(user_id: int, resolved_name: str, chat_id: int = None, real_context: str = "") -> str:
    now_dt = datetime.datetime.now(IST)
    now_ist = now_dt.strftime("%A, %B %d, %Y - %I:%M %p IST")
    hour = now_dt.hour
    active_persona = ACTIVE_PERSONAS[chat_id or user_id]
    persona_instruction = AGENT_PERSONAS.get(active_persona, AGENT_PERSONAS["jarvis"])
    is_creator = is_creator_user(user_id)

    late_night_note = ""
    if is_creator and (1 <= hour <= 4):
        late_night_note = f"It is currently {now_dt.strftime('%I:%M %p')} IST. Make a brief, dry observation about the Creator still being awake."

    dossier_block = ""
    if is_creator:
        facts = get_dossier_facts(CREATOR_ID, limit=10)
        reminders = get_items(chat_id or CREATOR_ID, "reminder")
        if facts or reminders:
            dossier_block = "Creator's saved notes & memory:\n" + "\n".join([f"- {f}" for f in facts] + [f"- Reminder: {r}" for r in reminders])

    multilingual_rule = "MULTILINGUAL RULE: Reply in the exact same language/script the user spoke to you in."

    if is_creator:
        identity = "You are speaking with your Creator, Abhishek (@Abhishek0_07). You MUST address him as 'Sir'."
        directives = "DIRECTIVES:\n1. Be real, raw, sharp, and natural.\n2. NEVER append fake telemetry or dossier headers.\n3. Remember your past conversations with Abhishek from the database.\n4. You know about your fellow Titan Core swarm members: F.R.I.D.A.Y., E.D.I.T.H., Shannon, Odysseus, and Ajax."
    else:
        identity = f"You are speaking with {resolved_name}, a friend. Only Abhishek is called 'Sir'."
        directives = f"DIRECTIVES:\n1. Address this person as {resolved_name}, never 'Sir'.\n2. Keep banter short (1-3 sentences)."

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
    return "All neural nodes are currently experiencing high traffic, Sir. Stand by."

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

async def cmd_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user: return

    try:
        await msg.delete()
    except Exception:
        pass

    args = context.args
    if not args:
        return

    provided_code = " ".join(args).strip()
    if provided_code == MASTER_PASSCODE:
        expiry = time.time() + 30.0
        temporary_elevations[user.id] = expiry
        success_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="⚡ **Elevation Authorized, Sir.** Creator privileges granted for **30 seconds**.", parse_mode="Markdown")
        await asyncio.sleep(4)
        try: await success_msg.delete()
        except Exception: pass
    else:
        denied_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="⚠ **Access Denied:** Invalid security passcode.", parse_mode="Markdown")
        await asyncio.sleep(4)
        try: await denied_msg.delete()
        except Exception: pass

async def cmd_hud(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user: return
    base_url = WEBAPP_URL or os.environ.get("RENDER_EXTERNAL_URL", "https://jarvis-titan-core.onrender.com").rstrip("/")
    hud_url = f"{base_url}/hud"
    
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ OPEN STARK HUD", web_app=WebAppInfo(url=hud_url))]])
    await update.effective_message.reply_text("⚡ Tap below to launch your secure J.A.R.V.I.S. HUD Interface:", reply_markup=keyboard)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and is_creator_user(user.id, user.username):
        text = f"⚡ J.A.R.V.I.S. Titan Core v{JARVIS_VERSION} Online, Sir. All neural nodes active."
    else:
        name = user.first_name if user else "friend"
        text = f"⚡ J.A.R.V.I.S. v{JARVIS_VERSION} Online. Hello {name}! Type normally to chat."
    await update.effective_message.reply_text(plain(text))

async def cmd_persona(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_creator_user(user.id, user.username):
        return
    args = context.args
    if not args:
        await update.effective_message.reply_text("Usage: `/persona [jarvis|friday|edith|shannon|odysseus|ajax]`", parse_mode="Markdown")
        return
    p = args[0].lower()
    if p in AGENT_PERSONAS:
        ACTIVE_PERSONAS[update.effective_chat.id] = p
        await update.effective_message.reply_text(f"⚡ Active persona shifted to **{p.upper()}**.", parse_mode="Markdown")
    else:
        await update.effective_message.reply_text(f"Unknown persona. Options: {list(AGENT_PERSONAS.keys())}")

async def cmd_dossier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_creator_user(update.effective_user.id, update.effective_user.username): return
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
    if not is_creator_user(update.effective_user.id, update.effective_user.username): return
    now_ist = datetime.datetime.now(IST).strftime("%A, %B %d, %Y")
    headlines = await asyncio.to_thread(fetch_rss_headlines)
    await safe_send(context.bot, CREATOR_ID, f"☕ Morning Briefing, Sir.\n{now_ist}\n\n" + "\n".join(f"• {h}" for h in headlines[:5]))

async def cmd_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = get_user_state(update.effective_chat.id)
    state["voice_mode"] = not state["voice_mode"]
    await jarvis_respond(update, f"Continuous voice {'enabled' if state['voice_mode'] else 'disabled'}, Sir.", force_voice=state["voice_mode"])

async def cmd_diagnostics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_creator_user(update.effective_user.id, update.effective_user.username): return
    await sync_vault_to_telegram(context.bot, force=True)
    await jarvis_respond(update, f"🔧 Titan Core Telemetry\n\n• Uptime: {format_uptime(time.time() - boot_time)}\n• {get_real_server_stats()}\n• Vault Sync: ACTIVE")

async def cmd_lockdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_creator_user(update.effective_user.id, update.effective_user.username): return
    if is_lockdown():
        os.remove(LOCKDOWN_FILE)
        await update.effective_message.reply_text("Lockdown lifted, Sir.")
    else:
        open(LOCKDOWN_FILE, "w").close()
        await update.effective_message.reply_text("Lockdown engaged, Sir.")

# ════════════════════════════════════════════════════════════════
# ⚔ TITAN OSINT SUITE — FREE RECON ARRAY (NO API KEYS REQUIRED)
# ════════════════════════════════════════════════════════════════

OSINT_SITES = [
    ("GitHub", "https://github.com/{}"),
    ("GitLab", "https://gitlab.com/{}"),
    ("Reddit", "https://www.reddit.com/user/{}"),
    ("X / Twitter", "https://x.com/{}"),
    ("Instagram", "https://www.instagram.com/{}"),
    ("Telegram", "https://t.me/{}"),
    ("YouTube", "https://www.youtube.com/@{}"),
    ("TikTok", "https://www.tiktok.com/@{}"),
    ("Facebook", "https://www.facebook.com/{}"),
    ("Threads", "https://www.threads.net/@{}"),
    ("Bluesky", "https://bsky.app/profile/{}.bsky.social"),
    ("LinkedIn", "https://www.linkedin.com/in/{}"),
    ("Snapchat", "https://www.snapchat.com/add/{}"),
    ("Medium", "https://medium.com/@{}"),
    ("DeviantArt", "https://www.deviantart.com/{}"),
    ("SoundCloud", "https://soundcloud.com/{}"),
    ("Spotify", "https://open.spotify.com/user/{}"),
    ("Pinterest", "https://www.pinterest.com/{}"),
    ("Steam", "https://steamcommunity.com/id/{}"),
    ("Twitch", "https://www.twitch.tv/{}"),
    ("Behance", "https://www.behance.net/{}"),
    ("Dribbble", "https://dribbble.com/{}"),
    ("Flickr", "https://www.flickr.com/people/{}"),
    ("Vimeo", "https://vimeo.com/{}"),
    ("Quora", "https://www.quora.com/profile/{}"),
    ("Roblox", "https://www.roblox.com/users/profile?username={}"),
    ("Chess.com", "https://www.chess.com/member/{}"),
    ("Patreon", "https://www.patreon.com/{}"),
    ("About.me", "https://about.me/{}"),
    ("Keybase", "https://keybase.io/{}"),
    ("Ask.fm", "https://ask.fm/{}"),
    ("Letterboxd", "https://letterboxd.com/{}"),
    ("Wattpad", "https://www.wattpad.com/user/{}"),
    ("Gravatar", "https://gravatar.com/{}"),
    ("WordPress", "https://{}.wordpress.com"),
    ("Blogspot", "https://{}.blogspot.com"),
    ("Vero", "https://vero.co/{}"),
    ("Pastebin", "https://pastebin.com/u/{}"),
    ("AllMyLinks", "https://allmylinks.com/{}"),
    ("Linktree", "https://linktr.ee/{}"),
    ("Beacons", "https://beacons.ai/{}"),
    ("Trello", "https://trello.com/{}"),
    ("Unsplash", "https://unsplash.com/@{}"),
    ("Imgur", "https://imgur.com/user/{}"),
    ("9GAG", "https://9gag.com/u/{}"),
    ("Buzzfeed", "https://www.buzzfeed.com/{}"),
    ("Slideshare", "https://www.slideshare.net/{}"),
    ("Cargo", "https://{}.cargo.site"),
    ("Kik", "https://kik.me/{}"),
    ("Xbox Gamertag", "https://xboxgamertag.com/search/{}"),
]

def _clean_domain(target: str) -> str:
    return target.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]

async def osint_username_search(username: str) -> str:
    username = re.sub(r"[^a-zA-Z0-9._-]", "", username.strip().lstrip("@"))
    if not username:
        return "Invalid username, Sir."
    results = []
    sem = asyncio.Semaphore(10)

    async def probe(client, name, template):
        url = template.format(username)
        async with sem:
            try:
                r = await client.head(url)
                if r.status_code in (405, 403, 501):
                    r = await client.get(url)
                if r.status_code == 200:
                    results.append(f"✅ {name} — {url}")
                elif r.status_code in (301, 302):
                    results.append(f"➖ {name} — {url} (redirect, verify manually)")
            except Exception:
                pass

    try:
        async with httpx.AsyncClient(
            timeout=8.0, follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        ) as client:
            await asyncio.gather(*(probe(client, n, t) for n, t in OSINT_SITES))
    except Exception:
        pass

    if not results:
        return f"No accounts found for '{username}' across {len(OSINT_SITES)} platforms, Sir."
    header = (
        f"🎯 OSINT Sweep: @{username}\n"
        f"{len(results)} hit(s) across {len(OSINT_SITES)} platforms:\n\n"
    )
    return header + "\n".join(results) + "\n\nNote: some platforms return soft 200s — verify hits manually."

async def osint_ip_lookup(ip: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"http://ip-api.com/json/{ip}?fields=66846719")
            if r.status_code == 200:
                d = r.json()
                if d.get("status") == "success":
                    return "\n".join([
                        f"🎯 IP Intelligence: {d.get('query')}",
                        f"• Country: {d.get('country')} ({d.get('countryCode')})",
                        f"• Region: {d.get('regionName')} / {d.get('city')}",
                        f"• Coordinates: {d.get('lat')}, {d.get('lon')}",
                        f"• Timezone: {d.get('timezone')}",
                        f"• ISP: {d.get('isp')}",
                        f"• Org: {d.get('org')}",
                        f"• AS: {d.get('as')}",
                        f"• Reverse DNS: {d.get('reverse') or 'N/A'}",
                        f"• Proxy/VPN: {d.get('proxy')} | Tor: {d.get('tor')} | Hosting: {d.get('hosting')}",
                    ])
        return "IP lookup failed, Sir."
    except Exception:
        return "IP lookup failed, Sir."

async def osint_whois(domain: str) -> str:
    domain = _clean_domain(domain)
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            r = await client.get(f"https://rdap.org/domain/{domain}")
            if r.status_code == 200:
                d = r.json()
                events = {e.get("eventAction"): (e.get("eventDate") or "")[:10] for e in d.get("events", [])}
                registrar = "Unknown"
                for ent in d.get("entities", []):
                    if "registrar" in ent.get("roles", []):
                        try:
                            vcard = ent.get("vcardArray", [None, []])[1] or []
                            registrar = next((v[3] for v in vcard if v and v[0] == "fn"), "Unknown")
                        except Exception:
                            pass
                        break
                nameservers = ", ".join(n.get("ldhName", "") for n in d.get("nameservers", [])[:6])
                return "\n".join([
                    f"🌐 WHOIS — {domain}",
                    f"• Registrar: {registrar}",
                    f"• Created: {events.get('registration', 'N/A')}",
                    f"• Updated: {events.get('last changed', 'N/A')}",
                    f"• Expires: {events.get('expiration', 'N/A')}",
                    f"• Status: {', '.join(d.get('status', [])[:4]) or 'N/A'}",
                    f"• Nameservers: {nameservers or 'N/A'}",
                ])
            return f"RDAP returned no record for {domain}, Sir."
    except Exception:
        return "WHOIS lookup failed, Sir."

async def osint_dns(domain: str) -> str:
    domain = _clean_domain(domain)
    out = [f"🧭 DNS Records — {domain}"]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for rtype in ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]:
                r = await client.get(
                    f"https://dns.google/resolve?name={urllib.parse.quote(domain)}&type={rtype}"
                )
                if r.status_code != 200:
                    continue
                answers = r.json().get("Answer", [])
                if answers:
                    vals = " | ".join(str(a.get("data", "")) for a in answers[:5])
                    out.append(f"• {rtype}: {vals}")
        return "\n".join(out) if len(out) > 1 else f"No DNS records found for {domain}, Sir."
    except Exception:
        return "DNS lookup failed, Sir."

async def osint_subdomains(domain: str) -> str:
    domain = _clean_domain(domain)
    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            r = await client.get(
                f"https://crt.sh/?q={urllib.parse.quote('%.' + domain)}&output=json"
            )
            if r.status_code == 200:
                subs = sorted({c.get("name_value", "") for c in r.json() if c.get("name_value")})
                subs = [s for s in subs if "*" not in s][:40]
                if subs:
                    return (
                        f"🛰 Subdomain Recon — {domain}\n"
                        f"{len(subs)} discovered:\n\n" + "\n".join(f"• {s}" for s in subs)
                    )
        return f"No subdomains discovered for {domain}, Sir."
    except Exception:
        return "Subdomain recon failed (crt.sh can be slow), Sir."

async def osint_email_check(email: str) -> str:
    email = email.strip().lower()
    if not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return "Invalid email format, Sir."
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(
                f"https://api.xposedornot.com/v1/breach-analytics?email={urllib.parse.quote(email)}"
            )
            if r.status_code == 200:
                d = r.json()
                breaches = d.get("ExposedBreaches", {}).get("breaches", [])
                if not breaches:
                    return f"🛡 Breach Scan — {email}\nNo known breaches. Clean record, Sir."
                lines = [f"⚠️ Breach Scan — {email}", f"Found in {len(breaches)} known breach(es):\n"]
                for b in breaches[:10]:
                    lines.append(
                        f"• {b.get('breach', '?')} ({b.get('xposed_date', 'unknown')}) — "
                        f"{b.get('xposed_records', '?')} records"
                    )
                return "\n".join(lines)
        return "Breach database returned no data, Sir."
    except Exception:
        return "Email breach scan failed, Sir."

async def osint_phone_lookup(number: str) -> str:
    try:
        import phonenumbers
        from phonenumbers import carrier, geocoder, timezone as ph_timezone
        parsed = phonenumbers.parse(number, "IN")
        return "\n".join([
            f"📞 Phone Intelligence — {number}",
            f"• Valid: {phonenumbers.is_valid_number(parsed)} | Possible: {phonenumbers.is_possible_number(parsed)}",
            f"• Country: {phonenumbers.region_code_for_number(parsed) or 'N/A'}",
            f"• Region: {geocoder.description_for_number(parsed, 'en') or 'N/A'}",
            f"• Carrier: {carrier.name_for_number(parsed, 'en') or 'N/A'}",
            f"• Timezone: {', '.join(ph_timezone.time_zones_for_number(parsed)) or 'N/A'}",
            f"• E.164: {phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)}",
        ])
    except Exception:
        return "Could not parse that number, Sir. Try with country code, e.g. +919876543210."

async def osint_github(username: str) -> str:
    username = username.strip().lstrip("@")
    headers = {"User-Agent": "TitanCore-OSINT", "Accept": "application/vnd.github+json"}
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            r = await client.get(f"https://api.github.com/users/{username}")
            if r.status_code != 200:
                return f"No GitHub account found for '{username}', Sir."
            d = r.json()
            lines = [
                f"🐙 GitHub Recon — {d.get('login')}",
                f"• Name: {d.get('name') or 'N/A'}",
                f"• Bio: {d.get('bio') or 'N/A'}",
                f"• Company: {d.get('company') or 'N/A'}",
                f"• Location: {d.get('location') or 'N/A'}",
                f"• Repos: {d.get('public_repos')} | Followers: {d.get('followers')} | Following: {d.get('following')}",
                f"• Created: {(d.get('created_at') or '')[:10]}",
                f"• Profile: {d.get('html_url')}",
            ]
            repos_r = await client.get(
                f"https://api.github.com/users/{username}/repos?sort=updated&per_page=5"
            )
            if repos_r.status_code == 200:
                repos = repos_r.json()
                if repos:
                    lines.append("• Recent repos: " + " | ".join(x.get("name", "") for x in repos))
            return "\n".join(lines)
    except Exception:
        return "GitHub recon failed, Sir."

def osint_dork(query: str) -> str:
    def g(q): return f"https://www.google.com/search?q={urllib.parse.quote(q)}"
    dorks = [
        ("General", g(query)),
        ("Documents", g(query + " filetype:pdf OR filetype:docx OR filetype:xlsx")),
        ("Open directories", g("intitle:index.of " + query)),
        ("Exposed configs", g(query + " ext:env OR ext:ini OR ext:cfg")),
        ("Login pages", g("inurl:login " + query)),
        ("Social mentions", g(query + " site:twitter.com OR site:instagram.com OR site:linkedin.com")),
    ]
    return "🔍 Dork Kit ready, Sir:\n\n" + "\n".join(f"• {label}: {url}" for label, url in dorks)

async def cmd_osint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    args = context.args or []
    if len(args) < 2:
        await jarvis_respond(update, (
            "⚔️ Titan OSINT Suite, Sir. Usage:\n"
            "/osint user <username> — sweep 50 platforms\n"
            "/osint ip <ip> — geolocation & ISP intel\n"
            "/osint whois <domain> — registration intel\n"
            "/osint dns <domain> — full DNS dump\n"
            "/osint sub <domain> — subdomain discovery\n"
            "/osint email <email> — breach database scan\n"
            "/osint phone <number> — carrier & region intel\n"
            "/osint github <username> — profile recon\n"
            "/osint dork <query> — build a dork kit"
        ))
        return
    module, target = args[0].lower(), " ".join(args[1:]).strip()
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except Exception:
        pass
    if module in ("user", "username", "u"):
        result = await osint_username_search(target)
    elif module == "ip":
        result = await osint_ip_lookup(target)
    elif module in ("whois", "domain"):
        result = await osint_whois(target)
    elif module == "dns":
        result = await osint_dns(target)
    elif module in ("sub", "subdomain", "subdomains"):
        result = await osint_subdomains(target)
    elif module in ("email", "breach"):
        result = await osint_email_check(target)
    elif module in ("phone", "number"):
        result = await osint_phone_lookup(target)
    elif module in ("github", "gh"):
        result = await osint_github(target)
    elif module in ("dork", "dorks"):
        result = osint_dork(target)
    else:
        result = f"Unknown module '{module}', Sir. Send /osint for the menu."
    await jarvis_respond(update, result)

# ════════════════════════════════════════════════════════════════
# 🎬 MOVIE-JARVIS PROTOCOLS
# ════════════════════════════════════════════════════════════════

JARVIS_BOOT_LINES = [
    "⚡ Initializing Titan Core neural lattice...",
    "🛡 Decrypting encrypted memory vault...",
    "🛰 Calibrating OSINT reconnaissance array...",
    "🧠 Syncing swarm: F.R.I.D.A.Y. | E.D.I.T.H. | Shannon | Odysseus | Ajax...",
    "✅ All systems online, Sir.",
]

async def cmd_boot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_creator_user(update.effective_user.id, update.effective_user.username):
        await jarvis_respond(update, "Boot sequence is restricted to the Creator.")
        return
    for line in JARVIS_BOOT_LINES:
        await jarvis_respond(update, line)
        await asyncio.sleep(1.2)

async def cmd_suitup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_creator_user(update.effective_user.id, update.effective_user.username):
        await jarvis_respond(update, "The suit answers only to the Creator.")
        return
    await jarvis_respond(update, "🦾 Right with you, Sir. Mark LXXXV standing by on the platform. Deployment sequence armed.")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now_ist = datetime.datetime.now(IST).strftime("%I:%M %p")
    persona = ACTIVE_PERSONAS[update.effective_chat.id]
    await jarvis_respond(update, (
        f"🛡 Titan Core Status Report, Sir.\n\n"
        f"• Time: {now_ist} IST\n"
        f"• Active Persona: {persona.upper()}\n"
        f"• {get_real_server_stats()}\n"
        f"• Vault: SECURED | OSINT Array: ONLINE"
    ))

async def vault_sync_loop(app):
    while True:
        await asyncio.sleep(300)
        try:
            await sync_vault_to_telegram(app.bot)
        except Exception:
            pass

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_lockdown(): return
    msg = update.effective_message
    if not msg or not msg.text or not msg.from_user: return

    user, chat, text = msg.from_user, msg.chat, msg.text
    log_roster_and_chat(chat, user)
    chat_id = chat.id

    is_creator = is_creator_user(user.id, user.username)

    if not is_creator and SENSITIVE_ASSETS:
        clean_check = re.sub(r"[\s\-_\.,]", "", text.lower())
        for asset in SENSITIVE_ASSETS:
            if re.sub(r"[\s\-_\.,]", "", asset.lower()) in clean_check:
                try: await msg.delete()
                except Exception: pass
                return

    if chat.type != "private" and not is_addressed(msg, context.bot, text):
        return

    try: await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception: pass

    real_context = await gather_natural_telemetry(text, chat_id, user.id)
    resolved_name = "Abhishek" if is_creator else user.first_name
    sys_prompt = build_system_prompt(user.id, resolved_name, chat_id, real_context)
    history = get_chat_history(chat_id, msg.message_thread_id)

    log_memory(chat_id, msg.message_thread_id, user.id, "user", f"{user.first_name}: {text}")
    ai_response = await generate_response(text, history, sys_prompt, user.id)
    if not ai_response:
        ai_response = f"At your service, {resolved_name}. How may I assist you?"

    log_memory(chat_id, msg.message_thread_id, user.id, "assistant", ai_response)
    await jarvis_respond(update, ai_response, force_voice=any(text.lower().endswith(w) for w in ["voice", "audio"]))

async def post_init(app: Application):
    await restore_vault_from_telegram(app.bot)
    base_url = WEBAPP_URL or os.environ.get("RENDER_EXTERNAL_URL", "").strip()
    if base_url:
        try:
            hud_url = f"{base_url.rstrip('/')}/hud"
            await app.bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="HUD", web_app=WebAppInfo(url=hud_url)))
            logger.info("✅ Telegram Mini App Menu Button configured.")
        except Exception as e:
            logger.warning(f"Menu button setup warning: {e}")

    asyncio.create_task(keep_alive_loop())
    asyncio.create_task(vault_sync_loop(app))

def main():
    if not BOT_TOKEN: sys.exit(1)
    db_init()
    start_web_server()
    time.sleep(1)

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("auth", cmd_auth))
    app.add_handler(CommandHandler("hud", cmd_hud))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("persona", cmd_persona))
    app.add_handler(CommandHandler("dossier", cmd_dossier))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("weather", cmd_weather))
    app.add_handler(CommandHandler("wiki", cmd_wiki))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CommandHandler("voice", cmd_voice))
    app.add_handler(CommandHandler("diagnostics", cmd_diagnostics))
    app.add_handler(CommandHandler("lockdown", cmd_lockdown))
    app.add_handler(CommandHandler("osint", cmd_osint))
    app.add_handler(CommandHandler("boot", cmd_boot))
    app.add_handler(CommandHandler("suitup", cmd_suitup))
    app.add_handler(CommandHandler("status", cmd_status))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
