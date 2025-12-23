import os
import json
import logging
import urllib.parse
import asyncio
import requests
import io
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# Telegram Imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# --- CONFIG ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", 7349230382))

# Global Application Instance for the Web Server to access
app = None

logging.basicConfig(level=logging.INFO)

# --- WEB SERVER / API ENDPOINT ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS so the browser can talk to the bot server."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        # 1. Standard Health Check
        if self.path == "/":
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"Krok Bot API Active")
            return

        # 2. GET File Trigger
        if self.path.startswith("/send"):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            
            uid = params.get('user_id', [None])[0]
            file_url = params.get('url', [None])[0]
            file_name = params.get('name', [None])[0]

            # Security check
            if uid and file_url and int(uid) == ALLOWED_USER_ID:
                # We use threadsafe to call the async bot method from the synchronous server thread
                asyncio.run_coroutine_threadsafe(
                    self.download_and_send(int(uid), file_url, file_name),
                    app.loop
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
        """Downloads the file from the provided URL and sends it to Telegram."""
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                # Wrap the content in an in-memory file object
                pdf_file = io.BytesIO(r.content)
                # Ensure the filename ends in .pdf
                display_name = name if name.lower().endswith(".pdf") else f"{name}.pdf"
                pdf_file.name = display_name
                
                await app.bot.send_document(
                    chat_id=chat_id, 
                    document=pdf_file, 
                    caption=f"📄 {display_name}"
                )
        except Exception as e:
            logging.error(f"Failed to forward file: {e}")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# --- BOT HANDLERS ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Access Denied.")
        return
    await update.message.reply_text("👋 Бот активний. Використовуй сайт для отримання файлів.")

if __name__ == '__main__':
    # Start the Web Server in a separate thread
    Thread(target=run_server, daemon=True).start()

    # Setup the Telegram Bot
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start_cmd))

    print("🚀 Bot and API Server started...")
    app.run_polling()
