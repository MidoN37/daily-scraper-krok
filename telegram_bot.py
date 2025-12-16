import os
import json
import logging
import time
import html
import re
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# Telegram Imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.error import Conflict

# --- CONFIG ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", 0))

MERGED_PDF_DIR = os.path.join("Merged", "PDF")
MERGED_TXT_DIR = os.path.join("Merged", "TXT")
CONFIG_FILE = "config.json"
DEFAULT_PASS = "12345"

# Global Cache
FILE_MAP = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- FAKE WEB SERVER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Krok Bot is Alive!")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

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
        if category == 'ua' and not fname.startswith("Крок"): continue
        if category == 'edki' and not fname.startswith("ЄДКІ"): continue
        if category == 'amps' and not fname.startswith("АМПС"): continue

        if subcategory:
            if subcategory == '1' and " 1 " not in fname: continue
            if subcategory == '2' and " 2 " not in fname: continue
            if subcategory == '3' and " 3 " not in fname: continue

        filtered.append((idx, fname))
    return filtered

def clean_display_name(filename):
    return filename.replace(".txt", "").replace(".pdf", "")

def get_question_count(filename):
    txt_path = os.path.join(MERGED_TXT_DIR, filename)
    if not os.path.exists(txt_path):
        return "?"
    try:
        count = 0
        with open(txt_path, 'r', encoding='utf-8') as f:
            for line in f:
                if re.match(r'^\d+\.', line): count += 1
        return count
    except:
        return "?"

# --- BOT HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Access Denied.")
        return
    await show_mode_selection(update, is_callback=False)

async def show_mode_selection(update: Update, is_callback=True):
    text = "🤖 <b>Krok Admin Bot</b>\nSelect Mode:"
    keyboard = [
        [InlineKeyboardButton("🔑 Passwords", callback_data='nav|pw')],
        [InlineKeyboardButton("📂 PDFs", callback_data='nav|pdf')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if is_callback:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def show_category_selection(update: Update, mode):
    text = f"📂 <b>{mode.upper()} Mode</b>\nSelect Category:"
    keyboard = [
        [InlineKeyboardButton("🇬🇧 Krok EN", callback_data=f'nav|{mode}|en')],
        [InlineKeyboardButton("🇺🇦 Крок UA", callback_data=f'nav|{mode}|ua')],
        [InlineKeyboardButton("📘 ЄДКІ", callback_data=f'nav|{mode}|edki')],
        [InlineKeyboardButton("📙 АМПС", callback_data=f'nav|{mode}|amps')],
        [InlineKeyboardButton("🔙 Back", callback_data='start')]
    ]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def show_subcategory_selection(update: Update, mode, category):
    if category in ['edki', 'amps']:
        await show_final_results(update, mode, category, None)
        return

    text = f"🔢 <b>Select Level:</b>"
    keyboard = []
    
    if category == 'en':
        keyboard.append([InlineKeyboardButton("Step 1", callback_data=f'nav|{mode}|{category}|1')])
        keyboard.append([InlineKeyboardButton("Step 2", callback_data=f'nav|{mode}|{category}|2')])
    elif category == 'ua':
        keyboard.append([InlineKeyboardButton("Крок 1", callback_data=f'nav|{mode}|{category}|1')])
        keyboard.append([InlineKeyboardButton("Крок 2", callback_data=f'nav|{mode}|{category}|2')])
        keyboard.append([InlineKeyboardButton("Крок 3", callback_data=f'nav|{mode}|{category}|3')])

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f'nav|{mode}')])
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def show_final_results(update: Update, mode, category, subcategory):
    files = get_filtered_files(category, subcategory)
    
    back_data = f'nav|{mode}|{category}' if subcategory else f'nav|{mode}'
    
    if not files:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data=back_data)]]
        await update.callback_query.edit_message_text("❌ No files found.", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # --- PASSWORD MODE ---
    if mode == 'pw':
        config = load_config()
        pass_map = config.get('passwords', {})
        full_msg = ""
        
        for _, fname in files:
            pw = pass_map.get(fname, DEFAULT_PASS)
            count = get_question_count(fname)
            name = clean_display_name(fname)
            
            # Using Text List ensures full name visibility + wrapping
            full_msg += f"📄 <b>{name}</b> ({count})\n🔑 <code>{pw}</code>\n\n"

        chunk_size = 4000
        chunks = [full_msg[i:i+chunk_size] for i in range(0, len(full_msg), chunk_size)]
        
        for i, chunk in enumerate(chunks):
            if i == 0:
                await update.callback_query.edit_message_text(f"🔐 <b>Passwords:</b>\n\n{chunk}", parse_mode=ParseMode.HTML)
            else:
                await update.callback_query.message.reply_text(chunk, parse_mode=ParseMode.HTML)
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data=back_data)]]
        await update.callback_query.message.reply_text("End.", reply_markup=InlineKeyboardMarkup(keyboard))

    # --- PDF MODE (LEGEND SYSTEM) ---
    elif mode == 'pdf':
        msg_header = "📂 <b>Select a PDF to download:</b>\n\n"
        msg_body = ""
        keyboard = []
        row = []

        # Build Legend Text & Numbered Buttons
        for i, (idx, fname) in enumerate(files):
            num = i + 1
            count = get_question_count(fname)
            name = clean_display_name(fname)
            
            # 1. Add Full Name to Text (Wraps automatically)
            msg_body += f"<b>{num}.</b> {name} <i>({count} q.)</i>\n\n"
            
            # 2. Add Number Button
            btn = InlineKeyboardButton(f"⬇️ {num}", callback_data=f'send|{idx}')
            row.append(btn)
            
            # 4 Buttons per row for compactness
            if len(row) == 4:
                keyboard.append(row)
                row = []

        if row: keyboard.append(row) # Add remaining buttons
        
        # Navigation
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=back_data)])

        # Split text if huge
        full_text = msg_header + msg_body
        if len(full_text) > 4000:
            # Simple truncation for safety, though unlikely with pagination usually
            full_text = full_text[:4000] + "\n...(list truncated)..."

        await update.callback_query.edit_message_text(full_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def send_pdf_file(update: Update, file_id):
    if not FILE_MAP: rebuild_file_map()
    
    txt_filename = FILE_MAP.get(file_id)
    if not txt_filename:
        await update.callback_query.message.reply_text("❌ Map Error.")
        return

    pdf_filename = txt_filename.replace(".txt", ".pdf")
    file_path = os.path.join(MERGED_PDF_DIR, pdf_filename)

    if os.path.exists(file_path):
        await update.callback_query.message.reply_text(f"⏳ Uploading {pdf_filename}...")
        try:
            with open(file_path, 'rb') as f:
                await update.callback_query.message.reply_document(document=f, filename=pdf_filename)
        except Exception as e:
            await update.callback_query.message.reply_text(f"❌ Error: {e}")
    else:
        await update.callback_query.message.reply_text(f"❌ Missing: {pdf_filename}")

# --- ROUTER ---
async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'start':
        await show_mode_selection(update, True)
        return

    if data.startswith('send|'):
        file_id = int(data.split('|')[1])
        await send_pdf_file(update, file_id)
        return

    parts = data.split('|')
    if parts[0] == 'nav':
        mode = parts[1] if len(parts) > 1 else None
        cat = parts[2] if len(parts) > 2 else None
        sub = parts[3] if len(parts) > 3 else None

        if not mode: await show_mode_selection(update, True)
        elif not cat: await show_category_selection(update, mode)
        elif not sub:
            if cat in ['en', 'ua']: await show_subcategory_selection(update, mode, cat)
            else: await show_final_results(update, mode, cat, None)
        else:
            await show_final_results(update, mode, cat, sub)

if __name__ == '__main__':
    if not TOKEN:
        print("Error: TOKEN not set.")
        exit(1)

    t = Thread(target=start_fake_server, daemon=True)
    t.start()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(router))

    print("🤖 Bot started...", flush=True)

    while True:
        try:
            app.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)
        except Conflict:
            print("Conflict. Retrying...", flush=True)
            time.sleep(10)
        except Exception as e:
            print(f"Error: {e}. Retrying...", flush=True)
            time.sleep(10)
