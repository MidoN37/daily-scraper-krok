import os
import json
import logging
import urllib.parse
import asyncio
import requests
import io
import sys
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# Force UTF-8 for Render logs
sys.stdout.reconfigure(encoding='utf-8')

# --- CONFIG ---
MAIN_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PW_TOKEN = os.environ.get("PASSWORD_BOT_TOKEN")
ALLOWED_USER_ID = 7349230382
CONFIG_FILE = "config.json"

logging.basicConfig(level=logging.INFO)

# Global variables for the Main Bot API
main_app = None
loop = None

def load_config():
    if not os.path.exists(CONFIG_FILE): return {"files": [], "passwords": {}}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)

# --- WEB SERVER (Handles Render Health Check & GET Button) ---
class APIHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        """Fixes the 501 error and tells Render the app is healthy."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

    def do_GET(self):
        # Handle the GET button from the website
        if self.path.startswith("/send"):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            uid = params.get('user_id', [None])[0]
            url = params.get('url', [None])[0]
            name = params.get('name', [None])[0]

            if uid and url and int(uid) == ALLOWED_USER_ID:
                if loop and main_app:
                    asyncio.run_coroutine_threadsafe(self.forward_pdf(int(uid), url, name), loop)
                    self.send_response(200)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b"OK")
                    return
        
        # Standard root response
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(b"Bots are Active")

    async def forward_pdf(self, chat_id, url, name):
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                f = io.BytesIO(r.content)
                f.name = name if name.lower().endswith(".pdf") else f"{name}.pdf"
                await main_app.bot.send_document(chat_id=chat_id, document=f, caption=f"📄 {f.name}")
        except Exception as e: logging.error(f"Forward failed: {e}")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), APIHandler)
    server.serve_forever()

# --- BOT 1: MAIN (PDF) HANDLERS ---
async def main_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.effective_user.id == ALLOWED_USER_ID:
        await u.message.reply_text("✅ PDF Bot Active. Use the website to GET files.")

# --- BOT 2: PASSWORD HANDLERS ---
async def pw_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.effective_user.id != ALLOWED_USER_ID: return
    data = load_config()
    cats = set()
    for f in data.get("files", []):
        if f.startswith("Krok"): cats.add("🇬🇧 Krok English")
        elif f.startswith("Крок"): cats.add("🇺🇦 Крок Українська")
        elif f.startswith("ЄДКІ"): cats.add("📘 ЄДКІ")
        elif f.startswith("АМПС"): cats.add("📙 АМПС")
    kb = [[InlineKeyboardButton(cat, callback_data=f"cat|{cat}")] for cat in sorted(list(cats))]
    await u.message.reply_text("🔑 <b>Krok Passwords</b>\nSelect Category:", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def pw_callback(u: Update, c: ContextTypes.DEFAULT_TYPE):
    query = u.callback_query; await query.answer()
    d = query.data.split("|")
    if d[0] == "cat":
        cat = d[1]
        if "Krok" in cat or "Крок" in cat:
            kb = [[InlineKeyboardButton(f"Level {l}", callback_data=f"list|{cat}|{l}")] for l in ["1","2","3"]]
            kb.append([InlineKeyboardButton("🔙 Back", callback_data="start_over")])
            await query.edit_message_text(f"📂 {cat}\nLevel:", reply_markup=InlineKeyboardMarkup(kb))
        else: await show_pws(query, cat)
    elif d[0] == "list": await show_pws(query, d[1], d[2])
    elif d[0] == "start_over":
        data = load_config()
        cats = set()
        for f in data.get("files", []):
            if f.startswith("Krok"): cats.add("🇬🇧 Krok English")
            elif f.startswith("Крок"): cats.add("🇺🇦 Крок Українська")
            elif f.startswith("ЄДКІ"): cats.add("📘 ЄДКІ")
            elif f.startswith("АМПС"): cats.add("📙 АМПС")
        kb = [[InlineKeyboardButton(cat, callback_data=f"cat|{cat}")] for cat in sorted(list(cats))]
        await query.edit_message_text("Select Category:", reply_markup=InlineKeyboardMarkup(kb))

async def show_pws(query, cat, lvl=None):
    data = load_config()
    pws = data.get("passwords", {})
    pre = "Krok" if "English" in cat else ("Крок" if "Українська" in cat else ("ЄДКІ" if "ЄДКІ" in cat else "АМПС"))
    filtered = [f for f in data.get("files", []) if f.startswith(pre) and (not lvl or f" {lvl} " in f)]
    msg = f"🔑 <b>{cat} {lvl or ''}</b>\n<i>Tap password to copy:</i>\n\n"
    for f in sorted(filtered): msg += f"📄 {f.replace('.txt','')}\n└ <code>{pws.get(f, '12345')}</code>\n\n"
    kb = [[InlineKeyboardButton("🔙 Back", callback_data="start_over")]]
    await query.edit_message_text(msg[:4000], reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

# --- EXECUTION ---
async def start_all():
    global main_app, loop
    loop = asyncio.get_running_loop()
    Thread(target=run_server, daemon=True).start()

    # Bot 1 (Main/PDF)
    main_app = ApplicationBuilder().token(MAIN_TOKEN).build()
    main_app.add_handler(CommandHandler("start", main_start))

    # Bot 2 (Passwords)
    pw_app = ApplicationBuilder().token(PW_TOKEN).build()
    pw_app.add_handler(CommandHandler("start", pw_start))
    pw_app.add_handler(CallbackQueryHandler(pw_callback))

    async with main_app, pw_app:
        await main_app.initialize(); await main_app.updater.start_polling()
        await pw_app.initialize(); await pw_app.updater.start_polling()
        print("🚀 Both bots are running...")
        while True: await asyncio.sleep(3600)

if __name__ == '__main__':
    try: asyncio.run(start_all())
    except KeyboardInterrupt: pass
