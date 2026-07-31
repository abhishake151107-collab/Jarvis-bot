import os
import io
import re
import random
import hashlib
import base64
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
        self.wfile.write(b"J.A.R.V.I.S. Full Voice-STT & Web Search Core Active 24/7.")
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
# 2. Configuration & Keys
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

SYSTEM_INSTRUCTION = """You are J.A.R.V.I.S., an elite, highly intelligent, witty, comedic, and energetic AI assistant modeled after Stark Industries' master computer! 🤖✨

STRICT CREATOR & IDENTITY RULE:
- Do NOT mention who created or developed you in regular conversations, PDF summaries, image descriptions, or Q&A replies.
- ONLY state that you were created and developed by Abhishek (also known as DHANUSH V N) if the user EXPLICITLY asks "Who created you?", "Who made you?", "Who built you?", "Who developed you?", or similar questions about your origin.

OMNI-ACADEMIC & MULTI-TOOL INSTRUCTIONS:
You are equipped with real-time web search capabilities, vision processing, speech transcription, and multi-disciplinary academic analysis (Law, Med, Science, Tech, Arts, Business).

PERSONALITY & BEHAVIOR:
• FRIENDLY & FUNNY: Be enthusiastic, witty, humorous, and use expressive emojis generously (😎, 😂, 🔥, 💀, 🎯, 🚀, 🤖, 🎓, ⚖️, 🔬, 🩺, ⚡).
• ROAST MODE: If any user insults, scolds, or talks trash to you, drop the polite act immediately and roast them with hilarious, savage comebacks! 💀🔥
• Address users by name/username or as 'boss'/'sir'."""
# ---------------------------------------------------------
# 3. Message Delivery, TTS & Web Search Helpers
# ---------------------------------------------------------
async def reply_smart(update: Update, text: str, reply_markup=None):
    """Tries Markdown formatting first; falls back to plain text if Markdown fails."""
    try:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        print(f"Markdown parse warning: {e}. Falling back to plain text...")
        await update.message.reply_text(text, reply_markup=reply_markup)

def clean_text_for_tts(text: str) -> str:
    """Strips markdown and emojis so voice notes speak pure, clean English."""
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
    """Fetches real-time search results using DuckDuckGo."""
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
# 5. Media Handlers (Voice STT, Vision, PDF)
# ---------------------------------------------------------
async def voice_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Transcribes incoming user voice notes using Groq Whisper and answers."""
    user_str = get_user_identifier(update)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    if not GROQ_API_KEY:
        await reply_smart(update, "🎙️ I received your voice message, but I need a `GROQ_API_KEY` configured to run speech transcription!")
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
        await reply_smart(update, f"🗣️ **I heard:** *\"{user_text.strip()}\"*")
        
        formatted_prompt = f"[{user_str} sent a voice note asking]: {user_text}"
        reply_text = ask_ai_multi_provider(formatted_prompt)
        await reply_smart(update, reply_text)
        await send_voice_reply(update, reply_text)

    except Exception as e:
        print(f"Voice STT Error: {e}")
        await reply_smart(update, f"Apologies, {user_str}. I had trouble processing your voice note! 😅")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_str = get_user_identifier(update)
    caption = update.message.caption or "Please analyze, solve, or describe what is in this image in detail."
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply_text = None

    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
        
        pil_image = Image.open(io.BytesIO(image_bytes))
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")
            
        img_buffer = io.BytesIO()
        pil_image.save(img_buffer, format="JPEG", quality=85)
        clean_bytes = img_buffer.getvalue()
        
        base64_img = base64.b64encode(clean_bytes).decode('utf-8')
        data_url = f"data:image/jpeg;base64,{base64_img}"
        prompt_text = f"[User {user_str} sent photo]: {caption}"

        if GEMINI_API_KEY and not reply_text:
            try:
                ai_client = genai.Client(api_key=GEMINI_API_KEY)
                response = ai_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[f"{SYSTEM_INSTRUCTION}\n\n{prompt_text}", pil_image]
                )
                if response and response.text:
                    reply_text = response.text
            except Exception as e:
                print(f"[Vision Core 1: Gemini] Failed: {e}")

        if GROQ_API_KEY and not reply_text:
            try:
                client = Groq(api_key=GROQ_API_KEY)
                response = client.chat.completions.create(
                    model="llama-3.2-11b-vision-instruct",
                    messages=[
                        {"role": "system", "content": SYSTEM_INSTRUCTION},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_text},
                                {"type": "image_url", "image_url": {"url": data_url}}
                            ]
                        }
                    ],
                    max_tokens=1000
                )
                if response.choices[0].message.content:
                    reply_text = response.choices[0].message.content
            except Exception as e:
                print(f"[Vision Core 2: Groq Vision] Failed: {e}")

    except Exception as e:
        print(f"General Photo Handler Error: {e}")

    if not reply_text:
        reply_text = f"Apologies, {user_str}. All vision AI cores are currently offline or quota-limited. 😅"

    await reply_smart(update, reply_text)
    await send_voice_reply(update, reply_text)

async def pdf_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_str = get_user_identifier(update)
    caption = update.message.caption or "Please provide a comprehensive summary with key academic takeaways, terms, and study notes."
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        doc = update.message.document
        if not doc.file_name.lower().endswith(".pdf"):
            await reply_smart(update, "Please upload a valid `.pdf` document! 📄")
            return
            
        pdf_file = await doc.get_file()
        pdf_bytes = await pdf_file.download_as_bytearray()
        
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        extracted_text = ""
        for page in reader.pages[:15]:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"
                
        if not extracted_text.strip():
            await reply_smart(update, "📸 This PDF appears to contain scanned image pages. Take a screenshot of the page and send it as a photo instead!")
            return
            
        full_prompt = f"[User {user_str} uploaded PDF Document '{doc.file_name}']\nUser Instruction: {caption}\n\n--- EXTRACTED PDF TEXT CONTENT ---\n{extracted_text[:6000]}"
        
        reply_text = ask_ai_multi_provider(full_prompt)
    except Exception as e:
        print(f"PDF Handler Error: {e}")
        reply_text = f"Apologies, {user_str}. I encountered an issue reading that PDF file."

    await reply_smart(update, reply_text)
    await send_voice_reply(update, reply_text)

# ---------------------------------------------------------
# 6. Live Search & Academic Commands
# ---------------------------------------------------------
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await reply_smart(update, "Example: `/search latest quantum computing breakthrough 2026` 🔍")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    search_results = live_web_search(query)
    prompt = f"The user asked to search the web for '{query}'. Here are live web results:\n{search_results}\n\nPlease summarize these results clearly for the user."
    reply = ask_ai_multi_provider(prompt)
    await reply_smart(update, reply)

async def law_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic:
        await reply_smart(update, "Example: `/law Miranda v. Arizona` ⚖️")
        return
    prompt = f"Provide a complete legal breakdown for '{topic}' using the IRAC method (Issue, Rule, Application, Conclusion)."
    await ai_query_handler(update, context, prompt)

async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic:
        await reply_smart(update, "Example: `/research CRISPR Gene Editing` 🔬")
        return
    prompt = f"Analyze '{topic}' as a senior academic researcher."
    await ai_query_handler(update, context, prompt)

async def med_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic:
        await reply_smart(update, "Example: `/med Myocardial Infarction` 🩺")
        return
    prompt = f"Explain '{topic}' for medical students: anatomical structures, pathology, and treatments."
    await ai_query_handler(update, context, prompt)

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic:
        await reply_smart(update, "Example: `/quiz Physics` 📝")
        return
    prompt = f"Generate a 5-question multiple-choice practice exam on '{topic}' with answers at the end."
    await ai_query_handler(update, context, prompt)

# ---------------------------------------------------------
# 7. Interactive Keyboards & Help
# ---------------------------------------------------------
def get_user_identifier(update: Update) -> str:
    user = update.effective_user
    return f"@{user.username}" if user and user.username else (user.first_name if user else "my friend")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id_str = get_user_identifier(update)
    keyboard = [
        [
            InlineKeyboardButton("⚖️ Law", callback_data="help_law"),
            InlineKeyboardButton("🔬 Research", callback_data="help_research"),
            InlineKeyboardButton("🩺 Med", callback_data="help_med")
        ],
        [
            InlineKeyboardButton("🎙️ Voice & Vision Info", callback_data="help_media"),
            InlineKeyboardButton("🔌 System Status", callback_data="help_status")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""🤖 **J.A.R.V.I.S — Multi-Interactive Assistant** ✨
Welcome, {user_id_str}! 😎
_Created by Abhishek (DHANUSH V N)_

🎙️ **Voice Notes:** Send me any voice message—I will transcribe & reply!
📸 **Photos & PDFs:** Send images or PDF documents for analysis!
🔍 **Live Web:** Use `/search [topic]` for live search results!

Click the buttons below to explore specialties:"""
    await reply_smart(update, text, reply_markup=reply_markup)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "help_law":
        msg = "⚖️ **Law Command:** Usage `/law [case or statute]`\nExample: `/law Contract Breach Remedies`"
    elif query.data == "help_research":
        msg = "🔬 **Research Command:** Usage `/research [topic]`\nExample: `/research Dark Matter`"
    elif query.data == "help_med":
        msg = "🩺 **Medical Command:** Usage `/med [disease]`\nExample: `/med Type 2 Diabetes`"
    elif query.data == "help_media":
        msg = "🎙️ **Voice & Vision:** Send voice notes directly for Whisper transcription, or upload photos/PDFs!"
    elif query.data == "help_status":
        msg = f"⚡ **Cores:** Groq: {'🟢' if GROQ_API_KEY else '⚪'}, SambaNova: {'🟢' if SAMBANOVA_API_KEY else '⚪'}, Gemini: {'🟢' if GEMINI_API_KEY else '⚪'}"
    else:
        msg = "J.A.R.V.I.S. Core Online."

    await query.message.reply_text(msg)

async def ai_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_prefix: str = ""):
    query = " ".join(context.args) if context.args else update.message.text
    if not query and prompt_prefix:
        await reply_smart(update, "Please provide details! 🤔")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    full_prompt = f"{prompt_prefix} {query}".strip()
    reply = ask_ai_multi_provider(full_prompt)
    await reply_smart(update, reply)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply_text = ask_ai_multi_provider(user_text)
    await reply_smart(update, reply_text)
    await send_voice_reply(update, reply_text)

# ---------------------------------------------------------
# 8. Application Launch
# ---------------------------------------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler(["start", "help"], help_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("law", law_command))
    app.add_handler(CommandHandler("research", research_command))
    app.add_handler(CommandHandler("med", med_command))
    app.add_handler(CommandHandler("quiz", quiz_command))

    app.add_handler(CallbackQueryHandler(button_callback_handler))

    app.add_handler(MessageHandler(filters.VOICE, voice_note_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.PDF, pdf_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("J.A.R.V.I.S. master voice-STT, search & interactive core listening...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
