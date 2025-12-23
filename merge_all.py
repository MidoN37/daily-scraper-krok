import os
import re
import glob
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
MERGED_TXT_DIR = os.path.join(BASE_DIR, "Merged", "TXT")
MERGED_PDF_DIR = os.path.join(BASE_DIR, "Merged", "PDF")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# Relative Font Path
FONT_FILE = os.path.join(BASE_DIR, "DejaVuSans.ttf") 
FONT_NAME = 'DejaVuSans'

class MasterMerger:
    def __init__(self):
        os.makedirs(MERGED_TXT_DIR, exist_ok=True)
        os.makedirs(MERGED_PDF_DIR, exist_ok=True)
        try:
            if os.path.exists(FONT_FILE):
                pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))
        except:
            print("⚠️ Font registration failed.")

    def parse_file_to_dict(self, filepath):
        """Parses a TXT file into {question_text: full_block}"""
        questions = {}
        if not os.path.exists(filepath):
            return questions
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read().replace('\r\n', '\n')
            # Split by "Number." (e.g., "1. ", "15. ")
            blocks = re.split(r'\n(?=\d+\.)', content)
            for block in blocks:
                block = block.strip()
                if not block: continue
                # Extract question text (first line minus the number)
                clean_block = re.sub(r'^\d+\.\s*', '', block)
                lines = clean_block.split('\n')
                q_text = lines[0].strip()
                if q_text:
                    questions[q_text] = clean_block
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
        return questions

    def run(self):
        # 1. Find all date folders
        date_pattern = re.compile(r"^\d{2}-\d{2}-\d{4}$")
        date_folders = [d for d in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, d)) and date_pattern.match(d)]
        
        if not date_folders:
            print("✅ No new scrape folders to merge.")
            self.update_website_config()
            return

        print(f"🔄 Found {len(date_folders)} folders. Merging into Master Database...")

        for d_folder in sorted(date_folders):
            full_date_path = os.path.join(BASE_DIR, d_folder)
            txt_in_folder = os.path.join(full_date_path, "TXT")
            
            if not os.path.exists(txt_in_folder):
                continue

            for txt_file in glob.glob(os.path.join(txt_in_folder, "*.txt")):
                # CLEAN FILENAME: Remove newlines and "Quiz" labels
                raw_filename = os.path.basename(txt_file)
                filename = raw_filename.replace('\n', ' ').replace('\r', '').replace('Quiz', '').replace('  ', ' ').strip()
                if not filename.endswith(".txt"): filename += ".txt"
                filename = filename.replace(".txt.txt", ".txt")
                
                master_file_path = os.path.join(MERGED_TXT_DIR, filename)

                # Load existing questions from Master
                master_questions = self.parse_file_to_dict(master_file_path)
                # Load new questions from Scrape
                new_questions = self.parse_file_to_dict(txt_file)

                # Merge (New questions overwrite/add to master)
                initial_count = len(master_questions)
                master_questions.update(new_questions)
                added = len(master_questions) - initial_count

                # Save updated Master TXT
                with open(master_file_path, 'w', encoding='utf-8') as f:
                    for i, block in enumerate(master_questions.values(), 1):
                        f.write(f"{i}. {block}\n\n")
                
                # Generate PDF for this master file
                pdf_out = os.path.join(MERGED_PDF_DIR, filename.replace(".txt", ".pdf"))
                self.save_pdf(master_file_path, pdf_out)
                print(f"   ✅ {filename}: {len(master_questions)} total (+{added} new)")

            # 2. CLUTTER CONTROL: Delete the date folder after successful merge
            print(f"🗑️ Deleting processed folder: {d_folder}")
            shutil.rmtree(full_date_path)

        # 3. Update config.json
        self.update_website_config()

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
        print("⚙️ Updating config.json...")
        data = {"files": [], "passwords": {}, "active_folder": "Merged/TXT", "last_updated": ""}
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                    data['passwords'] = old_data.get('passwords', {})
            except: pass

        current_files = sorted([f for f in os.listdir(MERGED_TXT_DIR) if f.endswith(".txt")])
        data['files'] = current_files
        
        for f in current_files:
            if f not in data['passwords']:
                data['passwords'][f] = "12345"

        data['last_updated'] = datetime.now().strftime('%d-%m-%Y') + " (Master Database)"

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    MasterMerger().run()
