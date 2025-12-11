import os
import json
import logging
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# --- CONFIG ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", 0))

MERGED_PDF_DIR = os.path.join("Merged", "PDF")
CONFIG_FILE = "config.json"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- FAKE WEB SERVER FOR RENDER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Krok Bot is Alive and Running!")

def start_fake_server():
    # Render assigns a port automatically via environment variable
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌍 Fake web server listening on port {port}", flush=True)
    server.serve_forever()

# --- BOT LOGIC ---
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
        filename = data.replace('pdf_', '')
        await send_pdf(query, filename)

async def send_passwords(query):
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f: config = json.load(f)
            passwords = config.get('passwords', {})
        else:
            passwords = {}

        if not passwords:
            await query.edit_message_text("No passwords found.")
            return

        msg = "🔐 **Passwords:**\n\n"
        for fname, pw in passwords.items():
            msg += f"📄 `{fname}`\n🔑 `{pw}`\n\n"
        
        if len(msg) > 4000: msg = msg[:4000] + "\n...(truncated)"
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="start")]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        await query.edit_message_text(f"Error: {e}")

async def list_pdfs(query):
    if not os.path.exists(MERGED_PDF_DIR):
        await query.edit_message_text("❌ Merged PDF folder missing.")
        return

    files = sorted([f for f in os.listdir(MERGED_PDF_DIR) if f.endswith(".pdf")])
    if not files:
        await query.edit_message_text("❌ No PDFs found.")
        return

    keyboard = []
    for f in files:
        # Telegram has a limit on callback data size (64 bytes). 
        # If filename is too long, we might need a workaround, but usually fine.
        keyboard.append([InlineKeyboardButton(f[:30], callback_data=f"pdf_{f}")])

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="start")])
    await query.edit_message_text("📂 **Select PDF:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def send_pdf(query, filename):
    file_path = os.path.join(MERGED_PDF_DIR, filename)
    if os.path.exists(file_path):
        await query.message.reply_text(f"⏳ Uploading {filename}...")
        try:
            await query.message.reply_document(document=open(file_path, 'rb'))
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {e}")
    else:
        await query.message.reply_text("❌ File not found.")

if __name__ == '__main__':
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set.")
        exit(1)

    # 1. Start Fake Server in Background Thread
    t = Thread(target=start_fake_server, daemon=True)
    t.start()

    # 2. Start Bot
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot started polling...", flush=True)
    application.run_polling()
