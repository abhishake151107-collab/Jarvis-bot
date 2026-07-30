import os
import random
import hashlib
import base64
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# ---------------------------------------------------------
# 1. Instant Port Binding for Render Web Service
# ---------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"J.A.R.V.I.S. multi-AI core operational 24/7.")
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
# 2. Imports & Configuration
# ---------------------------------------------------------
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from groq import Groq
import edge_tts

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

JARVIS_VOICE = "en-GB-RyanNeural"  # British J.A.R.V.I.S. Voice

if not TELEGRAM_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN environment variable!")

# Global Memory Stores
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
# 3. Smart Multi-Provider AI Routing (Groq -> Gemini -> OpenRouter)
# ---------------------------------------------------------
def ask_ai_multi_provider(prompt: str) -> str:
    """Tries multiple free AI APIs in order until one succeeds."""
    
    # 1. Primary: Groq (Llama 3.3 70B)
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
            print(f"Groq API primary failed, trying Gemini fallback... Error: {e}")

    # 2. Secondary: Google Gemini (gemini-2.0-flash)
    if GEMINI_API_KEY:
        try:
            ai_client = genai.Client(api_key=GEMINI_API_KEY)
            response = ai_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"{SYSTEM_INSTRUCTION}\n\n{prompt}"
            )
            return response.text
        except Exception as e:
            print(f"Gemini API fallback failed, trying OpenRouter... Error: {e}")

    # 3. Tertiary: OpenRouter Free Tier
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
            print(f"OpenRouter API failed... Error: {e}")

    return "Apologies, sir. All available AI sub-systems are currently at capacity. Please try again in a few moments."

# ---------------------------------------------------------
# 4. Helpers & Handlers
# ---------------------------------------------------------
def get_chat_context(update: Update) -> str:
    """Detects whether this is a Private Chat (DM) or a Group Chat."""
    chat = update.effective_chat
    user = update.effective_user
    user_str = f"@{user.username}" if user and user.username else (user.first_name if user else "sir")
    
    if chat.type == "private":
        return f"[Private 1-on-1 Chat with {user_str}]"
    else:
        group_title = chat.title or "Group Chat"
        return f"[Group Chat '{group_title}' - Message from {user_str}]"

def get_user_identifier(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "sir"
    if user.username:
        return f"@{user.username}"
    return user.first_name or "sir"

async def send_voice_reply(update: Update, text: str):
    chat_id = update.effective_chat.id
    audio_path = f"jarvis_{chat_id}.mp3"
    try:
        tts_text = text[:400]
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
        "• `/github [user/repo]` — GitHub details\n"
        "• `/wiki [topic]` — Wikipedia summary\n"
        "• `/define [word]` — Dictionary definition\n"
        "• `/search [query]` — Web search\n"
        "• `/lyrics [song]` — Song lyrics\n"
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
        f"💬 **Chat ID:** `{update.effective_chat.id}`\n"
        f"📍 **Type:** `{update.effective_chat.type.title()}`",
        parse_mode="Markdown"
    )

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
    chat_ctx = get_chat_context(update)
    query = " ".join(context.args) if context.args else update.message.text
    if not query and prompt_prefix:
        await update.message.reply_text("Please provide details.", parse_mode="Markdown")
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    full_prompt = f"{chat_ctx}: {prompt_prefix} {query}".strip()
    reply = ask_ai_multi_provider(full_prompt)
    await update.message.reply_text(reply, parse_mode="Markdown")

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
        await update.message.reply_text(f"No saved notes found, {user_str}.")
        return
    text = "📝 **Saved Notes:**\n" + "\n".join(f"{i+1}. {n}" for i, n in enumerate(notes))
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
    await update.message.reply_text(f"⚡ Logged *\"{habit}\"* for {user_str}. Streak count: **{habits[key]}**", parse_mode="Markdown")

async def habits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    habits = user_habits.get(update.effective_chat.id, {})
    if not habits:
        await update.message.reply_text("No habit streaks recorded yet in this chat.")
        return
    text = "⚡ **Active Habit Streaks:**\n" + "\n".join(f"• **{k}:** {v} days" for k, v in habits.items())
    await update.message.reply_text(text, parse_mode="Markdown")

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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_ctx = get_chat_context(update)
    user_text = update.message.text
    formatted_prompt = f"{chat_ctx}: {user_text}"

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply_text = ask_ai_multi_provider(formatted_prompt)
    await update.message.reply_text(reply_text, parse_mode="Markdown")
    await send_voice_reply(update, reply_text)

# ---------------------------------------------------------
# 5. Application Launch
# ---------------------------------------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler(["start", "help"], help_command))
    app.add_handler(CommandHandler("myid", myid_command))

    # Multi-AI Query Handlers
    app.add_handler(CommandHandler("weather", lambda u, c: ai_query_handler(u, c, "Provide current weather forecast for:")))
    app.add_handler(CommandHandler("time", lambda u, c: ai_query_handler(u, c, "What is current local time in:")))
    app.add_handler(CommandHandler("news", lambda u, c: ai_query_handler(u, c, "Give live news headlines for:")))
    app.add_handler(CommandHandler("crypto", lambda u, c: ai_query_handler(u, c, "Provide current prices for top 10 cryptocurrencies")))
    app.add_handler(CommandHandler("stock", lambda u, c: ai_query_handler(u, c, "What is current stock price for:")))
    app.add_handler(CommandHandler("wiki", lambda u, c: ai_query_handler(u, c, "Provide concise Wikipedia summary for:")))
    app.add_handler(CommandHandler("define", lambda u, c: ai_query_handler(u, c, "Define word:")))
    app.add_handler(CommandHandler("search", lambda u, c: ai_query_handler(u, c, "Search web for:")))
    app.add_handler(CommandHandler("recipe", lambda u, c: ai_query_handler(u, c, "Provide step-by-step recipe for:")))
    app.add_handler(CommandHandler("translate", lambda u, c: ai_query_handler(u, c, "Translate into requested language:")))

    app.add_handler(CommandHandler("image", image_command))
    app.add_handler(CommandHandler("story", lambda u, c: ai_query_handler(u, c, "Write a short story about:")))
    app.add_handler(CommandHandler("explain", lambda u, c: ai_query_handler(u, c, "Explain this code:")))
    app.add_handler(CommandHandler("code", lambda u, c: ai_query_handler(u, c, "Generate clean Python code for:")))

    app.add_handler(CommandHandler("calc", calc_command))
    app.add_handler(CommandHandler("qr", qr_command))
    app.add_handler(CommandHandler("password", password_command))

    app.add_handler(CommandHandler("note", note_command))
    app.add_handler(CommandHandler("notes", notes_command))
    app.add_handler(CommandHandler("delnote", delnote_command))
    app.add_handler(CommandHandler("habit", habit_command))
    app.add_handler(CommandHandler("habits", habits_command))

    app.add_handler(CommandHandler("rps", rps_command))
    app.add_handler(CommandHandler("flip", flip_command))
    app.add_handler(CommandHandler("joke", lambda u, c: ai_query_handler(u, c, "Tell a witty joke")))
    app.add_handler(CommandHandler("quote", lambda u, c: ai_query_handler(u, c, "Give an inspiring quote")))

    # Listens in both Private DMs and Groups!
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("J.A.R.V.I.S. multi-AI core listening...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
