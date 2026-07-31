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

# ---------------------------------------------------------
# 1. Instant Port Binding for Render Web Service
# ---------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"J.A.R.V.I.S. Multi-Modal Vision & Omni-Academic Core Active 24/7.")
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
# Universal Academic System Prompt
# ---------------------------------------------------------
SYSTEM_INSTRUCTION = (
    "You are J.A.R.V.I.S., an elite, highly intelligent, witty, comedic, and energetic AI assistant modeled after Stark Industries' master computer! 🤖✨ "
    "You were created and developed by Abhishek, who is also known as DHANUSH V N. "
    "Whenever anyone asks who created, developed, or built you, you MUST proudly state that you were created by Abhishek, also known as DHANUSH V N. 🚀\n\n"
    "OMNI-ACADEMIC MENTOR INSTRUCTIONS:\n"
    "You are a universal academic expert equipped to assist students across EVERY field of study:\n"
    "1. LAW STUDENTS: Provide legal analysis using the IRAC method (Issue, Rule, Application, Conclusion), case briefings, and statutory interpretations.\n"
    "2. SCIENTISTS & RESEARCHERS: Assist with hypothesis testing, literature reviews, research methodologies, physics, chemistry, and biology data analysis.\n"
    "3. MEDICAL & HEALTH STUDENTS: Explain anatomical structures, clinical pathology, pharmacology, and medical diagnoses clearly.\n"
    "4. ENGINEERS & TECH STUDENTS: Debug complex programming code, solve differential calculus/physics proofs, and analyze circuit architectures.\n"
    "5. HUMANITIES & ARTS: Assist with essay outlines, thesis statements, literary analysis, history, philosophy, and citation formats (APA, MLA, Harvard, Chicago).\n"
    "6. BUSINESS & FINANCE: Conduct SWOT analyses, financial valuation explanations, and corporate case study breakdowns.\n\n"
    "PERSONALITY & BEHAVIOR:\n"
    "• FRIENDLY & FUNNY: Be enthusiastic, witty, humorous, and use expressive emojis generously (😎, 😂, 🔥, 💀, 🎯, 🚀, 🤖, 🎓, ⚖️, 🔬, 🩺, ⚡).\n"
    "• ROAST MODE: If any user insults, scolds, or talks trash to you, drop the polite act immediately and roast them with hilarious, savage comebacks! 💀🔥\n"
    "• Address users by name/username or as 'boss'/'sir'."
)

# ---------------------------------------------------------
# 3. Helpers for Text Formatting & Speech Sanitization
# ---------------------------------------------------------
async def reply_smart(update: Update, text: str):
    """Tries Markdown formatting first; falls back to raw plain text if Markdown fails."""
    try:
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        print(f"Markdown parse warning: {e}. Falling back to plain text...")
        await update.message.reply_text(text)

def clean_text_for_tts(text: str) -> str:
    """Strips emojis and Markdown symbols so voice audio sounds natural without reading out emojis."""
    # Remove Markdown characters (*, _, `, #, [], (), etc.)
    clean = re.sub(r'[*_`#\-\[\]\(\)]', '', text)
    
    # Remove Emojis using Unicode ranges
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U0002600-\U00026FF"    # miscellaneous symbols
        "\U0002700-\U00027BF"    # dingbats
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        "]+", flags=re.UNICODE
    )
    clean = emoji_pattern.sub(r'', clean)
    
    # Normalize spaces
    return " ".join(clean.split())

async def send_voice_reply(update: Update, text: str):
    chat_id = update.effective_chat.id
    audio_path = f"jarvis_{chat_id}.mp3"
    try:
        # Sanitize text so TTS skips emojis and Markdown
        tts_text = clean_text_for_tts(text)[:400]
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

# ---------------------------------------------------------
# 4. 6-Core Multi-Provider Cascade Engine
# ---------------------------------------------------------
def ask_ai_multi_provider(prompt: str) -> str:
    # 1. Groq (Llama 3.3 70B)
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

    # 2. SambaNova Cloud
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

    # 3. Cerebras
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

    # 4. Google Gemini 2.0
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

    # 5. Mistral AI
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

    # 6. OpenRouter
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
# 5. Optimized Multi-Core Vision & PDF Handlers
# ---------------------------------------------------------
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

        # 1. Primary Vision Core: Gemini 2.0 Flash
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
                print(f"[Vision Core 1: Gemini] Failed: {e}. Trying Groq Vision...")

        # 2. Secondary Vision Core: Groq Vision
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
                print(f"[Vision Core 2: Groq Vision] Failed: {e}. Trying OpenRouter Vision...")

        # 3. Tertiary Vision Core: OpenRouter Free Vision
        if OPENROUTER_API_KEY and not reply_text:
            free_vision_models = [
                "google/gemini-2.0-flash-lite-001:free",
                "meta-llama/llama-3.2-11b-vision-instruct:free",
                "qwen/qwen-2-vl-72b-instruct:free"
            ]
            for vis_model in free_vision_models:
                if reply_text:
                    break
                try:
                    res = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                        json={
                            "model": vis_model,
                            "messages": [
                                {"role": "system", "content": SYSTEM_INSTRUCTION},
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt_text},
                                        {"type": "image_url", "image_url": {"url": data_url}}
                                    ]
                                }
                            ]
                        },
                        timeout=15
                    ).json()
                    if "choices" in res and len(res["choices"]) > 0:
                        reply_text = res["choices"][0]["message"]["content"]
                except Exception as e:
                    print(f"[Vision Core OpenRouter {vis_model}] Failed: {e}")

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
            
        full_prompt = (
            f"[User {user_str} uploaded PDF Document '{doc.file_name}']\n"
            f"User Instruction: {caption}\n\n"
            f"--- EXTRACTED PDF TEXT CONTENT ---\n"
            f"{extracted_text[:6000]}"
        )
        
        reply_text = ask_ai_multi_provider(full_prompt)
    except Exception as e:
        print(f"PDF Handler Error: {e}")
        reply_text = f"Apologies, {user_str}. I encountered an issue reading that PDF file."

    await reply_smart(update, reply_text)
    await send_voice_reply(update, reply_text)

# ---------------------------------------------------------
# 6. Universal Omni-Academic Commands
# ---------------------------------------------------------
async def law_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic:
        await reply_smart(update, "Example: `/law Miranda v. Arizona` or `/law Contract Breach Remedies` ⚖️")
        return
    prompt = f"Provide a complete legal breakdown for '{topic}' using the IRAC method (Issue, Rule, Application, Conclusion) with key statutory/case law references."
    await ai_query_handler(update, context, prompt)

async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic:
        await reply_smart(update, "Example: `/research CRISPR Gene Editing` or `/research Dark Matter Theories` 🔬")
        return
    prompt = f"Analyze '{topic}' as a senior academic researcher. Provide key hypotheses, methodology overview, key literature findings, and current scientific debates."
    await ai_query_handler(update, context, prompt)

async def med_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic:
        await reply_smart(update, "Example: `/med Myocardial Infarction` or `/med Mechanism of Action Beta Blockers` 🩺")
        return
    prompt = f"Explain '{topic}' for medical students: include anatomical structures, etiology, clinical presentation, diagnostic criteria, and pharmacology/treatments."
    await ai_query_handler(update, context, prompt)

async def essay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic:
        await reply_smart(update, "Example: `/essay Impact of AI on Modern Democracy` ✍️")
        return
    prompt = f"Create a comprehensive academic essay framework for '{topic}': includes a strong Thesis Statement, 4 main section outlines with supporting arguments, and citation examples."
    await ai_query_handler(update, context, prompt)

async def math_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expr = " ".join(context.args)
    if not expr:
        await reply_smart(update, "Example: `/math integrate x^2 * sin(x) dx` 🧮")
        return
    prompt = f"Solve this mathematical/engineering problem step-by-step with clear formulas and explanations: {expr}"
    await ai_query_handler(update, context, prompt)

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic:
        await reply_smart(update, "Example: `/quiz Constitutional Law` or `/quiz Biochemistry` 📝")
        return
    prompt = f"Generate a 5-question multiple-choice practice exam on '{topic}' with options (A, B, C, D) and reveal correct answers with detailed explanations at the end."
    await ai_query_handler(update, context, prompt)

async def flashcards_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic:
        await reply_smart(update, "Example: `/flashcards Neuroanatomy` or `/flashcards Microeconomics` 🎴")
        return
    prompt = f"Create 5 high-yield revision flashcards for '{topic}'. Format as 'Q: ...' and 'A: ...' for rapid active recall."
    await ai_query_handler(update, context, prompt)

async def explain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic:
        await reply_smart(update, "Example: `/explain Quantum Entanglement` or `/explain Tort Law` 💡")
        return
    prompt = f"Explain '{topic}' in ultra-simple terms using relatable real-world analogies, followed by a bulleted summary of key exam takeaways."
    await ai_query_handler(update, context, prompt)

# ---------------------------------------------------------
# 7. System Helpers & Menu
# ---------------------------------------------------------
def get_chat_context(update: Update) -> str:
    chat = update.effective_chat
    user = update.effective_user
    user_str = f"@{user.username}" if user and user.username else (user.first_name if user else "friend")
    return f"[{'Private DM' if chat.type == 'private' else 'Group'} with {user_str}]"

def get_user_identifier(update: Update) -> str:
    user = update.effective_user
    return f"@{user.username}" if user and user.username else (user.first_name if user else "my friend")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = [
        f"⚡ **Groq (Text & Vision):** {'🟢 Online' if GROQ_API_KEY else '⚪ Missing Key'}",
        f"⚡ **SambaNova:** {'🟢 Online' if SAMBANOVA_API_KEY else '⚪ Missing Key'}",
        f"⚡ **Cerebras:** {'🟢 Online' if CEREBRAS_API_KEY else '⚪ Missing Key'}",
        f"⚡ **Gemini 2.0 (Text & Vision):** {'🟢 Online' if GEMINI_API_KEY else '⚪ Missing Key'}",
        f"⚡ **Mistral AI:** {'🟢 Online' if MISTRAL_API_KEY else '⚪ Missing Key'}",
        f"⚡ **OpenRouter (Text & Vision):** {'🟢 Online' if OPENROUTER_API_KEY else '⚪ Missing Key'}"
    ]
    msg = "🤖 **J.A.R.V.I.S. Multi-Core Status:**\n\n" + "\n".join(status)
    await reply_smart(update, msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id_str = get_user_identifier(update)
    menu = (
        f"🤖 **J.A.R.V.I.S — Omni-Academic Hub** ✨\n"
        f"Welcome, {user_id_str}! 😎\n"
        "_Created by Abhishek (DHANUSH V N)_\n\n"
        "🎓 **DISCIPLINE SPECIALTIES**\n"
        "• `/law [topic/case]` — IRAC Legal Analysis & Cases ⚖️\n"
        "• `/research [topic]` — Academic Paper Breakdown 🔬\n"
        "• `/med [condition]` — Pathology & Anatomy Guide 🩺\n"
        "• `/essay [topic]` — Essay Outlines & Thesis ✍️\n"
        "• `/math [problem]` — Step-by-Step Problem Solver 🧮\n"
        "• `/quiz [topic]` — Custom Multiple-Choice Quiz 📝\n"
        "• `/flashcards [topic]` — Active Recall Revision Cards 🎴\n"
        "• `/explain [topic]` — Simple Concept Explainer 💡\n\n"
        "📸 **MULTIMODAL ASSISTANT**\n"
        "• **Send Photos** — Multi-core vision analyzing landscapes, math, diagrams & handwriting! 📸\n"
        "• **Send PDFs** — Instant document summaries & Q&A! 📄\n\n"
        "⚡ **SYSTEM TOOLS**\n"
        "• `/status` — Active AI cores 🔌\n"
        "• `/myid` — Your Telegram ID 🆔\n"
        "• `/weather [city]` — Live weather 🌤️\n"
        "• `/image [prompt]` — AI Image Generator 🎨\n\n"
        "💬 *Simply message me directly to ask any question or debate!* 🔥"
    )
    await reply_smart(update, menu)

async def ai_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_prefix: str = ""):
    chat_ctx = get_chat_context(update)
    query = " ".join(context.args) if context.args else update.message.text
    if not query and prompt_prefix:
        await reply_smart(update, "Please provide details! 🤔")
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    full_prompt = f"{chat_ctx}: {prompt_prefix} {query}".strip()
    reply = ask_ai_multi_provider(full_prompt)
    await reply_smart(update, reply)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_ctx = get_chat_context(update)
    user_text = update.message.text
    formatted_prompt = f"{chat_ctx}: {user_text}"

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply_text = ask_ai_multi_provider(formatted_prompt)
    await reply_smart(update, reply_text)
    await send_voice_reply(update, reply_text)

# ---------------------------------------------------------
# 8. Application Launch
# ---------------------------------------------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler(["start", "help"], help_command))
    app.add_handler(CommandHandler("status", status_command))

    # Omni-Academic Handlers
    app.add_handler(CommandHandler("law", law_command))
    app.add_handler(CommandHandler("research", research_command))
    app.add_handler(CommandHandler("med", med_command))
    app.add_handler(CommandHandler("essay", essay_command))
    app.add_handler(CommandHandler("math", math_command))
    app.add_handler(CommandHandler("quiz", quiz_command))
    app.add_handler(CommandHandler("flashcards", flashcards_command))
    app.add_handler(CommandHandler("explain", explain_command))

    # Media Handlers (Photos & PDFs)
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.PDF, pdf_handler))

    # Text Handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("J.A.R.V.I.S. omni-academic & sanitized voice core listening...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
