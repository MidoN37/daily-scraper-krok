import os
import json
import logging
import time
import math
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# Telegram Imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.error import Conflict

# --- CONFIG ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", 0))

MERGED_PDF_DIR = os.path.join("Merged", "PDF")
CONFIG_FILE = "config.json"

# Global Cache to map short IDs to long filenames
# e.g. {0: "Krok 1 Medicine.pdf", 1: "Krok 2.pdf"}
PDF_CACHE = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- FAKE WEB SERVER FOR RENDER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Krok Bot is Alive!")

def start_fake_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌍 Fake web server listening on port {port}", flush=True)
    server.serve_forever()

# --- HELPERS ---
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def refresh_pdf_cache():
    """Maps index numbers to filenames to fix button size limits"""
    global PDF_CACHE
    PDF_CACHE = {}
    if os.path.exists(MERGED_PDF_DIR):
        files = sorted([f for f in os.listdir(MERGED_PDF_DIR) if f.endswith(".pdf")])
        for idx, filename in enumerate(files):
            PDF_CACHE[idx] = filename

# --- BOT HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Access Denied.")
        return

    text = "🤖 **Krok Admin Bot**\nI'm ready. What do you need?"
    keyboard = [
        [InlineKeyboardButton("🔑 Get Passwords", callback_data='passwords')],
        [InlineKeyboardButton("📂 Get PDF Files", callback_data='list_pdfs')]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'passwords':
        await send_passwords(query)
    elif data == 'list_pdfs':
        await list_pdfs(query)
    elif data == 'start':
        await start(update, context)
    elif data.startswith('pdf_'):
        # Extract the index ID from the button data
        file_id = int(data.split('_')[1])
        await send_pdf(query, file_id)

async def send_passwords(query):
    config = load_config()
    passwords = config.get('passwords', {})

    if not passwords:
        await query.edit_message_text("❌ No passwords found in config.")
        return

    # Build the full message first
    full_message = ""
    for fname, pw in passwords.items():
        # Using plain text format to avoid Markdown parsing errors with special chars
        full_message += f"📄 {fname}\n🔑 {pw}\n\n"

    # Split into chunks of 4000 characters
    chunk_size = 4000
    chunks = [full_message[i:i+chunk_size] for i in range(0, len(full_message), chunk_size)]

    # Send chunks
    for i, chunk in enumerate(chunks):
        if i == 0:
            # Edit the original message for the first chunk
            await query.edit_message_text(f"🔐 **Passwords (Part {i+1}/{len(chunks)}):**\n\n{chunk}", parse_mode=None)
        else:
            # Send new messages for subsequent chunks
            await query.message.reply_text(f"🔐 **(Part {i+1}/{len(chunks)}):**\n\n{chunk}", parse_mode=None)
    
    # Add a back button at the end
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="start")]]
    await query.message.reply_text("Done.", reply_markup=InlineKeyboardMarkup(keyboard))

async def list_pdfs(query):
    refresh_pdf_cache()
    
    if not PDF_CACHE:
        await query.edit_message_text("❌ No PDFs found in Merged/PDF folder.")
        return

    keyboard = []
    # Create buttons using ID (pdf_0, pdf_1) to save space
    for idx, filename in PDF_CACHE.items():
        # Show filename in button label, but pass ID in data
        btn = InlineKeyboardButton(filename, callback_data=f"pdf_{idx}")
        keyboard.append([btn])

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="start")])
    
    await query.edit_message_text("📂 **Select a PDF to download:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def send_pdf(query, file_id):
    if not PDF_CACHE:
        refresh_pdf_cache()

    filename = PDF_CACHE.get(file_id)
    
    if not filename:
        await query.message.reply_text("❌ Error: File mapping lost. Please reload list.")
        return

    file_path = os.path.join(MERGED_PDF_DIR, filename)
    
    if os.path.exists(file_path):
        await query.message.reply_text(f"⏳ Uploading: {filename} ...")
        try:
            with open(file_path, 'rb') as f:
                await query.message.reply_document(document=f, filename=filename)
        except Exception as e:
            await query.message.reply_text(f"❌ Error uploading: {e}")
    else:
        await query.message.reply_text("❌ File not found on server.")

if __name__ == '__main__':
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set.")
        exit(1)

    # 1. Start Fake Server (For Render)
    t = Thread(target=start_fake_server, daemon=True)
    t.start()

    # 2. Build Bot
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is starting...", flush=True)

    # 3. Robust Loop (For Zero-Downtime Deploys)
    while True:
        try:
            application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)
        except Conflict:
            print("⚠️ Conflict detected (Old instance alive). Retrying in 10s...", flush=True)
            time.sleep(10)
        except Exception as e:
            print(f"❌ Critical Bot Error: {e}. Retrying in 10s...", flush=True)
            time.sleep(10)
