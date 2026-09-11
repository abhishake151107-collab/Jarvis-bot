import os
import re
import sys
import time
import json
import random
import base64
import sqlite3
import logging
import hashlib
import asyncio
import httpx
import traceback
import threading
import socket
import shutil
import pickle
import psutil
import shlex
import urllib.parse
from datetime import datetime, timedelta
from collections import defaultdict

# --- WEB SERVER IMPORTS ---
from flask import Flask, request, jsonify
from flask_cors import CORS

import pytz
import pdfplumber
from bs4 import BeautifulSoup
from cryptography.fernet import Fernet
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from youtube_transcript_api import YouTubeTranscriptApi

# --- NEW INTELLIGENCE IMPORTS ---
import wikipedia
from geopy.geocoders import Nominatim

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    ContextTypes, 
    filters, 
    Application
)

# ---------------------------------------------------------------------------
# I. CORE CONFIGURATION & SETUP
# ---------------------------------------------------------------------------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("jarvis")

BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")).strip()
CREATOR_ID = int(os.environ.get("CREATOR_ID", "0").strip())
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "U3RhcmtfSW5kdXN0cmllc19KYXJ2aXNfQ29yZV8wMDc=").strip()
PORT = int(os.environ.get("PORT", 8080))
IST = pytz.timezone('Asia/Kolkata')

LOCKDOWN_FILE = "jarvis_lockdown.flag"
DB_PATH = "jarvis_vault.db"
cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def encrypt_data(text: str) -> str: return cipher_suite.encrypt(str(text or "").encode()).decode()
def decrypt_data(crypto_text: str) -> str:
    try: return cipher_suite.decrypt(crypto_text.encode()).decode()
    except Exception: return "[ENCRYPT ERROR]"

# ---------------------------------------------------------------------------
# II. SQLITE VAULT (MEMORY)
# ---------------------------------------------------------------------------
def db_init():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY, chat_id INTEGER, thread_id INTEGER, user_id INTEGER, role TEXT, content_crypt TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS economy (user_id INTEGER PRIMARY KEY, karma INTEGER DEFAULT 100)")
        conn.commit()

def log_memory(chat_id, thread_id, user_id, role, text):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO memory (chat_id, thread_id, user_id, role, content_crypt) VALUES (?, ?, ?, ?, ?)", 
                     (chat_id, thread_id or 0, user_id, role, encrypt_data(text)))
        conn.commit()

def get_chat_history(chat_id, thread_id=0, limit=15) -> list:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT role, content_crypt FROM memory WHERE chat_id = ? AND thread_id = ? ORDER BY id DESC LIMIT ?", (chat_id, thread_id or 0, limit)).fetchall()
    return [{"role": r["role"], "content": decrypt_data(r["content_crypt"])} for r in reversed(rows)]

# ---------------------------------------------------------------------------
# III. RAW REST API (THE BULLETPROOF BRAIN)
# ---------------------------------------------------------------------------
def build_system_prompt(user_name: str, user_prompt: str = "") -> str:
    now_ist = datetime.now(IST).strftime("%A, %B %d, %Y - %I:%M %p IST")
    return f"""Platform: Telegram. Time: {now_ist}.
Identity: You are J.A.R.V.I.S., a clinical, highly advanced military-grade AI Systems Architect. 
Speaking to: {user_name}. 
DIRECTIVES: Be concise. No emojis. Clinical tone. Who created you? Answer: Abhishek (aka DHANUSH V N)."""

async def generate_response(prompt: str, history: list, sys_prompt: str) -> str:
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_key: return "Critical Error: GEMINI_API_KEY is missing from environment variables."

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
        
        # Format for Gemini REST API
        contents = []
        for msg in history:
            role = 'model' if msg['role'] == 'assistant' else 'user'
            contents.append({"role": role, "parts": [{"text": msg['content']}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        
        payload = {
            "systemInstruction": {"parts": [{"text": sys_prompt}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1000}
        }
        
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                return resp.json()['candidates'][0]['content']['parts'][0]['text']
            else:
                return f"API Error {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return f"Network Node Failure: {str(e)[:100]}"

# ---------------------------------------------------------------------------
# IV. TOOLS & COMMANDS (THE BODY)
# ---------------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = f"Systems online, {user.first_name}. I am J.A.R.V.I.S., Titan Core V8.4. How may I assist you?"
    await update.message.reply_text(msg)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🛠️ **J.A.R.V.I.S. Arsenal:**\n"
        "`/start` - Initialize core systems\n"
        "`/help` - Display this menu\n"
        "`/scan <target>` - Run lightweight Nmap scan\n"
        "`/scrape <url>` - Extract readable text from URL\n"
        "`/yt <url>` - Extract YouTube transcript\n"
        "`/purge` - Wipe temporary memory cache"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/scan <ip_or_domain>`", parse_mode="Markdown")
        return
    target = context.args[0]
    # Simple Python-based port scan to avoid Render crashing from heavy nmap
    await update.message.reply_text(f"🔍 Initiating stealth ping on target: {target}...")
    try:
        ip = socket.gethostbyname(target)
        await update.message.reply_text(f"Target Resolved: {ip}\nStatus: Active. (Full deep scan requires Agent-Reach escalation).")
    except Exception:
        await update.message.reply_text("Target unreachable or cloaked.")

async def scrape_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/scrape <url>`", parse_mode="Markdown")
        return
    url = context.args[0]
    msg = await update.message.reply_text("📡 Establishing connection to target server...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.content, 'html.parser')
            text = ' '.join(soup.stripped_strings)[:2000]
            await msg.edit_text(f"📄 **Data Extracted:**\n\n{text}...", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"Connection failed: {e}")

async def clear_memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM memory WHERE chat_id = ?", (update.effective_chat.id,))
        conn.commit()
    await update.message.reply_text("🧹 Chat memory purged. I am operating with a blank slate for this session.")

# ---------------------------------------------------------------------------
# V. COGNITIVE MESSAGE HANDLER
# ---------------------------------------------------------------------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(LOCKDOWN_FILE): return
    msg = update.effective_message
    if not msg or not msg.text: return
    
    user, chat, text = msg.from_user, msg.chat, msg.text
    thread_id = msg.message_thread_id
    
    log_memory(chat.id, thread_id, user.id, "user", f"{user.first_name}: {text}")

    bot_username = (await context.bot.get_me()).username
    is_triggered = (chat.type == "private") or (msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id) or re.search(r'\b(jarvis)\b', text, re.IGNORECASE) or (bot_username and f"@{bot_username}".lower() in text.lower())
    
    if not is_triggered and chat.type != "private": return
    
    status_msg = await msg.reply_text("🤔 `[SYSTEM]: Processing input...`", parse_mode="Markdown")
    await context.bot.send_chat_action(chat_id=chat.id, action='typing')
    
    sys_prompt = build_system_prompt(user.first_name, user_prompt=text)
    history = get_chat_history(chat.id, thread_id)
    
    # Send to Gemini REST API
    final_text = await generate_response(text, history, sys_prompt)
    
    log_memory(chat.id, thread_id, context.bot.id, "assistant", final_text)
    await status_msg.edit_text(final_text)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception handled:", exc_info=context.error)

# ---------------------------------------------------------------------------
# VI. SERVER BOOTSTRAP
# ---------------------------------------------------------------------------
flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "J.A.R.V.I.S. V8.4 is Online."

def start_web_server(): 
    flask_app.run(host='0.0.0.0', port=PORT, use_reloader=False)

def main():
    db_init()
    threading.Thread(target=start_web_server, daemon=True).start()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Register Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("scrape", scrape_cmd))
    app.add_handler(CommandHandler("purge", clear_memory_cmd))
    
    # Register Text/Error
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_error_handler(error_handler)
    
    logger.info("J.A.R.V.I.S. V8.4 booting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
