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
from PyPDF2 import PdfReader

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

# Cache for question counts to avoid re-parsing PDFs
_question_count_cache = {}

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

# --- QUESTION COUNTING ---
def extract_question_count(pdf_path):
    """Extract the highest question number from a PDF file."""
    # Check cache first
    if pdf_path in _question_count_cache:
        return _question_count_cache[pdf_path]
    
    try:
        reader = PdfReader(pdf_path)
        max_question = 0
        pages_to_check = min(10, len(reader.pages))  # Check last 10 pages
        
        for i in range(len(reader.pages) - 1, max(0, len(reader.pages) - pages_to_check - 1), -1):
            page = reader.pages[i]
            text = page.extract_text()
            
            # Find all question numbers (e.g., "468.", "469.", "470.")
            matches = re.findall(r'(?:^|\s)(\d+)\.', text, re.MULTILINE)
            
            if matches:
                numbers = [int(m) for m in matches]
                page_max = max(numbers)
                if page_max > max_question:
                    max_question = page_max
                
                if max_question > 0:
                    break
        
        result = max_question if max_question > 0 else None
        _question_count_cache[pdf_path] = result
        return result
        
    except Exception as e:
        logger.error(f"Error extracting question count from {pdf_path}: {e}")
        return None

def format_question_count(count):
    """Format question count for display."""
    if count is None:
        return ""
    return f" • {count} питань" if count > 0 else ""

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
    kb.append([InlineKeyboardButton("🔍 Пошук по базі", callback_data="S")])
    kb.append([InlineKeyboardButton("⭐ Обране", callback_data="FAV")])
    text = "👋 <b>Krok Master Bot</b>\nОберіть категорію:"
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
        kb.append([InlineKeyboardButton("🔙 Назад", callback_data="root")])
        await query.edit_message_text(f"🌐 <b>{cat}</b>\n\nОберіть джерело:", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    elif act == "M": # Levels
        cat = cats[int(data[1])]; srcs = sorted(list(set(i['source'] for i in master if i['exam_type'] == cat)))
        src = srcs[int(data[2])]; lvls = sorted(list(set(i['level'] for i in master if i['exam_type'] == cat and i['source'] == src)))
        kb = [[InlineKeyboardButton(lvl, callback_data=f"V|{data[1]}|{data[2]}|{i}|0")] for i, lvl in enumerate(lvls)]
        kb.append([InlineKeyboardButton("🔙 Назад", callback_data=f"C|{data[1]}")])
        breadcrumb = f"🧭 {cat} → {src}"
        await query.edit_message_text(f"{breadcrumb}\n\nОберіть рівень:", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    elif act == "V": # Files (Paginated)
        cat_idx, src_idx, lvl_idx, page = int(data[1]), int(data[2]), int(data[3]), int(data[4])
        cat = cats[cat_idx]; srcs = sorted(list(set(i['source'] for i in master if i['exam_type'] == cat)))
        src = srcs[src_idx]; lvls = sorted(list(set(i['level'] for i in master if i['exam_type'] == cat and i['source'] == src)))
        lvl = lvls[lvl_idx]
        files = [i for i in master if i['exam_type'] == cat and i['source'] == src and i['level'] == lvl]
        start_idx = page * PAGE_SIZE; end_idx = start_idx + PAGE_SIZE; page_files = files[start_idx:end_idx]
        breadcrumb = f"🧭 {cat} → {src} → {lvl}"
        msg = f"{breadcrumb}\n\n📖 <b>{lvl}</b> (Сторінка {page+1} з {(len(files)-1)//PAGE_SIZE + 1})\n\n"
        kb = []; row = []
        for i, f in enumerate(page_files):
            num = start_idx + i + 1
            q_count = extract_question_count(f['path'])
            q_text = format_question_count(q_count)
            msg += f"<b>{num}.</b> {f['name']}{q_text}\n"
            row.append(InlineKeyboardButton(str(num), callback_data=f"F|{cat_idx}|{src_idx}|{lvl_idx}|{start_idx+i}"))
            if len(row) == 5: kb.append(row); row = []
        if row: kb.append(row)
        nav_row = []
        if page > 0: nav_row.append(InlineKeyboardButton("⬅️ Попередня", callback_data=f"V|{cat_idx}|{src_idx}|{lvl_idx}|{page-1}"))
        if end_idx < len(files): nav_row.append(InlineKeyboardButton("Наступна ➡️", callback_data=f"V|{cat_idx}|{src_idx}|{lvl_idx}|{page+1}"))
        if nav_row: kb.append(nav_row)
        kb.append([InlineKeyboardButton("🔙 Назад", callback_data=f"M|{cat_idx}|{src_idx}")])
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    elif act == "F":
        cat_idx, src_idx, lvl_idx, f_idx = int(data[1]), int(data[2]), int(data[3]), int(data[4])
        cat = cats[cat_idx]; srcs = sorted(list(set(i['source'] for i in master if i['exam_type'] == cat)))
        src = srcs[src_idx]; lvls = sorted(list(set(i['level'] for i in master if i['exam_type'] == cat and i['source'] == src)))
        lvl = lvls[lvl_idx]
        files = [i for i in master if i['exam_type'] == cat and i['source'] == src and i['level'] == lvl]
        item = files[f_idx]; c.user_data['last_item'] = item
        
        # Add to recent files
        if 'recent_files' not in c.user_data: c.user_data['recent_files'] = []
        recent = c.user_data['recent_files']
        item_id = item['path']
        if item_id in recent: recent.remove(item_id)
        recent.insert(0, item_id)
        c.user_data['recent_files'] = recent[:10]
        
        # Check if favorited
        favs = c.user_data.get('favorites', [])
        is_fav = item['path'] in favs
        fav_btn_text = "💔 Видалити з обраного" if is_fav else "⭐ Додати в обране"
        
        # Get question count
        q_count = extract_question_count(item['path'])
        q_text = f"\n<i>Кількість питань:</i> {q_count}" if q_count else ""
        
        breadcrumb = f"🧭 {cat} → {src} → {lvl}"
        msg = f"{breadcrumb}\n\n📄 <b>{item['name']}</b>\n\n"
        msg += f"<i>Категорія:</i> {cat}\n<i>Джерело:</i> {src}\n<i>Рівень:</i> {lvl}{q_text}"
        
        kb = [
            [InlineKeyboardButton("📥 Отримати PDF", callback_data="GPDF")],
            [InlineKeyboardButton("🔑 Отримати пароль", callback_data="GPW")],
            [InlineKeyboardButton(fav_btn_text, callback_data="TOGGLEFAV")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"V|{cat_idx}|{src_idx}|{lvl_idx}|{f_idx // PAGE_SIZE}")]
        ]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    elif act == "GPDF":
        item = c.user_data.get('last_item')
        if item: await query.message.reply_document(document=open(item['path'], 'rb'), caption=f"📄 {item['name']}")
    elif act == "GPW":
        item = c.user_data.get('last_item')
        if item:
            pws = load_passwords(); raw_name = os.path.basename(item['path']).replace(".pdf", "")
            p = pws.get(raw_name + ".txt") or pws.get(raw_name)
            if p: await query.message.reply_text(f"🔑 Пароль для <b>{item['name']}</b>:\n\n<code>{p}</code>", parse_mode=ParseMode.HTML)
            else: await query.message.reply_text("Цей іспит не в форматі Quiz, ви можете додати його через адмін-панель.")
    elif act == "TOGGLEFAV":
        item = c.user_data.get('last_item')
        if item:
            if 'favorites' not in c.user_data: c.user_data['favorites'] = []
            favs = c.user_data['favorites']
            if item['path'] in favs:
                favs.remove(item['path'])
                await query.answer("Видалено з обраного", show_alert=True)
            else:
                favs.append(item['path'])
                await query.answer("Додано в обране", show_alert=True)
            await handle_callback(u, c)
    elif act == "FAV":
        favs = c.user_data.get('favorites', [])
        if not favs:
            kb = [[InlineKeyboardButton("🔙 Головне меню", callback_data="root")]]
            await query.edit_message_text("⭐ У вас поки немає обраних файлів", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        else:
            fav_items = [i for i in master if i['path'] in favs]
            msg = "⭐ <b>Обране</b>\n\n"; kb = []; row = []
            for i, f in enumerate(fav_items):
                num = i + 1
                q_count = extract_question_count(f['path'])
                q_text = format_question_count(q_count)
                msg += f"<b>{num}.</b> {f['name']}{q_text} <i>[{f['source']}]</i>\n"
                row.append(InlineKeyboardButton(str(num), callback_data=f"FAVF|{i}"))
                if len(row) == 5: kb.append(row); row = []
            if row: kb.append(row)
            kb.append([InlineKeyboardButton("🔙 Головне меню", callback_data="root")])
            c.user_data['fav_items'] = fav_items
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    elif act == "FAVF":
        idx = int(data[1])
        fav_items = c.user_data.get('fav_items', [])
        if idx < len(fav_items):
            item = fav_items[idx]
            c.user_data['last_item'] = item
            
            favs = c.user_data.get('favorites', [])
            is_fav = item['path'] in favs
            fav_btn_text = "💔 Видалити з обраного" if is_fav else "⭐ Додати в обране"
            
            q_count = extract_question_count(item['path'])
            q_text = f"\n<i>Кількість питань:</i> {q_count}" if q_count else ""
            
            msg = f"📄 <b>{item['name']}</b>\n\n"
            msg += f"<i>Категорія:</i> {item['exam_type']}\n<i>Джерело:</i> {item['source']}\n<i>Рівень:</i> {item['level']}{q_text}"
            
            kb = [
                [InlineKeyboardButton("📥 Отримати PDF", callback_data="GPDF")],
                [InlineKeyboardButton("🔑 Отримати пароль", callback_data="GPW")],
                [InlineKeyboardButton(fav_btn_text, callback_data="TOGGLEFAV")],
                [InlineKeyboardButton("🔙 До обраного", callback_data="FAV")]
            ]
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    elif act == "S":
        c.user_data['state'] = 'searching'
        kb = [[InlineKeyboardButton("🔙 Скасувати", callback_data="root")]]
        await query.edit_message_text("🔍 Введіть ключове слово для пошуку (наприклад, 'Анатомія'):", reply_markup=InlineKeyboardMarkup(kb))
    elif act == "SSRC":
        keyword = c.user_data.get('search_keyword', '')
        src_filter = data[1] if data[1] != "ALL" else None
        master = get_master_list()
        
        if src_filter:
            res = [i for i in master if keyword in i['name'].lower() and i['source'] == src_filter]
        else:
            res = [i for i in master if keyword in i['name'].lower()]
        
        if not res:
            await query.answer("❌ Нічого не знайдено", show_alert=True)
            return
            
        c.user_data['search_results'] = res[:50]
        c.user_data['last_search_source'] = src_filter if src_filter else "ALL"
        msg = f"🔍 <b>Результати пошуку</b>: \"{keyword}\"\n"
        if src_filter: msg += f"<i>Джерело: {src_filter}</i>\n"
        msg += f"\n<i>Знайдено: {len(res[:50])} файлів</i>\n\n"
        
        kb = []; row = []
        for i, f in enumerate(res[:50]):
            num = i + 1
            q_count = extract_question_count(f['path'])
            q_text = format_question_count(q_count)
            msg += f"<b>{num}.</b> {f['name']}{q_text}\n    <i>└ {f['source']}</i>\n"
            row.append(InlineKeyboardButton(str(num), callback_data=f"SF|{i}"))
            if len(row) == 5: kb.append(row); row = []
        if row: kb.append(row)
        kb.append([InlineKeyboardButton("🔄 Новий пошук", callback_data="S")])
        kb.append([InlineKeyboardButton("🔙 Головне меню", callback_data="root")])
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def handle_message(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.effective_user.id != MY_ID or c.user_data.get('state') != 'searching': return
    keyword = u.message.text.lower(); master = get_master_list()
    c.user_data['search_keyword'] = keyword
    
    res = [i for i in master if keyword in i['name'].lower()]
    
    if not res:
        await u.message.reply_text("❌ Нічого не знайдено. Спробуйте інше ключове слово.")
        c.user_data['state'] = None
        return
    
    sources = sorted(list(set(i['source'] for i in res)))
    
    msg = f"🔍 Знайдено <b>{len(res)}</b> результатів для: \"{keyword}\"\n\n"
    msg += "Оберіть джерело для фільтрації результатів:"
    
    kb = [[InlineKeyboardButton(f"🌐 Всі джерела ({len(res)})", callback_data="SSRC|ALL")]]
    
    for src in sources:
        count = len([i for i in res if i['source'] == src])
        kb.append([InlineKeyboardButton(f"{src} ({count})", callback_data=f"SSRC|{src}")])
    
    kb.append([InlineKeyboardButton("🔄 Новий пошук", callback_data="S")])
    kb.append([InlineKeyboardButton("🔙 Головне меню", callback_data="root")])
    
    await u.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    c.user_data['state'] = None

async def handle_search_click(u: Update, c: ContextTypes.DEFAULT_TYPE):
    query = u.callback_query; await query.answer()
    idx = int(query.data.split("|")[1]); item = c.user_data.get('search_results')[idx]
    c.user_data['last_item'] = item
    
    if 'recent_files' not in c.user_data: c.user_data['recent_files'] = []
    recent = c.user_data['recent_files']
    item_id = item['path']
    if item_id in recent: recent.remove(item_id)
    recent.insert(0, item_id)
    c.user_data['recent_files'] = recent[:10]
    
    favs = c.user_data.get('favorites', [])
    is_fav = item['path'] in favs
    fav_btn_text = "💔 Видалити з обраного" if is_fav else "⭐ Додати в обране"
    
    q_count = extract_question_count(item['path'])
    q_text = f"\n<i>Кількість питань:</i> {q_count}" if q_count else ""
    
    msg = f"📄 <b>{item['name']}</b>\n\n"
    msg += f"<i>Категорія:</i> {item['exam_type']}\n<i>Джерело:</i> {item['source']}\n<i>Рівень:</i> {item['level']}{q_text}"
    
    kb = [
        [InlineKeyboardButton("📥 Отримати PDF", callback_data="GPDF")],
        [InlineKeyboardButton("🔑 Отримати пароль", callback_data="GPW")],
        [InlineKeyboardButton(fav_btn_text, callback_data="TOGGLEFAV")],
        [InlineKeyboardButton("🔙 До результатів", callback_data=f"SSRC|{c.user_data.get('last_search_source', 'ALL')}")]
    ]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

if __name__ == '__main__':
    Thread(target=run_health_server, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(handle_search_click, pattern=r"^SF\|"))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("🚀 Bot starting...")
    app.run_polling(drop_pending_updates=True)
