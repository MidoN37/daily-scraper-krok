import os
import json
import logging
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# Force UTF-8 encoding
sys.stdout.reconfigure(encoding='utf-8')

# --- CONFIG ---
# Use a different Environment Variable name for this bot on Render!
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

# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Access Denied.")
        return
    
    cats = get_categories()
    keyboard = [[InlineKeyboardButton(c, callback_data=f"cat|{c}")] for c in cats]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔑 <b>Krok Password Manager</b>\nSelect Category:", reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")
    action = data[0]

    if action == "start":
        cats = get_categories()
        kb = [[InlineKeyboardButton(c, callback_data=f"cat|{c}")] for c in cats]
        await query.edit_message_text("Select Category:", reply_markup=InlineKeyboardMarkup(kb))

    elif action == "cat":
        cat_name = data[1]
        # For Krok categories, show levels. For others, show flat list.
        if "Krok" in cat_name or "Крок" in cat_name:
            levels = ["1", "2", "3"]
            kb = [[InlineKeyboardButton(f"Level {l}", callback_data=f"list|{cat_name}|{l}")] for l in levels]
            kb.append([InlineKeyboardButton("🔙 Back", callback_data="start")])
            await query.edit_message_text(f"📂 {cat_name}\nSelect Level:", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await show_passwords(query, cat_name)

    elif action == "list":
        cat_name, level = data[1], data[2]
        await show_passwords(query, cat_name, level)

async def show_passwords(query, cat_name, level=None):
    data = load_data()
    files = data.get("files", [])
    passwords = data.get("passwords", {})
    
    prefix = "Krok" if "English" in cat_name else ("Крок" if "Українська" in cat_name else ("ЄДКІ" if "ЄДКІ" in cat_name else "АМПС"))
    
    filtered = []
    for f in files:
        if f.startswith(prefix):
            if level and f" {level} " not in f:
                continue
            filtered.append(f)
    
    if not filtered:
        await query.edit_message_text("❌ No passwords found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="start")]]))
        return

    msg = f"🔑 <b>Passwords for {cat_name} {level or ''}</b>\n\n"
    for f in sorted(filtered):
        pw = passwords.get(f, "12345")
        name = f.replace(".txt", "")
        # Using <code> makes it copyable on tap
        msg += f"📄 {name}\n└ <code>{pw}</code>\n\n"

    kb = [[InlineKeyboardButton("🔙 Back", callback_data="start")]]
    
    # Split message if too long
    if len(msg) > 4000:
        await query.message.reply_text(msg[4000:], parse_mode=ParseMode.HTML)
        msg = msg[:4000]
        
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

if __name__ == '__main__':
    if not TOKEN:
        print("Set PASSWORD_BOT_TOKEN environment variable.")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler('start', start))
        app.add_handler(CallbackQueryHandler(handle_callback))
        app.run_polling()
