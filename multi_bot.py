import os
import json
import logging
import asyncio
import sys
import re
import io
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# Force UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# --- CONFIG ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
MY_ID = 7349230382 
CONFIG_FILE = "config.json"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAGE_SIZE = 15

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- RENDER HEALTH CHECK SERVER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"Krok Master Bot is Alive")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    httpd = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    httpd.serve_forever()

# --- INDEXING ENGINE ---
def clean_title(text):
    text = re.sub(r'(Krok|Крок)\s*([123])', r'КРОК \2', text, flags=re.IGNORECASE)
    words = text.split()
    final = []
    for w in words:
        if not final or w.lower() != final[-1].lower(): final.append(w)
    return ' '.join(final).strip()

def get_master_list():
    master_list = []
    # 1. База з ЦТ
    root_ct = os.path.join(BASE_DIR, "Merged/PDF")
    if os.path.exists(root_ct):
        for f in os.listdir(root_ct):
            if f.lower().endswith(".pdf"):
                name = f.replace(".pdf", "")
                exam_type = "🇬🇧 Krok English" if "(EN)" in name.upper() else "🇺🇦 Крок Українська"
                if "ЄДКІ" in name: exam_type = "📘 ЄДКІ"
                if "АМПС" in name: exam_type = "📙 АМПС"
                level = "Інше"
                if "КРОК 1" in name.upper(): level = "КРОК 1"
                elif "КРОК 2" in name.upper(): level = "КРОК 2"
                elif "КРОК 3" in name.upper(): level = "КРОК 3"
                elif "Бакалаври" in name: level = "ЄДКІ Бакалаври"
                elif "Фахова" in name: level = "ЄДКІ Фахова передвища освіта"
                master_list.append({"name": clean_title(name), "source": "📡 База з ЦТ", "path": os.path.join(root_ct, f), "exam_type": exam_type, "level": level})

    # 2. Звичайні Базі
    root_baza = os.path.join(BASE_DIR, "Звичайні Базі")
    for root, dirs, files in os.walk(root_baza):
        if "PDF Merged" in root:
            for f in files:
                if f.lower().endswith(".pdf"):
                    rel = os.path.relpath(os.path.join(root, f), BASE_DIR)
                    p = rel.split(os.sep)
                    lang = "🇬🇧 Krok English" if p[1] == "English" else ("⚰️ Московська" if p[1] == "Московська" else "🇺🇦 Крок Українська")
                    level = clean_title(p[3])
                    master_list.append({"name": clean_title(f"{level} {p[4]} - {f.replace('.pdf', '')}"), "source": "📚 Звичайні Базі", "path": rel, "exam_type": "📘 ЄДКІ" if "ЄДКІ" in level else lang, "level": level})

    # 3. Старше ЦТ
    root_old = os.path.join(BASE_DIR, "Старше ЦТ")
    for root, dirs, files in os.walk(root_old):
        if root.lower().endswith(os.sep + "pdf") or "єдкі" in root.lower():
            for f in files:
                if f.lower().endswith(".pdf"):
                    rel = os.path.relpath(os.path.join(root, f), BASE_DIR)
                    p = rel.split(os.sep)
                    if p[1].lower() == "єдкі": level = clean_title(p[2]); et = "📘 ЄДКІ"
                    else: level = clean_title(p[1]); et = "🇺🇦 Крок Українська"
                    master_list.append({"name": clean_title(f"{level} {p[2] if et != '📘 ЄДКІ' else p[3]}"), "source": "💾 Старше ЦТ", "path": rel, "exam_type": et, "level": level})
    return master_list

def load_passwords():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get("passwords", {})
    return {}

# --- HANDLERS ---

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.effective_user.id != MY_ID: return
    master = get_master_list()
    cats = sorted(list(set(i['exam_type'] for i in master)))
    kb = [[InlineKeyboardButton(cat, callback_data=f"C|{i}")] for i, cat in enumerate(cats)]
    kb.append([InlineKeyboardButton("🔍 Search Database", callback_data="S")])
    text = "👋 <b>Krok Master Bot</b>\nSelect Category:"
    if u.callback_query: await u.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    else: await u.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def handle_callback(u: Update, c: ContextTypes.DEFAULT_TYPE):
    query = u.callback_query; await query.answer()
    data = query.data.split("|"); act = data[0]
    master = get_master_list(); cats = sorted(list(set(i['exam_type'] for i in master)))

    if act == "root": await start(u, c)
    elif act == "C": # Sources
        cat = cats[int(data[1])]
        srcs = sorted(list(set(i['source'] for i in master if i['exam_type'] == cat)))
        kb = [[InlineKeyboardButton(s, callback_data=f"M|{data[1]}|{i}")] for i, s in enumerate(srcs)]
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="root")])
        await query.edit_message_text(f"🌐 <b>{cat}</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    elif act == "M": # Levels
        cat = cats[int(data[1])]; srcs = sorted(list(set(i['source'] for i in master if i['exam_type'] == cat)))
        src = srcs[int(data[2])]; lvls = sorted(list(set(i['level'] for i in master if i['exam_type'] == cat and i['source'] == src)))
        kb = [[InlineKeyboardButton(lvl, callback_data=f"V|{data[1]}|{data[2]}|{i}|0")] for i, lvl in enumerate(lvls)]
        kb.append([InlineKeyboardButton("🔙 Back", callback_data=f"C|{data[1]}")])
        await query.edit_message_text(f"📂 <b>{src}</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    elif act == "V": # Files (Paginated)
        cat_idx, src_idx, lvl_idx, page = int(data[1]), int(data[2]), int(data[3]), int(data[4])
        cat = cats[cat_idx]; srcs = sorted(list(set(i['source'] for i in master if i['exam_type'] == cat)))
        src = srcs[src_idx]; lvls = sorted(list(set(i['level'] for i in master if i['exam_type'] == cat and i['source'] == src)))
        lvl = lvls[lvl_idx]
        files = [i for i in master if i['exam_type'] == cat and i['source'] == src and i['level'] == lvl]
        start_idx = page * PAGE_SIZE; end_idx = start_idx + PAGE_SIZE; page_files = files[start_idx:end_idx]
        msg = f"📖 <b>{lvl}</b> (Page {page+1})\n\n"
        kb = []; row = []
        for i, f in enumerate(page_files):
            num = start_idx + i + 1
            msg += f"<b>{num}.</b> {f['name']}\n"
            row.append(InlineKeyboardButton(str(num), callback_data=f"F|{cat_idx}|{src_idx}|{lvl_idx}|{start_idx+i}"))
            if len(row) == 5: kb.append(row); row = []
        if row: kb.append(row)
        nav_row = []
        if page > 0: nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"V|{cat_idx}|{src_idx}|{lvl_idx}|{page-1}"))
        if end_idx < len(files): nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"V|{cat_idx}|{src_idx}|{lvl_idx}|{page+1}"))
        if nav_row: kb.append(nav_row)
        kb.append([InlineKeyboardButton("🔙 Back", callback_data=f"M|{cat_idx}|{src_idx}")])
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    elif act == "F":
        cat_idx, src_idx, lvl_idx, f_idx = int(data[1]), int(data[2]), int(data[3]), int(data[4])
        cat = cats[cat_idx]; srcs = sorted(list(set(i['source'] for i in master if i['exam_type'] == cat)))
        src = srcs[src_idx]; lvls = sorted(list(set(i['level'] for i in master if i['exam_type'] == cat and i['source'] == src)))
        lvl = lvls[lvl_idx]
        files = [i for i in master if i['exam_type'] == cat and i['source'] == src and i['level'] == lvl]
        item = files[f_idx]; c.user_data['last_item'] = item
        kb = [[InlineKeyboardButton("📥 GET PDF", callback_data="GPDF")], [InlineKeyboardButton("🔑 GET Password", callback_data="GPW")], [InlineKeyboardButton("🔙 Back", callback_data=f"V|{cat_idx}|{src_idx}|{lvl_idx}|{f_idx // PAGE_SIZE}")]]
        await query.edit_message_text(f"📄 <b>{item['name']}</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    elif act == "GPDF":
        item = c.user_data.get('last_item')
        if item: await query.message.reply_document(document=open(item['path'], 'rb'), caption=f"📄 {item['name']}")
    elif act == "GPW":
        item = c.user_data.get('last_item')
        if item:
            pws = load_passwords(); raw_name = os.path.basename(item['path']).replace(".pdf", "")
            p = pws.get(raw_name + ".txt") or pws.get(raw_name)
            if p: await query.message.reply_text(f"🔑 Password for <b>{item['name']}</b>:\n\n<code>{p}</code>", parse_mode=ParseMode.HTML)
            else: await query.message.reply_text("This exam is not on the Quiz format, you can add it using the Admin page.")
    elif act == "S":
        c.user_data['state'] = 'searching'
        await query.edit_message_text("🔍 Type keyword (e.g. 'Anatomy'):")

async def handle_message(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.effective_user.id != MY_ID or c.user_data.get('state') != 'searching': return
    keyword = u.message.text.lower(); master = get_master_list()
    res = [i for i in master if keyword in i['name'].lower()]
    if not res: await u.message.reply_text("❌ No matches.")
    else:
        c.user_data['search_results'] = res[:50]
        msg = "🔍 <b>Results:</b>\n\n"; kb = []; row = []
        for i, f in enumerate(res[:50]):
            num = i + 1; msg += f"<b>{num}.</b> {f['name']}\n"
            row.append(InlineKeyboardButton(str(num), callback_data=f"SF|{i}"))
            if len(row) == 5: kb.append(row); row = []
        if row: kb.append(row)
        await u.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    c.user_data['state'] = None

async def handle_search_click(u: Update, c: ContextTypes.DEFAULT_TYPE):
    query = u.callback_query; await query.answer()
    idx = int(query.data.split("|")[1]); item = c.user_data.get('search_results')[idx]
    c.user_data['last_item'] = item
    kb = [[InlineKeyboardButton("📥 GET PDF", callback_data="GPDF")], [InlineKeyboardButton("🔑 GET Password", callback_data="GPW")], [InlineKeyboardButton("🔙 Main Menu", callback_data="root")]]
    await query.edit_message_text(f"📄 <b>{item['name']}</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

if __name__ == '__main__':
    Thread(target=run_health_server, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(handle_search_click, pattern=r"^SF\|"))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("🚀 Bot starting...")
    app.run_polling(drop_pending_updates=True)
