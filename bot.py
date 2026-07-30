import os
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types

# ---------------------------------------------------------
# 1. Environment & API Keys
# ---------------------------------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or GEMINI_API_KEY environment variables!")

ai_client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------------
# 2. 24/7 Health-Check Server (For Render hosting)
# ---------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Jarvis AI Agent is active and running!")

def run_health_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# ---------------------------------------------------------
# 3. Command Handlers
# ---------------------------------------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = (
        "🤖 **Jarvis AI Agent — Feature Menu**\n\n"
        "🧠 **AI FEATURES**\n"
        "• `/image [prompt]` — Generate AI image\n"
        "• `/story [prompt]` — Write a short story\n"
        "• `/debate [topic]` — Both sides of a debate\n"
        "• `/explain [code]` — Explain any code\n"
        "• `/code [lang] [task]` — Generate code\n"
        "• `/name [type]` — Creative name generator\n"
        "• `/horoscope [sign]` — Daily horoscope\n\n"
        "⚙️ **UTILITIES**\n"
        "• `/myid` — Show your Telegram ID\n"
        "• `/help` — Show this menu\n\n"
        "💬 *Or just type any question to chat with AI directly!*"
    )
    await update.message.reply_text(menu, parse_mode="Markdown")

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"👤 **User ID:** `{user_id}`\n💬 **Chat ID:** `{chat_id}`", parse_mode="Markdown")

async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Please provide a prompt! Example: `/image futuristic city at night`", parse_mode="Markdown")
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
    image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"
    try:
        await update.message.reply_photo(photo=image_url, caption=f"🎨 **Prompt:** {prompt}")
    except Exception:
        await update.message.reply_text("Apologies, I encountered an error generating that image.")

async def story_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Example: `/story a detective investigating a haunted space station`", parse_mode="Markdown")
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    res = ai_client.models.generate_content(
        model=MODEL_NAME,
        contents=f"Write an engaging short story based on: {prompt}"
    )
    await update.message.reply_text(res.text)

async def debate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic:
        await update.message.reply_text("Example: `/debate Remote work vs Office work`", parse_mode="Markdown")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    res = ai_client.models.generate_content(
        model=MODEL_NAME,
        contents=f"Provide a balanced debate presenting both Pros and Cons for: {topic}"
    )
    await update.message.reply_text(res.text)

async def explain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code_snippet = " ".join(context.args)
    if not code_snippet:
        await update.message.reply_text("Example: `/explain print([x**2 for x in range(10)])`", parse_mode="Markdown")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    res = ai_client.models.generate_content(
        model=MODEL_NAME,
        contents=f"Explain this code step-by-step clearly:\n```\n{code_snippet}\n```"
    )
    await update.message.reply_text(res.text, parse_mode="Markdown")

async def code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task = " ".join(context.args)
    if not task:
        await update.message.reply_text("Example: `/code python script to scrape news headlines`", parse_mode="Markdown")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    res = ai_client.models.generate_content(
        model=MODEL_NAME,
        contents=f"Write clean, well-commented code for this task: {task}"
    )
    await update.message.reply_text(res.text)

async def name_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = " ".join(context.args) or "AI Tech Startup"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    res = ai_client.models.generate_content(
        model=MODEL_NAME,
        contents=f"Generate 5 creative, brandable name ideas with short descriptions for: {category}"
    )
    await update.message.reply_text(res.text)

async def horoscope_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sign = " ".join(context.args)
    if not sign:
        await update.message.reply_text("Example: `/horoscope Leo`", parse_mode="Markdown")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    res = ai_client.models.generate_content(
        model=MODEL_NAME,
        contents=f"Provide a fun, insightful, and motivating daily horoscope for the zodiac sign: {sign}"
    )
    await update.message.reply_text(res.text)

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    res = ai_client.models.generate_content(
        model=MODEL_NAME,
        contents=user_text,
        config=types.GenerateContentConfig(
            system_instruction="You are Jarvis, a smart, witty, and polite personal AI assistant."
        )
    )
    await update.message.reply_text(res.text)

# ---------------------------------------------------------
# 4. Main Engine
# ---------------------------------------------------------
def main():
    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Register Commands
    app.add_handler(CommandHandler(["start", "help"], help_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("image", image_command))
    app.add_handler(CommandHandler("story", story_command))
    app.add_handler(CommandHandler("debate", debate_command))
    app.add_handler(CommandHandler("explain", explain_command))
    app.add_handler(CommandHandler("code", code_command))
    app.add_handler(CommandHandler("name", name_command))
    app.add_handler(CommandHandler("horoscope", horoscope_command))

    # General Chat
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))

    print("Jarvis is online with all commands ready!")
    app.run_polling()

if __name__ == "__main__":
    main()
  
