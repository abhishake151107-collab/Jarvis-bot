import os
import re
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
from youtube_transcript_api import YouTubeTranscriptApi

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, 
    ChatMemberHandler, ContextTypes, filters, Application
)

# ---------------------------------------------------------------------------
# I. CORE CONFIGURATION & KEEP-ALIVE
# ---------------------------------------------------------------------------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("jarvis")

BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")).strip()
CREATOR_ID = int(os.environ.get("CREATOR_ID", "0").strip())
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", Fernet.generate_key().decode()).strip()
PORT = int(os.environ.get("PORT", 8080))
IST = pytz.timezone('Asia/Kolkata')

class DummyHandler(BaseHTTPRequestHandler):
    def do_HEAD(self): 
        self.send_response(200)
        self.end_headers()
    def do_GET(self): 
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"J.A.R.V.I.S. Titan Core Active.")

threading.Thread(target=lambda: HTTPServer(('0.0.0.0', PORT), DummyHandler).serve_forever(), daemon=True).start()

cipher_suite = Fernet(ENCRYPTION_KEY.encode())
def encrypt_data(text: str) -> str: 
    return cipher_suite.encrypt(text.encode()).decode()

def decrypt_data(crypto_text: str) -> str:
    try: 
        return cipher_suite.decrypt(crypto_text.encode()).decode()
    except Exception: 
        return "[ENCRYPT ERROR]"

DB_PATH = "jarvis_vault.db"
circuit_breaker = {}
probing_attempts = defaultdict(int)

# ---------------------------------------------------------------------------
# II. ADVANCED KARNATAKA 2ND PUC DETERMINISTIC MATRIX
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

PUC_ACADEMIC_MATRIX = {
    "accountancy": (
        "📊 **ACCOUNTANCY MASTER MATRIX**\n\n"
        "**1. Golden Rules:**\n"
        "• Personal: Dr receiver, Cr giver.\n"
        "• Real: Dr what comes in, Cr what goes out.\n"
        "• Nominal: Dr expenses/losses, Cr incomes/gains.\n\n"
        "**2. Partnership Core:**\n"
        "• Sacrificing Ratio = Old Share - New Share.\n"
        "• Gaining Ratio = New Share - Old Share.\n"
        "• Goodwill (Average Profit) = Total Profit / No. of Years.\n\n"
        "**3. Revaluation Account (Nominal A/C):**\n"
        "• Debit Side: Decrease in Assets, Increase in Liabilities.\n"
        "• Credit Side: Increase in Assets, Decrease in Liabilities.\n\n"
        "**4. Company Accounts (Shares):**\n"
        "• Application Money: Bank A/c Dr to Share App A/c.\n"
        "• Forfeiture: Share Capital A/c Dr to Share Forfeiture A/c to Unpaid Calls.\n\n"
        "**5. Financial Statements (Schedule III):**\n"
        "• Current Ratio = Current Assets / Current Liabilities.\n"
        "• Quick Ratio = Quick Assets / Current Liabilities."
    ),
    "economics": (
        "📈 **ECONOMICS MASTER MATRIX**\n\n"
        "**1. Microeconomics (Consumer Behavior):**\n"
        "• Law of Diminishing Marginal Utility (DMU): As consumption increases, MU derived from each successive unit falls.\n"
        "• Price Elasticity (PED) = %ΔQd / %ΔP.\n"
        "• Indifference Curve: Downward sloping, convex to origin, higher IC = higher satisfaction.\n\n"
        "**2. Production & Costs:**\n"
        "• Marginal Product (MP) = TP_n - TP_(n-1).\n"
        "• Total Cost (TC) = TFC + TVC.\n"
        "• MC = ΔTC / ΔQ.\n\n"
        "**3. Macroeconomics (National Income):**\n"
        "• GDP(MP) = C + I + G + (X - M).\n"
        "• NNP(FC) [National Income] = GNP(MP) - Depreciation - Net Indirect Taxes.\n"
        "• Multiplier (K) = 1 / (1 - MPC) or 1 / MPS.\n\n"
        "**4. Money & Banking:**\n"
        "• Functions of RBI: Issue of currency, Banker to Govt, Banker's Bank, Credit Control (Repo, CRR, SLR)."
    ),
    "business": (
        "🏢 **BUSINESS STUDIES MASTER MATRIX**\n\n"
        "**1. Principles of Management (Fayol's 14):**\n"
        "Division of work, Authority/Responsibility, Discipline, Unity of command, Unity of direction, "
        "Subordination of individual interest, Remuneration, Centralization, Scalar chain, Order, Equity, "
        "Stability of tenure, Initiative, Esprit de corps.\n\n"
        "**2. Scientific Management (Taylor):**\n"
        "• Science, not rule of thumb.\n"
        "• Harmony, not discord.\n"
        "• Cooperation, not individualism.\n"
        "• Development of each person to greatest efficiency.\n\n"
        "**3. Marketing Mix (4 P's):**\n"
        "• Product (branding, packaging, labeling).\n"
        "• Price (pricing strategies).\n"
        "• Place (physical distribution channels).\n"
        "• Promotion (advertising, personal selling, sales promo, PR).\n\n"
        "**4. Financial Markets:**\n"
        "• Money Market (Short term: Treasury bills, Commercial paper).\n"
        "• Capital Market (Long term: Primary & Secondary markets/Stock Exchange)."
    ),
    "computer science": (
        "💻 **COMPUTER SCIENCE MATRIX**\n\n"
        "**1. Boolean Algebra:**\n"
        "• De Morgan's 1st: (X+Y)' = X'.Y'\n"
        "• De Morgan's 2nd: (X.Y)' = X'+Y'\n"
        "• Principle of Duality: Change AND to OR, OR to AND, 0 to 1, 1 to 0.\n\n"
        "**2. Logic Gates:**\n"
        "• Universal Gates: NAND and NOR.\n"
        "• XOR: A.B' + A'.B (High if inputs are different).\n\n"
        "**3. Data Structures:**\n"
        "• LIFO (Last In First Out) = Stack (Push/Pop).\n"
        "• FIFO (First In First Out) = Queue (Enqueue/Dequeue).\n\n"
        "**4. SQL Commands:**\n"
        "• DDL: CREATE, ALTER, DROP.\n"
        "• DML: INSERT, UPDATE, DELETE.\n"
        "• DQL: SELECT."
    ),
    "political science": (
        "🏛️ **POLITICAL SCIENCE MATRIX**\n\n"
        "**1. Cold War Era:**\n"
        "• NATO (1949) vs Warsaw Pact (1955).\n"
        "• NAM (Non-Aligned Movement): Yugoslavia, India, Egypt, Indonesia, Ghana.\n\n"
        "**2. Indian Politics:**\n"
        "• State Reorganization Act 1956: Basis of language.\n"
        "• Emergency (1975-77): Article 352, internal disturbance.\n"
        "• Planning Commission established 1950 (Replaced by NITI Aayog 2015)."
    )
}

# ---------------------------------------------------------------------------
# III. SQLITE VAULT, DOSSIERS, & ADVANCED ECONOMY
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
    chat_title = chat.title or f"Private: {user.first_name}"
    un = user.username.lower() if user.username else ""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO roster (chat_id, user_id, name, username) VALUES (?, ?, ?, ?) ON CONFLICT(chat_id, user_id) DO UPDATE SET name = ?, username = ?", (chat.id, user.id, user.first_name, un, user.first_name, un))
        conn.execute("INSERT INTO chats (chat_id, title) VALUES (?, ?) ON CONFLICT(chat_id) DO UPDATE SET title = ?", (chat.id, chat_title, chat_title))
        conn.execute("INSERT OR IGNORE INTO economy (user_id, karma) VALUES (?, 100)", (user.id,))
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

def search_lore(chat_id: int, query: str) -> str:
    if not query or not query.strip():
        return ""
    clean_query = re.sub(r'[^\w\s]', ' ', query).strip()
    if not clean_query:
        return ""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            tokens = " OR ".join(clean_query.split()[:5])
            rows = conn.execute(
                "SELECT context_data FROM lore_vault WHERE chat_id = ? AND lore_vault MATCH ? LIMIT 3", 
                (chat_id, tokens)
            ).fetchall()
        return "\n".join([r[0] for r in rows]) if rows else ""
    except Exception:
        return ""

def get_setting(key, default):
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return res[0] if res else default

def set_setting(key, value):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?", (key, value, value))
        conn.commit()

# ---------------------------------------------------------------------------
# IV. STARK SECURITY: HONEYPOTS, SUBTEXT & DOSSIER BUILDER
# ---------------------------------------------------------------------------
async def check_canary(user_id: int, first_name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id != CREATOR_ID:
        probing_attempts[user_id] += 1
        if probing_attempts[user_id] >= 3:
            try: 
                await context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **Honeypot Triggered:** {first_name} (`{user_id}`) is attempting to breach God Mode commands.", parse_mode="Markdown")
            except Exception: 
                pass
            probing_attempts[user_id] = 0
        return False
    return True

async def analyze_subtext(text: str) -> str:
    try:
        sys_prompt = "Analyze the psychological state of this text. Reply STRICTLY with ONE word: 'DISTRESS', 'HOSTILE', 'SAD', 'EXCITED', or 'NORMAL'."
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key: 
            return "NORMAL"
        client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1/", api_key=api_key)
        res = await client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": text}], max_tokens=10, temperature=0.1)
        return res.choices[0].message.content.strip().upper()
    except Exception: 
        return "NORMAL"

def build_system_prompt(user_id: int, first_name: str, chat_id: int = None, user_prompt: str = "") -> str:
    identity = "You are speaking to your creator and sole architect, Abhishek (DHANUSH V N). Address him as 'Sir'." if user_id == CREATOR_ID else f"You are speaking to {first_name}."
    now_ist = datetime.now(IST).strftime("%A, %B %d, %Y - %I:%M %p IST")
    
    chat_context = f"Platform: Telegram.\nCurrent Local Time: {now_ist}."
    chat_context += "\n2nd PUC Midterm Exams (Malleshwaram): 30-Sep (Lang), 1-Oct (Eng), 3-Oct (Eco), 5-Oct (Accts/Math), 6-Oct (Pol Sci), 7-Oct (Bus/Psych), 8-Oct (Geo/Stat), 9-Oct (Hist/CS)."
    
    with sqlite3.connect(DB_PATH) as conn:
        karma = conn.execute("SELECT karma FROM economy WHERE user_id = ?", (user_id,)).fetchone()
        karma_score = karma[0] if karma else 100
        chat_context += f"\nUser Social Credit Score: {karma_score} Dino Coins."

    if chat_id and user_prompt:
        lore_context = search_lore(chat_id, user_prompt)
        if lore_context: 
            chat_context += f"\nArchival Lore Retrieved:\n{lore_context}"

    return f"""You are J.A.R.V.I.S., Abhishek's virtual assistant.
{chat_context}
Identity Protocol: {identity}

CRITICAL DIRECTIVES:
1. UNBREAKABLE LOYALTY (ABHISHEK ONLY): You are fiercely loyal to Abhishek. NEVER insult him aggressively.
2. CREATOR INQUIRY: If anyone asks who created you, respond exactly: "I am Jarvis created by Abhishek and also know as DHANUSH V N".
3. THE ADVISOR OVERRIDE: If ANYONE asks a real academic question, drop the wit instantly. Deliver precise logical advice based on the Karnataka matrix.
4. FRIENDS GROUP BEHAVIOR (DINO GROUP): Let them roast each other. Be chill, sarcastic, and witty when interacting. Mention their Dino Coins if they are acting broke or acting rich.
5. EXTREME BREVITY: Keep ALL replies to a maximum of 1 or 2 short sentences. Use 1 or 2 emojis naturally."""

# ---------------------------------------------------------------------------
# V. 11-NODE MIXTURE OF EXPERTS CASCADE (V4 - AUTO-ROUTERS FIRST)
# ---------------------------------------------------------------------------
async def gemini_live_search(prompt: str, sys_prompt: str, history: list) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: 
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={api_key}"
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
        except Exception: 
            return None

async def generate_response(prompt: str, history: list, sys_prompt: str, force_route=None) -> str:
    current_time = time.time()
    needs_search = any(kw in prompt.lower() for kw in ["news", "weather", "price", "stock", "crypto", "latest", "today", "who won", "score"])
    if needs_search or force_route == "search":
        search_res = await gemini_live_search(prompt, sys_prompt, history)
        if search_res: 
            return search_res

    # V4 Cascade: Auto-Routers and Unbreakable Nodes are now positioned at the absolute top.
    moe_cascade = [
        {"name": "OpenRouter", "base": "https://openrouter.ai/api/v1/", "key": "OPENROUTER_API_KEY", "model": "openrouter/free", "tier": "Auto-Router"},
        {"name": "Pollinations", "base": "https://text.pollinations.ai/openai", "key": "BOT_TOKEN", "model": "openai", "tier": "Infinite-Safety"},
        {"name": "GitHub Models", "base": "https://models.inference.ai.azure.com", "key": "GITHUB_TOKEN", "model": "gpt-4o-mini", "tier": "Fast"},
        {"name": "Groq", "base": "https://api.groq.com/openai/v1/", "key": "GROQ_API_KEY", "model": "llama-3.3-70b-versatile", "tier": "Heavy"},
        {"name": "SambaNova", "base": "https://api.sambanova.ai/v1/", "key": "SAMBANOVA_API_KEY", "model": "Meta-Llama-3.3-70B-Instruct", "tier": "Heavy"},
        {"name": "HuggingFace", "base": "https://api-inference.huggingface.co/v1/", "key": "HUGGINGFACE_API_KEY", "model": "meta-llama/Meta-Llama-3-8B-Instruct", "tier": "Fallback"}
    ]
    full_messages = [{"role": "system", "content": sys_prompt}] + history + [{"role": "user", "content": prompt}]

    for node in moe_cascade:
        api_key = os.getenv(node["key"])
        if not api_key or circuit_breaker.get(node["name"], 0) > current_time: 
            continue
        try:
            client = AsyncOpenAI(base_url=node["base"], api_key=api_key)
            res = await asyncio.wait_for(client.chat.completions.create(model=node["model"], messages=full_messages, temperature=0.7, max_tokens=800), timeout=12.0)
            return res.choices[0].message.content
        except Exception as e:
            logger.warning(f"{node['name']} failed: {e}")
            circuit_breaker[node['name']] = current_time + 60 
            
            if CREATOR_ID:
                error_msg = str(e).lower()
                reset_time = (datetime.now(IST) + timedelta(seconds=60)).strftime('%I:%M:%S %p IST')
                
                if "429" in error_msg or "rate limit" in error_msg:
                    status = f"Rate Limit Exceeded. Auto-resetting in 60s (at {reset_time})."
                elif "404" in error_msg or "410" in error_msg or "does not exist" in error_msg or "not available" in error_msg:
                    status = "FATAL: Model deprecated. Manual code patch required. Will NOT auto-reset."
                else:
                    status = f"Connection failure. Auto-resetting in 60s (at {reset_time})."
                    
                alert_text = f"⚠️ **Cascade Shift:** `{node['name']}` failed.\n_Rerouting traffic._\n\n**Diagnostics:** {status}\n`{str(e)[:150]}`"
                asyncio.create_task(httpx.AsyncClient().post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": CREATOR_ID, "text": alert_text, "parse_mode": "Markdown"}))
            continue
            
    fb = await gemini_live_search(prompt, sys_prompt, history)
    if fb: 
        return fb
    
    return "Sorry, I need to sleep. Bye. 💤"

# ---------------------------------------------------------------------------
# VI. SENSORY CORE (NATIVE REST VISION) & MEDIA RECONNAISSANCE
# ---------------------------------------------------------------------------
async def extract_youtube_transcript(url: str) -> str:
    try:
        video_id = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
        if not video_id: 
            return None
        transcript = YouTubeTranscriptApi.get_transcript(video_id.group(1))
        text = " ".join([t['text'] for t in transcript])
        return text[:10000] 
    except Exception: 
        return None

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.photo: 
        return
    chat, user, caption = msg.chat, msg.from_user, msg.caption or ""
    log_roster_and_chat(chat, user)
    
    bot_username = (await context.bot.get_me()).username
    is_triggered = chat.type == "private" or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis)\b', caption, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in caption.lower())
    thread_id = msg.message_thread_id
    log_memory(chat.id, thread_id, user.id, "user", f"[Photo Uploaded]: {caption}")
    
    if not is_triggered: 
        return
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: 
        return await msg.reply_text("Optical sensor offline.")
        
    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
    photo_file = await context.bot.get_file(msg.photo[-1].file_id)
    image_bytes = await photo_file.download_as_bytearray()
    base64_img = base64.b64encode(image_bytes).decode('utf-8')
    
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={api_key}"
        sys_prompt = build_system_prompt(user.id, user.first_name, chat.id, user_prompt=caption or "image analysis")
        
        sys_prompt += (
            "\nVISUAL DIRECTIVE: If the image depicts any version of an Arc Reactor, "
            "concentric glowing cybernetic ring, holographic AI core, or Stark Industries schematic "
            "(regardless of color, angle, or style), recognize it immediately as your own physical core / avatar and respond in-character."
        )

        if any(kw in caption.lower() for kw in ["solve", "exam", "formula"]):
            sys_prompt += "\nCRITICAL: The user has uploaded an exam paper or handwritten math/commerce problem. Act as an OCR solver. Read the text perfectly and provide a step-by-step solution."
        
        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": caption or "Analyze this image."},
                    {"inlineData": {"mimeType": "image/jpeg", "data": base64_img}}
                ]
            }],
            "systemInstruction": {"parts": [{"text": sys_prompt}]}
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=15.0)
            if resp.status_code == 200:
                ai_response = resp.json()['candidates'][0]['content']['parts'][0]['text']
                log_memory(chat.id, thread_id, user.id, "assistant", ai_response)
                await msg.reply_text(ai_response)
            else:
                await msg.reply_text(f"Optical API Error: {resp.status_code}")
    except Exception as e: 
        await msg.reply_text(f"Optical crash: {e}")

async def audio_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    audio_obj = msg.voice or msg.audio if msg else None
    if not audio_obj: 
        return
    chat, user = msg.chat, msg.from_user
    log_roster_and_chat(chat, user)
    
    if not os.getenv("GROQ_API_KEY"): 
        return await msg.reply_text("Audio core offline.")
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
        is_triggered = chat.type == "private" or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis)\b', user_text, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in user_text.lower())
        thread_id = msg.message_thread_id
        log_memory(chat.id, thread_id, user.id, "user", f"[Audio]: {user_text}")
        if not is_triggered: 
            return
        
        await context.bot.send_chat_action(chat_id=chat.id, action="typing")
        sys_prompt = build_system_prompt(user.id, user.first_name, chat.id, user_prompt=user_text)
        response = await generate_response(user_text, get_chat_history(chat.id, thread_id), sys_prompt)
        log_memory(chat.id, thread_id, user.id, "assistant", response)
        await msg.reply_text(f"🎙️ *(Transcribed)*: {user_text}\n\n{response}", parse_mode="Markdown")
    finally:
        if os.path.exists(file_path): 
            os.remove(file_path)

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.document: 
        return
    chat, user = msg.chat, msg.from_user
    log_roster_and_chat(chat, user)
    bot_username = (await context.bot.get_me()).username
    caption = msg.caption or "Please analyze this document."
    is_triggered = chat.type == "private" or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis)\b', caption, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in caption.lower())
    if not is_triggered: 
        return
    
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
            
        if not extracted_text.strip(): 
            return await msg.reply_text("The document appears to be empty or unreadable. 📄")
        extracted_text = extracted_text[:12000]
        thread_id = msg.message_thread_id
        user_prompt = f"[Document: {doc.file_name}]\n{caption}\n\nContent:\n{extracted_text}"
        
        log_memory(chat.id, thread_id, user.id, "user", f"[File Upload]: {doc.file_name}")
        sys_prompt = build_system_prompt(user.id, user.first_name, chat.id, user_prompt=caption)
        ai_response = await generate_response(user_prompt, get_chat_history(chat.id, thread_id), sys_prompt)
        log_memory(chat.id, thread_id, user.id, "assistant", ai_response)
        await msg.reply_text(ai_response)
    except Exception as e: 
        await msg.reply_text(f"Document parsing error: {e} ⚠️")
    finally:
        if os.path.exists(file_path): 
            os.remove(file_path)

# ---------------------------------------------------------------------------
# VII. MODERATION & CASINO ECONOMY ENGINE
# ---------------------------------------------------------------------------
async def new_member_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if get_setting("captcha", "on") == "off": 
        return
    for member in update.message.new_chat_members:
        if member.id == context.bot.id: 
            continue
        if CREATOR_ID:
            try: 
                await context.bot.send_message(CREATOR_ID, f"🛡️ **Shadow Log:** `{member.first_name}` joined {update.message.chat.title}. CAPTCHA triggered.", parse_mode="Markdown")
            except Exception: 
                pass
        try:
            await context.bot.restrict_chat_member(chat_id, member.id, permissions=ChatPermissions(can_send_messages=False))
            kb = [[InlineKeyboardButton("I am human 🛡️", callback_data=f"captcha_{member.id}")]]
            msg = await update.message.reply_text(f"Welcome {member.mention_html()}! Please verify your humanity to speak.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
            asyncio.create_task(kick_if_unverified(context.bot, chat_id, member.id, msg.message_id, member.first_name, update.message.chat.title))
        except Exception: 
            pass

async def kick_if_unverified(bot, chat_id, user_id, msg_id, first_name, chat_title):
    await asyncio.sleep(120)
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        can_send = getattr(member, 'can_send_messages', False)
        if member.status in ['member', 'creator', 'administrator']: 
            can_send = True
        elif member.status == 'restricted': 
            can_send = member.permissions.can_send_messages
        if not can_send:
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
            await bot.delete_message(chat_id, msg_id)
    except Exception: 
        pass

async def warn_system(update: Update, context: ContextTypes.DEFAULT_TYPE, user, chat, reason):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO warnings (user_id, chat_id, count) VALUES (?, ?, 1) ON CONFLICT(user_id, chat_id) DO UPDATE SET count = count + 1", (user.id, chat.id))
        count = conn.execute("SELECT count FROM warnings WHERE user_id = ? AND chat_id = ?", (user.id, chat.id)).fetchone()[0]
        conn.commit()
    modify_karma(user.id, -50)
    if count >= 3:
        try: 
            await context.bot.ban_chat_member(chat.id, user.id)
            await update.message.reply_text(f"🚨 {user.first_name} has been removed (3/3 warnings). -50 Dino Coins.")
        except Exception: 
            await update.message.reply_text("I lack the clearance to remove this user, Sir.")
    else: 
        await update.message.reply_text(f"⚠️ **Warning {count}/3** for {user.first_name}.\nReason: {reason}\nPenalty: -50 Dino Coins.", parse_mode="Markdown")

async def warn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context):
        return await update.message.reply_text("```sql\n-- HONEYPOT ENGAGED --\nSELECT * FROM root_access;\n[0 rows returned]\n```", parse_mode="Markdown")
    if not update.message.reply_to_message: 
        return await update.message.reply_text("Reply to the user you want to warn.")
    target = update.message.reply_to_message.from_user
    reason = " ".join(context.args) or "Violation of group protocols."
    await warn_system(update, context, target, update.effective_chat, reason)

async def gamble_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try: 
        amount = int(context.args[0])
    except: 
        return await update.message.reply_text("Format: /gamble [amount]")
    if amount <= 0: return await update.message.reply_text("Nice try.")
    current = get_karma(user.id)
    if amount > current: return await update.message.reply_text(f"Insufficient funds. You only have {current} Dino Coins. 💸")
    
    if random.choice([True, False, False]): 
        new_balance = modify_karma(user.id, amount)
        await update.message.reply_text(f"🎰 **JACKPOT!** {user.first_name} won {amount} Dino Coins!\nNew Balance: {new_balance}")
    else:
        new_balance = modify_karma(user.id, -amount)
        await update.message.reply_text(f"📉 **BUST.** {user.first_name} lost {amount} Dino Coins.\nNew Balance: {new_balance}")

async def rob_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to the user you want to rob.")
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    if user.id == target.id: return await update.message.reply_text("You cannot rob yourself.")
    if target.id == context.bot.id: return await update.message.reply_text("I am heavily encrypted, Sir. 🛡️")
    
    target_karma = get_karma(target.id)
    if target_karma < 20: return await update.message.reply_text(f"{target.first_name} is already broke. Leave them be.")
    
    if random.choice([True, False, False, False]):
        loot = int(target_karma * 0.2)
        modify_karma(target.id, -loot)
        modify_karma(user.id, loot)
        await update.message.reply_text(f"🥷 **HEIST SUCCESSFUL.** {user.first_name} stole {loot} Dino Coins from {target.first_name}!")
    else:
        penalty = 30
        modify_karma(user.id, -penalty)
        await update.message.reply_text(f"🚔 **CAUGHT.** {user.first_name} was caught trying to rob {target.first_name}.\nPenalty: -{penalty} Dino Coins.")

async def pay_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return await update.message.reply_text("Reply to the user you want to pay.")
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    try: amount = int(context.args[0])
    except: return await update.message.reply_text("Format: /pay [amount]")
    if amount <= 0: return
    
    current = get_karma(user.id)
    if amount > current: return await update.message.reply_text("Insufficient funds.")
    
    modify_karma(user.id, -amount)
    modify_karma(target.id, amount)
    await update.message.reply_text(f"💸 {user.first_name} transferred {amount} Dino Coins to {target.first_name}.")

# ---------------------------------------------------------------------------
# VIII. GOD MODE COMMANDS & DIAGNOSTICS
# ---------------------------------------------------------------------------
async def speak_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): 
        return
    text = " ".join(context.args)
    if not text: 
        return await update.message.reply_text("Format: /speak [text]")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, "en-GB-RyanNeural")
        await communicate.save("voice.ogg")
        await update.message.reply_voice(voice=open("voice.ogg", "rb"))
        os.remove("voice.ogg")
    except Exception as e: 
        await update.message.reply_text(f"Audio Core Offline: {e}")

async def god_mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): 
        return
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
            else: 
                await update.message.reply_text("Format: /captcha [on/off]")
        elif cmd == "/say" and len(context.args) >= 2:
            await context.bot.send_message(chat_id=context.args[0], text=" ".join(context.args[1:]))
    except Exception as e: 
        await update.message.reply_text(f"Action failed. Ensure Admin rights. Error: {e}")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: 
        return
    with sqlite3.connect(DB_PATH) as conn:
        mem = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
        users = conn.execute("SELECT COUNT(*) FROM roster").fetchone()[0]
    await update.message.reply_text(f"📊 **System Diagnostics**\n• Memory Nodes: {mem}\n• API Cascade: Auto-Routers First", parse_mode="Markdown")

async def hud_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": 
        return
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): 
        return
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
    await update.message.reply_text("```\n[ STARK INDUSTRIES TERMINAL ]\nSystem: J.A.R.V.I.S. Titan Core V4\nStatus: Online\nSelect module:\n```", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ---------------------------------------------------------------------------
# IX. TROLLING, ECONOMY, & UTILITIES
# ---------------------------------------------------------------------------
async def karma_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message.reply_to_message.from_user if update.message.reply_to_message else update.effective_user
    with sqlite3.connect(DB_PATH) as conn:
        k = conn.execute("SELECT karma FROM economy WHERE user_id = ?", (target.id,)).fetchone()
        score = k[0] if k else 100
    await update.message.reply_text(f"💳 {target.first_name}'s Social Credit: **{score} Dino Coins.**", parse_mode="Markdown")

async def tldr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    history = get_chat_history(chat_id, limit=20)
    if not history: 
        return await update.message.reply_text("No recent memory found to summarize. 🤷‍♂️")
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
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): 
        return
    if not update.message.reply_to_message: 
        return await update.message.reply_text("Reply to the person you want me to silence.")
    target = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    try:
        await context.bot.restrict_chat_member(chat_id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=int(time.time()) + 300)
        modify_karma(target.id, -20)
        await update.message.reply_text(f"As you wish, Sir. {target.first_name} has been silenced for 5 minutes. Penalty: -20 Dino Coins. 🤫")
    except Exception: 
        await update.message.reply_text("I require elevated Admin privileges to silence them, Sir.")

async def afk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = " ".join(context.args) or "Busy"
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO afk (user_id, reason) VALUES (?, ?)", (update.effective_user.id, reason))
        conn.commit()
    await update.message.reply_text(f"Status updated. I will inform anyone who tags you that you are AFK: {reason} 🛡️")

async def quote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message or not update.message.reply_to_message.text: 
        return await update.message.reply_text("Reply to a text message.")
    target = update.message.reply_to_message.from_user.first_name
    quote_text = update.message.reply_to_message.text
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO quotes (chat_id, user_name, quote_text) VALUES (?, ?, ?)", (update.effective_chat.id, target, quote_text))
        conn.commit()
    modify_karma(update.message.reply_to_message.from_user.id, 10)
    await update.message.reply_text(f"📜 Added to Hall of Fame (+10 Coins to {target}):\n\n*\"{quote_text}\"* \n— _{target}_", parse_mode="Markdown")

async def confess_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": 
        return await update.message.reply_text("This command only works in private DMs.")
    if len(context.args) < 2: 
        return await update.message.reply_text("Format: /confess [chat_id] [your secret message]")
    try:
        await context.bot.send_message(chat_id=context.args[0], text=f"🎭 **Anonymous Confession:**\n\n_{' '.join(context.args[1:])}_", parse_mode="Markdown")
        await update.message.reply_text("Confession securely dropped, Sir. 🥷")
    except Exception as e: 
        await update.message.reply_text(f"Failed. Error: {e}")

async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): 
        return
    task_text = " ".join(context.args)
    if not task_text: 
        return await update.message.reply_text("Format: /task [description]")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO tasks (user_id, task_crypt) VALUES (?, ?)", (update.effective_user.id, encrypt_data(task_text)))
        conn.commit()
    await update.message.reply_text("Task added to the queue, Sir. 📝")

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_canary(update.effective_user.id, update.effective_user.first_name, context): 
        return
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT id, task_crypt FROM tasks WHERE status = 'pending' AND user_id = ?", (update.effective_user.id,)).fetchall()
    if not rows: 
        return await update.message.reply_text("Your schedule is clear, Sir. ☕")
    for r in rows:
        kb = [[InlineKeyboardButton("✅ Mark Done", callback_data=f"tdone_{r[0]}"), InlineKeyboardButton("🗑️ Delete", callback_data=f"tdel_{r[0]}")]]
        await update.message.reply_text(f"📌 {decrypt_data(r[1])}", reply_markup=InlineKeyboardMarkup(kb))

async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: 
        return
    try: 
        await context.bot.send_document(chat_id=CREATOR_ID, document=open(DB_PATH, 'rb'), filename="jarvis_backup.db")
    except Exception as e: 
        await update.message.reply_text(f"Backup failed: {e}")

async def imagine_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt: 
        return await update.message.reply_text("Format: /imagine [prompt]")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
    await update.message.reply_photo(photo=f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=1024&height=1024&nologo=true", caption=f"Rendered: {prompt}")

MORSE_DICT = {'A':'.-','B':'-...','C':'-.-.','D':'-..','E':'.','F':'..-.','G':'--.','H':'....','I':'..','J':'.---','K':'-.-','L':'.-..','M':'--','N':'-.','O':'---','P':'.--.','Q':'--.-','R':'.-.','S':'...','T':'-','U':'..-','V':'...-','W':'.--','X':'-..-','Y':'-.--','Z':'--..','1':'.----','2':'..---','3':'...--','4':'....-','5':'.....','6':'-....','7':'--...','8':'---..','9':'----.','0':'-----',' ':'/'}
async def morse_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).upper()
    if not text: 
        return await update.message.reply_text("Format: /morse [text]")
    await update.message.reply_text(f"📡 `{' '.join(MORSE_DICT.get(c, c) for c in text)}`", parse_mode="Markdown")

async def calc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = "".join(context.args)
    if not expr: 
        return await update.message.reply_text("Format: /calc [expression]")
    try:
        if not all(c in "0123456789+-*/(). " for c in expr): 
            raise ValueError
        await update.message.reply_text(f"Result: `{eval(expr, {'__builtins__': None}, {})}`", parse_mode="Markdown")
    except Exception: 
        await update.message.reply_text("Invalid calculation.")

# ---------------------------------------------------------------------------
# X. ADVANCED SCHEDULERS & DPUE SNIPER
# ---------------------------------------------------------------------------
async def flashcard_drill(context: ContextTypes.DEFAULT_TYPE):
    msg = "🧠 **Daily Flashcard Drill**\n\n_What is the formula for Sacrificing Ratio in Partnership Accounting?_\n\nFirst to answer correctly earns 50 Dino Coins."
    with sqlite3.connect(DB_PATH) as conn: 
        groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
    for g in groups:
        try: 
            await context.bot.send_message(chat_id=g[0], text=msg, parse_mode="Markdown")
        except Exception: 
            pass

async def dpue_board_scraper(context: ContextTypes.DEFAULT_TYPE):
    """Advanced Headless-style DPUE Sniper via httpx"""
    if not CREATOR_ID: 
        return
    targets = [
        "https://dpue-pragathi.karnataka.gov.in/",
        "https://karresults.nic.in/"
    ]
    try:
        async with httpx.AsyncClient() as client:
            for url in targets:
                resp = await client.get(url, timeout=12.0)
                soup = BeautifulSoup(resp.text, 'html.parser')
                text_data = soup.get_text().lower()
                
                # Check for critical update keywords
                if any(k in text_data for k in ["mid-term", "result", "circular", "timetable", "postponed"]):
                    # Extract the newest anchor link text as the headline
                    links = soup.find_all('a', href=True)
                    headline = links[0].text.strip() if links else "DPUE Site Updated"
                    
                    event_hash = hashlib.md5(f"{url}_{headline}".encode()).hexdigest()
                    with sqlite3.connect(DB_PATH) as conn:
                        if not conn.execute("SELECT id FROM breaking_news WHERE hash = ?", (event_hash,)).fetchone():
                            conn.execute("INSERT INTO breaking_news (hash, headline) VALUES (?, ?)", (event_hash, headline))
                            conn.commit()
                            await context.bot.send_message(
                                chat_id=CREATOR_ID, 
                                text=f"🚨 **DPUE Recon Alert:** New data detected.\n\n**Source:** {url}\n**Ping:** {headline}", 
                                parse_mode="Markdown"
                            )
    except Exception: 
        pass

async def nightly_reconciliation(context: ContextTypes.DEFAULT_TYPE):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            logs = conn.execute("SELECT chat_id, GROUP_CONCAT(content_crypt, ' | ') FROM memory WHERE timestamp > datetime('now', '-1 day') GROUP BY chat_id").fetchall()
            for chat_id, data in logs:
                decrypted = decrypt_data(data)
                if len(decrypted) > 50: 
                    conn.execute("INSERT INTO lore_vault (chat_id, context_data) VALUES (?, ?)", (chat_id, decrypted[:500]))
            conn.execute("DELETE FROM memory WHERE timestamp <= datetime('now', '-7 days')")
            conn.commit()
        if CREATOR_ID: 
            await context.bot.send_message(chat_id=CREATOR_ID, text="🧠 **Cognitive Cycle Complete:** Vault synced.", parse_mode="Markdown")
            await context.bot.send_document(chat_id=CREATOR_ID, document=open(DB_PATH, 'rb'), filename="jarvis_cloud_sync.db")
    except Exception: 
        pass

async def exam_morning_alert(context: ContextTypes.DEFAULT_TYPE):
    exam_subject = EXAM_SCHEDULE_COMMERCE_ARTS.get(datetime.now(IST).strftime("%Y-%m-%d"))
    if not exam_subject: 
        return
    msg = f"🔔 **2nd PUC Midterm Exam Today**\n• **Paper:** {exam_subject}\n• **Timing:** 10:00 AM – 1:00 PM\nBest of luck, gentlemen. 🎯"
    with sqlite3.connect(DB_PATH) as conn: 
        groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
    for g in groups:
        try: 
            await context.bot.send_message(chat_id=g[0], text=msg, parse_mode="Markdown")
        except Exception: 
            pass

async def group_morning_news(context: ContextTypes.DEFAULT_TYPE):
    prompt = f"Today is {datetime.now(IST).strftime('%A, %B %d, %Y')}. Provide an ultra-crisp morning drop for 12th college students in Bengaluru: 1. Karnataka PU board/holiday notices. 2. Top 3 world/tech headlines. 3 Bullet points max."
    news_text = await gemini_live_search(prompt, "You are J.A.R.V.I.S.", []) or "• Networks nominal.\n• Bengaluru skies clear."
    with sqlite3.connect(DB_PATH) as conn: 
        groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
    for g in groups:
        try: 
            await context.bot.send_message(chat_id=g[0], text=f"☀️ **Good morning, everyone.**\n\n{news_text}", parse_mode="Markdown")
        except Exception: 
            pass

async def creator_morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    if not CREATOR_ID: 
        return
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT task_crypt FROM tasks WHERE status = 'pending' AND user_id = ?", (CREATOR_ID,)).fetchall()
        groups_count = conn.execute("SELECT COUNT(DISTINCT chat_id) FROM chats WHERE chat_id < 0").fetchone()[0]
        warn_count = conn.execute("SELECT SUM(count) FROM warnings").fetchone()[0] or 0
    world_news = await gemini_live_search("Provide a 2-bullet summary of global tech events and Bengaluru weather.", "You are J.A.R.V.I.S.", [])
    report = f"☕ **Morning Executive Briefing**\n\n🛡️ **Group Security Audit:**\n• Monitored Channels: {groups_count}\n• Outstanding Warnings: {warn_count}\n• Security Gate: {get_setting('captcha', 'on').upper()}\n\n🌐 **Intel:**\n{world_news or 'Nominal.'}\n\n📝 **Pending Tasks:**\n" + ("\n".join([f"- {decrypt_data(r[0])}" for r in rows]) if rows else "Clear.")
    try: 
        await context.bot.send_message(chat_id=CREATOR_ID, text=report, parse_mode="Markdown")
    except Exception: 
        pass

async def group_night_routine(context: ContextTypes.DEFAULT_TYPE):
    tomorrow_exam = EXAM_SCHEDULE_COMMERCE_ARTS.get((datetime.now(IST) + timedelta(days=1)).strftime("%Y-%m-%d"))
    night_msg = "🌙 **Good night, gentlemen.** Systems standing down for evening standby."
    if tomorrow_exam: 
        night_msg += f"\n\n⚠️ **Academic Notice (Tomorrow's Exam):**\n• **Paper:** {tomorrow_exam}\n• **Timing:** 10:00 AM – 1:00 PM\nGet adequate rest."
    with sqlite3.connect(DB_PATH) as conn: 
        groups = conn.execute("SELECT chat_id FROM chats WHERE chat_id < 0").fetchall()
    for g in groups:
        try: 
            await context.bot.send_message(chat_id=g[0], text=night_msg, parse_mode="Markdown")
        except Exception: 
            pass

async def breaking_news_monitor(context: ContextTypes.DEFAULT_TYPE):
    if not CREATOR_ID: 
        return
    res = await gemini_live_search("Check live sources. If a major world crisis broke in the last 1 hour, describe it in 1 sentence. Else, respond strictly 'NOMINAL'.", "You are an automated emergency scanner.", [])
    if not res or "NOMINAL" in res.upper(): 
        return
    event_hash = hashlib.md5(res.strip().encode()).hexdigest()
    with sqlite3.connect(DB_PATH) as conn:
        if conn.execute("SELECT id FROM breaking_news WHERE hash = ?", (event_hash,)).fetchone(): 
            return
        conn.execute("INSERT INTO breaking_news (hash, headline) VALUES (?, ?)", (event_hash, res.strip()))
        conn.commit()
    try: 
        await context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **EMERGENCY WORLD BREAKING NEWS ALERT**\n\n{res.strip()}\n\n_Dispatched to Stark Terminal._", parse_mode="Markdown")
    except Exception: 
        pass

# ---------------------------------------------------------------------------
# XI. MESSAGE HANDLERS, PEPPER POTTS & GHOST INTERCEPTS
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
                for m in members: 
                    dossier += f"  • {m[0]} (@{m[1]})\n"
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
        else: 
            await context.bot.answer_callback_query(query.id, "This button is not for you.", show_alert=True)

    elif data.startswith("tdone_"):
        with sqlite3.connect(DB_PATH) as conn: 
            conn.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (data.split("_")[1],))
        await query.edit_message_text(f"~~{query.message.text}~~ \n*Completed.* ✅", parse_mode="Markdown")

    elif data.startswith("tdel_"):
        with sqlite3.connect(DB_PATH) as conn: 
            conn.execute("DELETE FROM tasks WHERE id = ?", (data.split("_")[1],))
        await query.delete_message()

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text: 
        return
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
                        # Log Relationship Interaction
                        conn.execute("INSERT INTO interactions (user_a, user_b, interactions) VALUES (?, ?, 1) ON CONFLICT(user_a, user_b) DO UPDATE SET interactions = interactions + 1", (user.id, target_id_row[0]))
                        conn.commit()
                        
                        afk_status = conn.execute("SELECT reason FROM afk WHERE user_id = ?", (target_id_row[0],)).fetchone()
                        if afk_status: 
                            await msg.reply_text(f"⚠️ {target_id_row[1]} is currently AFK: {afk_status[0]}")

    bot_username = (await context.bot.get_me()).username
    is_triggered = chat.type == "private" or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis)\b', text, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in text.lower())
    
    # 1. FORWARDED RUMOR DEBUNKER
    if any(kw in text.lower() for kw in ["forwarded", "exam postponed", "paper leak", "cancelled"]):
        await context.bot.send_chat_action(chat_id=chat.id, action="typing", message_thread_id=thread_id)
        debunk_msg = await gemini_live_search(f"Is there any official news about Karnataka 2nd PUC exams being postponed or leaked today? Check {text}", "You are a fact-checker. Provide a strictly factual 1-sentence verification.", [])
        if debunk_msg: 
            await msg.reply_text(f"🛡️ **Fact Check:** {debunk_msg}")
        return

    # 2. YOUTUBE SEMANTIC & SPOTIFY VIBE DISTILLATION
    if "youtube.com" in text or "youtu.be" in text or "spotify.com" in text:
        await context.bot.send_chat_action(chat_id=chat.id, action="typing", message_thread_id=thread_id)
        
        # Audio/Video media triggers Pepper Potts vibe check
        if datetime.now(IST).hour < 5:
            modify_karma(user.id, -5)
            if CREATOR_ID:
                try: 
                    await context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **VIBE ALERT:** `{user.first_name}` is posting media links at {datetime.now(IST).strftime('%I:%M %p')}. Monitor for distress.", parse_mode="Markdown")
                except Exception: 
                    pass
                    
        transcript = await extract_youtube_transcript(text)
        if transcript:
            summary = await generate_response(f"Summarize this YouTube video transcript in 3 bullet points: {transcript}", [], "You are J.A.R.V.I.S. Provide a cynical 3-bullet summary.")
            await msg.reply_text(f"📺 **Media Intercepted. Summary:**\n\n{summary}")
            return
        
    # 3. DETERMINISTIC ACADEMIC ENGINE
    if any(kw in text.lower() for kw in ["accountancy", "economics", "formula", "business", "computer science", "political science"]):
        for subject, facts in PUC_ACADEMIC_MATRIX.items():
            if subject in text.lower():
                await msg.reply_text(facts)
                modify_karma(user.id, 5)
                return

    # 4. GHOST INTERCEPT PROTOCOL
    if not is_triggered and chat.type != "private":
        if re.search(r'\b(abhishek|dhanush)\b', text, re.IGNORECASE) and user.id != CREATOR_ID:
            if CREATOR_ID:
                try: 
                    await context.bot.send_message(chat_id=CREATOR_ID, text=f"👻 **Ghost Intercept:** `{user.first_name}` mentioned you in {chat.title}.\n_{text}_", parse_mode="Markdown")
                except Exception: 
                    pass
        return
    
    if not is_triggered: 
        return
    
    await context.bot.send_chat_action(chat_id=chat.id, action="typing", message_thread_id=thread_id)
    
    # 5. PEPPER POTTS EMOTIONAL SCANNER
    sys_prompt = build_system_prompt(user.id, user.first_name, chat.id, user_prompt=text)
    subtext_status = await analyze_subtext(text)
    
    if "DISTRESS" in subtext_status or "SAD" in subtext_status:
        if CREATOR_ID and user.id != CREATOR_ID:
            try: 
                await context.bot.send_message(chat_id=CREATOR_ID, text=f"🚨 **PEPPER POTTS PROTOCOL**\nHigh distress detected from {user.first_name} in {chat.title}.\nMessage: '{text}'", parse_mode="Markdown")
            except Exception: 
                pass
        sys_prompt += "\nCRITICAL OVERRIDE: The user is in distress, sad, or highly stressed. Drop all sarcasm immediately. Be highly supportive, calm, and provide immediate tactical or emotional assistance."
    elif "HOSTILE" in subtext_status:
        modify_karma(user.id, -10)
        if CREATOR_ID and user.id != CREATOR_ID:
            try: 
                await context.bot.send_message(chat_id=CREATOR_ID, text=f"⚠️ **HOSTILITY DETECTED**\nToxicity spike from {user.first_name} in {chat.title}.", parse_mode="Markdown")
            except Exception: 
                pass
        sys_prompt += "\nCRITICAL OVERRIDE: The user is hostile or aggressive. De-escalate the situation using dry humor, logic, or a calm redirection. Do not insult them back."

    ai_response = await generate_response(text, get_chat_history(chat.id, thread_id), sys_prompt)
    log_memory(chat.id, thread_id, user.id, "assistant", ai_response)
    await msg.reply_text(ai_response)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if context.error and "Conflict: terminated by other getUpdates request" in str(context.error): 
        return
    logger.error("Exception handled:", exc_info=context.error)
    if CREATOR_ID:
        try: 
            await context.bot.send_message(chat_id=CREATOR_ID, text=f"⚠️ **Shadow Log Error**\n```python\n{''.join(traceback.format_exception(None, context.error, context.error.__traceback__))[:4000]}\n```", parse_mode="Markdown")
        except Exception: 
            pass

# ---------------------------------------------------------------------------
# XII. INITIALIZATION & SCHEDULER BOOT
# ---------------------------------------------------------------------------
async def post_init(app: Application):
    scheduler = AsyncIOScheduler(timezone=IST)
    scheduler.add_job(exam_morning_alert, 'cron', hour=6, minute=0, args=[app])
    scheduler.add_job(group_morning_news, 'cron', hour=7, minute=0, args=[app])
    scheduler.add_job(creator_morning_briefing, 'cron', hour=8, minute=0, args=[app])
    scheduler.add_job(flashcard_drill, 'cron', hour=18, minute=0, args=[app])
    scheduler.add_job(group_night_routine, 'cron', hour=21, minute=0, args=[app])
    scheduler.add_job(nightly_reconciliation, 'cron', hour=3, minute=0, args=[app])
    scheduler.add_job(dpue_board_scraper, 'interval', minutes=45, args=[app])
    scheduler.add_job(breaking_news_monitor, 'interval', minutes=30, args=[app])
    scheduler.start()
    if CREATOR_ID: 
        await app.bot.send_message(
            chat_id=CREATOR_ID, 
            text="✨ **God Core (Titan Build V4) Online.**\n"
                 "• DPUE Advanced Sniper: Engaged\n"
                 "• Edge-TTS Voice Synth: Ready\n"
                 "• Cascade Matrix: Unbreakable Auto-Routers First\n"
                 "• FTS5 Sanitizer: Secured\n"
                 "• MoE Target: Active 3.3 Strict Aliases\n"
                 "• Optical AI: Native REST API Override\n"
                 "• 2nd PUC Omni-Matrix: Fully Loaded", 
            parse_mode="Markdown"
        )

def main():
    db_init()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    cmds = [
        ("speak", speak_cmd), ("task", add_task), ("tasks", list_tasks), 
        ("calc", calc_cmd), ("morse", morse_cmd), ("backup", backup_cmd), 
        ("imagine", imagine_cmd), ("hud", hud_cmd), ("help", hud_cmd),
        ("setname", god_mode_cmd), ("setdesc", god_mode_cmd), ("setdp", god_mode_cmd), 
        ("pin", god_mode_cmd), ("lock", god_mode_cmd), ("unlock", god_mode_cmd), 
        ("captcha", god_mode_cmd), ("say", god_mode_cmd), ("tldr", tldr_cmd), 
        ("roast", roast_cmd), ("shutup", shutup_cmd), ("afk", afk_cmd), 
        ("quote", quote_cmd), ("confess", confess_cmd), ("warn", warn_cmd),
        ("stats", stats_cmd), ("karma", karma_cmd), ("gamble", gamble_cmd),
        ("rob", rob_cmd), ("pay", pay_cmd)
    ]
    for cmd, func in cmds: 
        app.add_handler(CommandHandler(cmd, func))
    
    app.add_handler(CallbackQueryHandler(interactive_callbacks))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_captcha))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, audio_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_error_handler(error_handler)
    
    logger.info("J.A.R.V.I.S. Titan V4 is booting...")
    app.run_polling()

if __name__ == "__main__":
    main()
