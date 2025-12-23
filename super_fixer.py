import os
import re
import json
import shutil
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors

# --- CONFIG ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TXT_DIR = os.path.join(BASE_DIR, "Merged", "TXT")
PDF_DIR = os.path.join(BASE_DIR, "Merged", "PDF")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
FONT_FILE = os.path.join(BASE_DIR, "DejaVuSans.ttf") 
FONT_NAME = 'DejaVuSans'

class SuperFixer:
    def __init__(self):
        os.makedirs(TXT_DIR, exist_ok=True)
        os.makedirs(PDF_DIR, exist_ok=True)
        self.setup_font()

    def setup_font(self):
        if os.path.exists(FONT_FILE):
            pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))
        else:
            print("⬇️ Downloading font...")
            import requests
            url = "https://github.com/googlefonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf"
            r = requests.get(url)
            with open(FONT_FILE, 'wb') as f: f.write(r.content)
            pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))

    def parse_to_dict(self, filepath):
        questions = {}
        if not os.path.exists(filepath): return questions
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read().replace('\r\n', '\n')
            blocks = re.split(r'\n(?=\d+\.)', content)
            for block in blocks:
                block = block.strip()
                if not block: continue
                clean_block = re.sub(r'^\d+\.\s*', '', block)
                q_text = clean_block.split('\n')[0].strip()
                if q_text: questions[q_text] = clean_block
        except: pass
        return questions

    def normalize_name(self, name):
        """Aggressively cleans filenames to find duplicates"""
        # 1. Remove extension
        clean = name.replace(".txt", "").replace(".pdf", "")
        # 2. Remove newlines and the word 'Quiz'
        clean = clean.replace('\n', ' ').replace('Quiz', ' ')
        # 3. Remove extra spaces and trailing spaces
        clean = ' '.join(clean.split()).strip()
        return clean + ".txt"

    def run(self):
        print("🧼 Step 1: Normalizing names and merging all duplicates...")
        
        # Map of { "CleanName.txt": { "QuestionText": "FullBlock" } }
        master_database = {}
        all_files = [f for f in os.listdir(TXT_DIR) if f.endswith(".txt")]

        for filename in all_files:
            clean_name = self.normalize_name(filename)
            file_path = os.path.join(TXT_DIR, filename)
            
            print(f"   Processing: {filename} -> {clean_name}")
            
            if clean_name not in master_database:
                master_database[clean_name] = {}
            
            # Extract questions and add to the master dictionary for this clean name
            file_questions = self.parse_to_dict(file_path)
            master_database[clean_name].update(file_questions)

        # Step 2: Wipe the TXT folder and save only the cleaned, merged versions
        print("💾 Step 2: Saving merged Master files...")
        # Delete everything in TXT folder first to get rid of the "Space" files
        for f in os.listdir(TXT_DIR):
            os.remove(os.path.join(TXT_DIR, f))

        for filename, questions in master_database.items():
            if not questions: continue
            file_path = os.path.join(TXT_DIR, filename)
            with open(file_path, 'w', encoding='utf-8') as f:
                for i, block in enumerate(questions.values(), 1):
                    f.write(f"{i}. {block}\n\n")

        print("📄 Step 3: Rebuilding all PDFs...")
        if os.path.exists(PDF_DIR):
            shutil.rmtree(PDF_DIR)
        os.makedirs(PDF_DIR)
        
        for filename in os.listdir(TXT_DIR):
            txt_path = os.path.join(TXT_DIR, filename)
            pdf_path = os.path.join(PDF_DIR, filename.replace(".txt", ".pdf"))
            self.create_pdf(txt_path, pdf_path)
        
        print("⚙️ Step 4: Updating config.json...")
        self.update_config()

    def create_pdf(self, txt_path, pdf_path):
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

    def update_config(self):
        data = {"files": [], "passwords": {}, "active_folder": "Merged/TXT", "last_updated": ""}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                data['passwords'] = old_data.get('passwords', {})
        current_files = sorted([f for f in os.listdir(TXT_DIR) if f.endswith(".txt")])
        data['files'] = current_files
        for f in current_files:
            if f not in data['passwords']: data['passwords'][f] = "12345"
        data['last_updated'] = datetime.now().strftime('%d-%m-%Y') + " (Database Cleaned)"
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    SuperFixer().run()