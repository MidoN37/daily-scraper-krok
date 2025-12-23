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

# Force UTF-8 for systems that default to ASCII (Fixes the weird symbols)
sys.stdout.reconfigure(encoding='utf-8')

# --- CONFIG ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", 7349230382))

# Global variables for cross-thread communication
app = None
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
                # Use the captured loop to schedule the async task
                if loop:
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
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                pdf_file = io.BytesIO(r.content)
                display_name = name if name.lower().endswith(".pdf") else f"{name}.pdf"
                pdf_file.name = display_name
                await app.bot.send_document(
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

async def main():
    global app, loop
    loop = asyncio.get_running_loop()
    
    # Start Web Server thread
    Thread(target=run_server, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start_cmd))

    async with app:
        await app.initialize()
        await app.start_polling()
        # Keep the main loop running
        while True:
            await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
