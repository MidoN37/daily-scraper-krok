import os
import re
import glob
import json
import requests
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors

# --- CONFIG ---
MERGED_TXT_DIR = os.path.join("Merged", "TXT")
MERGED_PDF_DIR = os.path.join("Merged", "PDF")
CONFIG_FILE = "config.json"
DEFAULT_PASS = "12345"

# Font Config
FONT_URL = "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/ttf/DejaVuSans.ttf"
FONT_FILE = "DejaVuSans.ttf"
FONT_NAME = 'DejaVuSans'

class MasterMerger:
    def __init__(self):
        self.ensure_folders()
        self.setup_font()
        self.database = {} 

    def ensure_folders(self):
        os.makedirs(MERGED_TXT_DIR, exist_ok=True)
        os.makedirs(MERGED_PDF_DIR, exist_ok=True)

    def setup_font(self):
        if not os.path.exists(FONT_FILE):
            print("⬇️ Downloading font...", flush=True)
            try:
                r = requests.get(FONT_URL)
                with open(FONT_FILE, 'wb') as f: f.write(r.content)
            except: pass
        try: pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))
        except: pass

    def run(self):
        print("🚀 Starting Merge...", flush=True)
        
        # 1. SCAN DATES
        date_pattern = re.compile(r"^\d{2}-\d{2}-\d{4}$")
        date_folders = [d for d in os.listdir('.') if os.path.isdir(d) and date_pattern.match(d)]
        
        if not date_folders:
            print("❌ No date folders found.")
            return

        # 2. COLLECT & DEDUPLICATE
        for d_folder in date_folders:
            txt_path = os.path.join(d_folder, "TXT")
            if not os.path.exists(txt_path): continue
            
            for txt_file in glob.glob(os.path.join(txt_path, "*.txt")):
                filename = os.path.basename(txt_file)
                if filename not in self.database: self.database[filename] = set()
                self.parse_and_add(txt_file, filename)

        # 3. SAVE MERGED FILES
        print(f"💾 Saving {len(self.database)} merged tests...", flush=True)
        for filename, questions_set in self.database.items():
            sorted_questions = sorted(list(questions_set))
            
            txt_out = os.path.join(MERGED_TXT_DIR, filename)
            self.save_txt(txt_out, sorted_questions)
            
            pdf_out = os.path.join(MERGED_PDF_DIR, filename.replace(".txt", ".pdf"))
            self.save_pdf(txt_out, pdf_out)

        # 4. UPDATE CONFIG.JSON
        self.update_website_config()

    def parse_and_add(self, filepath, filename):
        try:
            with open(filepath, 'r', encoding='utf-8') as f: content = f.read()
            content = content.replace('\r\n', '\n')
            blocks = re.split(r'\n(?=\d+\.)', content)
            
            for block in blocks:
                block = block.strip()
                if not block: continue
                # Remove leading number "1. " to deduplicate purely by text
                clean_block = re.sub(r'^\d+\.\s*', '', block)
                if clean_block: self.database[filename].add(clean_block)
        except: pass

    def save_txt(self, path, questions):
        with open(path, 'w', encoding='utf-8') as f:
            for i, q in enumerate(questions):
                f.write(f"{i+1}. {q}\n")

    def save_pdf(self, txt_path, pdf_path):
        # (Simplified PDF generation logic reused here)
        c = canvas.Canvas(pdf_path, pagesize=A4)
        width, height = A4
        margin = 40
        max_w = width - 2*margin
        y = height - 40 
        c.setFont(FONT_NAME, 10)
        
        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line: 
                    y-=6 
                    continue
                
                bg = None
                if re.match(r'^\d+\.', line): bg = colors.lightyellow
                elif line.startswith('*'): 
                    line = line[1:].strip()
                    bg = colors.lightgreen
                
                if y < 40:
                    c.showPage()
                    c.setFont(FONT_NAME, 10)
                    y = height - 40
                
                if bg:
                    c.setFillColor(bg)
                    c.rect(margin-2, y-4, max_w+4, 14, fill=1, stroke=0)
                
                c.setFillColor(colors.black)
                c.drawString(margin, y, line[:100]) # Trim very long lines for PDF safety
                y -= 14
        c.save()

    def update_website_config(self):
        print("⚙️ Updating config.json...", flush=True)
        
        data = {"files": [], "passwords": {}, "active_folder": "", "last_updated": ""}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                    data['passwords'] = old_data.get('passwords', {})
            except: pass

        # POINT TO MERGED FOLDER
        data['active_folder'] = "Merged/TXT" 
        
        # Get Files
        current_files = sorted([f for f in os.listdir(MERGED_TXT_DIR) if f.endswith(".txt")])
        data['files'] = current_files
        
        # Update Passwords
        for f in current_files:
            if f not in data['passwords']:
                data['passwords'][f] = DEFAULT_PASS

        # Update Date
        data['last_updated'] = datetime.now().strftime('%d-%m-%Y') + " (Merged)"

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("✅ Config updated. Website now serves Merged data.")

if __name__ == "__main__":
    MasterMerger().run()
