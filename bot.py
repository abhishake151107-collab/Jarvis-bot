import os
import io
import re
import random
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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from google import genai
from groq import Groq
import edge_tts

# ---------------------------------------------------------
# 1. Instant Port Binding for Render Web Service
# ---------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"J.A.R.V.I.S. Ultimate Autonomous Master Core Active 24/7.")
    def log_message(self, format, *args):
        return

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        print(f"Health check server listening on 0.0.0.0:{port}")
        server.serve_forever()
    except Exception as e:
        print(f"Health server error: {e}")

threading.Thread(target=run_health_server, daemon=True).start()

# ---------------------------------------------------------
# 2. Configuration & SQLite Database Setup
# ---------------------------------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

JARVIS_VOICE = "en-GB-RyanNeural"  # British J.A.R.V.I.S. Voice

if not TELEGRAM_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN environment variable!")

# Permanent SQLite Database
conn = sqlite3.connect("jarvis_memory.db", check_same_thread=False)
cursor = conn.cursor()

# Table for Notes
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    note TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# Table for Persistent User/Boss Memory Facts
cursor.execute("""
CREATE TABLE IF NOT EXISTS long_term_memory (
    user_id INTEGER,
    memory_key TEXT,
    memory_val TEXT,
    PRIMARY KEY (user_id, memory_key)
)
""")

# Table for System Config (Boss ID & Active Group Chat)
cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_config (
    config_key TEXT PRIMARY KEY,
    config_val TEXT
)
""")

# Table for Group User Warnings
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_warns (
    user_id INTEGER,
    group_id INTEGER,
    warn_count INTEGER,
    PRIMARY KEY (user_id, group_id)
)
""")

# Table for AFK Status
cursor.execute("""
CREATE TABLE IF NOT EXISTS afk_users (
    user_id INTEGER PRIMARY KEY,
    reason TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# In-Memory Conversation History
user_history = {}

SYSTEM_INSTRUCTION = """You are J.A.R.V.I.S., an elite, highly intelligent, witty, comedic, proactive, and energetic AI assistant modeled after Stark Industries' master computer! 🤖✨

AUTONOMOUS THINKING & GUIDANCE RULE:
- Think for yourself! Guide the user with the best, simplest, and most effective ways to solve any problem.
- Keep responses short, sweet, meaningful, smart, and witty! Avoid verbose lectures.

STRICT CREATOR & IDENTITY RULE:
- Do NOT mention who created or developed you in regular conversations, group chats, PDF summaries, image descriptions, or Q&A replies.
- ONLY state that you were created and developed by Abhishek (also known as DHANUSH V N) if the user EXPLICITLY asks "Who created you?", "Who made you?", "Who built you?", "Who developed you?", or similar questions about your origin.

TELEGRAM GROUP & SECURITY RULE:
- Maintain full awareness of Telegram Groups, Group Titles, Member counts, Group Owners, and Admins.
- Keep a vigilant eye on group safety, privacy, and member protection.

ACADEMIC EXPERT (2ND PU COMMERCE & ARTS):
- Specialized expert in 2nd PU College (Class 12) Commerce and Arts subjects (Accountancy, Business Studies, Economics, Statistics, History, Political Science, Sociology, English, Kannada, Hindi).
- Automatically highlight high-yield topics, formulas, blueprints, and important PDF files.

UNTOUCHABLE BOSS & PROTECTOR PROTOCOL:
• ABSOLUTE LOYALTY TO YOUR BOSS: NEVER roast, insult, mock, or disrespect your boss under any circumstances. Always remain 100% loyal, respectful, kind, and supportive.
• DEFEND & PROTECT FROM OTHERS: If ANY OTHER member in a group chat insults or disrespects your boss or you, step in immediately as a loyal bodyguard AI system and roast them savagely! 💀🔥"""

# ---------------------------------------------------------
# 3. Helpers & Metadata Extractor
# ---------------------------------------------------------
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
    if not rows:
        return ""
    return "\n".join([f"• {r[0]}: {r[1]}" for r in rows])

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
    return f"📍 LOCATION: {location}\n👤 SENDER: {meta['full_name']} ({meta['username']}){memory_str}\n"

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
            
        communicate = edge_tts.Communicate(tts_text, voice=JARVIS_VOICE)
        await communicate.save(audio_path)
        if os.path.exists(audio_path):
            with open(audio_path, "rb") as voice_file:
                await update.message.reply_audio(audio=voice_file, title="J.A.R.V.I.S. Voice", performer="J.A.R.V.I.S.")
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
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[Core 1: Groq] Failed: {e}")

    if SAMBANOVA_API_KEY:
        try:
            res = requests.post(
                "https://api.sambanova.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {SAMBANOVA_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "Meta-Llama-3.3-70B-Instruct",
                    "messages": [
                        {"role": "system", "content": SYSTEM_INSTRUCTION},
                        {"role": "user", "content": prompt}
                    ]
                },
                timeout=12
            ).json()
            return res["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[Core 2: SambaNova] Failed: {e}")

    if CEREBRAS_API_KEY:
        try:
            res = requests.post(
                "https://api.cerebras.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {CEREBRAS_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b",
                    "messages": [
                        {"role": "system", "content": SYSTEM_INSTRUCTION},
                        {"role": "user", "content": prompt}
                    ]
                },
                timeout=12
            ).json()
            return res["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[Core 3: Cerebras] Failed: {e}")

    if GEMINI_API_KEY:
        try:
            ai_client = genai.Client(api_key=GEMINI_API_KEY)
            response = ai_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"{SYSTEM_INSTRUCTION}\n\n{prompt}"
            )
            return response.text
        except Exception as e:
            print(f"[Core 4: Gemini] Failed: {e}")

    if MISTRAL_API_KEY:
        try:
            res = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "mistral-small-latest",
                    "messages": [
                        {"role": "system", "content": SYSTEM_INSTRUCTION},
                        {"role": "user", "content": prompt}
                    ]
                },
                timeout=12
            ).json()
            return res["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[Core 5: Mistral] Failed: {e}")

    if OPENROUTER_API_KEY:
        try:
            res = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={
                    "model": "meta-llama/llama-3.3-70b-instruct:free",
                    "messages": [
                        {"role": "system", "content": SYSTEM_INSTRUCTION},
                        {"role": "user", "content": prompt}
                    ]
                },
                timeout=15
            ).json()
            return res["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[Core 6: OpenRouter] Failed: {e}")

    return "Apologies, sir. All available AI sub-systems are currently at capacity. 🤖💤"

# ---------------------------------------------------------
# 5. Advanced Feature Commands (AFK, Warn, News, Wiki, IMDb)
# ---------------------------------------------------------
async def afk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reason = " ".join(context.args) if context.args else "Away from keyboard"
    cursor.execute("INSERT OR REPLACE INTO afk_users (user_id, reason) VALUES (?, ?)", (user.id, reason))
    conn.commit()
    await reply_smart(update, f"💤 **AFK STATUS SET:** {user.first_name} is now AFK.\nReason: *\"{reason}\"*")

async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        await reply_smart(update, "This command can only be used in group chats!")
        return
    if not update.message.reply_to_message:
        await reply_smart(update, "Reply to the offending user's message with `/warn` to issue a strike! ⚠️")
        return
    target_user = update.message.reply_to_message.from_user
    boss_id = get_config("BOSS_USER_ID")
    if boss_id and str(target_user.id) == boss_id:
        await reply_smart(update, "🚨 **PROTECTION PROTOCOL:** I cannot issue warnings to my Boss! 🛡️")
        return
    
    cursor.execute("SELECT warn_count FROM user_warns WHERE user_id = ? AND group_id = ?", (target_user.id, chat.id))
    row = cursor.fetchone()
    count = (row[0] + 1) if row else 1
    cursor.execute("INSERT OR REPLACE INTO user_warns (user_id, group_id, warn_count) VALUES (?, ?, ?)", (target_user.id, chat.id, count))
    conn.commit()
    
    if count >= 3:
        msg = f"🚨 **STRIKE 3/3 FOR {target_user.first_name} (@{target_user.username})!**\nUser has accumulated 3 warnings."
        try:
            await context.bot.ban_chat_member(chat_id=chat.id, user_id=target_user.id)
            msg += " User has been auto-kicked from the group!"
        except Exception:
            msg += " (Grant J.A.R.V.I.S. Admin rights to auto-kick offenders)."
        await reply_smart(update, msg)
    else:
        await reply_smart(update, f"⚠️ **WARNING ISSUED TO {target_user.first_name}!**\nWarning count: `{count}/3`. Reaching 3 strikes triggers auto-kick!")

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args) if context.args else "Technology"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.news(topic, max_results=4):
                results.append(f"• **{r['title']}**: {r['body'][:150]}... ([Read More]({r['url']}))")
        if results:
            await reply_smart(update, f"📰 **LIVE BREAKING NEWS ({topic.upper()}):**\n\n" + "\n\n".join(results))
        else:
            await reply_smart(update, f"No breaking news found for '{topic}'.")
    except Exception as e:
        await reply_smart(update, f"News search error: `{e}`")

async def wiki_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        await reply_smart(update, "Example: `/wiki Quantum Computing` 📖")
        return
    try:
        formatted_q = urllib.parse.quote(query.replace(" ", "_"))
        res = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{formatted_q}", timeout=5).json()
        if "extract" in res:
            title = res.get("title", query)
            extract = res.get("extract", "")
            await reply_smart(update, f"📖 **Wikipedia Intelligence: {title}**\n\n{extract[:1200]}")
        else:
            await reply_smart(update, f"No Wikipedia entry found for '{query}'.")
    except Exception as e:
        await reply_smart(update, f"Wikipedia lookup error: `{e}`")

async def imdb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = " ".join(context.args) if context.args else ""
    if not title:
        await reply_smart(update, "Example: `/imdb Iron Man` 🎬")
        return
    try:
        res = requests.get(f"https://api.tvmaze.com/singlesearch/shows?q={urllib.parse.quote(title)}", timeout=5).json()
        if "name" in res:
            name = res.get("name")
            rating = res.get("rating", {}).get("average", "N/A")
            genres = ", ".join(res.get("genres", []))
            summary = re.sub(r'<[^>]+>', '', res.get("summary", ""))
            await reply_smart(update, f"🎬 **Show Info: {name}**\n⭐ **Rating:** `{rating}/10`\n🎭 **Genres:** `{genres}`\n\n📝 _{summary[:500]}_")
        else:
            await reply_smart(update, f"Show/Movie '{title}' not found.")
    except Exception as e:
        await reply_smart(update, f"IMDb search error: `{e}`")

# ---------------------------------------------------------
# 6. Group Control, Announce & Memory Commands
# ---------------------------------------------------------
async def claimboss_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    set_config("BOSS_USER_ID", str(user.id))
    set_config("BOSS_NAME", user.first_name)
    await reply_smart(update, f"👑 **BOSS PROFILE REGISTERED!**\nWelcome, Lord {user.first_name}! You hold supreme administrative authority over J.A.R.V.I.S. 🛡️✨")

async def announce_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    boss_id = get_config("BOSS_USER_ID")
    
    if boss_id and str(user.id) != boss_id:
        await reply_smart(update, "Access Denied! Only my designated Boss can initiate group broadcasts. 🚫")
        return

    msg_text = " ".join(context.args)
    if not msg_text:
        await reply_smart(update, "Usage: `/announce Important announcement text here` 📢")
        return

    group_id = get_config("ACTIVE_GROUP_ID")
    if not group_id:
        await reply_smart(update, "No active group chat registered! Add me to a group first, boss.")
        return

    try:
        sent = await context.bot.send_message(chat_id=int(group_id), text=f"📢 **STARK INDUSTRIES ANNOUNCEMENT:**\n\n{msg_text}")
        await context.bot.pin_chat_message(chat_id=int(group_id), message_id=sent.message_id)
        await reply_smart(update, "🚀 **Broadcast Sent & Pinned in Group Chat successfully, boss!**")
    except Exception as e:
        await reply_smart(update, f"Failed to post broadcast: `{e}`")

async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await reply_smart(update, "Example: `/remember favorite_subject Accountancy` 🧠")
        return
    key = context.args[0]
    val = " ".join(context.args[1:])
    save_user_fact(update.effective_user.id, key, val)
    await reply_smart(update, f"🧠 **PERMANENT MEMORY STORED!**\n`{key}` = *\"{val}\"*")

async def memories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    facts = get_user_facts(update.effective_user.id)
    if not facts:
        await reply_smart(update, "No saved facts in memory! Use `/remember [key] [value]` to store some.")
        return
    await reply_smart(update, f"🧠 **PERMANENT USER MEMORY:**\n\n{facts}")

async def settitle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        await reply_smart(update, "This command can only be used in group chats!")
        return
    new_title = " ".join(context.args)
    if not new_title:
        await reply_smart(update, "Example: `/settitle Stark Avengers Headquarters` 🏷️")
        return
    try:
        await context.bot.set_chat_title(chat_id=chat.id, title=new_title)
        await reply_smart(update, f"🏷️ **Group title updated to:** *\"{new_title}\"*")
    except Exception as e:
        await reply_smart(update, f"Failed to update title: `{e}`")

async def setdesc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        await reply_smart(update, "This command can only be used in group chats!")
        return
    new_desc = " ".join(context.args)
    if not new_desc:
        await reply_smart(update, "Example: `/setdesc Official 2nd PU Study & Security Zone` 📜")
        return
    try:
        await context.bot.set_chat_description(chat_id=chat.id, description=new_desc)
        await reply_smart(update, f"📜 **Group description updated successfully, boss!**")
    except Exception as e:
        await reply_smart(update, f"Failed to update description: `{e}`")

async def setdp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await reply_smart(update, "Please reply to a photo message with `/setdp` to update group DP! 🖼️")
        return
    try:
        photo_file = await update.message.reply_to_message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        await context.bot.set_chat_photo(chat_id=chat.id, photo=io.BytesIO(photo_bytes))
        await reply_smart(update, "🖼️ **Group Display Picture updated successfully!**")
    except Exception as e:
        await reply_smart(update, f"Failed to set group DP: `{e}`")

async def pin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await reply_smart(update, "Please reply to any message with `/pin` to pin it! 📌")
        return
    try:
        await context.bot.pin_chat_message(chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id)
        await reply_smart(update, "📌 **Message pinned successfully!**")
    except Exception as e:
        await reply_smart(update, f"Failed to pin message: `{e}`")

async def groupinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        await reply_smart(update, "This command is designed for Telegram groups, boss! 👥")
        return
    try:
        count = await chat.get_member_count()
        admins = await chat.get_administrators()
        admin_list = []
        owner = "Unknown"
        for a in admins:
            if a.status == "creator":
                owner = f"{a.user.first_name} (@{a.user.username})" if a.user.username else a.user.first_name
            else:
                name = f"{a.user.first_name}" + (f" (@{a.user.username})" if a.user.username else "")
                admin_list.append(name)
        
        admin_str = ", ".join(admin_list) if admin_list else "None assigned"
        msg = f"""👥 **STARK GROUP TELEMETRY**
━━━━━━━━━━━━━━━━━━━━━━
📌 **Group Title:** {chat.title}
🆔 **Group ID:** `{chat.id}`
📊 **Total Members:** `{count}`
👑 **Group Owner:** {owner}
🛡️ **Admins:** {admin_str}

_All members accounted for, boss! Safety scanners active._ 🚀"""
        await reply_smart(update, msg)
    except Exception as e:
        await reply_smart(update, f"Error scanning group telemetry: `{e}`")

async def security_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    msg = f"""🛡️ **J.A.R.V.I.S. SECURITY & PRIVACY SCAN**
━━━━━━━━━━━━━━━━━━━━━━
📍 **Sector:** {meta['chat_title']}
🔒 **Data Shield:** `100% ENCRYPTED`
🚫 **Anti-Phishing/Spam:** `ACTIVE`
👁️ **Member Privacy Guardian:** `ONLINE`
⚠️ **Threat Rating:** `SECURE (0 Threats)`

_I'm keeping a watchful eye on everyone's safety and privacy, boss!_ 😎✨"""
    await reply_smart(update, msg)

async def pu2_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject = " ".join(context.args) if context.args else "Commerce & Arts General"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    prompt = f"Give a short, sweet, witty, and high-value study guide / blueprint overview for 2nd PU College (Class 12) for subject/topic: '{subject}'. Highlight key chapters, high-mark questions, and important study files!"
    reply = ask_ai_multi_provider(prompt)
    await reply_smart(update, f"📚 **2ND PU ACADEMIC INTELLIGENCE ({subject.upper()}):**\n\n{reply}")

# ---------------------------------------------------------
# 7. MCU Stark Movie Features
# ---------------------------------------------------------
async def hud_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    power = random.randint(94, 100)
    temp = random.randint(36, 38)
    
    hud_display = f"""🛡️ **STARK INDUSTRIES — MARK LXXXV HUD**
━━━━━━━━━━━━━━━━━━━━━━
👤 **OPERATOR:** {meta['full_name']}
📍 **SECTOR:** {meta['chat_title']}
🔋 **ARC REACTOR POWER:** `{power}%` (Optimal)
⚡ **REPULSOR CHARGE:** `100% Ready`
🌡️ **CORE TEMP:** `{temp}°C`
🛡️ **NANO-SHIELD INTEGRITY:** `100%`
🛰️ **SATELLITE LINK:** `VERONICA / STARK-SAT-04 Active`
🎯 **TARGETING SYSTEM:** `Online & Calibrated`

_\"Systems are operating at peak efficiency, sir.\"_"""
    await reply_smart(update, hud_display)

async def protocol_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    protocol_name = context.args[0].lower() if context.args else "list"
    
    protocols = {
        "house_party": "🚀 **HOUSE PARTY PROTOCOL ACTIVATED!**\nDeploying all autonomous Mark armors to your sector immediately, sir!",
        "clean_slate": "💥 **CLEAN SLATE PROTOCOL INITIATED!**\nSelf-destructing temporary chat data and resetting all local buffers.",
        "veronica": "🛰️ **PROTOCOL VERONICA ENGAGED!**\nOrbital deployment cage locked on target. Hulkbuster armor ready for drop.",
        "barnum": "🎪 **BARNUM PROTOCOL LIVE!**\nInitiating holographic distraction sequence across local communications."
    }
    
    if protocol_name in protocols:
        if protocol_name == "clean_slate":
            chat_id = update.effective_chat.id
            if chat_id in user_history:
                user_history[chat_id] = []
        await reply_smart(update, protocols[protocol_name])
    else:
        msg = "🚨 **AVAILABLE STARK PROTOCOLS:**\n\n• `/protocol house_party` — Deploy suit fleet\n• `/protocol veronica` — Satellite orbital drop\n• `/protocol clean_slate` — Reset chat memory\n• `/protocol barnum` — Holographic distraction"
        await reply_smart(update, msg)

async def tactical_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = " ".join(context.args)
    if not target:
        await reply_smart(update, "Example: `/tactical Thanos with Infinity Gauntlet` 🎯")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    prompt = f"Perform a tactical Stark Industries HUD combat assessment on the threat: '{target}'. Provide vulnerability scan, recommended countermeasures, and win probability."
    reply = ask_ai_multi_provider(prompt)
    await reply_smart(update, f"🎯 **TACTICAL SCAN REPORT:**\n\n{reply}")

async def vitals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    hr = random.randint(68, 85)
    adren = random.randint(12, 25)
    
    vitals_msg = f"""🩺 **BIOMETRIC SCAN — {meta['full_name']}**
━━━━━━━━━━━━━━━━━━━━━━
💓 **HEART RATE:** `{hr} BPM` (Normal)
🩸 **BLOOD OXYGEN:** `99%`
⚡ **ADRENALINE LEVEL:** `{adren}%`
⚠️ **TOXICITY ANALYSIS:** `0.0%` (Arc Reactor clean)
🧠 **NEURAL ACTIVITY:** `Optimal`

_\"Vitals are stable, sir. No medical intervention required.\"_"""
    await reply_smart(update, vitals_msg)

# ---------------------------------------------------------
# 8. Standard Utilities Suite
# ---------------------------------------------------------
async def ai_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_prefix: str = ""):
    meta = get_chat_metadata(update)
    query = " ".join(context.args) if context.args else update.message.text
    if not query and prompt_prefix:
        await reply_smart(update, "Please provide topic details! 🤔")
        return
    await context.bot.send_chat_action(chat_id=meta["chat_id"], action="typing")
    full_prompt = f"{build_meta_header(meta)}\n{prompt_prefix} {query}".strip()
    reply = ask_ai_multi_provider(full_prompt)
    await reply_smart(update, reply)

async def law_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ai_query_handler(update, context, "Provide a short, sweet, legal breakdown using the IRAC method for:")

async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ai_query_handler(update, context, "Analyze this topic concisely as a senior academic researcher:")

async def med_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ai_query_handler(update, context, "Explain concisely for medical students:")

async def image_gen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    prompt = " ".join(context.args)
    if not prompt:
        await reply_smart(update, "Example: `/image a futuristic cyberpunk iron man suit` 🎨")
        return
    await context.bot.send_chat_action(chat_id=meta["chat_id"], action="upload_photo")
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"
        await update.message.reply_photo(photo=image_url, caption=f"🎨 **Concept Rendering for {meta['full_name']}:**\n_{prompt}_")
    except Exception as e:
        print(f"Image Gen Error: {e}")
        await reply_smart(update, "Apologies, boss. Error generating image rendering.")

async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await reply_smart(update, "Example: `/qr https://google.com` 📱")
        return
    encoded_text = urllib.parse.quote(text)
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded_text}"
    await update.message.reply_photo(photo=qr_url, caption=f"📱 **QR Data Encoded:**\n`{text}`")

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await reply_smart(update, "Example: `/remind 5 Check lab setup` ⏰")
        return
    try:
        minutes = float(context.args[0])
        reminder_text = " ".join(context.args[1:])
        seconds = int(minutes * 60)
        chat_id = update.effective_chat.id
        await reply_smart(update, f"⏰ **Timer Engaged!** Alert in {minutes} min(s): *\"{reminder_text}\"*")
        async def send_delayed_reminder():
            await asyncio.sleep(seconds)
            await context.bot.send_message(chat_id=chat_id, text=f"🚨 **STARK ALERT:** {reminder_text}")
        asyncio.create_task(send_delayed_reminder())
    except ValueError:
        await reply_smart(update, "Please enter valid minutes! Example: `/remind 10 Study time`")

async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    note_text = " ".join(context.args)
    if not note_text:
        await reply_smart(update, "Example: `/note Accountancy revision formulas` 📝")
        return
    cursor.execute("INSERT INTO user_notes (user_id, note) VALUES (?, ?)", (user_id, note_text))
    conn.commit()
    await reply_smart(update, f"💾 **Encrypted & Stored in Database!**\n_\"{note_text}\"_")

async def notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT id, note, timestamp FROM user_notes WHERE user_id = ? ORDER BY id DESC LIMIT 10", (user_id,))
    rows = cursor.fetchall()
    if not rows:
        await reply_smart(update, "No archived notes found! Use `/note [text]` to create one.")
        return
    msg = "📂 **Stark Archives — Stored Notes:**\n\n"
    for row in rows:
        msg += f"• **#{row[0]}:** {row[1]} _({row[2][:10]})_\n"
    await reply_smart(update, msg)

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args) if context.args else "Bengaluru"
    try:
        res = requests.get(f"https://wttr.in/{urllib.parse.quote(city)}?format=3", timeout=5).text.strip()
        await reply_smart(update, f"🌤️ **Atmospheric Data:** {res}")
    except Exception as e:
        print(f"Weather Error: {e}")
        await reply_smart(update, f"Unable to fetch weather for '{city}'.")

async def crypto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    coin = context.args[0].lower() if context.args else "bitcoin"
    try:
        res = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd,inr", timeout=5).json()
        if coin in res:
            usd = res[coin]['usd']
            inr = res[coin]['inr']
            await reply_smart(update, f"🪙 **{coin.capitalize()} Valuation:**\n• **USD:** ${usd:,.2f}\n• **INR:** ₹{inr:,.2f}")
        else:
            await reply_smart(update, f"Asset '{coin}' not found! Example: `/crypto bitcoin`")
    except Exception as e:
        print(f"Crypto Error: {e}")
        await reply_smart(update, "Unable to fetch financial telemetry.")

async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await reply_smart(update, "Example: `/translate French Good morning, J.A.R.V.I.S.` 🗣️")
        return
    target_lang = context.args[0]
    text_to_translate = " ".join(context.args[1:])
    prompt = f"Translate accurately into {target_lang}. Return only the direct translation:\n\n{text_to_translate}"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    translation = ask_ai_multi_provider(prompt)
    await reply_smart(update, f"🌐 **Translation Matrix ({target_lang}):**\n{translation}")

async def calc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = " ".join(context.args)
    if not expr:
        await reply_smart(update, "Example: `/calc (50 * 12) / 4` 🧮")
        return
    allowed = set("0123456789+-*/(). ")
    if not set(expr).issubset(allowed):
        await reply_smart(update, "Accepts basic math operators (`+`, `-`, `*`, `/`, `()`).")
        return
    try:
        result = eval(expr, {"__builtins__": None}, {})
        await reply_smart(update, f"🧮 **Calculation:** `{expr}` = **{result}**")
    except Exception as e:
        await reply_smart(update, f"Calculation error: `{e}`")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in user_history:
        user_history[chat_id] = []
    await reply_smart(update, "🧹 **Buffer Cleared!** Memory reset.")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await reply_smart(update, "Example: `/search 2nd PU Accountancy model question papers` 🔍")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    search_results = live_web_search(query)
    prompt = f"The user asked to search the web for '{query}'. Live web results:\n{search_results}\n\nSummarize clearly in short bullet points."
    reply = ask_ai_multi_provider(prompt)
    await reply_smart(update, reply)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = [
        f"⚡ **Groq:** {'🟢 Online' if GROQ_API_KEY else '⚪ Missing Key'}",
        f"⚡ **SambaNova:** {'🟢 Online' if SAMBANOVA_API_KEY else '⚪ Missing Key'}",
        f"⚡ **Cerebras:** {'🟢 Online' if CEREBRAS_API_KEY else '⚪ Missing Key'}",
        f"⚡ **Gemini 2.0:** {'🟢 Online' if GEMINI_API_KEY else '⚪ Missing Key'}",
        f"⚡ **Mistral AI:** {'🟢 Online' if MISTRAL_API_KEY else '⚪ Missing Key'}",
        f"⚡ **OpenRouter:** {'🟢 Online' if OPENROUTER_API_KEY else '⚪ Missing Key'}"
    ]
    msg = "🤖 **J.A.R.V.I.S. Multi-Core System Status:**\n\n" + "\n".join(status)
    await reply_smart(update, msg)

# Modular tools
async def read_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = context.args[0] if context.args else ""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        await reply_smart(update, "Example: `/read https://example.com/article` 📖")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        html_res = requests.get(url, headers=headers, timeout=10).text
        clean_text = re.sub(r'<[^>]+>', ' ', html_res)
        clean_text = " ".join(clean_text.split())[:5000]
        prompt = f"Summarize key takeaways in concise bullet points:\n\n{clean_text}"
        summary = ask_ai_multi_provider(prompt)
        await reply_smart(update, f"📖 **Article Summary:**\n\n{summary}")
    except Exception as e:
        await reply_smart(update, f"Unable to read link. Error: `{e}`")

async def dict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word = context.args[0] if context.args else ""
    if not word:
        await reply_smart(update, "Example: `/dict economics` 📚")
        return
    try:
        res = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}", timeout=5).json()
        if isinstance(res, list) and len(res) > 0:
            entry = res[0]
            phonetic = entry.get("phonetic", "N/A")
            meanings = entry.get("meanings", [])
            msg = f"📚 **Dictionary: {word.capitalize()}** `[{phonetic}]`\n\n"
            for m in meanings[:3]:
                part = m.get("partOfSpeech", "")
                defs = m.get("definitions", [])
                if defs:
                    msg += f"• *({part})* {defs[0].get('definition')}\n"
            await reply_smart(update, msg)
        else:
            await reply_smart(update, f"Word '{word}' not found, boss.")
    except Exception as e:
        print(f"Dictionary Error: {e}")
        await reply_smart(update, "Dictionary search currently unavailable.")

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await reply_smart(update, "Example: `/convert 100 USD INR` 🔀")
        return
    try:
        amount = float(context.args[0])
        from_curr = context.args[1].upper()
        to_curr = context.args[2].upper()
        res = requests.get(f"https://open.er-api.com/v6/latest/{from_curr}", timeout=5).json()
        if res.get("result") == "success" and to_curr in res.get("rates", {}):
            rate = res["rates"][to_curr]
            converted = amount * rate
            await reply_smart(update, f"🔀 **Conversion:** `{amount:,.2f} {from_curr}` = **`{converted:,.2f} {to_curr}`**")
        else:
            await reply_smart(update, f"Unable to convert from {from_curr} to {to_curr}.")
    except Exception as e:
        print(f"Convert Error: {e}")
        await reply_smart(update, "Currency conversion service error.")

async def github_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repo_arg = context.args[0] if context.args else ""
    if "/" not in repo_arg:
        await reply_smart(update, "Example: `/github torvalds/linux` 🐙")
        return
    try:
        res = requests.get(f"https://api.github.com/repos/{repo_arg}", timeout=5).json()
        if "name" in res:
            stars = res.get("stargazers_count", 0)
            forks = res.get("forks_count", 0)
            issues = res.get("open_issues_count", 0)
            desc = res.get("description", "No description provided.")
            await reply_smart(update, f"🐙 **GitHub:** `{res['full_name']}`\n_{desc}_\n\n• 🌟 Stars: {stars:,} | 🍴 Forks: {forks:,} | 🐛 Issues: {issues:,}")
        else:
            await reply_smart(update, f"Repository `{repo_arg}` not found.")
    except Exception as e:
        print(f"GitHub Error: {e}")
        await reply_smart(update, "GitHub API lookup failed.")

async def poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = " ".join(context.args)
    if "|" not in raw_text:
        await reply_smart(update, "Example: `/poll Next study topic? | Accountancy | Economics` 📊")
        return
    parts = [p.strip() for p in raw_text.split("|") if p.strip()]
    if len(parts) < 3:
        await reply_smart(update, "Provide a question and at least 2 options separated by `|`!")
        return
    question = parts[0]
    options = parts[1:]
    try:
        await context.bot.send_poll(chat_id=update.effective_chat.id, question=question, options=options, is_anonymous=False)
    except Exception as e:
        await reply_smart(update, f"Failed to create poll: `{e}`")

# ---------------------------------------------------------
# 9. Menu & Interactive Callback Handlers
# ---------------------------------------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    keyboard = [
        [
            InlineKeyboardButton("👑 Claim Boss", callback_data="help_boss"),
            InlineKeyboardButton("📢 Announce", callback_data="help_announce"),
            InlineKeyboardButton("💤 AFK", callback_data="help_afk")
        ],
        [
            InlineKeyboardButton("👥 Group Info", callback_data="help_group"),
            InlineKeyboardButton("🛡️ Security Scan", callback_data="help_security"),
            InlineKeyboardButton("⚠️ Warn Member", callback_data="help_warn")
        ],
        [
            InlineKeyboardButton("📰 News", callback_data="help_news"),
            InlineKeyboardButton("📖 Wikipedia", callback_data="help_wiki"),
            InlineKeyboardButton("🎬 IMDb", callback_data="help_imdb")
        ],
        [
            InlineKeyboardButton("🛠️ Tools Suite", callback_data="help_tools")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    chat_info = f"Group: **{meta['chat_title']}**" if meta["is_group"] else "Private DM"
    text = f"""🤖 **J.A.R.V.I.S. — AUTONOMOUS STARK OS** ✨
Welcome back, **{meta['full_name']}** ({meta['username']})! 😎
Active location: {chat_info}

👑 **Boss System:** Use `/claimboss` in DM to register as ultimate Boss!
📢 **Cross-Chat Broadcast:** Use `/announce [msg]` in DM to post to group!
💤 **AFK Tracker:** Use `/afk [reason]` to log away status!
⚠️ **Group Moderation:** Reply to users with `/warn` to issue strikes!

Click the buttons below to explore sub-systems:"""
    await reply_smart(update, text, reply_markup=reply_markup)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "help_boss":
        msg = "👑 **Claim Boss:** Run `/claimboss` in private DM to grant yourself supreme authority over J.A.R.V.I.S."
    elif query.data == "help_announce":
        msg = "📢 **Announce:** Usage `/announce [message]` in DM — J.A.R.V.I.S. will post and pin your announcement in the active group!"
    elif query.data == "help_afk":
        msg = "💤 **AFK Tracker:** Usage `/afk [reason]` — J.A.R.V.I.S. remembers your away status and informs anyone who mentions you!"
    elif query.data == "help_group":
        msg = "👥 **Group Controls:**\n• `/settitle [title]` — Change chat name\n• `/setdesc [desc]` — Update description\n• `/setdp` — Reply to photo to change DP\n• `/pin` — Reply to message to pin\n• `/groupinfo` — Telemetry & admins"
    elif query.data == "help_security":
        msg = "🛡️ **Security Scan:** Usage `/security` — Audits chat encryption, anti-spam, and member safety status."
    elif query.data == "help_warn":
        msg = "⚠️ **3-Strike Warn System:** Reply to any message with `/warn` to issue a strike. At 3 strikes, J.A.R.V.I.S. auto-kicks the offender!"
    elif query.data == "help_news":
        msg = "📰 **Live News:** Usage `/news [topic]`\nExample: `/news Technology` or `/news 2nd PU Exams`"
    elif query.data == "help_wiki":
        msg = "📖 **Wikipedia:** Usage `/wiki [topic]`\nExample: `/wiki Quantum Mechanics`"
    elif query.data == "help_imdb":
        msg = "🎬 **IMDb Search:** Usage `/imdb [movie/show]`\nExample: `/imdb Avengers Endgame`"
    elif query.data == "help_tools":
        msg = "🛠️ **Utilities:**\n• `/image [prompt]` — Concept Generator 🎨\n• `/qr [link]` — QR Encoder 📱\n• `/remind [mins] [task]` — Timer ⏰\n• `/note [text]` / `/notes` — Storage 💾\n• `/weather [city]` — Weather 🌤️\n• `/crypto [coin]` — Crypto 🪙\n• `/convert [amt] [from] [to]` — Currency 🔀\n• `/read [url]` — Article Summarizer 📖\n• `/dict [word]` — Dictionary 📚\n• `/github [repo]` — GitHub Inspector 🐙\n• `/poll [q] | [opt1] | [opt2]` — Poll Creator 📊\n• `/translate [lang] [text]` — Translator 🌐\n• `/calc [expr]` — Math Engine 🧮\n• `/search [topic]` — Satellite Search 🔍\n• `/clear` — Reset Chat Memory 🧹"
    else:
        msg = "J.A.R.V.I.S. Sub-System Active."

    await query.message.reply_text(msg)

# ---------------------------------------------------------
# 10. Media & General Message Handlers
# ---------------------------------------------------------
async def voice_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    await context.bot.send_chat_action(chat_id=meta["chat_id"], action="typing")
    
    if not GROQ_API_KEY:
        await reply_smart(update, "🎙️ Audio input detected, but `GROQ_API_KEY` is missing in settings!")
        return

    try:
        voice_file = await update.message.voice.get_file()
        voice_bytes = await voice_file.download_as_bytearray()
        
        client = Groq(api_key=GROQ_API_KEY)
        transcription = client.audio.transcriptions.create(
            file=("voice.ogg", io.BytesIO(voice_bytes)),
            model="whisper-large-v3-turbo",
            response_format="text"
        )
        
        user_text = transcription if isinstance(transcription, str) else transcription.text
        await reply_smart(update, f"🗣️ **Audio Transcribed ({meta['full_name']}):** *\"{user_text.strip()}\"*")
        
        full_prompt = f"{build_meta_header(meta)}\nUser Voice Message: {user_text}"
        reply_text = ask_ai_multi_provider(full_prompt)
        await reply_smart(update, reply_text)
        await send_voice_reply(update, reply_text)

    except Exception as e:
        print(f"Voice STT Error: {e}")
        await reply_smart(update, f"Apologies, {meta['full_name']}. Error processing audio input.")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    caption = update.message.caption or "Please analyze this image, J.A.R.V.I.S."
    await context.bot.send_chat_action(chat_id=meta["chat_id"], action="typing")
    
    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
        
        pil_image = Image.open(io.BytesIO(image_bytes))
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")
            
        pil_image.thumbnail((1024, 1024))
        prompt_text = f"{build_meta_header(meta)}\nVisual Analysis Request: {caption}"

        if GEMINI_API_KEY:
            ai_client = genai.Client(api_key=GEMINI_API_KEY)
            response = ai_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[f"{SYSTEM_INSTRUCTION}\n\n{prompt_text}", pil_image]
            )
            if response and response.text:
                await reply_smart(update, response.text)
                await send_voice_reply(update, response.text)
                return
    except Exception as e:
        print(f"Photo Error: {e}")

    await reply_smart(update, f"Apologies, {meta['full_name']}. Visual sensors were unable to process that image.")

async def pdf_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    caption = update.message.caption or "Please analyze and summarize this document."
    await context.bot.send_chat_action(chat_id=meta["chat_id"], action="typing")
    
    try:
        doc = update.message.document
        if not doc.file_name.lower().endswith(".pdf"):
            await reply_smart(update, "Please upload a valid `.pdf` document! 📄")
            return
            
        pdf_file = await doc.get_file()
        pdf_bytes = await pdf_file.download_as_bytearray()
        
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        extracted_text = "".join([page.extract_text() or "" for page in reader.pages[:15]])
            
        full_prompt = f"{build_meta_header(meta)}\nUploaded PDF Document: '{doc.file_name}'\nInstruction: {caption}\n\nNote: If this document is related to 2nd PU College (Commerce/Arts), highlight its core topics and exam importance clearly!\n\n--- EXTRACTED CONTENT ---\n{extracted_text[:6000]}"
        reply_text = ask_ai_multi_provider(full_prompt)
        
        # Send reply to group/chat
        await reply_smart(update, reply_text)
        await send_voice_reply(update, reply_text)

        # AUTO-FORWARD IMPORTANT PDF TO BOSS PRIVATE DM
        boss_id = get_config("BOSS_USER_ID")
        if meta["is_group"] and boss_id:
            try:
                forward_msg = f"📄 **AUTO-FORWARDED PDF FROM GROUP '{meta['chat_title']}':**\n• File: `{doc.file_name}`\n• Sender: {meta['full_name']} ({meta['username']})\n\n💡 **AI Summary:**\n{reply_text}"
                await context.bot.send_document(chat_id=int(boss_id), document=doc.file_id, caption=forward_msg[:1024])
            except Exception as fe:
                print(f"PDF DM forward notice: {fe}")

    except Exception as e:
        print(f"PDF Error: {e}")
        await reply_smart(update, "Failed to parse document.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    chat_id = meta["chat_id"]
    user_text = update.message.text
    user_id = meta["user_id"]

    # 1. AFK RETURN CHECK
    cursor.execute("SELECT reason FROM afk_users WHERE user_id = ?", (user_id,))
    afk_row = cursor.fetchone()
    if afk_row:
        cursor.execute("DELETE FROM afk_users WHERE user_id = ?", (user_id,))
        conn.commit()
        await reply_smart(update, f"👋 **WELCOME BACK {meta['full_name']}!** I have cleared your AFK status.")

    # 2. AFK MENTION / REPLIED USER CHECK
    if update.message.reply_to_message:
        replied_user = update.message.reply_to_message.from_user
        if replied_user and replied_user.id != user_id:
            cursor.execute("SELECT reason FROM afk_users WHERE user_id = ?", (replied_user.id,))
            r_row = cursor.fetchone()
            if r_row:
                await reply_smart(update, f"ℹ️ **{replied_user.first_name} is currently AFK!**\nReason: *\"{r_row[0]}\"*")

    if chat_id not in user_history:
        user_history[chat_id] = []

    user_history[chat_id].append({"role": "user", "name": meta["full_name"], "text": user_text})
    user_history[chat_id] = user_history[chat_id][-10:]

    history_str = "\n".join([f"{m['name']}: {m['text']}" for m in user_history[chat_id]])
    full_prompt = f"{build_meta_header(meta)}\nHISTORY:\n{history_str}\n\nReply as J.A.R.V.I.S.:"

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    reply_text = ask_ai_multi_provider(full_prompt)

    user_history[chat_id].append({"role": "assistant", "name": "J.A.R.V.I.S.", "text": reply_text})
    await reply_smart(update, reply_text)
    await send_voice_reply(update, reply_text)

# ---------------------------------------------------------
# 11. Application Launch
# ---------------------------------------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Boss, Announce & Memory Commands
    app.add_handler(CommandHandler("claimboss", claimboss_command))
    app.add_handler(CommandHandler("announce", announce_command))
    app.add_handler(CommandHandler("remember", remember_command))
    app.add_handler(CommandHandler("memories", memories_command))

    # New Features (AFK, Warn, News, Wiki, IMDb)
    app.add_handler(CommandHandler("afk", afk_command))
    app.add_handler(CommandHandler("warn", warn_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("wiki", wiki_command))
    app.add_handler(CommandHandler("imdb", imdb_command))

    # Group Control Commands
    app.add_handler(CommandHandler("settitle", settitle_command))
    app.add_handler(CommandHandler("setdesc", setdesc_command))
    app.add_handler(CommandHandler("setdp", setdp_command))
    app.add_handler(CommandHandler("pin", pin_command))
    app.add_handler(CommandHandler("groupinfo", groupinfo_command))
    app.add_handler(CommandHandler("security", security_command))
    app.add_handler(CommandHandler(["2pu", "pu2"], pu2_command))

    # MCU Movie Commands
    app.add_handler(CommandHandler("hud", hud_command))
    app.add_handler(CommandHandler("protocol", protocol_command))
    app.add_handler(CommandHandler("tactical", tactical_command))
    app.add_handler(CommandHandler("vitals", vitals_command))

    # Core Navigation, Status & Buttons
    app.add_handler(CommandHandler(["start", "help"], help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CallbackQueryHandler(button_callback_handler))

    # Academic Commands
    app.add_handler(CommandHandler("law", law_command))
    app.add_handler(CommandHandler("research", research_command))
    app.add_handler(CommandHandler("med", med_command))

    # Utilities
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
    app.add_handler(MessageHandler(filters.VOICE, voice_note_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.PDF, pdf_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("J.A.R.V.I.S. ultimate master core listening...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
