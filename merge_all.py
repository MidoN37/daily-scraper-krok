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
        # Structure: { "filename.txt": { "Question Text Hash": "Full Block String" } }
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
        print("🚀 Starting Smart Merge...", flush=True)
        
        # 1. SCAN DATES
        date_pattern = re.compile(r"^\d{2}-\d{2}-\d{4}$")
        date_folders = [d for d in os.listdir('.') if os.path.isdir(d) and date_pattern.match(d)]
        
        if not date_folders:
            print("❌ No date folders found.")
            return

        print(f"📅 Scanning {len(date_folders)} date folders...")

        # 2. COLLECT & DEDUPLICATE (SMART MODE)
        for d_folder in date_folders:
            txt_path = os.path.join(d_folder, "TXT")
            if not os.path.exists(txt_path): continue
            
            for txt_file in glob.glob(os.path.join(txt_path, "*.txt")):
                filename = os.path.basename(txt_file)
                if filename not in self.database: self.database[filename] = {}
                self.parse_and_add(txt_file, filename)

        # 3. SAVE MERGED FILES
        print(f"💾 Saving {len(self.database)} merged tests...", flush=True)
        
        for filename, questions_dict in self.database.items():
            # We take values() because that holds the Full Block
            unique_blocks = list(questions_dict.values())
            
            # Save TXT
            txt_out = os.path.join(MERGED_TXT_DIR, filename)
            self.save_txt(txt_out, unique_blocks)
            
            # Save PDF
            pdf_out = os.path.join(MERGED_PDF_DIR, filename.replace(".txt", ".pdf"))
            self.save_pdf(txt_out, pdf_out)
            
            print(f"   ✅ {filename}: {len(unique_blocks)} unique questions.")

        # 4. UPDATE CONFIG.JSON
        self.update_website_config()

    def parse_and_add(self, filepath, filename):
        try:
            with open(filepath, 'r', encoding='utf-8') as f: content = f.read()
            content = content.replace('\r\n', '\n')
            
            # Split by "Number." (e.g., "1. ", "15. ")
            blocks = re.split(r'\n(?=\d+\.)', content)
            
            for block in blocks:
                block = block.strip()
                if not block: continue
                
                # 1. Clean the block (remove leading number "1. ")
                clean_block = re.sub(r'^\d+\.\s*', '', block)
                
                # 2. EXTRACT QUESTION TEXT ONLY (Stop at options)
                lines = clean_block.split('\n')
                q_text_parts = []
                for line in lines:
                    line = line.strip()
                    # Stop if we hit an option (a., *a., etc)
                    if re.match(r'^\*?[a-eA-E]\.', line):
                        break
                    q_text_parts.append(line)
                
                question_key = " ".join(q_text_parts).strip()
                
                # 3. Store in Dictionary
                # Key = Question Text Only (For deduplication)
                # Value = Full Clean Block (For saving)
                if question_key:
                    # Only add if we haven't seen this question text before
                    if question_key not in self.database[filename]:
                        self.database[filename][question_key] = clean_block
                        
        except Exception as e:
            print(f"⚠️ Error parsing {filepath}: {e}")

    def save_txt(self, path, blocks):
        with open(path, 'w', encoding='utf-8') as f:
            for i, block in enumerate(blocks):
                # We re-add the number here
                f.write(f"{i+1}. {block}\n")

    def save_pdf(self, txt_path, pdf_path):
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
                
                # Wrap Text logic
                words = line.split(' ')
                current_line = []
                wrapped_lines = []
                
                for word in words:
                    test_line = ' '.join(current_line + [word])
                    if pdfmetrics.stringWidth(test_line, FONT_NAME, 10) < max_w:
                        current_line.append(word)
                    else:
                        wrapped_lines.append(' '.join(current_line))
                        current_line = [word]
                if current_line: wrapped_lines.append(' '.join(current_line))

                for w_line in wrapped_lines:
                    if y < 40:
                        c.showPage()
                        c.setFont(FONT_NAME, 10)
                        y = height - 40
                    
                    if bg:
                        c.setFillColor(bg)
                        c.rect(margin-2, y-4, max_w+4, 14, fill=1, stroke=0)
                    
                    c.setFillColor(colors.black)
                    c.drawString(margin, y, w_line)
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
        data['last_updated'] = datetime.now().strftime('%d-%m-%Y') + " (Merged Database)"

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("✅ Config updated.")

if __name__ == "__main__":
    MasterMerger().run()
