import os
import json
import logging
import time
import re
import urllib.parse
import asyncio
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# Telegram Imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.error import Conflict

# --- CONFIG ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", 7349230382)) # Your ID

MERGED_PDF_DIR = os.path.join("Merged", "PDF")
MERGED_TXT_DIR = os.path.join("Merged", "TXT")
CONFIG_FILE = "config.json"
DEFAULT_PASS = "12345"

# Global Application Instance
app = None
FILE_MAP = {}

logging.basicConfig(level=logging.INFO)

# --- WEB SERVER WITH API ENDPOINT ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        # Allow Netlify to talk to Render
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
            self.wfile.write(b"Krok Bot is Alive!")
            return

        # 2. API Endpoint: Send File to User
        if self.path.startswith("/send"):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            
            user_id = params.get('user_id', [None])[0]
            file_name = params.get('file', [None])[0]

            if user_id and file_name and int(user_id) == ALLOWED_USER_ID:
                # Clean filename and locate PDF
                pdf_name = file_name.replace(".txt", "") + ".pdf"
                path = os.path.join(MERGED_PDF_DIR, pdf_name)

                if os.path.exists(path):
                    # Trigger async send via the global app
                    asyncio.run_coroutine_threadsafe(
                        app.bot.send_document(chat_id=user_id, document=open(path, 'rb'), caption=f"üìÑ {pdf_name}"),
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

def start_fake_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# --- HELPERS ---
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f: return json.load(f)
        except: pass
    return {}

def rebuild_file_map():
    global FILE_MAP
    FILE_MAP = {}
    config = load_config()
    files_list = config.get('files', [])
    files_list.sort()
    for idx, txt_filename in enumerate(files_list):
        FILE_MAP[idx] = txt_filename

def get_filtered_files(category, subcategory=None):
    rebuild_file_map()
    filtered = []
    for idx, fname in FILE_MAP.items():
        if category == 'en' and not fname.startswith("Krok"): continue
        if category == 'ua' and not fname.startswith("–ö—Ä–æ–∫"): continue
        if category == 'edki' and not fname.startswith("–Ñ–î–ö–Ü"): continue
        if category == 'amps' and not fname.startswith("–ê–ú–ü–°"): continue
        if subcategory:
            if subcategory == '1' and " 1 " not in fname: continue
            if subcategory == '2' and " 2 " not in fname: continue
            if subcategory == '3' and " 3 " not in fname: continue
        filtered.append((idx, fname))
    return filtered

# --- BOT COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("‚õî Access Denied.")
        return
    await show_mode_selection(update, is_callback=False)

async def show_mode_selection(update: Update, is_callback=True):
    text = "ü§ñ <b>Krok Admin Bot</b>\nSelect Mode:"
    kb = [[InlineKeyboardButton("üîë Passwords", callback_data='nav|pw')], [InlineKeyboardButton("üìÇ PDFs", callback_data='nav|pdf')]]
    if is_callback: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

# (Keeping all your other existing handler functions: show_category_selection, show_subcategory_selection, show_final_results, send_pdf_file, router)
# ... [Omitted for brevity, but keep them in your actual file] ...

async def show_category_selection(update: Update, mode):
    text = f"üìÇ <b>{mode.upper()} Mode</b>\nSelect Category:"
    keyboard = [
        [InlineKeyboardButton("üá¨üáß Krok EN", callback_data=f'nav|{mode}|en')],
        [InlineKeyboardButton("üá∫üá¶ –ö—Ä–æ–∫ UA", callback_data=f'nav|{mode}|ua')],
        [InlineKeyboardButton("üìò –Ñ–î–ö–Ü", callback_data=f'nav|{mode}|edki')],
        [InlineKeyboardButton("üìô –ê–ú–ü–°", callback_data=f'nav|{mode}|amps')],
        [InlineKeyboardButton("üîô Back", callback_data='start')]
    ]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def show_subcategory_selection(update: Update, mode, category):
    if category in ['edki', 'amps']:
        await show_final_results(update, mode, category, None)
        return
    text = f"üî¢ <b>Select Level:</b>"
    keyboard = []
    if category == 'en':
        keyboard.append([InlineKeyboardButton("Step 1", callback_data=f'nav|{mode}|{category}|1')])
        keyboard.append([InlineKeyboardButton("Step 2", callback_data=f'nav|{mode}|{category}|2')])
    elif category == 'ua':
        keyboard.append([InlineKeyboardButton("–ö—Ä–æ–∫ 1", callback_data=f'nav|{mode}|{category}|1')])
        keyboard.append([InlineKeyboardButton("–ö—Ä–æ–∫ 2", callback_data=f'nav|{mode}|{category}|2')])
        keyboard.append([InlineKeyboardButton("–ö—Ä–æ–∫ 3", callback_data=f'nav|{mode}|{category}|3')])
    keyboard.append([InlineKeyboardButton("üîô Back", callback_data=f'nav|{mode}')])
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def show_final_results(update: Update, mode, category, subcategory):
    files = get_filtered_files(category, subcategory)
    back_data = f'nav|{mode}|{category}' if subcategory else f'nav|{mode}'
    if not files:
        await update.callback_query.edit_message_text("‚ùå No files found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("üîô Back", callback_data=back_data)]]))
        return
    if mode == 'pw':
        config = load_config()
        pass_map = config.get('passwords', {})
        full_msg = ""
        for _, fname in files:
            pw = pass_map.get(fname, DEFAULT_PASS)
            full_msg += f"üìÑ <b>{fname}</b>\nüîë <code>{pw}</code>\n\n"
        await update.callback_query.edit_message_text(full_msg[:4000], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("üîô Back", callback_data=back_data)]]), parse_mode=ParseMode.HTML)
    elif mode == 'pdf':
        keyboard = []
        for idx, fname in files:
            keyboard.append([InlineKeyboardButton(f"‚¨áÔ∏è {fname[:30]}", callback_data=f'send|{idx}')])
        keyboard.append([InlineKeyboardButton("üîô Back", callback_data=back_data)])
        await update.callback_query.edit_message_text("Select PDF:", reply_markup=InlineKeyboardMarkup(keyboard))

async def send_pdf_file(update: Update, file_id):
    txt_filename = FILE_MAP.get(int(file_id))
    if not txt_filename: return
    pdf_filename = txt_filename.replace(".txt", ".pdf")
    file_path = os.path.join(MERGED_PDF_DIR, pdf_filename)
    if os.path.exists(file_path):
        await update.callback_query.message.reply_document(document=open(file_path, 'rb'))

async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'start': await show_mode_selection(update, True)
    elif data.startswith('send|'): await send_pdf_file(update, data.split('|')[1])
    else:
        parts = data.split('|')
        mode, cat, sub = parts[1], parts[2] if len(parts)>2 else None, parts[3] if len(parts)>3 else None
        if not cat: await show_category_selection(update, mode)
        elif not sub: await show_subcategory_selection(update, mode, cat)
        else: await show_final_results(update, mode, cat, sub)

if __name__ == '__main__':
    t = Thread(target=start_fake_server, daemon=True)
    t.start()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(router))
    app.run_polling()
