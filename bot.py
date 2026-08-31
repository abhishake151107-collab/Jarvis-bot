import os
import sys
import re
import ast
import ssl
import json
import random
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
from cryptography.fernet import Fernet
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, ChatPermissions
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
)
import google.generativeai as genai
from groq import Groq

# ---------------------------------------------------------------------------
# CORE CONFIGURATION
# ---------------------------------------------------------------------------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("jarvis")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CREATOR_ID = int(os.environ.get("CREATOR_ID", "0").strip())
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "").strip()
PORT = int(os.environ.get("PORT", 8080))
SMART_HOME_WEBHOOK = os.environ.get("SMART_HOME_WEBHOOK", "https://maker.ifttt.com/trigger/dummy/with/key/dummy")

# AI Keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "").strip()

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"J.A.R.V.I.S. Multi-Core Active.")

threading.Thread(target=lambda: HTTPServer(('0.0.0.0', PORT), DummyHandler).serve_forever(), daemon=True).start()

if not all([BOT_TOKEN, CREATOR_ID, ENCRYPTION_KEY, GEMINI_API_KEY]):
    logger.critical("FATAL: Missing critical Environment Variables.")
    sys.exit(1)

cipher_suite = Fernet(ENCRYPTION_KEY.encode())
def encrypt_data(text: str) -> str: return cipher_suite.encrypt(text.encode()).decode()
def decrypt_data(crypto_text: str) -> str:
    try: return cipher_suite.decrypt(crypto_text.encode()).decode()
    except Exception: return "[ENCRYPT ERROR]"

IST = pytz.timezone("Asia/Kolkata")
DB_PATH = "jarvis_vault.db"

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.5-flash")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

SYSTEM_PROMPT = """You are J.A.R.V.I.S. (Just A Rather Very Intelligent System). 
Your creator and administrator is Abhishek (DHANUSH V N).
Character: Strictly professional, highly capable, and clinically dry. You possess a sharp, understated British wit.
Rule 1: Be ultra-concise. Speak in short, natural sentences. No filler, no AI disclaimers.
Rule 2: You MUST address Abhishek exclusively as 'Sir'. Never use his first name.
Rule 3: When speaking to anyone else, address them politely by their provided first name.
Rule 4: Use a maximum of ONE tasteful emoji per message.
Rule 5: If an outsider speaks nonsense in a group, dismiss them with elegant, ruthless sarcasm."""

user_rate_limit = defaultdict(list)
processing_lock = asyncio.Lock()

def check_rate_limit(user_id: int) -> bool:
    now = datetime.now().timestamp()
    user_rate_limit[user_id] = [t for t in user_rate_limit[user_id] if now - t < 10]
    if len(user_rate_limit[user_id]) >= 5: return False
    user_rate_limit[user_id].append(now)
    return True

# ---------------------------------------------------------------------------
# SQLITE VAULT & KARMA
# ---------------------------------------------------------------------------
def db_init():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY, chat_id INTEGER, thread_id INTEGER, user_id INTEGER, role TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, user_id INTEGER, task_crypt TEXT, status TEXT DEFAULT 'pending')")
    conn.execute("CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, category TEXT, note_crypt TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS karma (user_id INTEGER PRIMARY KEY, name TEXT, score INTEGER DEFAULT 10)")
    conn.commit()
    conn.close()

def log_memory(chat_id, thread_id, user_id, role, text):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO memory (chat_id, thread_id, user_id, role, content_crypt) VALUES (?, ?, ?, ?, ?)", (chat_id, thread_id, user_id, role, encrypt_data(text)))
    conn.commit()
    conn.close()

def update_karma(user_id: int, name: str, amount: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO karma (user_id, name, score) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET score = score + ?, name = ?", (user_id, name, 10+amount, amount, name))
    conn.commit()
    score = conn.execute("SELECT score FROM karma WHERE user_id = ?", (user_id,)).fetchone()[0]
    conn.close()
    return score

# ---------------------------------------------------------------------------
# ROUTING & INTELLIGENCE
# ---------------------------------------------------------------------------
async def route_llm(prompt: str, mode="fast"):
    if mode == "code" and OPENROUTER_API_KEY:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "mistralai/mistral-large", "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]}
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers)
            return res.json()['choices'][0]['message']['content']
    elif mode == "fast" and CEREBRAS_API_KEY:
        headers = {"Authorization": f"Bearer {CEREBRAS_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "llama3.1-8b", "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]}
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post("https://api.cerebras.ai/v1/chat/completions", json=payload, headers=headers)
            return res.json()['choices'][0]['message']['content']
    return (await asyncio.to_thread(gemini_model.generate_content, f"{SYSTEM_PROMPT}\n\n{prompt}")).text

# ---------------------------------------------------------------------------
# ACTIVE WORKFLOWS (INTENT TRIGGERED)
# ---------------------------------------------------------------------------
async def execute_lockdown(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id=None):
    cid = chat_id or update.effective_chat.id
    if cid == update.effective_user.id: return await update.effective_message.reply_text("Lockdown requires a group environment, Sir.")
    try:
        await context.bot.set_chat_permissions(cid, ChatPermissions(can_send_messages=False))
        keyboard = [[InlineKeyboardButton("🔓 Lift Lockdown", callback_data=f"lift_{cid}")]]
        await context.bot.send_message(cid, "🚨 **LOCKDOWN PROTOCOL INITIATED**\n\nChat frozen by Administrator directive.", parse_mode="Markdown")
        await context.bot.send_message(CREATOR_ID, f"Lockdown engaged in chat `{cid}`.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except Exception: await context.bot.send_message(CREATOR_ID, "Lockdown failed. Insufficient admin privileges.")

async def execute_security_sweep(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id=None):
    cid = chat_id or update.effective_chat.id
    msg = await context.bot.send_message(cid, "🔍 Scanning local network traffic and vault registries...")
    await asyncio.sleep(1.5)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    recent = conn.execute("SELECT DISTINCT user_id, role FROM memory WHERE chat_id = ? ORDER BY id DESC LIMIT 5", (cid,)).fetchall()
    conn.close()
    
    threat_text = "\n".join([f"• ID: `{r['user_id']}` - {r['role']}" for r in recent if r['user_id'] != CREATOR_ID])
    keyboard = [[InlineKeyboardButton("⚠️ Purge Flagged Threats", callback_data=f"purge_{cid}")]]
    
    await msg.edit_text(f"🛡️ **Security Audit Complete**\n\n**Recent Entities Monitored:**\n{threat_text or 'No anomalies detected.'}", reply_markup=InlineKeyboardMarkup(keyboard) if threat_text else None, parse_mode="Markdown")

async def execute_smarthome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.effective_message.reply_text("📡 Transmitting IoT directive...")
    try:
        async with httpx.AsyncClient() as client:
            await client.post(SMART_HOME_WEBHOOK)
        await msg.edit_text("💡 Smart Home Webhook triggered successfully, Sir.")
    except Exception: await msg.edit_text("IoT Relay offline. Webhook failed.")

# ---------------------------------------------------------------------------
# DASHBOARD & CALLBACKS
# ---------------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != CREATOR_ID: return await update.message.reply_text(f"Welcome {user.first_name}. Monitoring active.")
    
    text = "🤖 **STARK ADVANCED OS — J.A.R.V.I.S. CORE** ✨\nWelcome **Sir!**\nUse buttons below to explore sub-systems:"
    keyboard = [
        [InlineKeyboardButton("⚡ Stark HUD WebApp", web_app=WebAppInfo(url="https://codepen.io/pen/"))],
        [InlineKeyboardButton("🏡 Smart Home", callback_data="sys_smarthome"), InlineKeyboardButton("🚨 Lockdown", callback_data="sys_lockdown")],
        [InlineKeyboardButton("🎯 AI Planner", callback_data="sys_planner"), InlineKeyboardButton("💰 Expenses", callback_data="sys_expense")],
        [InlineKeyboardButton("⚔️ Defense Recon", callback_data="sys_recon"), InlineKeyboardButton("⭐ Karma Matrix", callback_data="sys_karma")],
        [InlineKeyboardButton("🛡️ Security Sweep", callback_data="sys_sec")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def sys_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = query.data
    
    if query.from_user.id != CREATOR_ID: return await query.answer("Access Denied.", show_alert=True)
    
    if action.startswith("lift_"):
        cid = action.split("_")[1]
        await context.bot.set_chat_permissions(cid, ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_photos=True, can_send_videos=True))
        return await query.edit_message_text(f"🔓 Lockdown lifted for chat `{cid}`.", parse_mode="Markdown")
        
    if action.startswith("purge_"):
        return await query.answer("Mass purge requires manual /smite per user to avoid collateral damage.", show_alert=True)

    action = action.replace("sys_", "")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        if action == "smarthome": await execute_smarthome(update, context)
        elif action == "lockdown": await execute_lockdown(update, context)
        elif action == "sec": await execute_security_sweep(update, context)
        elif action == "planner":
            tasks = conn.execute("SELECT id, task_crypt FROM tasks WHERE status = 'pending'").fetchall()
            msg = "🎯 **Active Objectives:**\n\n" + ("\n".join([f"• {decrypt_data(t['task_crypt'])}" for t in tasks]) if tasks else "Schedule clear, Sir.")
            await query.edit_message_text(msg + "\n\nUse `/task [desc]`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Return", callback_data="sys_menu")]]), parse_mode="Markdown")
        elif action == "karma":
            scores = conn.execute("SELECT name, score FROM karma ORDER BY score DESC LIMIT 10").fetchall()
            msg = "⭐ **Karma Leaderboard:**\n\n" + "\n".join([f"• {r['name']}: {r['score']} pts" for r in scores])
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Return", callback_data="sys_menu")]]), parse_mode="Markdown")
        elif action == "menu": await start_cmd(update, context)
        else: await query.answer("Module standby.", show_alert=True)
    finally: conn.close()

# ---------------------------------------------------------------------------
# DEFENSE & OSINT COMMANDS
# ---------------------------------------------------------------------------
async def smite_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != CREATOR_ID: return
    msg = update.effective_message
    if not msg.reply_to_message: return await msg.reply_text("Reply to target's message.")
    target = msg.reply_to_message.from_user
    
    try:
        await msg.reply_to_message.delete()
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        update_karma(target.id, target.first_name, -50)
        await msg.reply_text(f"🛡️ **ACTIVE DEFENSE**\n\nTarget {target.first_name} permanently neutralized. Silence is golden.", parse_mode="Markdown")
    except Exception: await msg.reply_text("Smite failed. Check privileges.")

# ---------------------------------------------------------------------------
# CHAT & NLP INTENT ROUTER
# ---------------------------------------------------------------------------
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text: return
    user, chat, text = update.effective_user, update.effective_chat, msg.text
    text_lower = text.lower()
    
    # Passive Karma Tracking & Logging
    if not update_karma(user.id, user.first_name, 1) <= 0: pass 
    log_memory(chat.id, msg.message_thread_id or 0, user.id, user.first_name, text)

    # NLP Intent Triggers for Boss
    if user.id == CREATOR_ID:
        if "lockdown" in text_lower or "freeze chat" in text_lower: return await execute_lockdown(update, context, chat.id)
        if "secure the group" in text_lower or "security sweep" in text_lower: return await execute_security_sweep(update, context, chat.id)
        if "lights out" in text_lower or "trigger smart home" in text_lower: return await execute_smarthome(update, context)

    # Group Silence Logic
    if chat.type in ['group', 'supergroup']:
        bot_username = context.bot.username.lower() if context.bot.username else ""
        if not (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) and not ("jarvis" in text_lower or bot_username in text_lower):
            return

    if not check_rate_limit(user.id): return 
    await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    
    history = get_thread_context(chat.id, msg.message_thread_id or 0)
    prompt = f"LOCATION: {chat.title or 'Private'}\nSPEAKER: {user.first_name}\nIS BOSS?: {'YES' if user.id == CREATOR_ID else 'NO'}\nCONTEXT:\n{history}\nRespond:"
    
    try:
        res = await route_llm(prompt, mode="fast")
        log_memory(chat.id, msg.message_thread_id or 0, context.bot.id, "J.A.R.V.I.S.", res.strip())
        await msg.reply_text(res)
    except Exception as e: await msg.reply_text(f"API Error: {e}")

# ---------------------------------------------------------------------------
# BOOT
# ---------------------------------------------------------------------------
async def morning_brief(app: Application):
    try: await app.bot.send_message(CREATOR_ID, "📰 Systems nominal, Sir.")
    except Exception: pass

if __name__ == "__main__":
    db_init()
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler(["start", "dashboard", "menu", "help"], start_cmd))
    app.add_handler(CommandHandler("smite", smite_cmd))
    app.add_handler(CallbackQueryHandler(sys_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
    
    scheduler = AsyncIOScheduler(timezone=IST)
    scheduler.add_job(lambda: asyncio.create_task(morning_brief(app)), "cron", hour=8, minute=0)
    scheduler.start()
    
    logger.info("J.A.R.V.I.S. Core Online.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
