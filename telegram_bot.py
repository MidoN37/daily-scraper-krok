import os
import json
import logging
import urllib.parse
import asyncio
import requests
import io
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# --- CONFIG ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", 7349230382))
CONFIG_FILE = "config.json"

app = None

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
        try:
            # Download file into memory
            r = requests.get(url)
            if r.status_code == 200:
                pdf_file = io.BytesIO(r.content)
                pdf_file.name = name if name.endswith(".pdf") else f"{name}.pdf"
                await app.bot.send_document(chat_id=chat_id, document=pdf_file, caption=f"📄 {pdf_file.name}")
        except Exception as e:
            logging.error(f"Failed to forward file: {e}")

if __name__ == '__main__':
    Thread(target=lambda: HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 10000))), HealthCheckHandler).serve_forever(), daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', lambda u, c: u.message.reply_text("Bot is active for API requests.")))
    app.run_polling()
