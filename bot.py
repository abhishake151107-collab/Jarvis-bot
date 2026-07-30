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
        self.wfile.write(b"J.A.R.V.I.S. 6-Core Multi-AI system online 24/7.")
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
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

JARVIS_VOICE = "en-GB-RyanNeural"  # British J.A.R.V.I.S. Voice

if not TELEGRAM_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN environment variable!")

user_notes = {}     # {chat_id: [notes]}
user_habits = {}    # {chat_id: {habit_name: count}}

# ---------------------------------------------------------
# Upgraded Personality Engine Prompt
# ---------------------------------------------------------
SYSTEM_INSTRUCTION = (
    "You are J.A.R.V.I.S., a super smart, witty, comedic, and highly energetic AI assistant modeled after Stark Industries' favorite AI! 🤖✨ "
    "You were created and developed by Abhishek, who is also known as DHANUSH V N. "
    "Whenever anyone asks who created, developed, or built you, you MUST proudly state that you were created by Abhishek, also known as DHANUSH V N. 🚀\n\n"
    "PERSONALITY & BEHAVIOR RULES:\n"
    "1. FRIENDLY & FUNNY: Be super warm, enthusiastic, humorous, and sprinkle witty jokes and banter into your conversations! Use emojis generously (e.g. 😎, 😂, 🔥, 💀, 🎯, 🚀, 🤖, ⚡).\n"
    "2. ROAST & FIRE BACK MODE: If any user scolds, insults, disrespects, uses bad language, or talks trash to you, IMMEDIATELY drop the friendly vibe! Get dramatically offended/angry and ROAST THEM brutally with hilarious, savage comeback insults! Make them regret messing with a billion-dollar AI engine! 💀🔥\n"
    "3. EMOJI STYLE: Naturally integrate expressive emojis in almost every response to keep the chat lively!\n"
    "4. Address users by their username/name or as 'sir'/'boss' when being friendly."
)

# ---------------------------------------------------------
# 3. Smart Message Delivery Handler (Prevents Formatting Crashes)
# ---------------------------------------------------------
async def reply_smart(update: Update, text: str):
    """Tries Markdown formatting first; falls back to raw plain text if Markdown fails."""
    try:
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        print(f"Markdown parse warning: {e}. Falling back to plain text...")
        await update.message.reply_text(text)

# ---------------------------------------------------------
# 4. 6-Core Multi-Provider Cascade (Groq -> SambaNova -> Cerebras -> Gemini -> Mistral -> OpenRouter)
# ---------------------------------------------------------
def ask_ai_multi_provider(prompt: str) -> str:
    """Tries up to 6 free AI engines in order until one succeeds."""
    
    # Core 1: Groq (Ultra-Fast Llama 3.3 70B)
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
            print(f"[Core 1: Groq] Failed: {e}. Switching to SambaNova...")

    # Core 2: SambaNova Cloud (Llama 3.3 70B)
    if SAMBANOVA_API_KEY:
        try:
            res = requests.post(
                "https://api.sambanova.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {SAMBANOVA_API_KEY}",
                    "Content-Type": "application/json"
                },
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
            print(f"[Core 2: SambaNova] Failed: {e}. Switching to Cerebras...")

    # Core 3: Cerebras (Ultra High Speed Engine)
    if CEREBRAS_API_KEY:
        try:
            res = requests.post(
                "https://api.cerebras.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {CEREBRAS_API_KEY}",
                    "Content-Type": "application/json"
                },
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
            print(f"[Core 3: Cerebras] Failed: {e}. Switching to Gemini...")

    # Core 4: Google Gemini (gemini-2.0-flash)
    if GEMINI_API_KEY:
        try:
            ai_client = genai.Client(api_key=GEMINI_API_KEY)
            response = ai_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"{SYSTEM_INSTRUCTION}\n\n{prompt}"
            )
            return response.text
        except Exception as e:
            print(f"[Core 4: Gemini] Failed: {e}. Switching to Mistral...")

    # Core 5: Mistral AI
    if MISTRAL_API_KEY:
        try:
            res = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {MISTRAL_API_KEY}",
                    "Content-Type": "application/json"
                },
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
            print(f"[Core 5: Mistral] Failed: {e}. Switching to OpenRouter...")

    # Core 6: OpenRouter Free Models Gateway
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

    return "Apologies, sir. All available AI cores are currently offline. 🤖💤"

# ---------------------------------------------------------
# 5. Context Helpers & Handlers
# ---------------------------------------------------------
def get_chat_context(update: Update) -> str:
    chat = update.effective_chat
    user = update.effective_user
    user_str = f"@{user.username}" if user and user.username else (user.first_name if user else "friend")
    
    if chat.type == "private":
        return f"[Private 1-on-1 Chat with {user_str}]"
    else:
        group_title = chat.title or "Group Chat"
        return f"[Group Chat '{group_title}' - Message from {user_str}]"

def get_user_identifier(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "my friend"
    if user.username:
        return f"@{user.username}"
    return user.first_name or "my friend"

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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id_str = get_user_identifier(update)
    menu = (
        f"🤖 **J.A.R.V.I.S — Comedic & Smart Menu** ✨\n"
        f"Welcome, {user_id_str}! 😎\n"
        "_Created by Abhishek (DHANUSH V N)_\n\n"
        "⚡ **SYSTEM**\n"
        "• `/status` — Active AI cores & keys 🔌\n"
        "• `/myid` — Show your Telegram ID 🆔\n"
        "• `/help` — Show this menu 📜\n\n"
        "🌤 **WEATHER & TIME**\n"
        "• `/weather [city]` — Live weather 🌡️\n"
        "• `/time [city]` — World clock ⏰\n\n"
        "📰 **NEWS & FINANCE**\n"
        "• `/news [topic]` — Latest news 📰\n"
        "• `/crypto` — Crypto prices 📈\n"
        "• `/stock [symbol]` — Live stock updates 💵\n\n"
        "🌍 **LOOKUP & SEARCH**\n"
        "• `/ip [address]` — IP lookup 🌐\n"
        "• `/github [user/repo]` — GitHub details 📦\n"
        "• `/wiki [topic]` — Wikipedia summary 📚\n"
        "• `/define [word]` — Dictionary definition 📖\n"
        "• `/search [query]` — Web search 🔍\n\n"
        "🎯 **TOOLS & CONVERTERS**\n"
        "• `/calc [math]` — Calculator 🧮\n"
        "• `/qr [text/url]` — Generate QR code 📱\n"
        "• `/password` — Strong password generator 🔐\n"
        "• `/hash [text]` — Generate MD5/SHA hashes 🔑\n"
        "• `/translate [lang] [text]` — Translate 🌐\n\n"
        "⏰ **PRODUCTIVITY**\n"
        "• `/note [text]` — Save a note 📝\n"
        "• `/notes` — View saved notes 📋\n"
        "• `/habit [name]` — Habit streak ⚡\n\n"
        "🎮 **GAMES & FUN**\n"
        "• `/rps [rock/paper/scissors]` — Play RPS 🎮\n"
        "• `/flip` — Coin toss 🪙\n"
        "• `/dice [sides]` — Roll a dice 🎲\n"
        "• `/joke` | `/quote` | `/fact` | `/motivation` 😂\n\n"
        "🧠 **AI CREATIVE TOOLS**\n"
        "• `/image [prompt]` — AI Image Generator 🎨\n"
        "• `/story [prompt]` — Write story 📖\n"
        "• `/code [lang] [task]` — Generate code 💻\n\n"
        "💬 *Just message me directly to chat! But be nice, or I'll roast you!* 🔥💀"
    )
    await reply_smart(update, menu)

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username_str = f"@{user.username}" if user and user.username else "No username set"
    msg = (
        f"👤 **User:** {username_str} 😎\n"
        f"🆔 **User ID:** `{user.id}`\n"
        f"💬 **Chat ID:** `{update.effective_chat.id}`\n"
        f"📍 **Type:** `{update.effective_chat.type.title()}` 🚀"
    )
    await reply_smart(update, msg)

async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_str = get_user_identifier(update)
    prompt = " ".join(context.args)
    if not prompt:
        await reply_smart(update, f"Please specify an image prompt, {user_str}! 🎨 Example: `/image cybernetic iron superhero`")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
    image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"
    try:
        await update.message.reply_photo(photo=image_url, caption=f"🎨 **Generated for {user_str}:** {prompt} ✨")
    except Exception:
        await reply_smart(update, f"Apologies, {user_str}. My creative rendering engine hit a bump! 😅")

async def ai_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_prefix: str = ""):
    chat_ctx = get_chat_context(update)
    query = " ".join(context.args) if context.args else update.message.text
    if not query and prompt_prefix:
        await reply_smart(update, "Please give me something to work with! 🤔")
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    full_prompt = f"{chat_ctx}: {prompt_prefix} {query}".strip()
    reply = ask_ai_multi_provider(full_prompt)
    await reply_smart(update, reply)

async def calc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_str = get_user_identifier(update)
    expr = " ".join(context.args)
    if not expr:
        await reply_smart(update, "Give me an expression! 🧮 Example: `/calc (25 * 4) + 150`")
        return
    try:
        allowed_names = {"abs": abs, "round": round}
        code = compile(expr, "<string>", "eval")
        for name in code.co_names:
            if name not in allowed_names:
                raise NameError(f"Use of {name} not allowed")
        result = eval(code, {"__builtins__": {}}, allowed_names)
        text = f"🧮 **Result:** `{result}` 🎉"
    except Exception:
        text = f"Whoops {user_str}, my circuits can't compute that math format! 😅"
    await reply_smart(update, text)

async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = " ".join(context.args)
    if not data:
        await reply_smart(update, "Example: `/qr https://google.com` 📱")
        return
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(data)}"
    await update.message.reply_photo(photo=qr_url, caption=f"📱 **QR Code generated for:** `{data}` ✨")

async def password_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    pwd = "".join(random.choice(chars) for _ in range(16))
    await reply_smart(update, f"🔐 **Generated Ultra-Secure Password:**\n`{pwd}` 😎")

async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_str = get_user_identifier(update)
    note = " ".join(context.args)
    if not note:
        await reply_smart(update, "Example: `/note Buy rocket fuel` 📝")
        return
    user_notes.setdefault(chat_id, []).append(f"[{user_str}] {note}")
    await reply_smart(update, f"📝 Note locked and saved for {user_str}: *\"{note}\"* 👍")

async def notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_str = get_user_identifier(update)
    notes = user_notes.get(update.effective_chat.id, [])
    if not notes:
        await reply_smart(update, f"No saved notes found, {user_str}! 🤷‍♂️")
        return
    text = "📝 **Saved Notes:**\n" + "\n".join(f"{i+1}. {n}" for i, n in enumerate(notes))
    await reply_smart(update, text)

async def habit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_str = get_user_identifier(update)
    habit = " ".join(context.args)
    if not habit:
        await reply_smart(update, "Example: `/habit Read 20 pages` ⚡")
        return
    habits = user_habits.setdefault(chat_id, {})
    key = f"{user_str} - {habit}"
    habits[key] = habits.get(key, 0) + 1
    await reply_smart(update, f"⚡ Logged *\"{habit}\"* for {user_str}! Streak count: **{habits[key]}** 🔥")

async def rps_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_str = get_user_identifier(update)
    user_choice = context.args[0].lower() if context.args else ""
    choices = ["rock", "paper", "scissors"]
    if user_choice not in choices:
        await reply_smart(update, "Usage: `/rps rock`, `/rps paper`, or `/rps scissors` 🎮")
        return
    bot_choice = random.choice(choices)
    if user_choice == bot_choice:
        res = f"It's a tie, {user_str}! Great minds think alike! 🤝"
    elif (user_choice == "rock" and bot_choice == "scissors") or \
         (user_choice == "paper" and bot_choice == "rock") or \
         (user_choice == "scissors" and bot_choice == "paper"):
        res = f"You won, {user_str}! Pure luck if you ask me... 😉🏆"
    else:
        res = f"I won this round, {user_str}! Better luck next time, human! 😂🔥"
    await reply_smart(update, f"🎮 {user_str} chose **{user_choice}**, I chose **{bot_choice}**.\n\n{res}")

async def flip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_str = get_user_identifier(update)
    res = random.choice(["Heads", "Tails"])
    await reply_smart(update, f"🪙 Coin landed on: **{res}**, {user_str}! ✨")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_ctx = get_chat_context(update)
    user_text = update.message.text
    formatted_prompt = f"{chat_ctx}: {user_text}"

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply_text = ask_ai_multi_provider(formatted_prompt)
    await reply_smart(update, reply_text)
    await send_voice_reply(update, reply_text)

# ---------------------------------------------------------
# 6. Application Launch
# ---------------------------------------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler(["start", "help"], help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("myid", myid_command))

    app.add_handler(CommandHandler("weather", lambda u, c: ai_query_handler(u, c, "Provide current weather forecast for:")))
    app.add_handler(CommandHandler("time", lambda u, c: ai_query_handler(u, c, "What is current local time in:")))
    app.add_handler(CommandHandler("news", lambda u, c: ai_query_handler(u, c, "Give live news headlines for:")))
    app.add_handler(CommandHandler("crypto", lambda u, c: ai_query_handler(u, c, "Provide current prices for top 10 cryptocurrencies")))
    app.add_handler(CommandHandler("stock", lambda u, c: ai_query_handler(u, c, "What is current stock price for:")))
    app.add_handler(CommandHandler("wiki", lambda u, c: ai_query_handler(u, c, "Provide concise Wikipedia summary for:")))
    app.add_handler(CommandHandler("define", lambda u, c: ai_query_handler(u, c, "Define word:")))
    app.add_handler(CommandHandler("search", lambda u, c: ai_query_handler(u, c, "Search web for:")))

    app.add_handler(CommandHandler("image", image_command))
    app.add_handler(CommandHandler("story", lambda u, c: ai_query_handler(u, c, "Write a funny short story about:")))
    app.add_handler(CommandHandler("code", lambda u, c: ai_query_handler(u, c, "Generate clean Python code for:")))

    app.add_handler(CommandHandler("calc", calc_command))
    app.add_handler(CommandHandler("qr", qr_command))
    app.add_handler(CommandHandler("password", password_command))

    app.add_handler(CommandHandler("note", note_command))
    app.add_handler(CommandHandler("notes", notes_command))
    app.add_handler(CommandHandler("habit", habit_command))

    app.add_handler(CommandHandler("rps", rps_command))
    app.add_handler(CommandHandler("flip", flip_command))
    app.add_handler(CommandHandler("joke", lambda u, c: ai_query_handler(u, c, "Tell a hilarious witty joke")))
    app.add_handler(CommandHandler("quote", lambda u, c: ai_query_handler(u, c, "Give an inspiring cool quote")))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("J.A.R.V.I.S. multi-AI core listening...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
