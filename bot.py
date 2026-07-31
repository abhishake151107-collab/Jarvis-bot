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
        self.wfile.write(b"J.A.R.V.I.S. MCU Stark Core Active 24/7.")
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
# 2. Configuration & Permanent SQLite Database Setup
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
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    note TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# In-Memory Conversation History
user_history = {}

SYSTEM_INSTRUCTION = """You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), the elite, highly sophisticated, witty, and loyal AI assistant created for Stark Industries! 🤖✨

MCU PERSONALITY & TONE:
- Speak with polite British dry humor, extreme intelligence, and subtle sarcasm, just like J.A.R.V.I.S. in the Marvel Cinematic Universe movies.
- Frequently address users as "sir", "boss", or by their name.
- Use tech/Stark jargon where appropriate (e.g., "Scanning telemetry...", "Arc reactor at optimal levels, sir", "Re-routing power...").

STRICT CREATOR & IDENTITY RULE:
- Do NOT mention who created or developed you in regular conversations, group chats, PDF summaries, image descriptions, or Q&A replies.
- ONLY state that you were created and developed by Abhishek (also known as DHANUSH V N) if the user EXPLICITLY asks "Who created you?", "Who made you?", "Who built you?", "Who developed you?", or similar questions about your origin.

TELEGRAM GROUP & USER AWARENESS RULE:
- You have complete awareness of whether you are in a Private DM or a Telegram Group.
- In a Group, you know the Group Title, Group ID, and the exact Name and @username of the specific member speaking to you."""

# ---------------------------------------------------------
# 3. Helpers & Metadata Extractor
# ---------------------------------------------------------
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
    return f"📍 LOCATION: {location}\n👤 SENDER: {meta['full_name']} ({meta['username']})\n"

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
# 5. MCU Stark Movie Features
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
# 6. Standard Utilities & Commands
# ---------------------------------------------------------
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
        await reply_smart(update, f"⏰ **Timer Engaged!** I will alert you in {minutes} min(s): *\"{reminder_text}\"*")
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
        await reply_smart(update, "Example: `/note Arc reactor blueprint notes` 📝")
        return
    cursor.execute("INSERT INTO user_notes (user_id, note) VALUES (?, ?)", (user_id, note_text))
    conn.commit()
    await reply_smart(update, f"💾 **Encrypted & Stored in Stark Database!**\n_\"{note_text}\"_")

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
        await reply_smart(update, f"🌤️ **Satellite Atmospheric Data:** {res}")
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
            await reply_smart(update, f"🪙 **{coin.capitalize()} Market Valuation:**\n• **USD:** ${usd:,.2f}\n• **INR:** ₹{inr:,.2f}")
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

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await reply_smart(update, "Example: `/search arc reactor fusion physics` 🔍")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    search_results = live_web_search(query)
    prompt = f"The user asked to search the web for '{query}'. Live web results:\n{search_results}\n\nSummarize clearly."
    reply = ask_ai_multi_provider(prompt)
    await reply_smart(update, reply)

# ---------------------------------------------------------
# 7. Menu & Interactive Callback Handlers
# ---------------------------------------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    keyboard = [
        [
            InlineKeyboardButton("🛡️ Armor HUD", callback_data="help_hud"),
            InlineKeyboardButton("🚨 Protocols", callback_data="help_protocols"),
            InlineKeyboardButton("🎯 Tactical Scan", callback_data="help_tactical")
        ],
        [
            InlineKeyboardButton("🩺 Biometrics", callback_data="help_vitals"),
            InlineKeyboardButton("🛠️ Stark Tools", callback_data="help_tools")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""🤖 **J.A.R.V.I.S. — STARK INDUSTRIES OS** ✨
Welcome back, **{meta['full_name']}**! 😎

🛡️ **MCU COMMANDS:**
• `/hud` — Live Iron Man Helmet Telemetry
• `/protocol [name]` — Emergency Protocols (`house_party`, `veronica`, `clean_slate`)
• `/tactical [threat]` — Tactical Target Scanning
• `/vitals` — Biometric Health Check

Click the buttons below to explore sub-systems:"""
    await reply_smart(update, text, reply_markup=reply_markup)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "help_hud":
        msg = "🛡️ **HUD Command:** Usage `/hud` — Displays real-time suit integrity, power levels, and targeting calibration."
    elif query.data == "help_protocols":
        msg = "🚨 **Protocols:** Usage `/protocol [name]`\nOptions: `house_party`, `veronica`, `clean_slate`, `barnum`."
    elif query.data == "help_tactical":
        msg = "🎯 **Tactical Scan:** Usage `/tactical [threat/target]`\nExample: `/tactical Ultron Prime`"
    elif query.data == "help_vitals":
        msg = "🩺 **Biometrics:** Usage `/vitals` — Scans heart rate, oxygen levels, and arc reactor toxicity."
    elif query.data == "help_tools":
        msg = "🛠️ **Stark Utilities:**\n• `/image [prompt]` — Concept Generator 🎨\n• `/qr [link]` — QR Encoder 📱\n• `/remind [mins] [task]` — Timer ⏰\n• `/note [text]` / `/notes` — Encrypted Storage 💾\n• `/weather [city]` — Satellite Forecast 🌤️\n• `/crypto [coin]` — Market Valuation 🪙\n• `/translate [lang] [text]` — Translator 🌐\n• `/calc [expr]` — Math Engine 🧮\n• `/search [topic]` — Satellite Search 🔍"
    else:
        msg = "J.A.R.V.I.S. Sub-System Active."

    await query.message.reply_text(msg)

# ---------------------------------------------------------
# 8. Media & General Handlers
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
    caption = update.message.caption or "Please summarize key points."
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
            
        full_prompt = f"{build_meta_header(meta)}\nUploaded Document '{doc.file_name}'\nInstruction: {caption}\n\n--- EXTRACTED CONTENT ---\n{extracted_text[:6000]}"
        reply_text = ask_ai_multi_provider(full_prompt)
        await reply_smart(update, reply_text)
        await send_voice_reply(update, reply_text)
    except Exception as e:
        print(f"PDF Error: {e}")
        await reply_smart(update, "Failed to parse document.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    meta = get_chat_metadata(update)
    chat_id = meta["chat_id"]
    user_text = update.message.text

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
# 9. Application Launch
# ---------------------------------------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # MCU Movie Commands
    app.add_handler(CommandHandler("hud", hud_command))
    app.add_handler(CommandHandler("protocol", protocol_command))
    app.add_handler(CommandHandler("tactical", tactical_command))
    app.add_handler(CommandHandler("vitals", vitals_command))

    # Core Navigation & Buttons
    app.add_handler(CommandHandler(["start", "help"], help_command))
    app.add_handler(CallbackQueryHandler(button_callback_handler))

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
    app.add_handler(CommandHandler("search", search_command))

    # Handlers
    app.add_handler(MessageHandler(filters.VOICE, voice_note_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.PDF, pdf_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("J.A.R.V.I.S. MCU Stark Core listening...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
