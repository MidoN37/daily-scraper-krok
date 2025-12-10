import os
import sys
import re
import time
import requests
import traceback
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# --- PDF IMPORTS ---
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors

# --- CONFIG ---
USERNAME = os.environ.get("KROK_USERNAME")
PASSWORD = os.environ.get("KROK_PASSWORD")

COURSE_URL = "https://test.testcentr.org.ua/course/view.php?id=4"
LOGIN_URL = "https://test.testcentr.org.ua/login/index.php"

# Font handling
FONT_URL = "https://github.com/googlefonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf"
FONT_FILE = "DejaVuSans.ttf" 
FONT_NAME = 'DejaVuSans'

class DailyKrokScraper:
    def __init__(self):
        self.driver = None
        # Create date-based folder structure: e.g., "10-12-2025"
        self.date_folder = datetime.now().strftime('%d-%m-%Y')
        self.txt_folder = os.path.join(self.date_folder, "TXT")
        self.pdf_folder = os.path.join(self.date_folder, "PDF")
        
        self.ensure_folders()
        self.setup_font()

    def ensure_folders(self):
        os.makedirs(self.txt_folder, exist_ok=True)
        os.makedirs(self.pdf_folder, exist_ok=True)
        print(f"📂 Folders ready: {self.date_folder}/[TXT|PDF]", flush=True)

    def setup_font(self):
        # Auto-download font if missing
        if not os.path.exists(FONT_FILE):
            print("⬇️ Font not found. Downloading DejaVuSans...", flush=True)
            try:
                r = requests.get(FONT_URL)
                with open(FONT_FILE, 'wb') as f:
                    f.write(r.content)
            except Exception as e:
                print(f"❌ Failed to download font: {e}")
                sys.exit(1)

        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))
        except Exception as e:
            print(f"❌ Font Registration Error: {e}", flush=True)
            sys.exit(1)

    def init_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        self.driver = webdriver.Chrome(options=options)

    def login(self):
        """Logs into the website. Returns True if successful."""
        try:
            print(f"🔑 Logging in...", flush=True)
            wait = WebDriverWait(self.driver, 20)
            self.driver.get(LOGIN_URL)
            
            # Check if already logged in
            if "login" not in self.driver.current_url:
                return True

            wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(USERNAME)
            self.driver.find_element(By.ID, "password").send_keys(PASSWORD)
            self.driver.find_element(By.ID, "loginbtn").click()
            wait.until(EC.presence_of_element_located((By.ID, "page-footer")))
            print("✅ Login successful.", flush=True)
            return True
        except Exception as e:
            print(f"❌ Login Failed: {e}", flush=True)
            return False

    def get_all_tests(self):
        """Extracts list of {name, url} for all available tests."""
        print("🔎 Scanning for available tests...", flush=True)
        self.driver.get(COURSE_URL)
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".activity.quiz"))
            )
            quiz_elements = self.driver.find_elements(By.CSS_SELECTOR, ".activity.quiz .activityname a")
            
            quizzes = []
            for q in quiz_elements:
                name = q.text.split("\n")[0].strip()
                link = q.get_attribute('href')
                if name and link:
                    quizzes.append({'name': name, 'link': link})
            
            print(f"📋 Found {len(quizzes)} tests to scrape.", flush=True)
            return quizzes
        except Exception as e:
            print(f"❌ Failed to get test list: {e}", flush=True)
            return []

    def run(self):
        # 1. Initial Setup
        self.init_driver()
        if not self.login():
            sys.exit(1)

        # 2. Get List of Tests
        quizzes = self.get_all_tests()
        if not quizzes:
            print("No quizzes found. Exiting.")
            sys.exit(1)

        # 3. Iterate through every test
        for i, quiz in enumerate(quizzes):
            print(f"\n[{i+1}/{len(quizzes)}] Processing: {quiz['name']}")
            
            # Retry logic for individual tests
            max_retries = 3
            success = False
            
            for attempt in range(max_retries):
                try:
                    # Check if session is still alive, if not, re-login
                    try:
                        self.driver.title 
                    except:
                        print("⚠️ Driver crashed. Restarting...", flush=True)
                        self.init_driver()
                        self.login()

                    questions = self.scrape_test_logic(quiz['link'])
                    
                    if questions:
                        self.save_results(quiz['name'], questions)
                        success = True
                        break # Exit retry loop
                    else:
                        print(f"⚠️ Warning: No questions found (Attempt {attempt+1}/{max_retries})", flush=True)
                        # Only retry if it might be a glitch, otherwise empty tests are just empty
                        if attempt < max_retries - 1:
                            time.sleep(5)
                            # Refresh session
                            self.init_driver()
                            self.login()
                except Exception as e:
                    print(f"❌ Error on attempt {attempt+1}: {e}", flush=True)
                    # Restart driver completely on error
                    self.init_driver()
                    self.login()
            
            if not success:
                print(f"💀 Failed to scrape '{quiz['name']}' after {max_retries} attempts. Skipping.", flush=True)

        self.driver.quit()
        print("\n🎉 All operations completed.")

    def scrape_test_logic(self, quiz_link):
        """The core scraping logic from your original script"""
        questions_map = {}
        wait = WebDriverWait(self.driver, 10)
        
        consecutive_empty_rounds = 0
        round_num = 1
        max_rounds = 4 

        while consecutive_empty_rounds < max_rounds:
            self.driver.get(quiz_link)

            # 1. Start/Continue
            started = False
            for sel in [".quizstartbuttondiv button", "//button[contains(text(), 'Continue')]", "//button[contains(text(), 'Attempt')]"]:
                try:
                    if "//" in sel: btn = wait.until(EC.element_to_be_clickable((By.XPATH, sel)))
                    else: btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                    self.driver.execute_script("arguments[0].click();", btn)
                    started = True
                    break
                except: continue
            
            # 2. Handle Popup
            try:
                popup_btn = self.driver.find_element(By.ID, "id_submitbutton")
                if popup_btn.is_displayed(): self.driver.execute_script("arguments[0].click();", popup_btn)
            except: pass

            # 3. Finish Attempt
            try:
                finish_link = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".endtestlink")))
                self.driver.execute_script("arguments[0].click();", finish_link)
            except:
                # If we can't find finish link, we might be on the review page already or stuck
                if len(questions_map) > 0 and round_num > 1:
                    # If we have questions, maybe the test is weird.
                    pass
                else:
                    print("   ⚠️ Could not find 'Finish attempt' link.", flush=True)
                    consecutive_empty_rounds += 1
                    continue

            # 4. Submit
            for _ in range(3):
                try:
                    s_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn-finishattempt button")))
                    self.driver.execute_script("arguments[0].click();", s_btn)
                    m_btn = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".modal-footer button.btn-primary")))
                    self.driver.execute_script("arguments[0].click();", m_btn)
                    break
                except: time.sleep(0.5)

            # 5. Expand
            try:
                show_all = wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'showall=1')]")))
                self.driver.execute_script("arguments[0].click();", show_all)
                time.sleep(2)
            except: pass

            # 6. Parse
            try:
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, "que")))
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                questions = soup.find_all("div", class_="que")
                
                new_count = 0
                for q in questions:
                    q_text_div = q.find("div", class_="qtext")
                    if not q_text_div: continue
                    q_text = q_text_div.get_text(strip=True)
                    
                    if q_text in questions_map: continue

                    correct_ans = ""
                    feedback = q.find("div", class_="feedback")
                    if feedback:
                        ra = feedback.find("div", class_="rightanswer")
                        if ra: correct_ans = ra.get_text(strip=True).replace("The correct answer is:", "").replace("Правильна відповідь:", "").strip()

                    options_str = ""
                    ans_div = q.find("div", class_="answer")
                    if ans_div:
                        opts = ans_div.find_all("div", recursive=False) or ans_div.find_all("div", class_="d-flex")
                        for opt in opts:
                            l_span = opt.find("span", class_="answernumber")
                            if not l_span: continue
                            letter = l_span.get_text(strip=True)
                            t_div = opt.find("div", class_="flex-fill")
                            txt = t_div.get_text(strip=True) if t_div else ""
                            
                            pre = "*" if correct_ans and txt.strip() == correct_ans else ""
                            options_str += f"{pre}{letter} {txt}\n"

                    questions_map[q_text] = f"{q_text}\n{options_str}"
                    new_count += 1
                
                print(f"   Questions collected: {len(questions_map)} (+{new_count})", flush=True)

                if new_count == 0: consecutive_empty_rounds += 1
                else: consecutive_empty_rounds = 0

                round_num += 1
                time.sleep(1)

            except Exception as e:
                print(f"   ⚠️ Parsing error: {e}")
                consecutive_empty_rounds += 1
        
        return questions_map

    def save_results(self, name, data):
        clean_name = re.sub(r'[\\/*?:"<>|]', "", name).strip()
        
        # 1. Save TXT
        txt_filename = f"{clean_name}.txt"
        txt_path = os.path.join(self.txt_folder, txt_filename)
        
        with open(txt_path, "w", encoding="utf-8") as f:
            counter = 1
            for _, val in data.items():
                f.write(f"{counter}. {val}\n")
                counter += 1
        
        # 2. Save PDF
        pdf_filename = f"{clean_name}.pdf"
        pdf_path = os.path.join(self.pdf_folder, pdf_filename)
        self.create_pdf(txt_path, pdf_path)

    def create_pdf(self, txt_path, pdf_path):
        # ReportLab PDF generation
        c = canvas.Canvas(pdf_path, pagesize=A4)
        width, height = A4
        margin_left = 40
        margin_right = 40
        max_text_width = width - margin_left - margin_right
        line_height = 14
        font_size = 10
        
        y = height - 40 
        c.setFont(FONT_NAME, font_size)

        def wrap_text(text, max_w):
            return [text[i:i+90] for i in range(0, len(text), 90)] # Simple wrapping logic for speed

        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    y -= 6
                    continue

                bg_color = None
                text_color = colors.black

                if re.match(r'^\d+\.', line):
                    bg_color = colors.lightyellow
                    text_color = colors.black
                elif line.startswith('*'):
                    line = line[1:].strip()
                    bg_color = colors.lightgreen
                    text_color = colors.darkgreen
                else:
                    text_color = colors.darkgrey

                # Simple char-limit wrapping to avoid heavy calculation loops
                # Logic refined from your original script
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
    DailyKrokScraper().run()
