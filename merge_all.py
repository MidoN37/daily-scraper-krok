import os
import re
import glob
import requests
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors

# --- CONFIG ---
MERGED_TXT_DIR = os.path.join("Merged", "TXT")
MERGED_PDF_DIR = os.path.join("Merged", "PDF")

# Font Config (Same as scraper)
FONT_URL = "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/ttf/DejaVuSans.ttf"
FONT_FILE = "DejaVuSans.ttf"
FONT_NAME = 'DejaVuSans'

class MasterMerger:
    def __init__(self):
        self.ensure_folders()
        self.setup_font()
        self.database = {} # { "TestName.txt": Set("Question text...") }

    def ensure_folders(self):
        os.makedirs(MERGED_TXT_DIR, exist_ok=True)
        os.makedirs(MERGED_PDF_DIR, exist_ok=True)
        print("📂 Merged folders ready.", flush=True)

    def setup_font(self):
        if not os.path.exists(FONT_FILE):
            print("⬇️ Downloading font...", flush=True)
            try:
                r = requests.get(FONT_URL)
                with open(FONT_FILE, 'wb') as f:
                    f.write(r.content)
            except Exception as e:
                print(f"❌ Font download failed: {e}")

        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))
        except:
            print("⚠️ Font register failed (might be already registered).")

    def run(self):
        print("🚀 Starting Merge Process...", flush=True)
        
        # 1. SCAN DATES
        # Regex for DD-MM-YYYY
        date_pattern = re.compile(r"^\d{2}-\d{2}-\d{4}$")
        date_folders = [d for d in os.listdir('.') if os.path.isdir(d) and date_pattern.match(d)]
        
        if not date_folders:
            print("❌ No date folders found to merge.")
            return

        print(f"📅 Found {len(date_folders)} date folders to scan.")

        # 2. COLLECT QUESTIONS
        for d_folder in date_folders:
            txt_path = os.path.join(d_folder, "TXT")
            if not os.path.exists(txt_path): continue
            
            for txt_file in glob.glob(os.path.join(txt_path, "*.txt")):
                filename = os.path.basename(txt_file)
                
                # Initialize set for this test if new
                if filename not in self.database:
                    self.database[filename] = set()

                self.parse_and_add(txt_file, filename)

        # 3. SAVE MERGED & PDF
        print(f"💾 Saving merged files for {len(self.database)} unique tests...", flush=True)
        
        for filename, questions_set in self.database.items():
            # Convert set to sorted list to maintain some order (optional: could just be random)
            # We sort simply to keep output deterministic if re-run
            sorted_questions = sorted(list(questions_set))
            
            # Save TXT
            txt_out_path = os.path.join(MERGED_TXT_DIR, filename)
            self.save_txt(txt_out_path, sorted_questions)
            
            # Save PDF
            pdf_out_path = os.path.join(MERGED_PDF_DIR, filename.replace(".txt", ".pdf"))
            self.save_pdf(txt_out_path, pdf_out_path)
            
            print(f"   ✅ Merged: {filename} ({len(sorted_questions)} unique questions)")

    def parse_and_add(self, filepath, filename):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Normalize newlines
            content = content.replace('\r\n', '\n')
            
            # Split by "Number." (e.g., "1. ", "15. ")
            # Regex: Newline followed by Digits + Dot
            blocks = re.split(r'\n(?=\d+\.)', content)
            
            for block in blocks:
                block = block.strip()
                if not block: continue
                
                # Remove the leading number "1. " to make it comparable
                # Regex: Start of string, Digits, Dot, Optional Spaces
                clean_block = re.sub(r'^\d+\.\s*', '', block)
                
                # Add to set (De-duplication happens here automatically)
                if clean_block:
                    self.database[filename].add(clean_block)
                    
        except Exception as e:
            print(f"⚠️ Error reading {filepath}: {e}")

    def save_txt(self, path, questions):
        with open(path, 'w', encoding='utf-8') as f:
            for i, q in enumerate(questions):
                # Add fresh numbering
                f.write(f"{i+1}. {q}\n")

    def save_pdf(self, txt_path, pdf_path):
        c = canvas.Canvas(pdf_path, pagesize=A4)
        width, height = A4
        margin_left = 40
        margin_right = 40
        max_text_width = width - margin_left - margin_right
        line_height = 14
        font_size = 10
        
        y = height - 40 
        c.setFont(FONT_NAME, font_size)

        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    y -= 6
                    continue

                bg_color = None
                text_color = colors.black

                # Detect Question Line
                if re.match(r'^\d+\.', line):
                    bg_color = colors.lightyellow
                    text_color = colors.black
                # Detect Correct Answer
                elif line.startswith('*'):
                    line = line[1:].strip()
                    bg_color = colors.lightgreen
                    text_color = colors.darkgreen
                # Normal Option
                else:
                    text_color = colors.darkgrey

                # Wrap Text logic
                words = line.split(' ')
                current_line = []
                wrapped_lines = []
                
                for word in words:
                    test_line = ' '.join(current_line + [word])
                    if pdfmetrics.stringWidth(test_line, FONT_NAME, font_size) < max_text_width:
                        current_line.append(word)
                    else:
                        wrapped_lines.append(' '.join(current_line))
                        current_line = [word]
                if current_line: wrapped_lines.append(' '.join(current_line))

                for w_line in wrapped_lines:
                    if y < 40:
                        c.showPage()
                        c.setFont(FONT_NAME, font_size)
                        y = height - 40

                    if bg_color:
                        c.setFillColor(bg_color)
                        c.rect(margin_left - 2, y - 4, max_text_width + 4, line_height, fill=1, stroke=0)

                    c.setFillColor(text_color)
                    c.drawString(margin_left, y, w_line)
                    y -= line_height

        c.save()

if __name__ == "__main__":
    MasterMerger().run()
