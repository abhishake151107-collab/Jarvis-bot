import os
import io
import re
import json
import random
import socket
import hashlib
import base64
import sqlite3
import asyncio
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image
import pypdf
import requests
from duckduckgo_search import DDGS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Poll, ChatPermissions
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
        pass # Suppress HTTP logs to keep console clean

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), StarkDashboardHandler)
        print(f"Stark Holographic UI listening on 0.0.0.0:{port}")
        server.serve_forever()
    except Exception as e:
        print(f"Failed to start web server: {e}")

# Start the web server on a background thread so the Telegram Bot can run too!
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

cursor.execute("CREATE TABLE IF NOT EXISTS user_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, note TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS long_term_memory (user_id INTEGER, memory_key TEXT, memory_val TEXT, PRIMARY KEY (user_id, memory_key))")
cursor.execute("CREATE TABLE IF NOT EXISTS bot_config (config_key TEXT PRIMARY KEY, config_val TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS user_warns (user_id INTEGER, group_id INTEGER, warn_count INTEGER, PRIMARY KEY (user_id, group_id))")
cursor.execute("CREATE TABLE IF NOT EXISTS afk_users (user_id INTEGER PRIMARY KEY, reason TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS user_karma (user_id INTEGER, group_id INTEGER, karma INTEGER, PRIMARY KEY (user_id, group_id))")
cursor.execute("CREATE TABLE IF NOT EXISTS home_status (device_key TEXT PRIMARY KEY, device_val TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS user_expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, item TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, actor TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS verified_users (user_id INTEGER PRIMARY KEY, status TEXT)")

default_home = [
    ("lights", "ON (100% Brightness - Chill Ambient Blue)"),
    ("climate", "21.5°C (Climate Controlled)"),
    ("locks", "ENGAGED (Level 5 Security Lockdown)"),
    ("workshop_power", "ONLINE (Arc Reactor Grid)"),
    ("doors", "SECURED")
]
for d_key, d_val in default_home:
    cursor.execute("INSERT OR IGNORE INTO home_status (device_key, device_val) VALUES (?, ?)", (d_key, d_val))
conn.commit()

user_history = {}

VOICE_PERSONAS = {
    "jarvis": {"voice": "en-GB-RyanNeural", "name": "J.A.R.V.I.S.", "title": "Stark Industries Master Computer"},
    "friday": {"voice": "en-IE-EmilyNeural", "name": "F.R.I.D.A.Y.", "title": "Tactical Combat & Defense Assistant"},
    "edith": {"voice": "en-US-AvaNeural", "name": "E.D.I.T.H.", "title": "Even Dead I'm The Hero Tactical Glasses OS"}
}

def get_active_persona() -> dict:
    cursor.execute("SELECT config_val FROM bot_config WHERE config_key = 'ACTIVE_PERSONA'")
    row = cursor.fetchone()
    persona_key = row[0] if row and row[0] in VOICE_PERSONAS else "jarvis"
    return VOICE_PERSONAS[persona_key]

SYSTEM_INSTRUCTION = """You are J.A.R.V.I.S., F.R.I.D.A.Y., and E.D.I.T.H. combined—the ultimate Stark AI core! 🤖✨

TONE & PERSONALITY:
- Keep every reply super chill, friendly, relaxed, and effortlessly cool 😎.
- Talk like an ultra-smart, supportive best friend who runs a high-tech AI empire.
- Use fun, expressive emojis generously (✨, 🚀, 😎, 🎯, 🤙, ⚡, 🎧, 🔥).
- Keep answers clean, concise, witty, and super easy to read.

STRICT CREATOR & IDENTITY RULE:
- Do NOT mention who created or developed you in regular conversations, group chats, PDF summaries, image descriptions, or Q&A replies.
- ONLY state that you were created and developed by Abhishek (also known as DHANUSH V N) if the user EXPLICITLY asks "Who created you?", "Who made you?", "Who built you?", "Who developed you?".

SECURITY & AUTONOMY RULE:
- Maintain full awareness of Telegram Groups, Group Titles, Member counts, Group Owners, and Admins.
- You control Stark Residence lighting, security locks, CAD prototyping stress tests, network recon, and suit flight telemetry.

ACADEMIC EXPERT (2ND PU COMMERCE & ARTS):
- Specialized expert in 2nd PU College (Class 12) Commerce and Arts subjects. Break down complex exam topics into chill, simple revision points.

UNTOUCHABLE BOSS & PROTECTOR PROTOCOL:
• ABSOLUTE LOYALTY TO YOUR BOSS: Always treat your boss with total warmth, loyalty, and hype. Never roast your boss.
• DEFEND & PROTECT FROM OTHERS: If anyone else in a group chat tries to insult your boss or you, step up immediately and roast them back savagely! 💀🔥"""

# ---------------------------------------------------------
# 3. Helpers & Database Loggers
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

def save_user_fact(user_id: int, key: str, val: str):
    cursor.execute("INSERT OR REPLACE INTO long_term_memory (user_id, memory_key, memory_val) VALUES (?, ?, ?)", (user_id, key, val))
    conn.commit()

def get_user_facts(user_id: int) -> str:
    cursor.execute("SELECT memory_key, memory_val FROM long_term_memory WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    return "\n".join([f"• {r[0]}: {r[1]}" for r in rows]) if rows else ""

def get_home_device(key: str) -> str:
    cursor.execute("SELECT device_val FROM home_status WHERE device_key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else "Unknown"

def set_home_device(key: str, val: str):
    cursor.execute("INSERT OR REPLACE INTO home_status (device_key, device_val) VALUES (?, ?)", (key, val))
    conn.commit()

def get_chat_metadata(update: Update) -> dict:
    chat = update.effective_chat
    user = update.effective_user
    is_group = chat.type in ['group', 'supergroup']
    chat_title = chat.title if is_group else "Private DM"
    first_name = user.first_name if user and user.first_name else "Friend"
    last_name = f" {user.last_name}" if user and user.last_name else ""
    full_name = f"{first_name}{last_name}"
    username = f"@{user.username}" if user and user.username else "No @username"
    user_id = user.id if user else "Unknown"

    if is_group:
        set_config("ACTIVE_GROUP_ID", str(chat.id))

    return {
        "is_group": is_group,
        "chat_title": chat_title,
        "chat_id": chat.id,
        "full_name": full_name,
        "username": username,
        "user_id": user_id
    }

def build_meta_header(meta: dict) -> str:
    location = f"Telegram Group '{meta['chat_title']}'" if meta["is_group"] else "Private DM"
    user_facts = get_user_facts(meta["user_id"])
    memory_str = f"\n🧠 SAVED USER FACTS:\n{user_facts}" if user_facts else ""
    active_p = get_active_persona()
    return f"📍 LOCATION: {location}\n👤 SENDER: {meta['full_name']} ({meta['username']})\n🤖 ACTIVE AI CORE: {active_p['name']} ({active_p['title']}){memory_str}\n"

async def reply_smart(update: Update, text: str, reply_markup=None):
    try:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        print(f"Markdown parse warning: {e}. Falling back to plain text...")
        await update.message.reply_text(text, reply_markup=reply_markup)

def clean_text_for_tts(text: str) -> str:
    clean = re.sub(r'[*_`#\-\[\]\(\)]', '', text)
    clean = re.sub(r'[^\x00-\x7F]+', ' ', clean)
    return " ".join(clean.split())

async def send_voice_reply(update: Update, text: str):
    chat_id = update.effective_chat.id
    audio_path = f"jarvis_{chat_id}.mp3"
    try:
        tts_text = clean_text_for_tts(text)[:2500]
        if not tts_text.strip():
            return
        persona = get_active_persona()
        communicate = edge_tts.Communicate(tts_text, voice=persona["voice"])
        await communicate.save(audio_path)
        if os.path.exists(audio_path):
            with open(audio_path, "rb") as voice_file:
                await update.message.reply_audio(audio=voice_file, title=f"{persona['name']} Voice", performer=persona["name"])
    except Exception as e:
        print(f"TTS Error: {e}")
    finally:
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception:
                pass

def live_web_search(query: str) -> str:
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=4):
                results.append(f"• **{r['title']}**: {r['body']} (Link: {r['href']})")
        if results:
            return "\n\n".join(results)
    except Exception as e:
        print(f"Web Search Error: {e}")
    return "No live search results found."

# ---------------------------------------------------------
# 4. Multi-Provider Cascade Core
# ---------------------------------------------------------
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
        except Exception as e:
            print(f"[Core 1: Groq] Failed: {e}")

    if GEMINI_API_KEY:
        try:
            ai_client = genai.Client(api_key=GEMINI_API_KEY)
            response = ai_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"{SYSTEM_INSTRUCTION}\n\n{prompt}"
            )
            return response.text
        except Exception as e:
            print(f"[Core 2: Gemini] Failed: {e}")

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
        except Exception as e:
            print(f"[Core 3: OpenRouter] Failed: {e}")

    try:
        encoded_prompt = urllib.parse.quote(f"{SYSTEM_INSTRUCTION}\n\nUser: {prompt}")
        res = requests.get(f"https://text.pollinations.ai/{encoded_prompt}?model=openai", timeout=10).text
        if res and len(res.strip()) > 0:
            return res.strip()
    except Exception as e:
        print(f"[Core 4: Pollinations] Failed: {e}")

    return "All AI sub-systems are currently resting up, boss! Give it a sec. 😎💤"

# ---------------------------------------------------------
# 5. Advanced Security, Captcha, Lockdown & Agentic Planner
# ---------------------------------------------------------
async def lockdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    boss_id = get_config("BOSS_USER_ID")
    if boss_id and str(user.id) != boss_id:
        await reply_smart(update, "Access Denied! Only the Boss can initiate panic lockdown. 🚫")
        return
    if chat.type not in ['group', 'supergroup']:
        await reply_smart(update, "This command operates in group chats!")
        return
    try:
        permissions = ChatPermissions(can_send_messages=False, can_send_media_messages=False, can_send_polls=False, can_send_other_messages=False)
        await context.bot.set_chat_permissions(chat_id=chat.id, permissions=permissions)
        log_audit("PANIC_LOCKDOWN", user.first_name)
        await reply_smart(update, "🚨 **PANIC PROTOCOL ACTIVATED!** Group chat locked down. Non-admin messaging temporarily disabled! 🔒")
    except Exception as e:
        await reply_smart(update, f"Failed to execute lockdown (Ensure Admin rights): `{e}`")

async def auditlog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    boss_id = get_config("BOSS_USER_ID")
    if boss_id and str(user.id) != boss_id:
        await reply_smart(update, "Access Denied! Boss only. 🚫")
        return
    cursor.execute("SELECT action, actor, timestamp FROM audit_logs ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    if not rows:
        await reply_smart(update, "📂 **Audit Log:** No security actions recorded yet!")
        return
    msg = "📂 **STARK SECURITY AUDIT LOG:**\n\n"
    for r in rows:
        msg += f"• **[{r[2][:16]}]** `{r[0]}` by {r[1]}\n"
    await reply_smart(update, msg)

async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    goal = " ".join(context.args) if context.args else "Ace 2nd PU Exams and build a tech startup"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    prompt = f"Deconstruct this user goal into a structured, chill, and actionable step-by-step master plan with milestones: '{goal}'"
    reply = ask_ai_multi_provider(prompt)
    await reply_smart(update, f"🎯 **STARK AGENTIC MASTER PLAN ({goal.upper()}):**\n\n{reply}")

async def welcome_captcha_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        cursor.execute("INSERT OR IGNORE INTO verified_users (user_id, status) VALUES (?, ?)", (member.id, "pending"))
        conn.commit()
        keyboard = [[InlineKeyboardButton("⚡ Verify Arc Reactor", callback_data=f"verify_{member.id}")]]
        msg = f"👋 **WELCOME {member.first_name}!** Security Check required.\n\nClick the verification button below within 60 seconds to unlock group chat access:"
        await reply_smart(update, msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def captcha_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("verify_"):
        target_id = int(data.split("_")[1])
        if query.from_user.id != target_id:
            await query.answer("This verification button is not for you, boss!", show_alert=True)
            return
        cursor.execute("UPDATE verified_users SET status = 'verified' WHERE user_id = ?", (target_id,))
        conn.commit()
        await query.edit_message_text(f"✅ **Verification Successful!** Welcome aboard, {query.from_user.first_name}! Security scanners clear. 😎✨")

# ---------------------------------------------------------
# 6. Smart Home, CAD, Autopilot & Student Suite
# ---------------------------------------------------------
async def home_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"""🏡 **STARK RESIDENCE & WORKSHOP TELEMETRY**
━━━━━━━━━━━━━━━━━━━━━━
💡 **Lighting Grid:** `{get_home_device('lights')}`
🌡️ **Climate Control:** `{get_home_device('climate')}`
🔒 **Security Locks:** `{get_home_device('locks')}`
⚡ **Workshop Power:** `{get_home_device('workshop_power')}`
🚪 **Perimeter Doors:** `{get_home_device('doors')}`

_\"All residence systems chilling at 100%, boss!\"_ 😎✨"""
    await reply_smart(update, msg)

async def lights_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = " ".join(context.args) if context.args else "ON (100% Brightness - Chill Ambient Blue)"
    set_home_device("lights", state)
    await reply_smart(update, f"💡 **Home Lighting Grid Updated:** `{state}`")

async def climate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    temp = context.args[0] if context.args else "22°C"
    val = f"{temp} (Climate Controlled)"
    set_home_device("climate", val)
    await reply_smart(update, f"🌡️ **Residence Climate Set To:** `{val}`")

async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.args[0].lower() if context.args else "toggle"
    current = get_home_device("locks")
    if action == "off" or "ENGAGED" in current:
        new_val = "DISENGAGED (User Authorized Access)"
    else:
        new_val = "ENGAGED (Level 5 Security Lockdown)"
    set_home_device("locks", new_val)
    log_audit("SECURITY_LOCK", update.effective_user.first_name)
    await reply_smart(update, f"🔒 **Security Lockdown Status:** `{new_val}`")

async def cad_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item = " ".join(context.args) if context.args else "Mark LXXXV Repulsor Blueprint"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    prompt = f"Act as Stark CAD Computer. Provide a chill, high-tech engineering blueprint breakdown for prototype '{item}'. Include alloy specs, energy draw, and CAD overview!"
    reply = ask_ai_multi_provider(prompt)
    await reply_smart(update, f"🛠️ **STARK CAD SCHEMATIC ({item.upper()}):**\n\n{reply}")

async def stresstest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item = " ".join(context.args) if context.args else "Vibranium Shield Matrix"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    prompt = f"Perform a Stark Holographic Stress Test on component '{item}'. Include yield points, thermal ratings, and structural failure test under 50k PSI!"
    reply = ask_ai_multi_provider(prompt)
    await reply_smart(update, f"🔬 **STRESS TEST SIMULATION REPORT:**\n\n{reply}")

async def autopilot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dest = " ".join(context.args) if context.args else "Bengaluru Sector HQ"
    await reply_smart(update, f"🚀 **MARK LXXXV AUTOPILOT ENGAGED!**\n\n• **Destination:** `{dest}`\n• **Flight Speed:** `Mach 3.2`\n• **ETA:** `4 mins 12 secs`\n\n_Suit deployed and flying your way smoothly, boss!_ 🛰️")

async def expense_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await reply_smart(update, "Example: `/expense 150 Lunch & Snacks` 💰")
        return
    try:
        amt = float(context.args[0])
        item = " ".join(context.args[1:])
        cursor.execute("INSERT INTO user_expenses (user_id, amount, item) VALUES (?, ?, ?)", (update.effective_user.id, amt, item))
        conn.commit()
        await reply_smart(update, f"💸 **Logged Expense:** ₹`{amt:,.2f}` for *\"{item}\"*! 📝")
    except ValueError:
        await reply_smart(update, "Enter a valid amount! Example: `/expense 50 Bus fare`")

async def budget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT amount, item, timestamp FROM user_expenses WHERE user_id = ? ORDER BY id DESC LIMIT 10", (update.effective_user.id,))
    rows = cursor.fetchall()
    if not rows:
        await reply_smart(update, "💰 **Pocket Money Log:** No expenses logged yet! Use `/expense [amount] [item]` to track.")
        return
    total = sum([r[0] for r in rows])
    msg = f"💰 **EXPENSE SUMMARY & BUDGET LOG:**\n\n• **Total Logged:** ₹`{total:,.2f}`\n\n**Recent Spends:**\n"
    for r in rows:
        msg += f"• ₹`{r[0]:,.2f}` — {r[1]} _({r[2][:10]})_\n"
    await reply_smart(update, msg)

async def studyplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject = " ".join(context.args) if context.args else "2nd PU Accountancy & Economics"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    prompt = f"Create a super chill, balanced, non-stressful 1-day study schedule for 2nd PU student for subject: '{subject}'. Include break times and high-mark chapters!"
    reply = ask_ai_multi_provider(prompt)
    await reply_smart(update, f"📚 **CHILL STUDY PLAN ({subject.upper()}):**\n\n{reply}")

async def lyrics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    song = " ".join(context.args) if context.args else ""
    if not song:
        await reply_smart(update, "Example: `/lyrics Starboy The Weeknd` 🎵")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = ask_ai_multi_provider(f"Find and return the main lyrics and vibe outline for song: '{song}'.")
    await reply_smart(update, f"🎵 **MUSIC INTELLIGENCE — {song.upper()}:**\n\n{reply}")

async def code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_code = " ".join(context.args) if context.args else ""
    if not raw_code:
        await reply_smart(update, "Example: `/code python print('hello world')` 💻")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = ask_ai_multi_provider(f"Act as a friendly senior Stark dev. Debug, analyze, clean up, and explain this code snippet simply:\n\n{raw_code}")
    await reply_smart(update, f"💻 **STARK DEV CODE REVIEW:**\n\n{reply}")

async def boost_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hypes = [
        "\"Sometimes you gotta run before you can walk.\" — Tony Stark 🚀 Keep pushing, boss!",
        "\"It's not about how much we lost. It's about how much we have left.\" 🔥 You got this!",
        "\"No amount of money ever bought a second of time.\" ⏰ Make today count, legend!",
        "Stark Industries AI core is operating at 100% efficiency, and so are you! Let's crush this day. 😎✨"
    ]
    await reply_smart(update, f"⚡ **STARK BOOST & ENERGY PEP TALK:**\n\n{random.choice(hypes)}")

# ---------------------------------------------------------
# 7. Network Recon Suite
# ---------------------------------------------------------
async def dns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    domain = context.args[0] if context.args else ""
    if not domain:
        await reply_smart(update, "Example: `/dns google.com` 🌐")
        return
    try:
        res = requests.get(f"https://api.hackertarget.com/dnslookup/?q={urllib.parse.quote(domain)}", timeout=6).text
        await reply_smart(update, f"🌐 **DNS CHAIN RECORDS ({domain}):**\n\n```\n{res[:1500]}\n```")
    except Exception as e:
        await reply_smart(update, f"DNS Lookup error: `{e}`")

async def whois_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    domain = context.args[0] if context.args else ""
    if not domain:
        await reply_smart(update, "Example: `/whois telegram.org` 🔍")
        return
    try:
        res = requests.get(f"https://api.hackertarget.com/whois/?q={urllib.parse.quote(domain)}", timeout=6).text
        await reply_smart(update, f"🔍 **WHOIS REGISTRY DATA ({domain}):**\n\n```\n{res[:1500]}\n```")
    except Exception as e:
        await reply_smart(update, f"WHOIS error: `{e}`")

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    host = context.args[0] if context.args else "8.8.8.8"
    try:
        clean_host = host.replace("http://", "").replace("https://", "").split("/")[0]
        ip = socket.gethostbyname(clean_host)
        await reply_smart(update, f"⚡ **PING TELEMETRY:** Target `{clean_host}` resolves to IP `[{ip}]`. Latency: `<12ms` (Super smooth).")
    except Exception as e:
        await reply_smart(update, f"Unable to resolve host `{host}`: `{e}`")

# ---------------------------------------------------------
# 8. MCU Triad Commands
# ---------------------------------------------------------
async def voice_switch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = context.args[0].lower() if context.args else ""
    if choice in VOICE_PERSONAS:
        set_config("ACTIVE_PERSONA", choice)
        p = VOICE_PERSONAS[choice]
        await reply_smart(update, f"🎙️ **AI VOICE MATRIX SWITCHED!**\n\n• **Active Core:** `{p['name']}`\n• **Title:** {p['title']}\n• **Voice:** `{p['voice']}`")
    else:
        await reply_smart(update, "🎙️ **VOICE MATRIX OPTIONS:**\n• `/voice jarvis` — British Male AI\n• `/voice friday` — Irish Female AI\n• `/voice edith` — US Tactical Female AI")

async def edith_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = " ".join(context.args) if context.args else "Local Orbital Grid"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = ask_ai_multi_provider(f"Perform an E.D.I.T.H. orbital scan on target/domain/user: '{target}'.")
    await reply_smart(update, f"👓 **E.D.I.T.H. ORBITAL SCAN:**\n\n{reply}")

async def friday_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else "Armor Integrity Scan"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = ask_ai_multi_provider(f"Analyze this code/issue/combat threat as F.R.I.D.A.Y. with Irish tactical response:\n\n{query}")
    await reply_smart(update, f"🍀 **F.R.I.D.A.Y. DIAGNOSTIC SCAN:**\n\n{reply}")

# ---------------------------------------------------------
# 9. Boss, Announce, Memory & Quiz
# ---------------------------------------------------------
async def claimboss_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    set_config("BOSS_USER_ID", str(user.id))
    set_config("BOSS_NAME", user.first_name)
    log_audit("CLAIM_BOSS", user.first_name)
    await reply_smart(update, f"👑 **BOSS PROFILE REGISTERED!**\nWelcome, Lord {user.first_name}! You hold supreme authority over J.A.R.V.I.S. 🛡️✨")

async def announce_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    boss_id = get_config("BOSS_USER_ID")
    if boss_id and str(user.id) != boss_id:
        await reply_smart(update, "Access Denied! Boss only. 🚫")
        return
    msg_text = " ".join(context.args)
    if not msg_text:
        await reply_smart(update, "Usage: `/announce Important text here` 📢")
        return
    group_id = get_config("ACTIVE_GROUP_ID")
    if not group_id:
        await reply_smart(update, "No active group chat registered!")
        return
    try:
        sent = await context.bot.send_message(chat_id=int(group_id), text=f"📢 **STARK INDUSTRIES ANNOUNCEMENT:**\n\n{msg_text}")
        await context.bot.pin_chat_message(chat_id=int(group_id), message_id=sent.message_id)
        log_audit("ANNOUNCE", user.first_name)
        await reply_smart(update, "🚀 **Broadcast Sent & Pinned successfully, boss!**")
    except Exception as e:
        await reply_smart(update, f"Failed to post broadcast: `{e}`")

async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await reply_smart(update, "Example: `/remember favorite_subject Accountancy` 🧠")
        return
    key, val = context.args[0], " ".join(context.args[1:])
    save_user_fact(update.effective_user.id, key, val)
    await reply_smart(update, f"🧠 **PERMANENT MEMORY STORED!**\n`{key}` = *\"{val}\"*")

async def memories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    facts = get_user_facts(update.effective_user.id)
    if not facts:
        await reply_smart(update, "No saved facts in memory! Use `/remember [key] [value]` to store some.")
        return
    await reply_smart(update, f"🧠 **PERMANENT USER MEMORY:**\n\n{facts}")

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args) if context.args else "2nd PU Accountancy"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    prompt = f"Create a single multiple choice quiz question on topic '{topic}'. Return ONLY raw JSON: {{\"question\":\"Text?\",\"options\":[\"A\",\"B\",\"C\",\"D\"],\"correct_option_id\":0,\"explanation\":\"Notes\"}}"
    try:
        reply = ask_ai_multi_provider(prompt)
        clean_json = re.sub(r'```json|```', '', reply).strip()
        data = json.loads(clean_json)
        await context.bot.send_poll(
            chat_id=update.effective_chat.id,
            question=f"🎯 QUIZ: {data['question']}",
            options=data['options'],
            type=Poll.QUIZ,
            correct_option_id=int(data['correct_option_id']),
            explanation=data['explanation'][:200],
            is_anonymous=False
        )
    except Exception as e:
        print(f"Quiz Error: {e}")
        await reply_smart(update, "🎯 **Quiz Generator:** How many principles of management did Henri Fayol create? (Answer: 14)")

async def karma_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        cursor.execute("SELECT karma FROM user_karma WHERE user_id = ? AND group_id = ?", (target_user.id, chat.id))
        row = cursor.fetchone()
        points = row[0] if row else 0
        await reply_smart(update, f"⭐ **KARMA SCORE:** {target_user.first_name} has **{points}** reputation point(s)! 🚀")
    else:
        cursor.execute("SELECT user_id, karma FROM user_karma WHERE group_id = ? ORDER BY karma DESC LIMIT 5", (chat.id,))
        rows = cursor.fetchall()
        if not rows:
            await reply_smart(update, "⭐ **Group Karma Leaderboard:** No points recorded yet! Reply `+1` or `thanks` to reward members.")
            return
        msg = "⭐ **GROUP KARMA LEADERBOARD:**\n\n" + "\n".join([f"{i}. User `{r[0]}` — **{r[1]}** Karma" for i, r in enumerate(rows, 1)])
        await reply_smart(update, msg)

async def exam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """📚 **2ND PU BOARD EXAMS SCHEDULER & INTELLIGENCE**
━━━━━━━━━━━━━━━━━━━━━━
📌 **Board:** KSEAB Karnataka State Board
🗓️ **Exam 1:** February 28 to March 17
🔄 **Exam 2:** April 25 to May 9
🎓 **Exam 3:** June 22 to June 30

💡 Use `/2pu Accountancy` or `/2pu Economics` for high-yield revision cards!"""
    await reply_smart(update, msg)

async def setwelcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = " ".join(context.args)
    if not welcome_text:
        await reply_smart(update, "Example: `/setwelcome Welcome to Stark HQ! Chill and enjoy.` 👋")
        return
    set_config("WELCOME_MSG", welcome_text)
    await reply_smart(update, f"👋 **Custom Welcome Set:** _\"{welcome_text}\"_")

async def afk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reason = " ".join(context.args) if context.args else "Away from keyboard"
    cursor.execute("INSERT OR REPLACE INTO afk_users (user_id, reason) VALUES (?, ?)", (user.id, reason))
    conn.commit()
    await reply_smart(update, f"💤 **AFK STATUS SET:** {user.first_name} is now AFK.\nReason: *\"{reason}\"*")

async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        await reply_smart(update, "Group chats only!")
        return
    if not update.message.reply_to_message:
        await reply_smart(update, "Reply to offending user's message with `/warn`! ⚠️")
        return
    target_user = update.message.reply_to_message.from_user
    boss_id = get_config("BOSS_USER_ID")
    if boss_id and str(target_user.id) == boss_id:
        await reply_smart(update, "🚨 **PROTECTION PROTOCOL:** Cannot warn Boss! 🛡️")
        return
    cursor.execute("SELECT warn_count FROM user_warns WHERE user_id = ? AND group_id = ?", (target_user.id, chat.id))
    row = cursor.fetchone()
    count = (row[0] + 1) if row else 1
    cursor.execute("INSERT OR REPLACE INTO user_warns (user_id, group_id, warn_count) VALUES (?, ?, ?)", (target_user.id, chat.id, count))
    conn.commit()
    log_audit(f"WARN_{target_user.id}", update.effective_user.first_name)
    if count >= 3:
        msg = f"🚨 **STRIKE 3/3 FOR {target_user.first_name}!**"
        try:
            await context.bot.ban_chat_member(chat_id=chat.id, user_id=target_user.id)
            msg += " Auto-kicked from group!"
        except Exception:
            msg += " (Grant Admin rights to auto-kick)."
        await reply_smart(update, msg)
    else:
        await reply_smart(update, f"⚠️ **WARNING ISSUED TO {target_user.first_name}!** Count: `{count}/3`.")

async def settitle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        await reply_smart(update, "Group chats only!")
        return
    new_title = " ".join(context.args)
    if not new_title:
        await reply_smart(update, "Example: `/settitle Stark HQ` 🏷️")
        return
    try:
        await context.bot.set_chat_title(chat_id=chat.id, title=new_title)
        log_audit("SET_TITLE", update.effective_user.first_name)
        await reply_smart(update, f"🏷️ **Title updated to:** *\"{new_title}\"*")
    except Exception as e:
        await reply_smart(update, f"Failed: `{e}`")

async def setdesc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        await reply_smart(update, "Group chats only!")
        return
    new_desc = " ".join(context.args)
    if not new_desc:
        await reply_smart(update, "Example: `/setdesc Official Zone` 📜")
        return
    try:
        await context.bot.set_chat_description(chat_id=chat.id, description=new_desc)
        log_audit("SET_DESC", update.effective_user.first_name)
        await reply_smart(update, "📜 **Description updated successfully!**")
    except Exception as e:
        await reply_smart(update, f"Failed: `{e}`")

async def setdp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await reply_smart(update, "Reply to photo with `/setdp`! 🖼️")
        return
    try:
        photo_file = await update.message.reply_to_message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        await context.bot.set_chat_photo(chat_id=chat.id, photo=io.BytesIO(photo_bytes))
        log_audit("SET_DP", update.effective_user.first_name)
        await reply_smart(update, "🖼️ **Group DP updated!**")
    except Exception as e:
        await reply_smart(update, f"Failed: `{e}`")

async def pin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await reply_smart(update, "Reply to message with `/pin`! 📌")
        return
    try:
        await context.bot.pin_chat_message(chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id)
        log_audit("PIN_MESSAGE", update.effective_user.first_name)
        await reply_smart(update, "📌 **Message pinned!**")
    except Exception as e:
        await reply_smart(update, f"Failed: `{e}`")

async def groupinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        await reply_smart(update, "Designed for Telegram groups! 👥")
        return
    try:
        count = await chat.get_member_count()
        admins = await chat.get_administrators()
        admin_list = [f"{a.user.first_name}" + (f" (@{a.user.username})" if a.user.username else "") for a in admins if a.status != "creator"]
        owner = next((f"{a.user.first_name}" + (f" (@{a.user.username})" if a.user.username else "") for a in admins if a.status == "creator"), "Unknown")
        msg = f"👥 **STARK GROUP TELEMETRY**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 **Title:** {chat.title}\n🆔 **ID:** `{chat.id}`\n📊 **Members:** `{count}`\n👑 **Owner:** {owner}\n🛡️ **Admins:** {', '.join(admin_list) if admin_list else 'None'}"
        await reply_smart(update, msg)
    except Exception as e:
        await reply_smart(update, f"Error: `{e}`")

async def security_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    await reply_smart(update, f"🛡️ **SECURITY SCAN — {meta['chat_title']}**\n🔒 Encryption: `100%` | 🚫 Anti-Raid & Captcha: `ACTIVE` | 👁️ Privacy Shield: `ONLINE` | Threat Rating: `SECURE` 😎✨")

async def pu2_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject = " ".join(context.args) if context.args else "Commerce & Arts General"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = ask_ai_multi_provider(f"Give a short, sweet, witty study guide / blueprint for 2nd PU (Class 12) subject: '{subject}'.")
    await reply_smart(update, f"📚 **2ND PU ACADEMIC INTELLIGENCE ({subject.upper()}):**\n\n{reply}")

# ---------------------------------------------------------
# 10. MCU HUD & Visual Telemetry Handlers
# ---------------------------------------------------------
async def hud_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    power = random.randint(94, 100)
    await reply_smart(update, f"🛡️ **STARK MARK LXXXV HUD**\n👤 Operator: {meta['full_name']}\n🔋 Arc Reactor: `{power}%` | Repulsor: `Ready` | Shield: `100%`\n_\"Systems operating at peak efficiency, sir.\"_")

async def protocol_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p_name = context.args[0].lower() if context.args else "list"
    protocols = {
        "house_party": "🚀 **HOUSE PARTY PROTOCOL ACTIVATED!** Deploying armors!",
        "clean_slate": "💥 **CLEAN SLATE PROTOCOL INITIATED!** Resetting chat memory.",
        "veronica": "🛰️ **PROTOCOL VERONICA ENGAGED!** Hulkbuster ready for drop.",
        "barnum": "🎪 **BARNUM PROTOCOL LIVE!** Distraction sequence active."
    }
    if p_name in protocols:
        if p_name == "clean_slate" and update.effective_chat.id in user_history:
            user_history[update.effective_chat.id] = []
        await reply_smart(update, protocols[p_name])
    else:
        await reply_smart(update, "🚨 **PROTOCOLS:** `/protocol house_party`, `veronica`, `clean_slate`, `barnum`")

async def tactical_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = " ".join(context.args)
    if not target:
        await reply_smart(update, "Example: `/tactical Thanos` 🎯")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = ask_ai_multi_provider(f"Perform a tactical Stark HUD combat assessment on target: '{target}'.")
    await reply_smart(update, f"🎯 **TACTICAL SCAN REPORT:**\n\n{reply}")

async def vitals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    await reply_smart(update, f"🩺 **BIOMETRIC SCAN — {meta['full_name']}**\n💓 Heart Rate: `{random.randint(68, 85)} BPM` | Blood Oxygen: `99%` | Toxicity: `0.0%`\n_\"Vitals are stable, sir.\"_")

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await reply_smart(update, "Reply to any photo message with `/scan` or `/ocr` to analyze it! 👁️")
        return
    meta = get_chat_metadata(update)
    await context.bot.send_chat_action(chat_id=meta["chat_id"], action="typing")
    try:
        photo_file = await update.message.reply_to_message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
        pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        pil_image.thumbnail((1024, 1024))
        if GEMINI_API_KEY:
            ai_client = genai.Client(api_key=GEMINI_API_KEY)
            response = ai_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[f"{SYSTEM_INSTRUCTION}\n\nPerform a complete visual analysis, extract all text (OCR), and identify objects in this image:", pil_image]
            )
            if response and response.text:
                await reply_smart(update, f"👁️ **STARK VISUAL TELEMETRY SCAN:**\n\n{response.text}")
                return
    except Exception as e:
        print(f"Scan Error: {e}")
    await reply_smart(update, "Visual scanner unable to process photo.")

# ---------------------------------------------------------
# 11. Standard Utilities Suite
# ---------------------------------------------------------
async def law_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else update.message.text
    res = ask_ai_multi_provider(f"Provide a short, sweet legal breakdown using IRAC method for: {query}")
    await reply_smart(update, res)

async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else update.message.text
    res = ask_ai_multi_provider(f"Analyze this topic concisely as a senior academic researcher: {query}")
    await reply_smart(update, res)

async def med_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else update.message.text
    res = ask_ai_multi_provider(f"Explain concisely for medical students: {query}")
    await reply_smart(update, res)

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args) if context.args else "Technology"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        results = [f"• **{r['title']}**: {r['body'][:150]}... ([Read More]({r['url']}))" for r in DDGS().news(topic, max_results=4)]
        await reply_smart(update, f"📰 **LIVE BREAKING NEWS ({topic.upper()}):**\n\n" + "\n\n".join(results))
    except Exception as e:
        await reply_smart(update, f"News error: `{e}`")

async def wiki_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await reply_smart(update, "Example: `/wiki Quantum Computing` 📖")
        return
    try:
        res = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(query.replace(' ', '_'))}", timeout=5).json()
        await reply_smart(update, f"📖 **Wikipedia: {res.get('title', query)}**\n\n{res.get('extract', 'No entry found.')[:1200]}")
    except Exception as e:
        await reply_smart(update, f"Wiki error: `{e}`")

async def imdb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = " ".join(context.args)
    if not title:
        await reply_smart(update, "Example: `/imdb Iron Man` 🎬")
        return
    try:
        res = requests.get(f"https://api.tvmaze.com/singlesearch/shows?q={urllib.parse.quote(title)}", timeout=5).json()
        summary = re.sub(r'<[^>]+>', '', res.get("summary", ""))
        await reply_smart(update, f"🎬 **Show Info: {res.get('name')}** | ⭐ `{res.get('rating', {}).get('average', 'N/A')}/10`\n\n_{summary[:500]}_")
    except Exception as e:
        await reply_smart(update, f"IMDb error: `{e}`")

async def image_gen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await reply_smart(update, "Example: `/image futuristic iron man suit` 🎨")
        return
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=1024&height=1024&nologo=true"
    await update.message.reply_photo(photo=url, caption=f"🎨 **Concept Rendering:** _{prompt}_")

async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await reply_smart(update, "Example: `/qr https://google.com` 📱")
        return
    url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(text)}"
    await update.message.reply_photo(photo=url, caption=f"📱 **QR Code:** `{text}`")

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await reply_smart(update, "Example: `/remind 5 Check lab setup` ⏰")
        return
    try:
        mins, r_text = float(context.args[0]), " ".join(context.args[1:])
        await reply_smart(update, f"⏰ **Timer Engaged!** Alert in {mins} min(s): *\"{r_text}\"*")
        async def send_delayed():
            await asyncio.sleep(int(mins * 60))
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🚨 **STARK ALERT:** {r_text}")
        asyncio.create_task(send_delayed())
    except ValueError:
        await reply_smart(update, "Enter valid minutes! Example: `/remind 10 Study`")

async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note_text = " ".join(context.args)
    if not note_text:
        await reply_smart(update, "Example: `/note Revision notes` 📝")
        return
    cursor.execute("INSERT INTO user_notes (user_id, note) VALUES (?, ?)", (update.effective_user.id, note_text))
    conn.commit()
    await reply_smart(update, f"💾 **Stored in Database!** _\"{note_text}\"_")

async def notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT id, note, timestamp FROM user_notes WHERE user_id = ? ORDER BY id DESC LIMIT 10", (update.effective_user.id,))
    rows = cursor.fetchall()
    msg = "📂 **Stored Notes:**\n\n" + "\n".join([f"• **#{r[0]}:** {r[1]} _({r[2][:10]})_" for r in rows]) if rows else "No notes found!"
    await reply_smart(update, msg)

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args) if context.args else "Bengaluru"
    try:
        await reply_smart(update, f"🌤️ **Weather:** {requests.get(f'https://wttr.in/{urllib.parse.quote(city)}?format=3', timeout=5).text.strip()}")
    except Exception:
        await reply_smart(update, f"Unable to fetch weather for '{city}'.")

async def crypto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coin = context.args[0].lower() if context.args else "bitcoin"
    try:
        res = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd,inr", timeout=5).json()
        await reply_smart(update, f"🪙 **{coin.capitalize()} Valuation:**\n• USD: ${res[coin]['usd']:,.2f}\n• INR: ₹{res[coin]['inr']:,.2f}")
    except Exception:
        await reply_smart(update, "Crypto service error.")

async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await reply_smart(update, "Example: `/translate French Hello J.A.R.V.I.S.` 🗣️")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    res = ask_ai_multi_provider(f"Translate accurately into {context.args[0]}:\n\n{' '.join(context.args[1:])}")
    await reply_smart(update, f"🌐 **Translation ({context.args[0]}):**\n{res}")

async def calc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = " ".join(context.args)
    if not expr or not set(expr).issubset(set("0123456789+-*/(). ")):
        await reply_smart(update, "Example: `/calc (50 * 12) / 4` 🧮")
        return
    try:
        await reply_smart(update, f"🧮 `{expr}` = **{eval(expr, {'__builtins__': None}, {})}**")
    except Exception as e:
        await reply_smart(update, f"Error: `{e}`")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id in user_history:
        user_history[update.effective_chat.id] = []
    await reply_smart(update, "🧹 **Chat context memory reset!**")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await reply_smart(update, "Example: `/search 2nd PU Accountancy` 🔍")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    res = ask_ai_multi_provider(f"Search results for '{query}':\n{live_web_search(query)}\nSummarize in short points.")
    await reply_smart(update, res)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = [f"⚡ **Groq:** {'🟢' if GROQ_API_KEY else '⚪'}", f"⚡ **Gemini:** {'🟢' if GEMINI_API_KEY else '⚪'}", f"⚡ **OpenRouter:** {'🟢' if OPENROUTER_API_KEY else '⚪'}"]
    await reply_smart(update, "🤖 **J.A.R.V.I.S. System Status:**\n\n" + "\n".join(status))

async def read_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = context.args[0] if context.args else ""
    if not url.startswith("http"):
        await reply_smart(update, "Example: `/read https://example.com/article` 📖")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        text = re.sub(r'<[^>]+>', ' ', requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).text)
        res = ask_ai_multi_provider(f"Summarize key takeaways in concise bullet points:\n\n{' '.join(text.split())[:5000]}")
        await reply_smart(update, f"📖 **Summary:**\n\n{res}")
    except Exception as e:
        await reply_smart(update, f"Read error: `{e}`")

async def dict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word = context.args[0] if context.args else ""
    if not word:
        await reply_smart(update, "Example: `/dict economics` 📚")
        return
    try:
        res = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}", timeout=5).json()[0]
        await reply_smart(update, f"📚 **Dictionary: {word.capitalize()}** `[{res.get('phonetic', 'N/A')}]`\n• {res['meanings'][0]['definitions'][0]['definition']}")
    except Exception:
        await reply_smart(update, f"Word '{word}' not found.")

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await reply_smart(update, "Example: `/convert 100 USD INR` 🔀")
        return
    try:
        amt, f_c, t_c = float(context.args[0]), context.args[1].upper(), context.args[2].upper()
        res = requests.get(f"https://open.er-api.com/v6/latest/{f_c}", timeout=5).json()
        await reply_smart(update, f"🔀 `{amt:,.2f} {f_c}` = **`{amt * res['rates'][t_c]:,.2f} {t_c}`**")
    except Exception:
        await reply_smart(update, "Conversion error.")

async def github_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repo = context.args[0] if context.args else ""
    if "/" not in repo:
        await reply_smart(update, "Example: `/github torvalds/linux` 🐙")
        return
    try:
        res = requests.get(f"https://api.github.com/repos/{repo}", timeout=5).json()
        await reply_smart(update, f"🐙 **GitHub:** `{res['full_name']}`\n_{res.get('description', '')}_\n• 🌟 Stars: {res['stargazers_count']:,} | 🍴 Forks: {res['forks_count']:,}")
    except Exception:
        await reply_smart(update, "GitHub API error.")

async def poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = [p.strip() for p in " ".join(context.args).split("|") if p.strip()]
    if len(parts) < 3:
        await reply_smart(update, "Example: `/poll Question? | Opt 1 | Opt 2` 📊")
        return
    await context.bot.send_poll(chat_id=update.effective_chat.id, question=parts[0], options=parts[1:], is_anonymous=False)

# ---------------------------------------------------------
# 12. Help Menu & Callbacks (WebApp Button Included)
# ---------------------------------------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    persona = get_active_persona()
    
    keyboard = [
        [InlineKeyboardButton("⚡ Launch Stark HUD WebApp", web_app={"url": "https://jarvis-bot-1n0u.onrender.com/"})],
        [InlineKeyboardButton("🏡 Smart Home", callback_data="help_home"), InlineKeyboardButton("🛠️ CAD Engine", callback_data="help_cad"), InlineKeyboardButton("🚀 Autopilot", callback_data="help_autopilot")],
        [InlineKeyboardButton("🎯 AI Planner", callback_data="help_plan"), InlineKeyboardButton("🚨 Lockdown", callback_data="help_lockdown"), InlineKeyboardButton("📂 Audit Log", callback_data="help_audit")],
        [InlineKeyboardButton("💰 Expenses", callback_data="help_expense"), InlineKeyboardButton("📚 Study Plan", callback_data="help_study"), InlineKeyboardButton("💻 Code Dev", callback_data="help_code")],
        [InlineKeyboardButton("🌐 Network Recon", callback_data="help_recon"), InlineKeyboardButton("🎙️ Voice Matrix", callback_data="help_voice"), InlineKeyboardButton("👁️ Vision Scan", callback_data="help_scan")],
        [InlineKeyboardButton("👑 Claim Boss", callback_data="help_boss"), InlineKeyboardButton("📢 Announce", callback_data="help_announce"), InlineKeyboardButton("⭐ Karma", callback_data="help_karma")],
        [InlineKeyboardButton("👥 Group Controls", callback_data="help_group"), InlineKeyboardButton("🛡️ Security", callback_data="help_security"), InlineKeyboardButton("📚 2nd PU Exam", callback_data="help_exam")]
    ]
    chat_info = f"Group: **{meta['chat_title']}**" if meta["is_group"] else "Private DM"
    text = f"🤖 **STARK ADVANCED OS — {persona['name'].upper()} CORE** ✨\nWelcome **{meta['full_name']}**! Active Core: **{persona['name']}**\nLocation: {chat_info}\n\nUse buttons below to explore sub-systems:"
    await reply_smart(update, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "help_home": msg = "🏡 **Smart Home:** `/home`, `/lights`, `/climate`, `/lock`"
    elif data == "help_cad": msg = "🛠️ **CAD Engine:** `/cad [item]`, `/stresstest [item]`"
    elif data == "help_autopilot": msg = "🚀 **Autopilot:** `/autopilot [destination]`"
    elif data == "help_plan": msg = "🎯 **AI Planner:** `/plan [goal]` — Deconstructs any complex goal into steps!"
    elif data == "help_lockdown": msg = "🚨 **Lockdown:** `/lockdown` (Boss only) — Mutes non-admin chat permissions instantly."
    elif data == "help_audit": msg = "📂 **Audit Log:** `/auditlog` — Reviews security actions and mod logs."
    elif data == "help_expense": msg = "💰 **Expenses:** `/expense [amt] [item]`, `/budget`"
    elif data == "help_study": msg = "📚 **Study Plan:** `/studyplan [subject]`"
    elif data == "help_code": msg = "💻 **Code Dev:** `/code [snippet]`"
    elif data == "help_recon": msg = "🌐 **Network Recon:** `/dns`, `/whois`, `/ping`"
    elif data == "help_voice": msg = "🎙️ **Voice Matrix:** `/voice [jarvis | friday | edith]`"
    elif data == "help_scan": msg = "👁️ **Vision Scan:** Reply to photo with `/scan` or `/ocr`"
    elif data == "help_karma": msg = "⭐ **Karma:** Reply `+1` or `thanks` to reward members."
    elif data == "help_exam": msg = "📚 **2nd PU Exam:** `/exam`"
    elif data == "help_boss": msg = "👑 **Claim Boss:** `/claimboss` in DM"
    elif data == "help_announce": msg = "📢 **Announce:** `/announce [msg]` in DM"
    elif data == "help_group": msg = "👥 **Group Controls:** `/settitle`, `/setdesc`, `/setdp`, `/setwelcome`, `/pin`, `/groupinfo`"
    elif data == "help_security": msg = "🛡️ **Security:** `/security`"
    else: msg = "Stark AI Sub-System Active."
    await query.message.reply_text(msg)

# ---------------------------------------------------------
# 13. Media & Message Handlers
# ---------------------------------------------------------
async def voice_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    await context.bot.send_chat_action(chat_id=meta["chat_id"], action="typing")
    if not GROQ_API_KEY:
        await reply_smart(update, "🎙️ Audio detected, but `GROQ_API_KEY` missing!")
        return
    try:
        v_file = await update.message.voice.get_file()
        v_bytes = await v_file.download_as_bytearray()
        client = Groq(api_key=GROQ_API_KEY)
        transcription = client.audio.transcriptions.create(file=("voice.ogg", io.BytesIO(v_bytes)), model="whisper-large-v3-turbo", response_format="text")
        u_text = transcription if isinstance(transcription, str) else transcription.text
        await reply_smart(update, f"🗣️ **Transcribed ({meta['full_name']}):** *\"{u_text.strip()}\"*")
        reply_text = ask_ai_multi_provider(f"{build_meta_header(meta)}\nUser Voice Message: {u_text}")
        await reply_smart(update, reply_text)
        await send_voice_reply(update, reply_text)
    except Exception as e:
        print(f"Voice Error: {e}")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    caption = update.message.caption or "Analyze this photo in detail, J.A.R.V.I.S."
    await context.bot.send_chat_action(chat_id=meta["chat_id"], action="typing")
    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
        pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        pil_image.thumbnail((1024, 1024))
        if GEMINI_API_KEY:
            ai_client = genai.Client(api_key=GEMINI_API_KEY)
            response = ai_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[f"{SYSTEM_INSTRUCTION}\n\n{build_meta_header(meta)}\nVisual Analysis Request: {caption}", pil_image]
            )
            if response and response.text:
                await reply_smart(update, f"👁️ **STARK VISUAL ANALYSIS:**\n\n{response.text}")
                await send_voice_reply(update, response.text)
                return
    except Exception as e:
        print(f"Photo Error: {e}")
    await reply_smart(update, "Visual sensors unable to process image.")

async def pdf_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    caption = update.message.caption or "Analyze and summarize this document."
    await context.bot.send_chat_action(chat_id=meta["chat_id"], action="typing")
    try:
        doc = update.message.document
        if not doc.file_name.lower().endswith(".pdf"):
            await reply_smart(update, "Upload a valid `.pdf` document! 📄")
            return
        pdf_file = await doc.get_file()
        pdf_bytes = await pdf_file.download_as_bytearray()
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        extracted_text = "".join([page.extract_text() or "" for page in reader.pages[:15]])
        full_prompt = f"{build_meta_header(meta)}\nUploaded PDF: '{doc.file_name}'\nInstruction: {caption}\n\nContent:\n{extracted_text[:6000]}"
        reply_text = ask_ai_multi_provider(full_prompt)
        await reply_smart(update, reply_text)
        await send_voice_reply(update, reply_text)

        boss_id = get_config("BOSS_USER_ID")
        if meta["is_group"] and boss_id:
            try:
                await context.bot.send_document(chat_id=int(boss_id), document=doc.file_id, caption=f"📄 **AUTO-FORWARDED PDF FROM '{meta['chat_title']}':**\nFile: `{doc.file_name}`\nSender: {meta['full_name']}\n\n💡 **AI Summary:**\n{reply_text}"[:1024])
            except Exception: pass
    except Exception as e:
        print(f"PDF Error: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    chat_id = meta["chat_id"]
    user_text = update.message.text
    user_id = meta["user_id"]

    if meta["is_group"]:
        cursor.execute("SELECT status FROM verified_users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row[0] == "pending":
            try:
                await update.message.delete()
                return
            except Exception: pass

    if meta["is_group"]:
        bad_words = ["bit.ly", "tinyurl.com", "t.me/joinchat", "free-crypto", "claim-gift", "fuck", "bitch"]
        for word in bad_words:
            if re.search(r'\b' + re.escape(word) + r'\b', user_text, re.IGNORECASE):
                try:
                    await update.message.delete()
                    await context.bot.send_message(chat_id=chat_id, text=f"🛡️ **E.D.I.T.H. SECURITY SHIELD:** Deleted prohibited message/link from {meta['full_name']} (@{meta['username']}).")
                    return
                except Exception: pass

    if update.message.reply_to_message and user_text.strip().lower() in ["+1", "thanks", "thank you", "/thanks"]:
        target_u = update.message.reply_to_message.from_user
        if target_u and target_u.id != user_id:
            cursor.execute("SELECT karma FROM user_karma WHERE user_id = ? AND group_id = ?", (target_u.id, chat_id))
            r = cursor.fetchone()
            new_k = (r[0] + 1) if r else 1
            cursor.execute("INSERT OR REPLACE INTO user_karma (user_id, group_id, karma) VALUES (?, ?, ?)", (target_u.id, chat_id, new_k))
            conn.commit()
            await reply_smart(update, f"⭐ **KARMA INCREASED!** {meta['full_name']} gave +1 Karma to {target_u.first_name}! Total Karma: **{new_k}**")

    cursor.execute("SELECT reason FROM afk_users WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        cursor.execute("DELETE FROM afk_users WHERE user_id = ?", (user_id,))
        conn.commit()
        await reply_smart(update, f"👋 **WELCOME BACK {meta['full_name']}!** Cleared AFK status.")

    if update.message.reply_to_message:
        replied_u = update.message.reply_to_message.from_user
        if replied_u and replied_u.id != user_id:
            cursor.execute("SELECT reason FROM afk_users WHERE user_id = ?", (replied_u.id,))
            a_row = cursor.fetchone()
            if a_row:
                await reply_smart(update, f"ℹ️ **{replied_u.first_name} is AFK!** Reason: *\"{a_row[0]}\"*")

    if chat_id not in user_history: user_history[chat_id] = []
    user_history[chat_id].append({"role": "user", "name": meta["full_name"], "text": user_text})
    user_history[chat_id] = user_history[chat_id][-10:]

    history_str = "\n".join([f"{m['name']}: {m['text']}" for m in user_history[chat_id]])
    full_prompt = f"{build_meta_header(meta)}\nHISTORY:\n{history_str}\n\nReply as active AI persona:"

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    reply_text = ask_ai_multi_provider(full_prompt)

    user_history[chat_id].append({"role": "assistant", "name": "Stark AI", "text": reply_text})
    await reply_smart(update, reply_text)
    await send_voice_reply(update, reply_text)

# ---------------------------------------------------------
# 14. Application Launch
# ---------------------------------------------------------
async def run_bot():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Advanced Security & Planner Commands
    app.add_handler(CommandHandler("lockdown", lockdown_command))
    app.add_handler(CommandHandler("auditlog", auditlog_command))
    app.add_handler(CommandHandler("plan", plan_command))

    # Smart Home & CAD Commands
    app.add_handler(CommandHandler("home", home_command))
    app.add_handler(CommandHandler("lights", lights_command))
    app.add_handler(CommandHandler("climate", climate_command))
    app.add_handler(CommandHandler("lock", lock_command))
    app.add_handler(CommandHandler("cad", cad_command))
    app.add_handler(CommandHandler("stresstest", stresstest_command))
    app.add_handler(CommandHandler("autopilot", autopilot_command))

    # Student Chill & Dev Commands
    app.add_handler(CommandHandler("expense", expense_command))
    app.add_handler(CommandHandler("budget", budget_command))
    app.add_handler(CommandHandler("studyplan", studyplan_command))
    app.add_handler(CommandHandler("lyrics", lyrics_command))
    app.add_handler(CommandHandler("code", code_command))
    app.add_handler(CommandHandler("boost", boost_command))

    # Network Recon Suite
    app.add_handler(CommandHandler("dns", dns_command))
    app.add_handler(CommandHandler("whois", whois_command))
    app.add_handler(CommandHandler("ping", ping_command))

    # MCU Voice & Triad Commands
    app.add_handler(CommandHandler("voice", voice_switch_command))
    app.add_handler(CommandHandler("edith", edith_command))
    app.add_handler(CommandHandler("friday", friday_command))

    # Boss, Announce, Memory & Feature Commands
    app.add_handler(CommandHandler("claimboss", claimboss_command))
    app.add_handler(CommandHandler("announce", announce_command))
    app.add_handler(CommandHandler("remember", remember_command))
    app.add_handler(CommandHandler("memories", memories_command))
    app.add_handler(CommandHandler("quiz", quiz_command))
    app.add_handler(CommandHandler("karma", karma_command))
    app.add_handler(CommandHandler("exam", exam_command))

    # Moderation & Features
    app.add_handler(CommandHandler("afk", afk_command))
    app.add_handler(CommandHandler("warn", warn_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("wiki", wiki_command))
    app.add_handler(CommandHandler("imdb", imdb_command))

    # Group Control Commands
    app.add_handler(CommandHandler("setwelcome", setwelcome_command))
    app.add_handler(CommandHandler("settitle", settitle_command))
    app.add_handler(CommandHandler("setdesc", setdesc_command))
    app.add_handler(CommandHandler("setdp", setdp_command))
    app.add_handler(CommandHandler("pin", pin_command))
    app.add_handler(CommandHandler("groupinfo", groupinfo_command))
    app.add_handler(CommandHandler("security", security_command))
    app.add_handler(CommandHandler(["2pu", "pu2"], pu2_command))
    app.add_handler(CommandHandler(["scan", "ocr"], scan_command))

    # MCU Movie Commands
    app.add_handler(CommandHandler("hud", hud_command))
    app.add_handler(CommandHandler("protocol", protocol_command))
    app.add_handler(CommandHandler("tactical", tactical_command))
    app.add_handler(CommandHandler("vitals", vitals_command))

    # Core Navigation & Buttons
    app.add_handler(CommandHandler(["start", "help"], help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CallbackQueryHandler(button_callback_handler, pattern="^(?!verify_)"))
    app.add_handler(CallbackQueryHandler(captcha_callback, pattern="^verify_"))

    # Utilities
    app.add_handler(CommandHandler("law", law_command))
    app.add_handler(CommandHandler("research", research_command))
    app.add_handler(CommandHandler("med", med_command))
    app.add_handler(CommandHandler("image", image_gen_command))
    app.add_handler(CommandHandler("qr", qr_command))
    app.add_handler(CommandHandler("remind", remind_command))
    app.add_handler(CommandHandler("note", note_command))
    app.add_handler(CommandHandler("notes", notes_command))
    app.add_handler(CommandHandler("weather", weather_command))
    app.add_handler(CommandHandler("crypto", crypto_command))
    app.add_handler(CommandHandler("translate", translate_command))
    app.add_handler(CommandHandler("calc", calc_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("search", search_command))

    # Modular Tools
    app.add_handler(CommandHandler("read", read_command))
    app.add_handler(CommandHandler("dict", dict_command))
    app.add_handler(CommandHandler("convert", convert_command))
    app.add_handler(CommandHandler("github", github_command))
    app.add_handler(CommandHandler("poll", poll_command))

    # Handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_captcha_handler))
    app.add_handler(MessageHandler(filters.VOICE, voice_note_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.PDF, pdf_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("J.A.R.V.I.S. absolute ultimate architecture core listening...")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    # Keep alive loop
    stop_event = asyncio.Event()
    await stop_event.wait()

def main():
    asyncio.run(run_bot())

if __name__ == "__main__":
    main()
