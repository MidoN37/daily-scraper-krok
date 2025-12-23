import os
import json
import logging
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# Force UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# --- CONFIG ---
TOKEN = os.environ.get("PASSWORD_BOT_TOKEN")
ALLOWED_USER_ID = 7349230382
CONFIG_FILE = "config.json"

logging.basicConfig(level=logging.INFO)

def load_data():
    if not os.path.exists(CONFIG_FILE):
        return {"files": [], "passwords": {}}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_categories():
    data = load_data()
    files = data.get("files", [])
    cats = set()
    for f in files:
        if f.startswith("Krok"): cats.add("🇬🇧 Krok English")
        elif f.startswith("Крок"): cats.add("🇺🇦 Крок Українська")
        elif f.startswith("ЄДКІ"): cats.add("📘 ЄДКІ")
        elif f.startswith("АМПС"): cats.add("📙 АМПС")
    return sorted(list(cats))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Access Denied.")
        return
    cats = get_categories()
    kb = [[InlineKeyboardButton(c, callback_data=f"cat|{c}")] for c in cats]
    await update.message.reply_text("🔑 <b>Krok Passwords</b>\nSelect Category:", 
                                   reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")
    
    if data[0] == "start":
        cats = get_categories()
        kb = [[InlineKeyboardButton(c, callback_data=f"cat|{c}")] for c in cats]
        await query.edit_message_text("Select Category:", reply_markup=InlineKeyboardMarkup(kb))

    elif data[0] == "cat":
        cat_name = data[1]
        if "Krok" in cat_name or "Крок" in cat_name:
            levels = ["1", "2", "3"]
            kb = [[InlineKeyboardButton(f"Level {l}", callback_data=f"list|{cat_name}|{l}")] for l in levels]
            kb.append([InlineKeyboardButton("🔙 Back", callback_data="start")])
            await query.edit_message_text(f"📂 {cat_name}\nSelect Level:", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await show_passwords(query, cat_name)

    elif data[0] == "list":
        await show_passwords(query, data[1], data[2])

async def show_passwords(query, cat_name, level=None):
    data = load_data()
    pws = data.get("passwords", {})
    prefix = "Krok" if "English" in cat_name else ("Крок" if "Українська" in cat_name else ("ЄДКІ" if "ЄДКІ" in cat_name else "АМПС"))
    
    filtered = [f for f in data.get("files", []) if f.startswith(prefix) and (not level or f" {level} " in f)]
    
    if not filtered:
        await query.edit_message_text("❌ No data.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start")]]))
        return

    msg = f"🔑 <b>{cat_name} {level or ''}</b>\n<i>Tap password to copy:</i>\n\n"
    for f in sorted(filtered):
        msg += f"📄 {f.replace('.txt','')}\n└ <code>{pws.get(f, '12345')}</code>\n\n"

    await query.edit_message_text(msg[:4000], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start")]]), parse_mode=ParseMode.HTML)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()
