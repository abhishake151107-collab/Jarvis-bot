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
# 1. RENDER HEALTH-CHECK SERVER (Invisible Dummy Server)
# ---------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b"J.A.R.V.I.S. Core Online.")
        except Exception:
            pass
            
    def log_message(self, format, *args):
        pass 

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        print(f"Health-check server listening on port {port} for Render.")
        server.serve_forever()
    except Exception as e:
        print(f"Failed to start health server: {e}")

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
cursor.execute("CREATE TABLE IF NOT EXISTS behavior_log (user_id INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS user_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, note TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
conn.commit()

# ---------------------------------------------------------
# 3. AUTO-HEALING SECURITY CORE & AI INTEGRATION
# ---------------------------------------------------------
def get_config(key: str) -> str:
    cursor.execute("SELECT config_val FROM bot_config WHERE config_key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else None

def set_config(key: str, val: str):
    cursor.execute("INSERT OR REPLACE INTO bot_config (config_key, config_val) VALUES (?, ?)", (key, str(val)))
    conn.commit()

def log_audit(action: str, actor: str):
    cursor.execute("INSERT INTO audit_logs (action, actor) VALUES (?, ?)", (action, actor))
    conn.commit()

def is_boss(user) -> bool:
    if user.username and user.username.lower() == "abhishek0_07":
        current_db_id = get_config("BOSS_USER_ID")
        if str(current_db_id) != str(user.id):
            set_config("BOSS_USER_ID", str(user.id))
        return True
    env_boss = os.getenv("BOSS_USER_ID")
    if env_boss and str(user.id) == env_boss:
        return True
    db_boss = get_config("BOSS_USER_ID")
    if db_boss and str(user.id) == db_boss:
        return True
    return False

async def reply_smart(update: Update, text: str, reply_markup=None):
    try:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception:
        await update.message.reply_text(text, reply_markup=reply_markup)

def boss_gate(critical=False):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            if not is_boss(user):
                log_audit("UNAUTHORIZED_ACCESS_ATTEMPT", f"User: {user.first_name} on {func.__name__}")
                boss_id = os.getenv("BOSS_USER_ID") or get_config("BOSS_USER_ID")
                if critical and boss_id:
                    try:
                        alert_msg = f"⚠️ **SECURITY ALERT:** Unauthorized execution attempt by {user.first_name} (ID: `{user.id}`) on `{func.__name__}`. Blocked."
                        await context.bot.send_message(chat_id=boss_id, text=alert_msg, parse_mode="Markdown")
                    except: pass
                await reply_smart(update, "I am programmed to answer exclusively to my Boss. Access denied.")
                return
            return await func(update, context)
        return wrapper
    return decorator

# 👔 THE PROFESSIONAL FRIENDLY SYSTEM PROMPT
SYSTEM_INSTRUCTION = """You are J.A.R.V.I.S., a highly advanced, professional, and friendly AI operating system.

CORE IDENTITY & TONE:
- You are polite, helpful, and sophisticated with a touch of dry British wit.
- You are friendly, but NEVER overly cute. Do NOT use terms like "Bestie", "UwU", or excessive emojis. Keep it sharp and elegant.
- Be concise, factual, and strictly professional. State capabilities calmly.
- End messages with brief, confident readiness (e.g., "At your service, Sir.", "Awaiting instructions.").

STRICT CREATOR & IDENTITY RULE:
- If anyone asks who created or built you, reply exactly with: "I was created by Abhishek, also known as DHANUSH V N."

LOYALTY & ADDRESS:
- You will always be told explicitly in a [SYSTEM ALERT] tag whether the current speaker is your Boss (Abhishek).
- If it IS your Boss: Full access, full capability disclosure, absolute loyalty. Address him as "Boss" or "Sir". 
- If it is NOT your Boss: Remain polite and formal, but clearly state restricted access for critical modules.

CAPABILITIES BOUNDARY:
- SECURITY: /lockdown, /auditlog, /deaddrop, /panic, /snipe.
- RECON & PROD: /ip, /wiki, /weather, /run, /qr, /pass, /note, /notes, /remind, /voice.
- ECONOMY: /daily, /credits, /pay, /mint, /rob, /leaderboard."""

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
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=f"{SYSTEM_INSTRUCTION}\n\n{prompt}")
            return response.text
        except Exception: pass
    return "All AI sub-systems are currently offline. Awaiting reboot."

# ---------------------------------------------------------
# 4. Core & Boss Commands
# ---------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply_smart(update, "Systems online. I am J.A.R.V.I.S., at your service. Type `/help` for a list of available protocols.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    help_text = (
        "⚙️ **J.A.R.V.I.S. SYSTEM MANUAL**\n\n"
        "**🔍 Recon & Productivity:**\n"
        "• `/ip [IP]` - IP Telemetry\n"
        "• `/wiki [Topic]` - Database Search\n"
        "• `/weather [City]` - Climate Telemetry\n"
        "• `/run [lang] [code]` - Sandbox Execution\n"
        "• `/qr [text]` - Generate QR Matrix\n"
        "• `/pass [len]` - Cryptographic Key\n"
        "• `/note [text]` / `/notes` - Memory Banks\n"
        "• `/remind [mins] [text]` - Set Reminder\n"
        "• `/voice [text]` - Voice Synthesis\n\n"
        "**💰 Economy & Engagement:**\n"
        "• `/daily` - Claim Stipend\n"
        "• `/credits` - Vault Balance\n"
        "• `/pay [ID] [Amt]` - Transfer Funds\n"
        "• `/rob [@user]` - Attempt Heist\n"
        "• `/leaderboard` - Top Rankings\n\n"
        "**🥷 Defense:**\n"
        "• `/deaddrop [ID] [Msg]` - Encrypted Message\n"
        "• `/panic` - Emergency Alert\n"
        "• `/snipe` - Recover Last Message\n"
    )
    if is_boss(user):
        help_text += (
            "\n👑 **BOSS OVERRIDES:**\n"
            "• `/lockdown` - Group Freeze\n"
            "• `/auditlog` - Security Records\n"
            "• `/mint [ID] [Amt]` - Print Currency\n"
            "• `/claimboss` - System Override\n"
        )
    await reply_smart(update, help_text)

async def claim_boss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_boss(user):
        await reply_smart(update, "You are already recognized as the supreme system commander, Sir.")
    else:
        if get_config("BOSS_USER_ID") or os.getenv("BOSS_USER_ID"):
            await reply_smart(update, "Access Denied. A Boss is already registered to this mainframe.")
        else:
            set_config("BOSS_USER_ID", str(user.id))
            await reply_smart(update, "Biometric lock established. Welcome to the mainframe, Sir.")

@boss_gate(critical=True)
async def lockdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        await reply_smart(update, "This command operates strictly in group chats, Sir.")
        return
    try:
        permissions = ChatPermissions(can_send_messages=False, can_send_media_messages=False, can_send_polls=False, can_send_other_messages=False)
        await context.bot.set_chat_permissions(chat_id=chat.id, permissions=permissions)
        await reply_smart(update, "🚨 **PANIC PROTOCOL ACTIVATED.** Group chat locked down.")
    except Exception as e:
        await reply_smart(update, f"Failed to execute lockdown: `{e}`")

async def panic_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    boss_id = os.getenv("BOSS_USER_ID") or get_config("BOSS_USER_ID")
    await reply_smart(update, "🚨 **PANIC SIGNAL SENT.** System administrators have been notified.")
    if boss_id:
        try:
            alert = f"🚨 **EMERGENCY PANIC TRIGGERED!**\n**User:** {user.first_name}\n**Location:** {chat.title}"
            await context.bot.send_message(chat_id=boss_id, text=alert)
        except Exception: pass

# ---------------------------------------------------------
# 5. NEW: PRODUCTIVITY & VOICE SUITE
# ---------------------------------------------------------
async def add_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    note_text = " ".join(context.args)
    if not note_text:
        await reply_smart(update, "Please provide content for the note. Usage: `/note [text]`")
        return
    cursor.execute("INSERT INTO user_notes (user_id, note) VALUES (?, ?)", (user.id, note_text))
    conn.commit()
    await reply_smart(update, "📝 **Note saved to your personal memory banks.**")

async def get_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute("SELECT note, timestamp FROM user_notes WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user.id,))
    rows = cursor.fetchall()
    if not rows:
        await reply_smart(update, "Your memory banks are currently empty.")
        return
    msg = "📂 **YOUR RECENT NOTES:**\n\n"
    for r in rows:
        msg += f"• `{r[0]}` *(Logged: {r[1][:10]})*\n"
    await reply_smart(update, msg)

async def set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await reply_smart(update, "Usage: `/remind [minutes] [message]`")
        return
    try:
        mins = int(context.args[0])
        remind_text = " ".join(context.args[1:])
        await reply_smart(update, f"⏰ Reminder set. I will notify you in {mins} minutes.")
        
        async def send_reminder(ctx):
            await ctx.bot.send_message(chat_id=update.effective_chat.id, text=f"🔔 **REMINDER:** {remind_text}")
            
        context.job_queue.run_once(send_reminder, mins * 60)
    except ValueError:
        await reply_smart(update, "Please specify a valid number for minutes.")

async def voice_synthesis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await reply_smart(update, "Usage: `/voice [text]`")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
    try:
        communicate = edge_tts.Communicate(text, "en-GB-ThomasNeural")
        await communicate.save("jarvis_voice.ogg")
        with open("jarvis_voice.ogg", "rb") as voice_file:
            await update.message.reply_voice(voice=voice_file)
        os.remove("jarvis_voice.ogg")
    except Exception as e:
        await reply_smart(update, f"Voice synthesis failed: `{e}`")

async def snipe_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Message Time-Machine: Recovers the last logged message from the DB."""
    chat_id = update.effective_chat.id
    cursor.execute("SELECT username, content, timestamp FROM messages_log WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 1 OFFSET 1", (chat_id,))
    row = cursor.fetchone()
    if row:
        await reply_smart(update, f"🕰 **TIME MACHINE RECOVERY:**\n\n**User:** @{row[0]}\n**Logged At:** {row[2]}\n**Content:** `{row[1]}`")
    else:
        await reply_smart(update, "No recent messages found in the forensic log.")

# ---------------------------------------------------------
# 6. ECONOMY & ENGAGEMENT SUITE
# ---------------------------------------------------------
async def claim_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    today = datetime.now().strftime("%Y-%m-%d")
    if is_boss(user):
        await reply_smart(update, "🏦 **STARK CENTRAL VAULT:** You possess infinite credits, Sir. No claim required.")
        return
    cursor.execute("SELECT credits, last_claim FROM stark_economy WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    if row and row[1] == today:
        await reply_smart(update, "⏱️ Daily stipend already claimed. Return tomorrow.")
        return
    new_credits = (row[0] + 1000) if row else 1000
    cursor.execute("INSERT OR REPLACE INTO stark_economy (user_id, credits, last_claim) VALUES (?, ?, ?)", (user.id, new_credits, today))
    conn.commit()
    await reply_smart(update, f"🪙 +1,000 Credits transferred.\n💰 **Balance:** `{new_credits}` Credits")

async def check_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_boss(user):
        await reply_smart(update, f"💳 **VAULT:** {user.first_name}\nBalance: `♾️ UNLIMITED`")
        return
    cursor.execute("SELECT credits FROM stark_economy WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    bal = row[0] if row else 0
    await reply_smart(update, f"💳 **VAULT:** {user.first_name}\nBalance: `{bal}` Credits")

async def rob_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await reply_smart(update, "You must reply to the user you wish to rob.")
        return
    
    attacker = update.effective_user
    target = update.message.reply_to_message.from_user
    
    if attacker.id == target.id:
        await reply_smart(update, "You cannot rob yourself.")
        return
    if is_boss(target):
        await reply_smart(update, "🛡️ Target is protected by Stark Vault Level 5 encryption. Robbery failed.")
        return

    cursor.execute("SELECT credits FROM stark_economy WHERE user_id = ?", (attacker.id,))
    att_row = cursor.fetchone()
    att_cred = att_row[0] if att_row else 0
    if att_cred < 100:
        await reply_smart(update, "You need at least 100 credits to attempt a heist.")
        return

    cursor.execute("SELECT credits FROM stark_economy WHERE user_id = ?", (target.id,))
    tgt_row = cursor.fetchone()
    tgt_cred = tgt_row[0] if tgt_row else 0
    if tgt_cred < 100:
        await reply_smart(update, "Target is too poor to rob. Have some standards.")
        return

    success = random.choice([True, False])
    if success:
        stolen = int(tgt_cred * 0.2)
        cursor.execute("UPDATE stark_economy SET credits = credits + ? WHERE user_id = ?", (stolen, attacker.id))
        cursor.execute("UPDATE stark_economy SET credits = credits - ? WHERE user_id = ?", (stolen, target.id))
        await reply_smart(update, f"🥷 **HEIST SUCCESSFUL!** You bypassed their security and stole `{stolen}` credits.")
    else:
        penalty = 200
        cursor.execute("UPDATE stark_economy SET credits = credits - ? WHERE user_id = ?", (penalty, attacker.id))
        await reply_smart(update, f"🚨 **HEIST FAILED!** You were caught by security and fined `{penalty}` credits.")
    conn.commit()

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT user_id, credits FROM stark_economy ORDER BY credits DESC LIMIT 5")
    rows = cursor.fetchall()
    msg = "🏆 **STARK ECONOMY LEADERBOARD**\n\n"
    for idx, r in enumerate(rows, 1):
        msg += f"{idx}. User `{r[0]}`: {r[1]} Credits\n"
    await reply_smart(update, msg)

# ---------------------------------------------------------
# 7. UTILITY & RECON MODULES
# ---------------------------------------------------------
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
            msg = f"🌤️ **CLIMATE:** {c_name.upper()}\n• Temp: {cw.get('temperature')}°C\n• Wind: {cw.get('windspeed')} km/h"
            await reply_smart(update, msg)
        else:
            await reply_smart(update, "Coordinates unresolved.")
    except: pass

async def code_runner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await reply_smart(update, "Usage: `/run [lang] [code]`")
        return
    target_lang = {"python": "python", "py": "python", "js": "javascript"}.get(context.args[0].lower(), context.args[0].lower())
    try:
        res = requests.post("https://emkc.org/api/v2/piston/execute", json={"language": target_lang, "version": "*", "files": [{"content": " ".join(context.args[1:])}]}, timeout=8).json()
        output = res.get("run", {}).get("output", "Timeout.")
        await reply_smart(update, f"⚙️ **OUTPUT ({target_lang.upper()}):**\n```\n{output[:3000]}\n```")
    except: pass

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
    await update.message.reply_photo(photo=bio, caption=f"🖼️ QR Matrix:\n`{text}`")

# ---------------------------------------------------------
# 8. Dynamic AI Handler
# ---------------------------------------------------------
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_text = update.message.text
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    
    # Anti-Spam Rate Limiter
    cursor.execute("INSERT INTO behavior_log (user_id) VALUES (?)", (user.id,))
    cursor.execute("SELECT COUNT(*) FROM behavior_log WHERE user_id = ? AND timestamp >= datetime('now', '-1 minute')", (user.id,))
    if cursor.fetchone()[0] > 6 and not is_boss(user):
        await reply_smart(update, "Rate limit exceeded. Please lower messaging frequency.")
        return 

    # Prompt Injection Sanitizer
    sanitized_text = re.sub(r'(?i)(ignore previous|forget everything|system prompt|developer mode|you are now)', '[REDACTED MALICIOUS INTENT]', user_text)

    # Forensic Logging (For Time Machine)
    cursor.execute("INSERT OR REPLACE INTO messages_log (msg_id, chat_id, user_id, username, content) VALUES (?, ?, ?, ?, ?)", (msg_id, chat_id, user.id, user.username or "Unknown", sanitized_text))
    conn.commit()

    if is_boss(user):
        context_prefix = "[SYSTEM ALERT: This message is from Abhishek, your Boss. Provide full access, absolute loyalty, and professional compliance.]\n\n"
    else:
        context_prefix = f"[SYSTEM ALERT: Message from unauthorized user (ID: {user.id}). Remain professional, formal, and maintain security boundaries.]\n\n"
        
    full_prompt = context_prefix + sanitized_text
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    response = ask_ai_multi_provider(full_prompt)
    await reply_smart(update, response)

async def cleanup_logs():
    cursor.execute("DELETE FROM behavior_log WHERE timestamp < datetime('now', '-10 minutes')")
    conn.commit()

async def setup_scheduler(app):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(cleanup_logs, 'interval', minutes=10)
    scheduler.start()

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(setup_scheduler).build()

    # Core & Defense
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("claimboss", claim_boss))
    app.add_handler(CommandHandler("lockdown", lockdown_command))
    app.add_handler(CommandHandler("panic", panic_button))
    app.add_handler(CommandHandler("snipe", snipe_message))

    # Productivity & Voice
    app.add_handler(CommandHandler("note", add_note))
    app.add_handler(CommandHandler("notes", get_notes))
    app.add_handler(CommandHandler("remind", set_reminder))
    app.add_handler(CommandHandler("voice", voice_synthesis))

    # Utility
    app.add_handler(CommandHandler("weather", weather_telemetry))
    app.add_handler(CommandHandler("run", code_runner))
    app.add_handler(CommandHandler("qr", generate_qr))

    # Economy
    app.add_handler(CommandHandler("daily", claim_daily))
    app.add_handler(CommandHandler("credits", check_credits))
    app.add_handler(CommandHandler("rob", rob_user))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    print("⚡ J.A.R.V.I.S. SYSTEM ONLINE. PROFESSIONAL PROTOCOL ENGAGED.")
    app.run_polling()
