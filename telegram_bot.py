import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# --- CONFIG ---
# We use Environment Variables for security so you don't expose your token on GitHub
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", 0))

MERGED_PDF_DIR = os.path.join("Merged", "PDF")
CONFIG_FILE = "config.json"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Access Denied. You are not the admin.")
        return

    text = (
        "🤖 **Krok Admin Bot**\n\n"
        "I have access to the latest Merged Database.\n"
        "What do you need?"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔑 Get Passwords", callback_data='passwords')],
        [InlineKeyboardButton("📂 Get PDF Files", callback_data='list_pdfs')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Acknowledge click
    
    data = query.data

    if data == 'passwords':
        await send_passwords(query)
    elif data == 'list_pdfs':
        await list_pdfs(query)
    elif data.startswith('pdf_'):
        filename = data.replace('pdf_', '')
        await send_pdf(query, filename)

async def send_passwords(query):
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        
        passwords = config.get('passwords', {})
        if not passwords:
            await query.edit_message_text("No passwords found in config.")
            return

        msg = "🔐 **Current Passwords:**\n\n"
        for fname, pw in passwords.items():
            msg += f"📄 `{fname}`\n🔑 `{pw}`\n\n"
        
        # Split message if too long for Telegram (4096 chars limit)
        if len(msg) > 4000:
            msg = msg[:4000] + "\n...(truncated)"

        await query.edit_message_text(msg, parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(f"Error reading config: {e}")

async def list_pdfs(query):
    if not os.path.exists(MERGED_PDF_DIR):
        await query.edit_message_text("❌ Merged PDF folder not found.")
        return

    files = sorted([f for f in os.listdir(MERGED_PDF_DIR) if f.endswith(".pdf")])
    
    if not files:
        await query.edit_message_text("❌ No PDFs found in the Merged folder.")
        return

    keyboard = []
    for f in files:
        # Callback data has a limit of 64 bytes, so we might need to truncate very long filenames
        # But usually Krok names are okay.
        btn = InlineKeyboardButton(f, callback_data=f"pdf_{f}")
        keyboard.append([btn])

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="start")])
    
    await query.edit_message_text("📂 **Select a PDF to download:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def send_pdf(query, filename):
    file_path = os.path.join(MERGED_PDF_DIR, filename)
    
    if os.path.exists(file_path):
        await query.message.reply_text(f"b⏳ Uploading {filename}...")
        try:
            await query.message.reply_document(document=open(file_path, 'rb'))
        except Exception as e:
            await query.message.reply_text(f"❌ Error uploading: {e}")
    else:
        await query.message.reply_text("❌ File not found on server.")

if __name__ == '__main__':
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set.")
        exit(1)

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is polling...", flush=True)
    application.run_polling()
