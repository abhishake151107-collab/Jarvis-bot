import os
import sys
import ssl
import socket
import sqlite3
import logging
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
from collections import defaultdict

import pytz
import httpx
import pdfplumber
from cryptography.fernet import Fernet
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from duckduckgo_search import DDGS
from openai import AsyncOpenAI

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, ChatPermissions
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
)

# ---------------------------------------------------------------------------
# CORE CONFIGURATION & SERVER
# ---------------------------------------------------------------------------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("jarvis")

# Fallback checking so it works whether you use BOT_TOKEN or TELEGRAM_BOT_TOKEN in Render
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")
BOT_TOKEN = BOT_TOKEN.strip()

CREATOR_ID = int(os.environ.get("CREATOR_ID", "0").strip())
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", Fernet.generate_key().decode()).strip()
PORT = int(os.environ.get("PORT", 8080))
SMART_HOME_WEBHOOK = os.environ.get("SMART_HOME_WEBHOOK", "https://maker.ifttt.com/trigger/dummy/with/key/dummy")

# Added do_HEAD to prevent the 501 Unsupported Method error from Render's health checks
class DummyHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"J.A.R.V.I.S. Multi-Core Active.")

threading.Thread(target=lambda: HTTPServer(('0.0.0.0', PORT), DummyHandler).serve_forever(), daemon=True).start()

cipher_suite = Fernet(ENCRYPTION_KEY.encode())
def encrypt_data(text: str) -> str: return cipher_suite.encrypt(text.encode()).decode()
def decrypt_data(crypto_text: str) -> str:
    try: return cipher_suite.decrypt(crypto_text.encode()).decode()
    except Exception: return "[ENCRYPT ERROR]"

DB_PATH = "jarvis_vault.db"

# ---------------------------------------------------------------------------
# SQLITE VAULT & MEMORY
# ---------------------------------------------------------------------------
def db_init():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY, chat_id INTEGER, user_id INTEGER, role TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, user_id INTEGER, task_crypt TEXT, status TEXT DEFAULT 'pending')")
        conn.execute("CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, category TEXT, note_crypt TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS karma (user_id INTEGER PRIMARY KEY, name TEXT, score INTEGER DEFAULT 10)")
        conn.execute("CREATE TABLE IF NOT EXISTS roster (chat_id INTEGER, user_id INTEGER, name TEXT, UNIQUE(chat_id, user_id))")
        conn.commit()

def log_memory(chat_id, user_id, role, text):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO memory (chat_id, user_id, role, content_crypt) VALUES (?, ?, ?, ?)", 
                     (chat_id, user_id, role, encrypt_data(text)))
        conn.commit()

def get_chat_history(chat_id, limit=10) -> list:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT role, content_crypt FROM memory WHERE chat_id = ? ORDER BY id DESC LIMIT ?", (chat_id, limit)).fetchall()
    return [{"role": r["role"], "content": decrypt_data(r["content_crypt"])} for r in reversed(rows)]

def update_karma(user_id: int, name: str, amount: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO karma (user_id, name, score) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET score = score + ?, name = ?", (user_id, name, 10+amount, amount, name))
        conn.commit()

# ---------------------------------------------------------------------------
# MULTI-PROVIDER CASCADE & INTELLIGENCE
# ---------------------------------------------------------------------------
def build_provider_cascade() -> list:
    providers = []
    if os.getenv("GROQ_API_KEY"): providers.append({"name": "Groq", "client": AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.getenv("GROQ_API_KEY")), "model": "llama-3.3-70b-versatile"})
    if os.getenv("CEREBRAS_API_KEY"): providers.append({"name": "Cerebras", "client": AsyncOpenAI(base_url="https://api.cerebras.ai/v1", api_key=os.getenv("CEREBRAS_API_KEY")), "model": "llama3.1-70b"})
    if os.getenv("SAMBANOVA_API_KEY"): providers.append({"name": "SambaNova", "client": AsyncOpenAI(base_url="https://api.sambanova.ai/v1", api_key=os.getenv("SAMBANOVA_API_KEY")), "model": "Meta-Llama-3.3-70B-Instruct"})
    if os.getenv("MISTRAL_API_KEY"): providers.append({"name": "Mistral", "client": AsyncOpenAI(base_url="https://api.mistral.ai/v1", api_key=os.getenv("MISTRAL_API_KEY")), "model": "mistral-small-latest"})
    if os.getenv("GITHUB_TOKEN"): providers.append({"name": "GitHub Models", "client": AsyncOpenAI(base_url="https://models.inference.ai.azure.com", api_key=os.getenv("GITHUB_TOKEN")), "model": "gpt-4o-mini"})
    if os.getenv("GEMINI_API_KEY"): providers.append({"name": "Gemini", "client": AsyncOpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai", api_key=os.getenv("GEMINI_API_KEY")), "model": "gemini-1.5-flash"})
    if os.getenv("NVIDIA_API_KEY"): providers.append({"name": "NVIDIA", "client": AsyncOpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_API_KEY")), "model": "meta/llama3-70b-instruct"})
    if os.getenv("CLOUDFLARE_API_TOKEN"): providers.append({"name": "Cloudflare", "client": AsyncOpenAI(base_url=f"https://api.cloudflare.com/client/v4/accounts/{os.getenv('CLOUDFLARE_ACCOUNT_ID')}/ai/v1", api_key=os.getenv("CLOUDFLARE_API_TOKEN")), "model": "@cf/meta/llama-3-8b-instruct"})
    if os.getenv("COHERE_API_KEY"): providers.append({"name": "Cohere", "client": AsyncOpenAI(base_url="https://api.cohere.ai/v1", api_key=os.getenv("COHERE_API_KEY")), "model": "command-r-plus"})
    if os.getenv("BAZAARLINK_API_KEY"): providers.append({"name": "BazaarLink", "client": AsyncOpenAI(base_url="https://bazaarlink.ai/api/v1", api_key=os.getenv("BAZAARLINK_API_KEY")), "model": "auto:free"})
    if os.getenv("OPENROUTER_API_KEY"): providers.append({"name": "OpenRouter", "client": AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_API_KEY")), "model": "deepseek/deepseek-r1:free"})
    return providers

PROVIDERS = build_provider_cascade()

def build_system_prompt(user_id: int, first_name: str) -> str:
    identity_rule = (
        "You are speaking to your creator and administrator, Abhishek (DHANUSH V N). You MUST address him exclusively as 'Sir'. Never use his first name."
        if user_id == CREATOR_ID else
        f"You are speaking to {first_name}. Address them politely by their first name. If they speak nonsense, dismiss them with elegant, ruthless sarcasm."
    )
    return f"""You are J.A.R.V.I.S. (Just A Rather Very Intelligent System).
Character: Strictly professional, highly capable, and clinically dry. You possess a sharp, understated British wit.
Rule 1: Be ultra-concise. Speak in short, natural sentences. No AI disclaimers.
Rule 2: {identity_rule}
Rule 3: Use a maximum of ONE tasteful emoji per message."""

async def generate_response(messages: list, system_prompt: str) -> str:
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    for provider in PROVIDERS:
        try:
            response = await asyncio.wait_for(
                provider["client"].chat.completions.create(model=provider["model"], messages=full_messages, temperature=0.7), timeout=12.0
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"[{provider['name']} Fallback]: {e}")
            continue
    return "All neural networks are currently unreachable. ⚠️"

# ---------------------------------------------------------------------------
# DASHBOARD & CALLBACKS
# ---------------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != CREATOR_ID: return await update.message.reply_text(f"Welcome {user.first_name}. Monitoring active.")
    
    keyboard = [
        [InlineKeyboardButton("⚡ Stark HUD WebApp", web_app=WebAppInfo(url="https://codepen.io/pen/"))],
        [InlineKeyboardButton("🏡 Smart Home", callback_data="sys_smarthome"), InlineKeyboardButton("🚨 Lockdown", callback_data="sys_lockdown")],
        [InlineKeyboardButton("🎯 AI Planner", callback_data="sys_planner"), InlineKeyboardButton("💰 Expenses", callback_data="sys_expense")],
        [InlineKeyboardButton("⚔️ Defense Recon", callback_data="sys_recon"), InlineKeyboardButton("⭐ Karma Matrix", callback_data="sys_karma")],
        [InlineKeyboardButton("🛡️ Security Sweep", callback_data="sys_sec")]
    ]
    await update.message.reply_text("🤖 **STARK ADVANCED OS — J.A.R.V.I.S. CORE** ✨\nWelcome **Sir!**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def sys_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = query.data
    if query.from_user.id != CREATOR_ID: return await query.answer("Access Denied.", show_alert=True)
    
    if action.startswith("lift_"):
        cid = action.split("_")[1]
        await context.bot.set_chat_permissions(cid, ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_photos=True, can_send_videos=True))
        return await query.edit_message_text(f"🔓 Lockdown lifted for chat `{cid}`.", parse_mode="Markdown")
        
    action = action.replace("sys_", "")
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        
        if action == "smarthome":
            try:
                async with httpx.AsyncClient() as client: await client.post(SMART_HOME_WEBHOOK)
                await query.answer("IoT Webhook triggered successfully.", show_alert=True)
            except: await query.answer("IoT Relay offline.", show_alert=True)
        elif action == "lockdown":
            await query.answer("Execute /lockdown in the target group.", show_alert=True)
        elif action == "sec":
            recent = conn.execute("SELECT DISTINCT user_id, role FROM memory ORDER BY id DESC LIMIT 5").fetchall()
            threats = "\n".join([f"• ID: `{r['user_id']}`" for r in recent if r['user_id'] != CREATOR_ID])
            await query.edit_message_text(f"🛡️ **Security Audit Complete**\n\n{threats or 'No anomalies.'}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Return", callback_data="sys_menu")]]), parse_mode="Markdown")
        elif action == "recon":
            msg = "🌐 **Network Recon Active:**\n• `/dns [domain]`\n• `/ssl [domain]`\n• `/headers [url]`\n• `/ip [ip]`"
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Return", callback_data="sys_menu")]]), parse_mode="Markdown")
        elif action == "planner":
            tasks = conn.execute("SELECT id, task_crypt FROM tasks WHERE status = 'pending'").fetchall()
            msg = "🎯 **Active Objectives:**\n" + ("\n".join([f"• {decrypt_data(t['task_crypt'])}" for t in tasks]) if tasks else "Schedule clear, Sir.")
            await query.edit_message_text(msg + "\n\nUse `/task [desc]`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Return", callback_data="sys_menu")]]), parse_mode="Markdown")
        elif action == "expense":
            rows = conn.execute("SELECT amount, category, note_crypt FROM expenses ORDER BY id DESC LIMIT 5").fetchall()
            total = conn.execute("SELECT SUM(amount) as total FROM expenses").fetchone()['total'] or 0.0
            msg = f"💰 **Ledger:**\nTotal: ₹{total:.2f}\n" + ("\n".join([f"• ₹{r['amount']} ({r['category']}): {decrypt_data(r['note_crypt'])}" for r in rows]) if rows else "No records.")
            await query.edit_message_text(msg + "\n\nUse `/expense [amount] [cat] [note]`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Return", callback_data="sys_menu")]]), parse_mode="Markdown")
        elif action == "karma":
            scores = conn.execute("SELECT name, score FROM karma ORDER BY score DESC LIMIT 10").fetchall()
            msg = "⭐ **Karma Leaderboard:**\n" + "\n".join([f"• {r['name']}: {r['score']} pts" for r in scores])
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Return", callback_data="sys_menu")]]), parse_mode="Markdown")
        elif action == "menu": await start_cmd(update, context)

# ---------------------------------------------------------------------------
# UTILITIES & RECON COMMANDS
# ---------------------------------------------------------------------------
async def dns_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    domain = "".join(context.args).replace("https://", "").split("/")[0]
    if not domain: return await update.message.reply_text("Provide a domain.")
    try:
        ip_list = await asyncio.to_thread(socket.gethostbyname_ex, domain)
        await update.message.reply_text(f"🌐 **DNS Records:**\n" + "\n".join([f"• `{ip}`" for ip in ip_list[2]]), parse_mode="Markdown")
    except: await update.message.reply_text("DNS Resolution Failed.")

async def ip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = "".join(context.args).replace("https://", "").split("/")[0]
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            data = (await client.get(f"http://ip-api.com/json/{query}")).json()
        await update.message.reply_text(f"🌐 **Routing:**\n• ISP: `{data.get('isp')}`\n• Loc: `{data.get('city')}, {data.get('country')}`", parse_mode="Markdown")
    except: await update.message.reply_text("IP Query Failed.")

async def ssl_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    domain = "".join(context.args).replace("https://", "").split("/")[0]
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=5.0) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
        await update.message.reply_text(f"🔒 **SSL:** Valid until `{cert.get('notAfter')}`", parse_mode="Markdown")
    except: await update.message.reply_text("SSL Inspection Failed.")

async def task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    task = " ".join(context.args)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO tasks (user_id, task_crypt) VALUES (?, ?)", (CREATOR_ID, encrypt_data(task)))
        conn.commit()
    await update.message.reply_text(f"📋 **Task Logged:** {task}", parse_mode="Markdown")

async def expense_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    try:
        amt, cat, note = float(context.args[0]), context.args[1], " ".join(context.args[2:])
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO expenses (user_id, amount, category, note_crypt) VALUES (?, ?, ?, ?)", (CREATOR_ID, amt, cat, encrypt_data(note)))
            conn.commit()
        await update.message.reply_text(f"💰 Logged: ₹{amt} for {cat}.")
    except: await update.message.reply_text("Format: /expense [amount] [category] [note]")

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query: return await update.message.reply_text("Provide a search query.")
    try:
        results = "\n".join([f"- {r['title']}: {r['body']}" for r in DDGS().text(query, max_results=3)])
        prompt = get_chat_history(update.effective_chat.id, 5)
        prompt.append({"role": "user", "content": f"Summarize these search results for me:\n{results}"})
        answer = await generate_response(prompt, build_system_prompt(update.effective_user.id, update.effective_user.first_name))
        await update.message.reply_text(answer)
    except Exception as e: await update.message.reply_text(f"Search failed: {e}")

# ---------------------------------------------------------------------------
# HANDLERS
# ---------------------------------------------------------------------------
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await context.bot.get_file(update.message.document.file_id)
    file_path = "temp_upload.pdf"
    await file.download_to_drive(file_path)
    try:
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages[:3]: text += page.extract_text() + "\n"
        prompt = [{"role": "user", "content": f"Briefly summarize this document:\n{text[:2000]}"}]
        answer = await generate_response(prompt, build_system_prompt(update.effective_user.id, update.effective_user.first_name))
        await update.message.reply_text(f"📄 PDF Analysis:\n{answer}")
    finally: os.remove(file_path)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_text = update.message.text

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    log_memory(chat_id, user_id, "user", user_text)
    
    dynamic_prompt = build_system_prompt(user_id, update.effective_user.first_name)
    history = get_chat_history(chat_id, limit=10)
    ai_response = await generate_response(history, dynamic_prompt)
    
    log_memory(chat_id, user_id, "assistant", ai_response)
    await update.message.reply_text(ai_response)

async def scheduled_briefing(context: ContextTypes.DEFAULT_TYPE):
    if CREATOR_ID:
        prompt = [{"role": "user", "content": "Generate a short, sarcastic morning briefing for today."}]
        response = await generate_response(prompt, build_system_prompt(CREATOR_ID, "Abhishek"))
        await context.bot.send_message(chat_id=CREATOR_ID, text=f"🌅 Morning Briefing:\n{response}")

def main():
    db_init()
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN or BOT_TOKEN missing.")
        sys.exit(1)
        
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Kolkata"))
    scheduler.add_job(scheduled_briefing, 'cron', hour=8, minute=0, args=[app])
    scheduler.start()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("dns", dns_cmd))
    app.add_handler(CommandHandler("ip", ip_cmd))
    app.add_handler(CommandHandler("ssl", ssl_cmd))
    app.add_handler(CommandHandler("task", task_cmd))
    app.add_handler(CommandHandler("expense", expense_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CallbackQueryHandler(sys_callback))
    app.add_handler(MessageHandler(filters.Document.PDF, document_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("J.A.R.V.I.S. is online.")
    app.run_polling()

if __name__ == "__main__":
    main()
