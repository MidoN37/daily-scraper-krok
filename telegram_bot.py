import os
import logging
import urllib.parse
import asyncio
import requests
import io
import sys
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# Telegram Imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# Force UTF-8 encoding for Render logs and strings
sys.stdout.reconfigure(encoding='utf-8')

# --- CONFIG ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", 7349230382))
MERGED_PDF_DIR = os.path.join("Merged", "PDF")

# Global variables for cross-thread communication
application = None
loop = None

logging.basicConfig(level=logging.INFO)

# --- WEB SERVER / API ENDPOINT ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"Krok Bot API Active")
            return

        if self.path.startswith("/send"):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            uid = params.get('user_id', [None])[0]
            file_url = params.get('url', [None])[0]
            file_name = params.get('name', [None])[0]

            if uid and file_url and int(uid) == ALLOWED_USER_ID:
                if loop and application:
                    asyncio.run_coroutine_threadsafe(
                        self.download_and_send(int(uid), file_url, file_name),
                        loop
                    )
                    self.send_response(200)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b"OK")
                    return

            self.send_response(400)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"Error")

    async def download_and_send(self, chat_id, url, name):
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                pdf_file = io.BytesIO(r.content)
                display_name = name if name.lower().endswith(".pdf") else f"{name}.pdf"
                pdf_file.name = display_name
                await application.bot.send_document(
                    chat_id=chat_id, 
                    document=pdf_file, 
                    caption=f"📄 {display_name}"
                )
        except Exception as e:
            logging.error(f"Download/Send failed: {e}")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ALLOWED_USER_ID:
        await update.message.reply_text("✅ Бот онлайн. Очікую запити з сайту.")
    else:
        await update.message.reply_text("⛔ Доступ заборонено.")

async def post_init(app):
    global loop
    loop = asyncio.get_running_loop()
    print("📍 Event loop captured.")

if __name__ == '__main__':
    # Start Web Server thread
    Thread(target=run_server, daemon=True).start()

    # Initialize Application
    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler('start', start_cmd))

    print("🚀 Starting Bot Polling...")
    application.run_polling()
