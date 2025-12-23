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
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"files": [], "passwords": {}}

# --- WEB SERVER (Handles GET Button) ---
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
                    self.send_response(200)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b"OK")
                    return
        self.send_response(200); self.end_headers(); self.wfile.write(b"Bots Active")

    async def forward_pdf(self, chat_id, url, name):
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                f = io.BytesIO(r.content)
                f.name = name if name.lower().endswith(".pdf") else f"{name}.pdf"
                await main_app.bot.send_document(chat_id=chat_id, document=f, caption=f"📄 {f.name}")
        except Exception as e:
            logger.error(f"Forward failed: {e}")

# --- BOT 1: MAIN (PDF) ---
async def main_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.effective_user.id == MY_ID:
        await u.message.reply_text("✅ PDF Bot Active.")
    else:
        await u.message.reply_text(f"⛔ Access Denied. Your ID: {u.effective_user.id}")

# --- BOT 2: PASSWORD BOT ---
async def pw_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    # Debug log to Render
    logger.info(f"PW Bot Start clicked by {u.effective_user.id}")
    
    if u.effective_user.id != MY_ID:
        await u.message.reply_text(f"⛔ Access Denied. Your ID: {u.effective_user.id}")
        return

    data = load_config()
    cats = set()
    for f in data.get("files", []):
        if f.startswith("Krok"): cats.add("🇬🇧 Krok English")
        elif f.startswith("Крок"): cats.add("🇺🇦 Крок Українська")
        elif f.startswith("ЄДКІ"): cats.add("📘 ЄДКІ")
        elif f.startswith("АМПС"): cats.add("📙 АМПС")
    
    if not cats:
        await u.message.reply_text("📭 База порожня.")
        return

    kb = [[InlineKeyboardButton(cat, callback_data=f"cat|{cat}")] for cat in sorted(list(cats))]
    await u.message.reply_text("🔑 <b>Krok Passwords</b>\nSelect Category:", 
                               reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def pw_callback(u: Update, c: ContextTypes.DEFAULT_TYPE):
    query = u.callback_query
    await query.answer()
    
    if u.effective_user.id != MY_ID: return

    d = query.data.split("|")
    if d[0] == "cat":
        cat = d[1]
        if "Krok" in cat or "Крок" in cat:
            kb = [[InlineKeyboardButton(f"Level {l}", callback_data=f"list|{cat}|{l}")] for l in ["1","2","3"]]
            kb.append([InlineKeyboardButton("🔙 Back", callback_data="start_over")])
            await query.edit_message_text(f"📂 {cat}\nSelect Level:", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await show_pws(query, cat)
    elif d[0] == "list":
        await show_pws(query, d[1], d[2])
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
    
    msg = f"🔑 <b>{cat} {lvl or ''}</b>\n\n"
    if not filtered:
        msg += "<i>Нічого не знайдено.</i>"
    else:
        for f in sorted(filtered):
            p = pws.get(f, "12345")
            msg += f"📄 {f.replace('.txt','')}\n└ <code>{p}</code>\n\n"
    
    kb = [[InlineKeyboardButton("🔙 Back", callback_data="start_over")]]
    await query.edit_message_text(msg[:4000], reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

# --- STARTUP ---
async def main():
    global main_app, loop
    loop = asyncio.get_running_loop()
    
    # Start API Web Server
    Thread(target=lambda: HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 10000))), APIHandler).serve_forever(), daemon=True).start()

    # Create Bot Instances
    main_app = ApplicationBuilder().token(MAIN_TOKEN).build()
    main_app.add_handler(CommandHandler("start", main_start))

    pw_app = ApplicationBuilder().token(PW_TOKEN).build()
    pw_app.add_handler(CommandHandler("start", pw_start))
    pw_app.add_handler(CallbackQueryHandler(pw_callback))

    # Initializing
    await main_app.initialize()
    await pw_app.initialize()

    # Drop pending updates fixes the 409 Conflict error
    await main_app.updater.start_polling(drop_pending_updates=True)
    await pw_app.updater.start_polling(drop_pending_updates=True)

    logger.info("🚀 BOTH BOTS STARTED SUCCESSFULLY")
    
    # Keep main alive
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
