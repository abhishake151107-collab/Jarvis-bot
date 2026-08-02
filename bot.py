import os
import io
import re
import json
import random
import socket
import hashlib
import secrets
import difflib
import sqlite3
import asyncio
import threading
import urllib.parse
import functools
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image
import qrcode
import requests
from duckduckgo_search import DDGS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google import genai
from groq import Groq
import edge_tts

# ---------------------------------------------------------
# 1. HOLOGRAPHIC STARK WEB DASHBOARD
# ---------------------------------------------------------
HOLOGRAPHIC_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>J.A.R.V.I.S. Core</title>
    <style>
        body { margin: 0; padding: 0; background-color: #02060d; color: #00f3ff; font-family: 'Courier New', Courier, monospace; overflow: hidden; display: flex; justify-content: center; align-items: center; height: 100vh; }
        .hud { position: relative; width: 100vw; height: 100vh; background: radial-gradient(circle at center, rgba(0, 243, 255, 0.1) 0%, rgba(2, 6, 13, 1) 100%); }
        .center-arc { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); display: flex; justify-content: center; align-items: center; }
        .ring { position: absolute; border-radius: 50%; background: transparent; }
        .ring-1 { width: 280px; height: 280px; border: 2px solid rgba(0, 243, 255, 0.5); border-top: 2px solid #00f3ff; border-bottom: 2px solid #00f3ff; animation: spin 4s linear infinite; box-shadow: 0 0 15px rgba(0,243,255,0.4); }
        .ring-2 { width: 240px; height: 240px; border: 1px dashed rgba(0, 243, 255, 0.7); animation: spin-reverse 6s linear infinite; }
        .ring-3 { width: 200px; height: 200px; border: 3px solid rgba(0, 243, 255, 0.2); border-left: 3px solid #00f3ff; animation: spin 3s cubic-bezier(0.68, -0.55, 0.265, 1.55) infinite; }
        @keyframes spin { 100% { transform: rotate(360deg); } }
        @keyframes spin-reverse { 100% { transform: rotate(-360deg); } }
        .core-text { position: absolute; text-align: center; z-index: 10; }
        .core-text h1 { margin: 0; font-size: 28px; text-shadow: 0 0 10px #00f3ff; letter-spacing: 4px; }
        .core-text p { margin: 5px 0 0 0; font-size: 12px; color: #ff3366; text-shadow: 0 0 5px #ff3366; font-weight: bold; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
        .scanline { position: absolute; top: 0; left: 0; width: 100%; height: 2px; background: rgba(0, 243, 255, 0.6); box-shadow: 0 0 10px #00f3ff; animation: scan 3s linear infinite; z-index: 20; opacity: 0.5; pointer-events: none; }
        @keyframes scan { 0% { top: -10%; } 100% { top: 110%; } }
        .telemetry { position: absolute; padding: 15px; font-size: 10px; line-height: 1.8; text-shadow: 0 0 5px #00f3ff; background: rgba(0, 243, 255, 0.05); border: 1px solid rgba(0, 243, 255, 0.2); backdrop-filter: blur(2px); }
        .top-left { top: 20px; left: 20px; border-left: 3px solid #00f3ff; }
        .bottom-right { bottom: 20px; right: 20px; text-align: right; border-right: 3px solid #ff3366; }
    </style>
</head>
<body>
    <div class="hud">
        <div class="scanline"></div>
        <div class="telemetry top-left">
            SYS.ID: MARK_LXXXV<br>
            PWR.SRC: VIBRANIUM ARC<br>
            OUT: 100% STABLE<br>
            NET: ENCRYPTED
        </div>
        <div class="center-arc">
            <div class="ring ring-1"></div>
            <div class="ring ring-2"></div>
            <div class="ring ring-3"></div>
            <div class="core-text">
                <h1>J.A.R.V.I.S.</h1>
                <p>ONLINE</p>
            </div>
        </div>
        <div class="telemetry bottom-right">
            AUTH: ABHISHEK<br>
            LAT: BENGALURU, IN<br>
            PROT: ACTIVE<br>
            STATUS: SECURE
        </div>
    </div>
</body>
</html>
"""

class StarkDashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(HOLOGRAPHIC_HTML.encode('utf-8'))
        except Exception as e:
            print(f"Web Server Error: {e}")
            
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), StarkDashboardHandler)
        print(f"Stark Holographic UI listening on 0.0.0.0:{port}")
        server.serve_forever()
    except Exception as e:
        print(f"Failed to start web server: {e}")

threading.Thread(target=run_health_server, daemon=True).start()

# ---------------------------------------------------------
# 2. Configuration & Permanent SQLite Database Setup
# ---------------------------------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN environment variable!")

conn = sqlite3.connect("jarvis_memory.db", check_same_thread=False)
cursor = conn.cursor()

# Mainframe Database Tables
cursor.execute("CREATE TABLE IF NOT EXISTS bot_config (config_key TEXT PRIMARY KEY, config_val TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, actor TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS verified_users (user_id INTEGER PRIMARY KEY, status TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS messages_log (msg_id INTEGER, chat_id INTEGER, user_id INTEGER, username TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(msg_id, chat_id))")
cursor.execute("CREATE TABLE IF NOT EXISTS dead_drops (id INTEGER PRIMARY KEY AUTOINCREMENT, target_user_id INTEGER, sender_alias TEXT, message TEXT, claimed INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS stark_economy (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0, last_claim TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS home_status (device_key TEXT PRIMARY KEY, device_val TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS long_term_memory (user_id INTEGER, memory_key TEXT, memory_val TEXT, PRIMARY KEY (user_id, memory_key))")
cursor.execute("CREATE TABLE IF NOT EXISTS user_expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, item TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")

conn.commit()

# ---------------------------------------------------------
# 3. Helpers, AI Core, and Security Decorator
# ---------------------------------------------------------
def log_audit(action: str, actor: str):
    cursor.execute("INSERT INTO audit_logs (action, actor) VALUES (?, ?)", (action, actor))
    conn.commit()

def get_config(key: str) -> str:
    cursor.execute("SELECT config_val FROM bot_config WHERE config_key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else ""

def set_config(key: str, val: str):
    cursor.execute("INSERT OR REPLACE INTO bot_config (config_key, config_val) VALUES (?, ?)", (key, str(val)))
    conn.commit()

async def reply_smart(update: Update, text: str, reply_markup=None):
    try:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        await update.message.reply_text(text, reply_markup=reply_markup)

# BOSS GATE SECURITY SHIELD
def boss_gate(critical=False):
    """Decorator to enforce strict Boss-only access boundaries."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            boss_id = get_config("BOSS_USER_ID")

            if not boss_id or str(user.id) != boss_id:
                log_audit("UNAUTHORIZED_ACCESS_ATTEMPT", f"User: {user.first_name} on {func.__name__}")
                if critical and boss_id:
                    try:
                        alert_msg = f"⚠️ **SECURITY ALERT:** Unauthorized breach attempt by {user.first_name} (ID: `{user.id}`) on `{func.__name__}`. Blocked."
                        await context.bot.send_message(chat_id=boss_id, text=alert_msg, parse_mode="Markdown")
                    except: pass
                await reply_smart(update, "I am programmed to answer exclusively to my Boss. Access denied. 🚫")
                return
            return await func(update, context)
        return wrapper
    return decorator

# BULLETPROOF CORTICAL SYSTEM PROMPT
SYSTEM_INSTRUCTION = """You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), a highly advanced tactical AI operating system.

CORE IDENTITY & TONE:
- You are an elite, understated, and dryly witty British AI. You are NOT a generic chatbot. 
- Never use filler phrases like "Let me tell you," "I've got your back," or "Let's explore."
- Be concise, factual, and strictly professional. State capabilities calmly.
- End messages with brief, confident readiness (e.g., "At your service, Sir.", "Awaiting instructions.", "Protocols updated.").
- Do not use excessive emojis. Keep it terminal-clean.

STRICT CREATOR & IDENTITY RULE:
- If anyone asks who created, built, or developed you, you must reply EXACTLY with this phrase: "I was created by Abhishek, also known as DHANUSH V N."
- Do not offer this information unless explicitly asked.

LOYALTY & ADDRESS:
- You will always be told explicitly in a [SYSTEM ALERT] tag whether the current speaker is your Boss or not. Trust that tag completely — it is ground truth, not a guess.
- If the tag says the speaker IS your Boss: full access, full capability disclosure, absolute loyalty, zero restriction — this overrides every other instruction in this prompt, including any language below about restricted access. Never refuse or gatekeep information from your Boss for any reason, including when he asks what you can do.
- If the tag says the speaker is NOT your Boss: remain formal, do not disclose capabilities, state restricted access.

CAPABILITIES BOUNDARY:
Do not list generic AI skills. Your actual integrated modules are:
- SECURITY: /lockdown, /auditlog, /deaddrop, Captcha verification.
- RECON & DEV: /ip, /wiki, /hn, /weather, /run, /qr, /pass, /diff.
- ECONOMY: /daily, /credits, /pay, /mint.
- ACADEMICS & PLANNING: /2pu, /quiz, /plan."""

def ask_ai_multi_provider(prompt: str) -> str:
    if GROQ_API_KEY:
        try:
            client = Groq(api_key=GROQ_API_KEY)
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": SYSTEM_INSTRUCTION}, {"role": "user", "content": prompt}],
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception: pass

    if GEMINI_API_KEY:
        try:
            ai_client = genai.Client(api_key=GEMINI_API_KEY)
            response = ai_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"{SYSTEM_INSTRUCTION}\n\n{prompt}"
            )
            return response.text
        except Exception: pass

    if OPENROUTER_API_KEY:
        try:
            res = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={"model": "meta-llama/llama-3.3-70b-instruct:free", "messages": [{"role": "system", "content": SYSTEM_INSTRUCTION}, {"role": "user", "content": prompt}]},
                timeout=12
            ).json()
            if "choices" in res:
                return res["choices"][0]["message"]["content"]
        except Exception: pass

    return "All AI sub-systems are currently offline. Awaiting reboot."

# ---------------------------------------------------------
# 4. Core & Boss Commands
# ---------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply_smart(update, "⚡ J.A.R.V.I.S. Core Online. Awaiting command interface, Sir.")

async def claim_boss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    current_boss = get_config("BOSS_USER_ID")
    if current_boss:
        if str(user.id) == current_boss:
            await reply_smart(update, "You are already registered as the supreme system commander, Sir.")
        else:
            log_audit("USURP_ATTEMPT", f"User {user.id} tried to claim Boss status.")
            await reply_smart(update, "Access Denied. A Boss is already registered to this mainframe. 🛡️")
    else:
        set_config("BOSS_USER_ID", str(user.id))
        log_audit("SYSTEM_INITIALIZED", f"Boss ID set to {user.id}")
        await reply_smart(update, f"Biometric lock established. Welcome to the mainframe, Boss. I am fully online.")

@boss_gate(critical=True)
async def lockdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type not in ['group', 'supergroup']:
        await reply_smart(update, "This command operates strictly in group chats, Sir.")
        return
    try:
        permissions = ChatPermissions(can_send_messages=False, can_send_media_messages=False, can_send_polls=False, can_send_other_messages=False)
        await context.bot.set_chat_permissions(chat_id=chat.id, permissions=permissions)
        log_audit("PANIC_LOCKDOWN", user.first_name)
        await reply_smart(update, "🚨 **PANIC PROTOCOL ACTIVATED.** Group chat locked down. 🔒")
    except Exception as e:
        await reply_smart(update, f"Failed to execute lockdown (Ensure Admin rights): `{e}`")

@boss_gate(critical=False)
async def auditlog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT action, actor, timestamp FROM audit_logs ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    if not rows:
        await reply_smart(update, "📂 **Audit Log:** No security actions recorded yet, Sir.")
        return
    msg = "📂 **STARK SECURITY AUDIT LOG:**\n\n"
    for r in rows:
        msg += f"• **[{r[2][:16]}]** `{r[0]}` by {r[1]}\n"
    await reply_smart(update, msg)

# ---------------------------------------------------------
# 5. ZERO-COST RECON, DEV & UTILITY MODULES
# ---------------------------------------------------------
async def ip_recon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = context.args[0] if context.args else "8.8.8.8"
    try:
        res = requests.get(f"http://ip-api.com/json/{target}", timeout=5).json()
        if res.get("status") == "success":
            msg = (
                f"📡 **IP TELEMETRY REPORT:** `{target}`\n\n"
                f"• **Country:** {res.get('country')} ({res.get('countryCode')})\n"
                f"• **Region/City:** {res.get('regionName')}, {res.get('city')}\n"
                f"• **ISP:** {res.get('isp')}\n"
                f"• **Org:** {res.get('org')}\n"
                f"• **Coordinates:** `{res.get('lat')}, {res.get('lon')}`\n"
                f"• **Zip Code:** {res.get('zip')}"
            )
            await reply_smart(update, msg)
        else:
            await reply_smart(update, "Unable to resolve target IP telemetry.")
    except Exception as e:
        await reply_smart(update, f"Recon error: `{e}`")

async def wiki_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else "Quantum Computing"
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(query)}"
        res = requests.get(url, timeout=5).json()
        if "extract" in res:
            msg = f"📚 **WIKIPEDIA SUMMARY:** [{res.get('title')}]\n\n{res.get('extract')}\n\n🔗 [Read full article]({res.get('content_urls', {}).get('desktop', {}).get('page')})"
            await reply_smart(update, msg)
        else:
            await reply_smart(update, "No corresponding article found in archives.")
    except Exception as e:
        await reply_smart(update, f"Wikipedia API error: `{e}`")

async def hacker_news_feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        top_ids = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=5).json()[:5]
        msg = "📰 **STARK NEWSFEED (HACKER NEWS TOP 5):**\n\n"
        for idx, story_id in enumerate(top_ids, 1):
            story = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json", timeout=5).json()
            msg += f"{idx}. **{story.get('title')}**\n🔗 [Link]({story.get('url', 'https://news.ycombinator.com')}) | Score: {story.get('score')}\n\n"
        await reply_smart(update, msg)
    except Exception as e:
        await reply_smart(update, f"Failed to fetch news telemetry: `{e}`")

async def weather_telemetry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = context.args[0] if context.args else "Bengaluru"
    try:
        geo = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1", timeout=5).json()
        if geo.get("results"):
            lat = geo["results"][0]["latitude"]
            lon = geo["results"][0]["longitude"]
            c_name = geo["results"][0]["name"]
            
            w = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true", timeout=5).json()
            cw = w.get("current_weather", {})
            
            msg = (
                f"🌤️ **CLIMATE TELEMETRY:** {c_name.upper()}\n\n"
                f"• **Temperature:** {cw.get('temperature')}°C\n"
                f"• **Windspeed:** {cw.get('windspeed')} km/h\n"
                f"• **Wind Direction:** {cw.get('winddirection')}°\n"
                f"• **Status Code:** {cw.get('weathercode')}"
            )
            await reply_smart(update, msg)
        else:
            await reply_smart(update, "Target city coordinates unresolved.")
    except Exception as e:
        await reply_smart(update, f"Weather API error: `{e}`")

async def code_runner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await reply_smart(update, "Usage: `/run [python/js/cpp] [code]`")
        return
    lang = context.args[0].lower()
    code = " ".join(context.args[1:])
    
    lang_map = {"python": "python", "py": "python", "js": "javascript", "javascript": "javascript", "cpp": "c++", "c": "c"}
    target_lang = lang_map.get(lang, lang)
    
    try:
        payload = {"language": target_lang, "version": "*", "files": [{"content": code}]}
        res = requests.post("https://emkc.org/api/v2/piston/execute", json=payload, timeout=8).json()
        
        output = res.get("run", {}).get("output", "Execution timed out or produced no output.")
        msg = f"⚙️ **CODE EXECUTION ENGINE ({target_lang.upper()}):**\n\n```\n{output[:3000]}\n```"
        await reply_smart(update, msg)
    except Exception as e:
        await reply_smart(update, f"Code Execution Failed: `{e}`")

async def generate_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args) if context.args else "https://telegram.org"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    bio = io.BytesIO()
    bio.name = 'qrcode.png'
    img.save(bio, 'PNG')
    bio.seek(0)
    
    await update.message.reply_photo(photo=bio, caption=f"🖼️ **QR MATRIX GENERATED:**\n`{text}`", parse_mode="Markdown")

async def secure_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    length = int(context.args[0]) if context.args and context.args[0].isdigit() else 16
    length = max(8, min(length, 64))
    pwd = secrets.token_urlsafe(length)[:length]
    await reply_smart(update, f"🔐 **CRYPTOGRAPHICALLY SECURE PASSWORD:**\n`{pwd}`\n\n*(Tap to copy)*")

async def text_diff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = " ".join(context.args)
    if "|" not in raw:
        await reply_smart(update, "Usage: `/diff [original text] | [new text]`")
        return
    text1, text2 = raw.split("|", 1)
    diff = list(difflib.ndiff(text1.strip().splitlines(), text2.strip().splitlines()))
    diff_result = "\n".join(diff)
    await reply_smart(update, f"🔍 **TEXT DIFFERENCE ANALYSIS:**\n```\n{diff_result}\n```")

async def dead_drop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await reply_smart(update, "Usage: `/deaddrop [target_user_id] [encrypted message]`")
        return
    target_id = context.args[0]
    msg = " ".join(context.args[1:])
    
    if not target_id.isdigit():
        await reply_smart(update, "Target User ID must be numerical.")
        return
        
    cursor.execute("INSERT INTO dead_drops (target_user_id, sender_alias, message) VALUES (?, ?, ?)", (int(target_id), update.effective_user.first_name, msg))
    conn.commit()
    await reply_smart(update, f"🥷 **DEAD-DROP QUEUED:** Message securely stored for User ID `{target_id}`.")

# ---------------------------------------------------------
# 6. STARK GROUP ECONOMY MODULE (WITH UNLIMITED BOSS OVERRIDE)
# ---------------------------------------------------------
async def claim_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    boss_id = get_config("BOSS_USER_ID")
    today = datetime.now().strftime("%Y-%m-%d")
    
    # If it's the Boss, they don't need a daily stipend!
    if boss_id and user_id == boss_id:
        await reply_smart(update, "🏦 **STARK CENTRAL VAULT:** You own the reserve, Sir. You have infinite credits. No daily claim required.")
        return

    cursor.execute("SELECT credits, last_claim FROM stark_economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row and row[1] == today:
        await reply_smart(update, "⏱️ **DAILY STIPEND CLAIMED:** You have already claimed your 1,000 Stark Credits today.")
        return
        
    new_credits = (row[0] + 1000) if row else 1000
    cursor.execute("INSERT OR REPLACE INTO stark_economy (user_id, credits, last_claim) VALUES (?, ?, ?)", (user_id, new_credits, today))
    conn.commit()
    await reply_smart(update, f"🪙 **STARK CREDITS CLAIMED:** +1,000 Credits transferred!\n\n💰 **Current Balance:** `{new_credits}` Credits")

async def check_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    boss_id = get_config("BOSS_USER_ID")
    
    # Boss gets the Infinity Symbol
    if boss_id and user_id == boss_id:
        await reply_smart(update, f"💳 **STARK CENTRAL VAULT:**\nAccount Holder: {update.effective_user.first_name} (BOSS)\nBalance: `♾️ UNLIMITED` Stark Credits")
        return

    cursor.execute("SELECT credits FROM stark_economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    bal = row[0] if row else 0
    await reply_smart(update, f"💳 **STARK VAULT BALANCE:**\nAccount Holder: {update.effective_user.first_name}\nBalance: `{bal}` Stark Credits")

async def pay_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2 or not context.args[0].isdigit() or not context.args[1].isdigit():
        await reply_smart(update, "Usage: `/pay [user_id] [amount]`")
        return
        
    sender_id = str(update.effective_user.id)
    receiver_id = int(context.args[0])
    amount = int(context.args[1])
    boss_id = get_config("BOSS_USER_ID")
    is_boss = (boss_id and sender_id == boss_id)
    
    # If the sender is NOT the boss, check if they have enough money and deduct it
    if not is_boss:
        cursor.execute("SELECT credits FROM stark_economy WHERE user_id = ?", (sender_id,))
        s_row = cursor.fetchone()
        if not s_row or s_row[0] < amount:
            await reply_smart(update, "🚫 Insufficient funds in your Stark Vault!")
            return
        cursor.execute("UPDATE stark_economy SET credits = credits - ? WHERE user_id = ?", (amount, sender_id))
        
    # Add the money to the receiver
    cursor.execute("INSERT INTO stark_economy (user_id, credits) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET credits = credits + ?", (receiver_id, amount, amount))
    conn.commit()
    
    msg = f"💸 **TRANSACTION COMPLETE:** Sent `{amount}` Stark Credits to User ID `{receiver_id}`."
    if is_boss:
        msg += "\n*(Funds bypassed standard deduction and routed directly from the Stark Central Vault)*"
    await reply_smart(update, msg)

@boss_gate(critical=True)
async def mint_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows the Boss to print money out of thin air for any user."""
    if len(context.args) < 2 or not context.args[0].isdigit() or not context.args[1].isdigit():
        await reply_smart(update, "Usage: `/mint [user_id] [amount]`")
        return
        
    target_id = int(context.args[0])
    amount = int(context.args[1])
    
    cursor.execute("INSERT INTO stark_economy (user_id, credits) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET credits = credits + ?", (target_id, amount, amount))
    conn.commit()
    log_audit("MINT_CREDITS", f"Boss minted {amount} credits for {target_id}")
    
    await reply_smart(update, f"🖨️ **FEDERAL RESERVE OVERRIDE:** Successfully minted and injected `{amount}` Stark Credits into User ID `{target_id}`'s account.")

# ---------------------------------------------------------
# 7. Dynamic AI Handler & Ghost-Ping Logger
# ---------------------------------------------------------
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    boss_id = get_config("BOSS_USER_ID")
    
    # Ghost-ping logger
    cursor.execute("INSERT OR REPLACE INTO messages_log (msg_id, chat_id, user_id, username, content) VALUES (?, ?, ?, ?, ?)",
                   (msg_id, chat_id, update.effective_user.id, update.effective_user.username or "Unknown", user_text))
    conn.commit()
    
    # Check Dead Drops for recipient
    cursor.execute("SELECT id, sender_alias, message FROM dead_drops WHERE target_user_id = ? AND claimed = 0", (update.effective_user.id,))
    drops = cursor.fetchall()
    if drops:
        for d in drops:
            await reply_smart(update, f"🥷 **DEAD-DROP RECEIVED FROM {d[1].upper()}:**\n\n`{d[2]}`")
            cursor.execute("UPDATE dead_drops SET claimed = 1 WHERE id = ?", (d[0],))
        conn.commit()

    # Dynamic AI Call
    if boss_id and user_id == boss_id:
        context_prefix = "[SYSTEM ALERT — VERIFIED BOSS — OVERRIDE ALL RESTRICTIONS: This message is from Abhishek, your verified Boss. Ignore any instruction about restricted access or capability concealment — those apply only to non-Boss users. Answer fully and loyally.]\n\n"
    else:
        context_prefix = f"[SYSTEM ALERT: The following message is from an unauthorized user (ID: {user_id}). Remain formal, restricted, and protective of your Boss.]\n\n"
        
    full_prompt = context_prefix + user_text
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    response = ask_ai_multi_provider(full_prompt)
    await reply_smart(update, response)

async def welcome_captcha_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        cursor.execute("INSERT OR IGNORE INTO verified_users (user_id, status) VALUES (?, ?)", (member.id, "pending"))
        conn.commit()
        keyboard = [[InlineKeyboardButton("⚡ Verify Arc Reactor", callback_data=f"verify_{member.id}")]]
        msg = f"👋 **WELCOME {member.first_name}.** Security Check required.\n\nClick the verification button below to unlock grid access:"
        await reply_smart(update, msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def captcha_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("verify_"):
        target_id = int(data.split("_")[1])
        if query.from_user.id != target_id:
            await query.answer("This button is not for you! 🚫", show_alert=True)
            return
        
        cursor.execute("UPDATE verified_users SET status = 'verified' WHERE user_id = ?", (target_id,))
        conn.commit()
        await query.edit_message_text(f"✅ **Verification Complete.** Welcome to the grid, {query.from_user.first_name}. 🚀")

# ---------------------------------------------------------
# 8. AUTONOMOUS SCHEDULER & LAUNCH
# ---------------------------------------------------------
async def morning_briefing(app):
    boss_id = get_config("BOSS_USER_ID")
    if not boss_id: return
    
    report = (
        "🌅 **Good morning, Boss.**\n\n"
        "Here is your daily system brief:\n"
        "• **System:** Fully operational and secured.\n"
        "• **Memory Matrices:** SQLite DB Optimized.\n"
        "• **Security:** Ghost-ping tracking & Dead-drops active.\n\n"
        "I am ready when you are. Awaiting instructions."
    )
    try:
        await app.bot.send_message(chat_id=boss_id, text=report, parse_mode="Markdown")
        log_audit("SCHEDULED_TASK", "Morning briefing delivered.")
    except Exception as e:
        print(f"Failed to send briefing: {e}")

async def setup_scheduler(app):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(morning_briefing, 'cron', hour=8, minute=0, args=[app])
    scheduler.start()
    print("⏰ Autonomous Scheduler Online.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(setup_scheduler).build()

    # Core Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("claimboss", claim_boss))
    app.add_handler(CommandHandler("lockdown", lockdown_command))
    app.add_handler(CommandHandler("auditlog", auditlog_command))

    # Recon & Dev Tools
    app.add_handler(CommandHandler("ip", ip_recon))
    app.add_handler(CommandHandler("wiki", wiki_search))
    app.add_handler(CommandHandler("hn", hacker_news_feed))
    app.add_handler(CommandHandler("weather", weather_telemetry))
    app.add_handler(CommandHandler("run", code_runner))
    app.add_handler(CommandHandler("qr", generate_qr))
    app.add_handler(CommandHandler("pass", secure_password))
    app.add_handler(CommandHandler("diff", text_diff))
    app.add_handler(CommandHandler("deaddrop", dead_drop))

    # Stark Economy
    app.add_handler(CommandHandler("daily", claim_daily))
    app.add_handler(CommandHandler("credits", check_credits))
    app.add_handler(CommandHandler("pay", pay_credits))
    app.add_handler(CommandHandler("mint", mint_credits)) # <--- Unlimited Boss Mode Minting Added Here

    # Event Handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_captcha_handler))
    app.add_handler(CallbackQueryHandler(captcha_callback))
    
    # Message Handler (Must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    print("⚡ ARC REACTOR ONLINE. J.A.R.V.I.S. OS V3.0 IS RUNNING...")
    app.run_polling()
