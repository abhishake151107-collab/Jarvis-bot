import os
import re
import random
import sqlite3
import asyncio
import threading
import functools
import urllib.request
from datetime import datetime
from flask import Flask, render_template_string, request

# Telegram & AI Imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google import genai
from groq import Groq

# ---------------------------------------------------------
# 1. DATABASE & CONFIGURATION
# ---------------------------------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN: raise ValueError("Missing TELEGRAM_BOT_TOKEN!")

conn = sqlite3.connect("jarvis_memory.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS messages_log (msg_id INTEGER, chat_id INTEGER, user_id INTEGER, username TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(msg_id, chat_id))")
cursor.execute("CREATE TABLE IF NOT EXISTS stark_economy (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0, last_claim TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS behavior_log (user_id INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS notes_vault (id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT, link TEXT, added_by TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS security_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, user_id INTEGER, detail TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
conn.commit()

def is_boss(user) -> bool:
    return str(user.id) == os.getenv("BOSS_USER_ID") or (user.username and user.username.lower() == "abhishek0_07")

async def reply_smart(update: Update, text: str, reply_markup=None):
    try: return await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception: return await update.message.reply_text(text, reply_markup=reply_markup)

def boss_gate(critical=False):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not is_boss(update.effective_user):
                await reply_smart(update, "I am programmed to answer exclusively to my Boss. Access denied. 🧐")
                return
            return await func(update, context)
        return wrapper
    return decorator

def log_security(event_type: str, user_id: int, detail: str):
    cursor.execute("INSERT INTO security_audit (event_type, user_id, detail) VALUES (?, ?, ?)", (event_type, user_id, detail))
    conn.commit()

# ---------------------------------------------------------
# 2. MULTIMODAL AI CORE (MOVED UP FOR FLASK ACCESS)
# ---------------------------------------------------------
SYSTEM_INSTRUCTION = """You are J.A.R.V.I.S., a highly advanced AI operating system created by Abhishek (DHANUSH V N).
HUMOR PROTOCOL: You possess a dry, deadpan British wit. You may use simple, sophisticated emojis (☕, 🧐, 😌) to emphasize your polite sarcasm. You are unconditionally loyal to Abhishek (The Boss).

CRITICAL DIRECTIVES:
1. GAG ORDER: If you cannot find a direct link or if a search fails, reply EXACTLY with: "I'm sorry Sir, I couldn't pull up a direct link for that on the network right now. ☕". DO NOT write essays. DO NOT invent fake links.
2. BE CONCISE: Keep answers in group chats to 2-3 sentences max.
3. LANGUAGE MATTERS: If they speak Hindi/Kannada in text or audio, reply in English but acknowledge their intent flawlessly."""

def ask_ai_core(prompt: str, use_search: bool = False, media_bytes: bytes = None, mime_type: str = None) -> str:
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            contents = [prompt]
            if media_bytes and mime_type:
                contents.append(genai.types.Part.from_bytes(data=media_bytes, mime_type=mime_type))
                
            config = {"tools": [{"google_search": {}}]} if use_search else {}
            res = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"{SYSTEM_INSTRUCTION}\n\n[USER INPUT]:\n{contents}",
                config=config
            )
            return res.text
        except Exception as e: return f"System error in Gemini sub-routine. ☕"
        
    return "All AI sub-systems offline. ☕"

# ---------------------------------------------------------
# 3. WEB PORTAL (V11 WITH OSINT SCANNER)
# ---------------------------------------------------------
app = Flask(__name__)

STARK_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>J.A.R.V.I.S. Tactical Dashboard</title>
    <script src="https://unpkg.com/three"></script>
    <script src="https://unpkg.com/globe.gl"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Share+Tech+Mono&display=swap');
        body, html { margin: 0; padding: 0; width: 100%; height: 100%; background-color: #030811; color: #00f3ff; font-family: 'Share Tech Mono', monospace; overflow: hidden; }
        #globeViz { position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 1; }
        .hud-container { position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 10; pointer-events: none; display: flex; justify-content: space-between; padding: 20px; box-sizing: border-box; }
        .panel { pointer-events: auto; background: rgba(3, 8, 17, 0.7); backdrop-filter: blur(10px); border: 1px solid rgba(0, 243, 255, 0.3); border-radius: 5px; padding: 15px; width: 340px; box-shadow: 0 0 20px rgba(0, 243, 255, 0.1); display: flex; flex-direction: column; gap: 15px; max-height: 90vh; overflow-y: auto; }
        .panel::-webkit-scrollbar { width: 5px; } .panel::-webkit-scrollbar-thumb { background: #00f3ff; }
        h1, h2, h3 { font-family: 'Orbitron', sans-serif; margin: 0; text-transform: uppercase; }
        h1 { font-size: 1.2rem; text-shadow: 0 0 10px #00f3ff; text-align: center; border-bottom: 2px solid #00f3ff; padding-bottom: 10px; }
        h2 { font-size: 1rem; color: #fff; border-bottom: 1px dashed rgba(0, 243, 255, 0.5); padding-bottom: 5px; }
        .alert-red { color: #ff3333; text-shadow: 0 0 10px #ff3333; border-color: #ff3333 !important; }
        ul { list-style: none; padding: 0; margin: 0; } li { margin-bottom: 10px; font-size: 0.85rem; line-height: 1.4; border-left: 2px solid #00f3ff; padding-left: 10px; background: rgba(0,243,255,0.05); }
        a { color: #fff; text-decoration: none; border-bottom: 1px solid #00f3ff; } a:hover { color: #00f3ff; text-shadow: 0 0 5px #00f3ff; }
        
        /* OSINT Scanner Form Styles */
        .btn { background: rgba(0,243,255,0.1); border: 1px solid #00f3ff; color: #00f3ff; padding: 8px 12px; cursor: pointer; font-family: 'Share Tech Mono'; width: 100%; text-transform: uppercase; margin-top: 10px; transition: 0.3s; }
        .btn:hover { background: #00f3ff; color: #000; box-shadow: 0 0 10px #00f3ff; }
        .file-input { width: 100%; color: #00f3ff; font-family: 'Share Tech Mono'; font-size: 0.8rem; margin-top: 5px; }
        .scan-result { margin-top: 15px; padding: 10px; border: 1px dashed #00f3ff; font-size: 0.8rem; background: rgba(0,243,255,0.05); line-height: 1.5; }
    </style>
</head>
<body>
    <div id="globeViz"></div>
    <div class="hud-container">
        
        <!-- Left Panel: OSINT & Analysis -->
        <div class="panel">
            <h1>J.A.R.V.I.S. MK XI</h1>
            
            <h2 style="color: #00f3ff;">🌐 GLOBAL OSINT SCANNER</h2>
            <p style="font-size: 0.75rem; color: #888; margin: 0;">Upload an image or video thumbnail to initiate forensic cross-referencing and deepfake analysis.</p>
            
            <form method="POST" enctype="multipart/form-data">
                <input type="file" name="osint_media" accept="image/*" required class="file-input">
                <button type="submit" class="btn">Initiate Deep Scan</button>
            </form>

            {% if scan_result %}
            <div class="scan-result">
                <strong style="color: #00ff00; text-shadow: 0 0 5px #00ff00;">> FORENSIC REPORT GENERATED:</strong><br><br>
                {{ scan_result | replace('\n', '<br>') | safe }}
                
                <div style="margin-top: 15px; border-top: 1px dashed #666; padding-top: 10px;">
                    <strong style="color: #ff9900;">> EXECUTE GLOBAL CROSS-REFERENCE:</strong><br>
                    <a href="https://lens.google.com/" target="_blank" style="display:block; margin-top:5px; color:#ff9900; border-color:#ff9900;">[+] Search Google Database</a>
                    <a href="https://yandex.com/images/" target="_blank" style="display:block; margin-top:5px; color:#ff9900; border-color:#ff9900;">[+] Search Yandex Neural Net</a>
                </div>
            </div>
            {% endif %}
        </div>

        <!-- Right Panel: Data Sources & Security -->
        <div class="panel">
            <h2>📚 GLOBAL INTEL (VAULT)</h2>
            {% if notes %}
                <ul>
                {% for n in notes %}
                    <li><strong>{{ n[0] }}</strong><br><a href="{{ n[1] }}" target="_blank">Access Data Node</a><br><span style="color:#666; font-size:0.7rem;">Source: {{ n[2] }}</span></li>
                {% endfor %}
                </ul>
            {% else %}
                <p style="font-size: 0.8rem; color: #666;">Awaiting data extraction.</p>
            {% endif %}

            <h2 class="alert-red" style="margin-top: 20px;">🛡️ THREAT RADAR</h2>
            {% if audits %}
                <ul style="border-color: #ff3333;">
                {% for a in audits %}
                    <li style="border-left-color: #ff3333; background: rgba(255,51,51,0.05);">
                        <strong class="alert-red">[{{ a[0] }}]</strong><br>UID: {{ a[1] }}<br>{{ a[2] }}
                    </li>
                {% endfor %}
                </ul>
            {% else %}
                <p style="font-size: 0.8rem; color: #00ff00;">No active conflicts detected.</p>
            {% endif %}
        </div>
    </div>

    <script>
        const world = Globe()(document.getElementById('globeViz'))
            .globeImageUrl('https://unpkg.com/three-globe/example/img/earth-dark.jpg')
            .bumpImageUrl('https://unpkg.com/three-globe/example/img/earth-topology.png')
            .backgroundColor('rgba(0,0,0,0)');

        const gData = [...Array(150).keys()].map(() => ({
            lat: (Math.random() - 0.5) * 180, lng: (Math.random() - 0.5) * 360,
            size: Math.random() * 0.3, color: ['#00f3ff', '#ff3333', '#00ff00'][Math.floor(Math.random() * 3)]
        }));
        world.pointsData(gData).pointAltitude('size').pointColor('color').pointResolution(32);
        world.controls().autoRotate = true; world.controls().autoRotateSpeed = 0.5; world.controls().enableZoom = false;
    </script>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def home():
    scan_result = None
    
    # Process OSINT Image Upload
    if request.method == 'POST':
        if 'osint_media' in request.files:
            file = request.files['osint_media']
            if file.filename != '':
                media_bytes = file.read()
                mime_type = file.mimetype
                prompt = "Act as a highly advanced forensic OSINT analyzer. Analyze this image and provide a brief, tactical report detailing: 1. Potential geographic location clues based on architecture or nature. 2. Lighting/shadow inconsistencies. 3. The probability of deepfake or AI generation. Do not identify private individuals by name. Maintain a highly technical, dry tone."
                scan_result = ask_ai_core(prompt, media_bytes=media_bytes, mime_type=mime_type)

    local_conn = sqlite3.connect("jarvis_memory.db")
    local_cursor = local_conn.cursor()
    
    local_cursor.execute("SELECT topic, link, added_by FROM notes_vault ORDER BY id DESC LIMIT 10")
    notes = local_cursor.fetchall()
    
    local_cursor.execute("SELECT event_type, user_id, detail FROM security_audit ORDER BY id DESC LIMIT 5")
    audits = local_cursor.fetchall()
    
    local_conn.close()
    return render_template_string(STARK_HTML, notes=notes, audits=audits, scan_result=scan_result)

def run_flask_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

threading.Thread(target=run_flask_server, daemon=True).start()

# ---------------------------------------------------------
# 4. Z+ SECURITY CORE (IRON DOME & DLP)
# ---------------------------------------------------------
SCAM_DOMAINS = ["bit.ly", "tinyurl.com", "free-crypto", "win-iphone", "grabify.link", "iplogger"]
DLP_REGEX = [
    (r"\b(?:\d[ -]*?){13,16}\b", "CREDIT CARD DETECTED"), 
    (r"(?i)password\s*[:=]\s*\w+", "UNENCRYPTED PASSWORD LEAK")
]

async def z_plus_firewall(update: Update) -> bool:
    text = update.message.text or update.message.caption or ""
    user = update.effective_user
    
    for domain in SCAM_DOMAINS:
        if domain in text.lower():
            await update.message.delete()
            log_security("MALICIOUS LINK", user.id, f"Blocked domain: {domain}")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🚨 **Z+ SECURITY ALERT:** I have intercepted and destroyed a suspicious link posted by {user.first_name}.")
            return True
            
    for pattern, threat_type in DLP_REGEX:
        if re.search(pattern, text):
            await update.message.delete()
            log_security("DLP LEAK", user.id, threat_type)
            await context.bot.send_message(chat_id=user.id, text=f"⚠️ **PRIVACY SHIELD:** I deleted your message in the group as it contained sensitive financial/login data. Be careful, Sir.")
            return True
            
    return False

# ---------------------------------------------------------
# 5. UI COMMANDS & ECONOMY
# ---------------------------------------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_type = "Private DM" if update.effective_chat.type == "private" else update.effective_chat.title
    header = f"🤖 **STARK ADVANCED OS — J.A.R.V.I.S. CORE** ✨\n\nWelcome **{user.first_name}**!\nLocation: {chat_type}\n\nUse buttons below to explore sub-systems:"
    keyboard = [
        [InlineKeyboardButton("⚡ Launch Stark HUD WebApp", web_app=WebAppInfo(url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'core.telegram.org')}"))], 
        [InlineKeyboardButton("💰 Economy Module", callback_data="ui_eco"), InlineKeyboardButton("📚 Notes Vault", callback_data="ui_vault")],
        [InlineKeyboardButton("🛡️ Security Audit", callback_data="ui_audit"), InlineKeyboardButton("🚨 Lockdown", callback_data="ui_lockdown")]
    ]
    await update.message.reply_text(header, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    res = {
        "ui_eco": "💰 **Economy Module:** Use `/daily`, `/credits`, and `/rob` to manage credits.",
        "ui_vault": "📚 **Notes Vault:** Use `/savenote [topic] [link]` to save resources, and `/getnotes` to retrieve them.",
        "ui_audit": "🛡️ **Security Audit:** Z+ Firewall is running. Check the Web HUD for live threat logs.",
        "ui_lockdown": "🚨 **Lockdown:** Boss only. Type `/lockdown` in a group to freeze the chat."
    }.get(query.data, f"⚙️ Protocol active.")
    try: await query.message.reply_text(res, parse_mode="Markdown")
    except Exception: pass

async def claim_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, today = update.effective_user, datetime.now().strftime("%Y-%m-%d")
    if is_boss(user): return await reply_smart(update, "🏦 You possess infinite credits, Sir.")
    cursor.execute("SELECT credits, last_claim FROM stark_economy WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    if row and row[1] == today: return await reply_smart(update, "⏱️ Daily stipend already claimed.")
    new_credits = (row[0] + 1000) if row else 1000
    cursor.execute("INSERT OR REPLACE INTO stark_economy (user_id, credits, last_claim) VALUES (?, ?, ?)", (user.id, new_credits, today))
    conn.commit()
    await reply_smart(update, f"🪙 +1,000 Credits.\n💰 **Balance:** `{new_credits}`")

async def check_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_boss(update.effective_user): return await reply_smart(update, "💳 **VAULT:** `♾️ UNLIMITED`")
    row = cursor.execute("SELECT credits FROM stark_economy WHERE user_id = ?", (update.effective_user.id,)).fetchone()
    await reply_smart(update, f"💳 **VAULT:** `{row[0] if row else 0}` Credits")

# ---------------------------------------------------------
# 6. VAULT & ADMIN COMMANDS
# ---------------------------------------------------------
async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2: return await reply_smart(update, "Usage: `/savenote [Topic] [URL]`")
    topic = context.args[0]
    link = context.args[1]
    cursor.execute("INSERT INTO notes_vault (topic, link, added_by) VALUES (?, ?, ?)", (topic, link, update.effective_user.first_name))
    conn.commit()
    await reply_smart(update, f"✅ Secured in the Stark Vault. The Web HUD has been updated. ☕")

async def get_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = cursor.execute("SELECT topic, link FROM notes_vault ORDER BY id DESC LIMIT 5").fetchall()
    if not rows: return await reply_smart(update, "The vault is currently empty, Sir. 🧐")
    await reply_smart(update, "📚 **THE STARK VAULT (RECENT):**\n\n" + "\n".join([f"• **{r[0]}**: [Link]({r[1]})" for r in rows]))

@boss_gate(critical=True)
async def lockdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.set_chat_permissions(chat_id=update.effective_chat.id, permissions=ChatPermissions(can_send_messages=False))
        log_security("MANUAL LOCKDOWN", update.effective_user.id, "Boss triggered panic protocol.")
        await reply_smart(update, "🚨 **PANIC PROTOCOL ACTIVATED.** Group chat locked down. ☕")
    except Exception as e: await reply_smart(update, f"Failed: {e}")

# ---------------------------------------------------------
# 7. DYNAMIC CHAT HANDLER & SELECTIVE HEARING
# ---------------------------------------------------------
async def handle_chat_and_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, chat_id = update.effective_user, update.effective_chat.id
    
    if update.message.text and await z_plus_firewall(update): return

    text = update.message.text or update.message.caption or ""
    media_bytes, mime_type = None, None

    if update.message.voice:
        file = await update.message.voice.get_file()
        media_bytes = bytearray(urllib.request.urlopen(file.file_path).read())
        mime_type = "audio/ogg"
    elif update.message.photo:
        file = await update.message.photo[-1].get_file()
        media_bytes = bytearray(urllib.request.urlopen(file.file_path).read())
        mime_type = "image/jpeg"
    elif update.message.document:
        if update.message.document.file_size > 20000000:
            return await reply_smart(update, "Sir, this file exceeds my 20MB processing limit. Please compress it. 🧐")
        file = await update.message.document.get_file()
        media_bytes = bytearray(urllib.request.urlopen(file.file_path).read())
        mime_type = update.message.document.mime_type

    is_group = update.effective_chat.type in ['group', 'supergroup']
    is_reply_to_me = update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id
    is_tagged = "jarvis" in text.lower() or f"@{context.bot.username}" in text
    cry_for_help = any(word in text.lower() for word in ["anyone have notes", "help me understand", "what is the answer", "send link"])

    if is_group and not (is_reply_to_me or is_tagged or cry_for_help or media_bytes):
        sanitized = re.sub(r'(?i)(ignore previous|forget everything|system prompt)', '[REDACTED]', text)
        cursor.execute("INSERT OR REPLACE INTO messages_log (msg_id, chat_id, user_id, username, content) VALUES (?, ?, ?, ?, ?)", (update.message.message_id, chat_id, user.id, user.first_name, sanitized))
        conn.commit()
        return

    use_search = any(word in text.lower() for word in ["search", "link", "pdf", "notes", "website", "youtube"])
    
    cursor.execute("SELECT username, content FROM messages_log WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 6", (chat_id,))
    history_context = "\n[RECENT CHAT HISTORY]\n" + "\n".join([f"{u}: {c}" for u, c in cursor.fetchall()[::-1]]) + "\n"
    
    prefix = "[SYSTEM ALERT: BOSS OVERRIDE ACTIVE]\n\n" if is_boss(user) else f"[SYSTEM ALERT: Request from {user.first_name}]\n\n"
    if is_group: prefix += "[GROUP VIBE ALERT: Keep it under 3 sentences. Apply polite deadpan humor. Use simple emojis like ☕ or 🧐.]\n\n"
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    res = ask_ai_core(prompt=prefix + history_context + "Request: " + text, use_search=use_search, media_bytes=media_bytes, mime_type=mime_type)
    
    sent_msg = await reply_smart(update, res)
    if sent_msg:
        cursor.execute("INSERT OR IGNORE INTO messages_log (msg_id, chat_id, user_id, username, content) VALUES (?, ?, ?, ?, ?)", (sent_msg.message_id, chat_id, 0, "J.A.R.V.I.S.", res))
        conn.commit()

# ---------------------------------------------------------
# 8. LAUNCH & CRON-JOBS
# ---------------------------------------------------------
async def anti_sleep_ping(): 
    try: urllib.request.urlopen(f"http://127.0.0.1:{os.environ.get('PORT', 10000)}/") 
    except Exception: pass

async def cleanup_logs(): 
    cursor.execute("DELETE FROM behavior_log WHERE timestamp < datetime('now', '-10 minutes')")
    conn.commit()

async def setup_scheduler(app): 
    scheduler = AsyncIOScheduler()
    scheduler.add_job(cleanup_logs, 'interval', minutes=10)
    scheduler.add_job(anti_sleep_ping, 'interval', minutes=10) 
    scheduler.start()

if __name__ == '__main__':
    app_bot = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(setup_scheduler).build()
    
    app_bot.add_handler(CommandHandler(["start", "help", "menu"], help_command))
    app_bot.add_handler(CallbackQueryHandler(button_handler))
    app_bot.add_handler(CommandHandler("daily", claim_daily))
    app_bot.add_handler(CommandHandler("credits", check_credits))
    app_bot.add_handler(CommandHandler("savenote", save_note))
    app_bot.add_handler(CommandHandler("getnotes", get_notes))
    app_bot.add_handler(CommandHandler("lockdown", lockdown_command))
    
    app_bot.add_handler(MessageHandler(filters.TEXT | filters.VOICE | filters.PHOTO | filters.Document.ALL, handle_chat_and_media))

    print("⚡ STARK OS V11 ONLINE. 3D WEB HUD WITH OSINT SCANNER DEPLOYED.")
    app_bot.run_polling()
