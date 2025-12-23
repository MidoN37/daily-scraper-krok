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
MY_ID = 7349230382 
CONFIG_FILE = "config.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

main_app = None
loop = None

def load_config():
    if not os.path.exists(CONFIG_FILE): return {"files": [], "passwords": {}}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {"files": [], "passwords": {}}

# --- WEB SERVER ---
class APIHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200); self.end_headers()
    def do_GET(self):
        if self.path.startswith("/send"):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            uid = params.get('user_id', [None])[0]
            url = params.get('url', [None])[0]
            name = params.get('name', [None])[0]
            if uid and url and int(uid) == MY_ID:
                if loop and main_app:
                    asyncio.run_coroutine_threadsafe(self.forward_pdf(int(uid), url, name), loop)
                    self.send_response(200); self.send_header('Access-Control-Allow-Origin', '*'); self.end_headers()
                    self.wfile.write(b"OK"); return
        self.send_response(200); self.end_headers(); self.wfile.write(b"Bots Active")

    async def forward_pdf(self, chat_id, url, name):
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                f = io.BytesIO(r.content)
                f.name = name if name.lower().endswith(".pdf") else f"{name}.pdf"
                await main_app.bot.send_document(chat_id=chat_id, document=f, caption=f"📄 {f.name}")
        except Exception as e: logger.error(f"Forward failed: {e}")

# --- BOT HANDLERS ---
async def main_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.effective_user.id == MY_ID:
        await u.message.reply_text("✅ PDF Bot Active.")

async def pw_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.effective_user.id != MY_ID: return
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
    if u.effective_user.id != MY_ID: return
    d = query.data.split("|")
    if d[0] == "cat":
        cat = d[1]
        if "Krok" in cat or "Крок" in cat:
            kb = [[InlineKeyboardButton(f"Level {l}", callback_data=f"list|{cat}|{l}")] for l in ["1","2","3"]]
            kb.append([InlineKeyboardButton("🔙 Back", callback_data="start_over")])
            await query.edit_message_text(f"📂 {cat}\nSelect Level:", reply_markup=InlineKeyboardMarkup(kb))
        else: await show_pws(query, cat)
    elif d[0] == "list": await show_pws(query, d[1], d[2])
    elif d[0] == "start_over":
        data = load_config(); cats = set()
        for f in data.get("files", []):
            if f.startswith("Krok"): cats.add("🇬🇧 Krok English")
            elif f.startswith("Крок"): cats.add("🇺🇦 Крок Українська")
            elif f.startswith("ЄДКІ"): cats.add("📘 ЄДКІ")
            elif f.startswith("АМПС"): cats.add("📙 АМПС")
        kb = [[InlineKeyboardButton(cat, callback_data=f"cat|{cat}")] for cat in sorted(list(cats))]
        await query.edit_message_text("Select Category:", reply_markup=InlineKeyboardMarkup(kb))

async def show_pws(query, cat, lvl=None):
    data = load_config(); pws = data.get("passwords", {})
    pre = "Krok" if "English" in cat else ("Крок" if "Українська" in cat else ("ЄДКІ" if "ЄДКІ" in cat else "АМПС"))
    filtered = [f for f in data.get("files", []) if f.startswith(pre) and (not lvl or f" {lvl} " in f)]
    msg = f"🔑 <b>{cat} {lvl or ''}</b>\n\n"
    for f in sorted(filtered): msg += f"📄 {f.replace('.txt','')}\n└ <code>{pws.get(f, '12345')}</code>\n\n"
    await query.edit_message_text(msg[:4000], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start_over")]]), parse_mode=ParseMode.HTML)

# --- STARTUP ---
async def main():
    global main_app, loop
    loop = asyncio.get_running_loop()
    Thread(target=lambda: HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 10000))), APIHandler).serve_forever(), daemon=True).start()

    main_app = ApplicationBuilder().token(MAIN_TOKEN).build()
    main_app.add_handler(CommandHandler("start", main_start))

    pw_app = ApplicationBuilder().token(PW_TOKEN).build()
    pw_app.add_handler(CommandHandler("start", pw_start))
    pw_app.add_handler(CallbackQueryHandler(pw_callback))

    # Initialize both
    await main_app.initialize()
    await pw_app.initialize()

    # Start polling for both - drop_pending_updates clears the Conflict error!
    await main_app.updater.start_polling(drop_pending_updates=True)
    await pw_app.updater.start_polling(drop_pending_updates=True)

    logger.info("🚀 BOTS STARTED - LOGGED IN AS 7349230382")
    while True: await asyncio.sleep(3600)

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
