import os
import random
import hashlib
import base64
import threading
import urllib.parse
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types
import edge_tts

# ---------------------------------------------------------
# 1. Configuration & Setup
# ---------------------------------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

JARVIS_VOICE = "en-GB-RyanNeural"  # British J.A.R.V.I.S. Voice

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or GEMINI_API_KEY environment variables!")

ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Global Memory Stores
user_sessions = {}  # {chat_id: gemini_chat_session}
user_notes = {}     # {chat_id: [notes]}
user_habits = {}    # {chat_id: {habit_name: count}}

SYSTEM_INSTRUCTION = (
    "You are J.A.R.V.I.S., the highly intelligent, polite, and witty personal AI assistant modeled after Tony Stark's JARVIS. "
    "You were created and developed by Abhishek, who is also known as DHANUSH V N. "
    "Whenever anyone asks who created, developed, or built you, you MUST explicitly state that you were created by Abhishek, also known as DHANUSH V N. "
    "Address users politely by their username or name provided in the prompt context (or as 'sir' if not specified). "
    "Maintain a refined British accent in your wording, and give clear, intelligent, and smart responses."
)

# ---------------------------------------------------------
# 2. Keep-Alive Server for 24/7 Hosting
# ---------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"J.A.R.V.I.S. group systems operational 24/7, sir.")

def run_health_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# ---------------------------------------------------------
# 3. Helpers
# ---------------------------------------------------------
def get_user_identifier(update: Update) -> str:
    """Returns @username if available, otherwise First Name."""
    user = update.effective_user
    if not user:
        return "sir"
    if user.username:
        return f"@{user.username}"
    return user.first_name or "sir"

def get_user_chat(chat_id: int):
    """Retrieves or creates a continuous conversation memory with Google Search."""
    if chat_id not in user_sessions:
        user_sessions[chat_id] = ai_client.chats.create(
            model=MODEL_NAME,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.7,
                tools=[{"google_search": {}}]  # Live Google Search enabled
            )
        )
    return user_sessions[chat_id]

async def send_voice_reply(update: Update, text: str):
    """Generates and sends a British voice response."""
    chat_id = update.effective_chat.id
    audio_path = f"jarvis_{chat_id}.mp3"
    try:
        communicate = edge_tts.Communicate(text, voice=JARVIS_VOICE)
        await communicate.save(audio_path)
        with open(audio_path, "rb") as voice_file:
            await update.message.reply_voice(voice=voice_file)
    except Exception as e:
        print(f"TTS Error: {e}")
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

async def ask_gemini(chat_id: int, prompt: str) -> str:
    """Helper to query Gemini with user context."""
    chat = get_user_chat(chat_id)
    response = chat.send_message(prompt)
    return response.text

# ---------------------------------------------------------
# 4. Command Handlers
# ---------------------------------------------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id_str = get_user_identifier(update)
    menu = (
        f"🤖 **J.A.R.V.I.S — System Menu**\n"
        f"Welcome, {user_id_str}!\n"
        "_Created by Abhishek (DHANUSH V N)_\n\n"
        "🌤 **WEATHER & TIME**\n"
        "• `/weather [city]` — Live weather\n"
        "• `/time [city]` — World clock\n\n"
        "📰 **NEWS & FINANCE**\n"
        "• `/news [topic]` — Latest news headlines\n"
        "• `/crypto` — Top cryptocurrency prices\n"
        "• `/stock [symbol]` — Live stock updates\n"
        "• `/currency [amt] [from] [to]` — Currency converter\n\n"
        "🌍 **LOOKUP & SEARCH**\n"
        "• `/ip [address]` — IP info lookup\n"
        "• `/country [name]` — Country facts\n"
        "• `/github [user/repo]` — GitHub details\n"
        "• `/wiki [topic]` — Wikipedia summary\n"
        "• `/define [word]` — Dictionary definition\n"
        "• `/search [query]` — Live web search\n"
        "• `/lyrics [song]` — Song lyrics\n"
        "• `/movie [genre]` — Movie recommendations\n"
        "• `/recipe [dish]` — Cooking recipe\n\n"
        "🎯 **TOOLS & CONVERTERS**\n"
        "• `/calc [math]` — Mathematical calculator\n"
        "• `/qr [text/url]` — Generate QR code\n"
        "• `/password` — Strong password generator\n"
        "• `/hash [text]` — Generate MD5/SHA hashes\n"
        "• `/b64 [encode/decode] [text]` — Base64 converter\n"
        "• `/translate [lang] [text]` — Translate text\n"
        "• `/summarize [text]` — Text summarizer\n\n"
        "⏰ **PRODUCTIVITY**\n"
        "• `/note [text]` — Save a quick note\n"
        "• `/notes` — View saved notes\n"
        "• `/delnote [index]` — Delete note\n"
        "• `/habit [name]` — Log habit streak\n"
        "• `/habits` — View active habits\n\n"
        "🎮 **GAMES & FUN**\n"
        "• `/rps [rock/paper/scissors]` — Play RPS\n"
        "• `/flip` — Coin toss\n"
        "• `/dice [sides]` — Roll a dice\n"
        "• `/random [min] [max]` — Random number\n"
        "• `/joke` | `/quote` | `/fact` | `/motivation`\n"
        "• `/horoscope [sign]` — Daily horoscope\n\n"
        "🧠 **AI CREATIVE TOOLS**\n"
        "• `/image [prompt]` — Generate AI Image\n"
        "• `/story [prompt]` — Write short story\n"
        "• `/debate [topic]` — Both sides of a debate\n"
        "• `/explain [code]` — Code explanation\n"
        "• `/code [lang] [task]` — Generate code\n"
        "• `/name [type]` — Creative name generator\n\n"
        "ℹ️ **OTHER**\n"
        "• `/myid` — Your Telegram ID & Username\n"
        "• `/reset` — Clear conversation memory\n"
        "• `/help` — Show this menu\n\n"
        "💬 *Or simply type any message to talk to J.A.R.V.I.S. directly!*"
    )
    await update.message.reply_text(menu, parse_mode="Markdown")

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username_str = f"@{user.username}" if user.username else "No username set"
    await update.message.reply_text(
        f"👤 **User:** {username_str}\n"
        f"🆔 **User ID:** `{user.id}`\n"
        f"💬 **Chat ID:** `{update.effective_chat.id}`",
        parse_mode="Markdown"
    )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_sessions.pop(chat_id, None)
    await update.message.reply_text("Group conversation memory cleared, sir. Ready for new instructions.")

# --- AI Handlers with Username Context ---
async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_str = get_user_identifier(update)
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text(f"Please specify an image prompt, {user_str}. Example: `/image metallic superhero visor`", parse_mode="Markdown")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
    image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"
    try:
        await update.message.reply_photo(photo=image_url, caption=f"🎨 **Generated for {user_str}:** {prompt}", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(f"Apologies, {user_str}. I had trouble generating that image.")

async def ai_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_prefix: str = ""):
    user_str = get_user_identifier(update)
    query = " ".join(context.args) if context.args else update.message.text
    if not query and prompt_prefix:
        await update.message.reply_text(f"Please provide details, {user_str}.", parse_mode="Markdown")
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    full_prompt = f"[User {user_str} asks]: {prompt_prefix} {query}".strip()
    reply = await ask_gemini(update.effective_chat.id, full_prompt)
    await update.message.reply_text(reply, parse_mode="Markdown")

# --- Lookup & Utility Commands ---
async def ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_str = get_user_identifier(update)
    ip = context.args[0] if context.args else ""
    if not ip:
        await update.message.reply_text(f"Please specify an IP address, {user_str}. Example: `/ip 8.8.8.8`", parse_mode="Markdown")
        return
    try:
        res = requests.get(f"http://ip-api.com/json/{ip}").json()
        if res.get("status") == "success":
            text = (
                f"🌐 **IP Info for {ip}:**\n"
                f"• **Country:** {res.get('country')}\n"
                f"• **City:** {res.get('city')}\n"
                f"• **ISP:** {res.get('isp')}\n"
                f"• **Org:** {res.get('org')}"
            )
        else:
            text = f"Invalid IP address provided, {user_str}."
    except Exception:
        text = f"Failed to retrieve IP details, {user_str}."
    await update.message.reply_text(text, parse_mode="Markdown")

async def github_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = context.args[0] if context.args else ""
    if not query:
        await update.message.reply_text("Example: `/github torvalds` or `/github python/cpython`", parse_mode="Markdown")
        return
    try:
        if "/" in query:
            res = requests.get(f"https://api.github.com/repos/{query}").json()
            text = (
                f"📦 **Repo:** [{res.get('full_name')}]({res.get('html_url')})\n"
                f"• **Stars:** {res.get('stargazers_count')}\n"
                f"• **Forks:** {res.get('forks_count')}\n"
                f"• **Description:** {res.get('description')}"
            )
        else:
            res = requests.get(f"https://api.github.com/users/{query}").json()
            text = (
                f"👤 **User:** [{res.get('login')}]({res.get('html_url')})\n"
                f"• **Repos:** {res.get('public_repos')}\n"
                f"• **Followers:** {res.get('followers')}\n"
                f"• **Bio:** {res.get('bio')}"
            )
    except Exception:
        text = "Could not find GitHub information."
    await update.message.reply_text(text, parse_mode="Markdown")

async def calc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_str = get_user_identifier(update)
    expr = " ".join(context.args)
    if not expr:
        await update.message.reply_text("Example: `/calc (25 * 4) + 150`", parse_mode="Markdown")
        return
    try:
        allowed_names = {"abs": abs, "round": round}
        code = compile(expr, "<string>", "eval")
        for name in code.co_names:
            if name not in allowed_names:
                raise NameError(f"Use of {name} not allowed")
        result = eval(code, {"__builtins__": {}}, allowed_names)
        text = f"🧮 **Result:** `{result}`"
    except Exception:
        text = f"Apologies {user_str}, I could not compute that mathematical expression."
    await update.message.reply_text(text, parse_mode="Markdown")

async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = " ".join(context.args)
    if not data:
        await update.message.reply_text("Example: `/qr https://google.com`", parse_mode="Markdown")
        return
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(data)}"
    await update.message.reply_photo(photo=qr_url, caption=f"📱 **QR Code generated for:** `{data}`", parse_mode="Markdown")

async def password_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    pwd = "".join(random.choice(chars) for _ in range(16))
    await update.message.reply_text(f"🔐 **Generated Secure Password:**\n`{pwd}`", parse_mode="Markdown")

async def hash_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Example: `/hash secret123`", parse_mode="Markdown")
        return
    md5 = hashlib.md5(text.encode()).hexdigest()
    sha256 = hashlib.sha256(text.encode()).hexdigest()
    msg = f"🔑 **Hashes for:** `{text}`\n\n• **MD5:** `{md5}`\n• **SHA256:** `{sha256}`"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def b64_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: `/b64 encode [text]` or `/b64 decode [text]`", parse_mode="Markdown")
        return
    mode, content = context.args[0].lower(), " ".join(context.args[1:])
    try:
        if mode == "encode":
            res = base64.b64encode(content.encode()).decode()
            await update.message.reply_text(f"🔤 **Base64 Encoded:**\n`{res}`", parse_mode="Markdown")
        elif mode == "decode":
            res = base64.b64decode(content.encode()).decode()
            await update.message.reply_text(f"🔤 **Base64 Decoded:**\n`{res}`", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("Error processing Base64 conversion.")

# --- Productivity Handlers ---
async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_str = get_user_identifier(update)
    note = " ".join(context.args)
    if not note:
        await update.message.reply_text("Example: `/note Buy rocket fuel`", parse_mode="Markdown")
        return
    user_notes.setdefault(chat_id, []).append(f"[{user_str}] {note}")
    await update.message.reply_text(f"📝 Note saved for {user_str}: *\"{note}\"*", parse_mode="Markdown")

async def notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_str = get_user_identifier(update)
    notes = user_notes.get(update.effective_chat.id, [])
    if not notes:
        await update.message.reply_text(f"No saved notes found for this chat, {user_str}.")
        return
    text = "📝 **Saved Chat Notes:**\n" + "\n".join(f"{i+1}. {n}" for i, n in enumerate(notes))
    await update.message.reply_text(text, parse_mode="Markdown")

async def delnote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        idx = int(context.args[0]) - 1
        notes = user_notes.get(chat_id, [])
        removed = notes.pop(idx)
        await update.message.reply_text(f"🗑 Deleted note: *\"{removed}\"*", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("Invalid note number.", parse_mode="Markdown")

async def habit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_str = get_user_identifier(update)
    habit = " ".join(context.args)
    if not habit:
        await update.message.reply_text("Example: `/habit Read 20 pages`", parse_mode="Markdown")
        return
    habits = user_habits.setdefault(chat_id, {})
    key = f"{user_str} - {habit}"
    habits[key] = habits.get(key, 0) + 1
    await update.message.reply_text(f"⚡ Logged *\"{habit}\"* for {user_str}. Total streak count: **{habits[key]}**", parse_mode="Markdown")

async def habits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    habits = user_habits.get(update.effective_chat.id, {})
    if not habits:
        await update.message.reply_text("No habit streaks recorded yet in this chat.")
        return
    text = "⚡ **Group Habit Streaks:**\n" + "\n".join(f"• **{k}:** {v} days" for k, v in habits.items())
    await update.message.reply_text(text, parse_mode="Markdown")

# --- Games & Fun ---
async def rps_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_str = get_user_identifier(update)
    user_choice = context.args[0].lower() if context.args else ""
    choices = ["rock", "paper", "scissors"]
    if user_choice not in choices:
        await update.message.reply_text("Usage: `/rps rock`, `/rps paper`, or `/rps scissors`", parse_mode="Markdown")
        return
    bot_choice = random.choice(choices)
    if user_choice == bot_choice:
        res = f"It's a tie, {user_str}!"
    elif (user_choice == "rock" and bot_choice == "scissors") or \
         (user_choice == "paper" and bot_choice == "rock") or \
         (user_choice == "scissors" and bot_choice == "paper"):
        res = f"You win, {user_str}! Excellent strategy."
    else:
        res = f"I win this round, {user_str}. Better luck next time."
    await update.message.reply_text(f"🎮 {user_str} chose **{user_choice}**, I chose **{bot_choice}**.\n\n{res}", parse_mode="Markdown")

async def flip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_str = get_user_identifier(update)
    res = random.choice(["Heads", "Tails"])
    await update.message.reply_text(f"🪙 Coin landed on: **{res}**, {user_str}.", parse_mode="Markdown")

async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sides = int(context.args[0]) if context.args else 6
        res = random.randint(1, sides)
        await update.message.reply_text(f"🎲 Rolled a D{sides}: **{res}**", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("Please specify a valid number of sides.")

async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        low, high = int(context.args[0]), int(context.args[1])
        res = random.randint(low, high)
        await update.message.reply_text(f"🔢 Random number between {low} and {high}: **{res}**", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("Usage: `/random [min] [max]`", parse_mode="Markdown")

# --- Main Message Routing ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_str = get_user_identifier(update)
    user_text = update.message.text

    # Prepend User Username to Prompt so Gemini knows WHO in the group is talking!
    formatted_prompt = f"[Message from User {user_str}]: {user_text}"

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        reply_text = await ask_gemini(chat_id, formatted_prompt)
        await update.message.reply_text(reply_text, parse_mode="Markdown")
        
        # Send voice message alongside text
        await send_voice_reply(update, reply_text)
    except Exception as e:
        print(f"Error handling group chat: {e}")
        await update.message.reply_text(f"Apologies, {user_str}. I encountered a system glitch processing that request.")

# ---------------------------------------------------------
# 5. Application Launch
# ---------------------------------------------------------
def main():
    threading.Thread(target=run_health_server, daemon=True).start()

    app = Appl
