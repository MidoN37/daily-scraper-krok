import os
import json
import shutil
from datetime import datetime

# --- CONFIG ---
DATE_STR = datetime.now().strftime('%d-%m-%Y')
SOURCE_DIR = os.path.join(DATE_STR, "TXT") # Where the scraper put them today
DEST_DIR = "TXTs"                          # Where the website looks for them
CONFIG_FILE = "config.json"
DEFAULT_PASS = "12345"

def update_website_data():
    # 1. Ensure Destination Directory Exists
    if not os.path.exists(DEST_DIR):
        os.makedirs(DEST_DIR)

    # 2. Copy files from Daily Folder to Website Folder
    if os.path.exists(SOURCE_DIR):
        print(f"🔄 Moving files from {SOURCE_DIR} to {DEST_DIR}...")
        for filename in os.listdir(SOURCE_DIR):
            if filename.endswith(".txt"):
                src = os.path.join(SOURCE_DIR, filename)
                dst = os.path.join(DEST_DIR, filename)
                shutil.copy2(src, dst) # copy2 preserves metadata
                print(f"   - Copied: {filename}")
    else:
        print(f"⚠️ Source folder {SOURCE_DIR} not found. Did the scraper run?")

    # 3. Load Existing Config
    data = {"files": [], "passwords": {}}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"⚠️ Error reading config.json, starting fresh: {e}")

    # 4. Scan TXTs folder for ALL current files
    # We scan the directory to ensure config matches reality
    current_files = sorted([f for f in os.listdir(DEST_DIR) if f.endswith(".txt")])
    data['files'] = current_files

    # 5. Update Passwords (preserve old, add default for new)
    updated_passwords = data.get('passwords', {})
    
    for f in current_files:
        if f not in updated_passwords:
            print(f"   🆕 New file detected: {f} -> Password: {DEFAULT_PASS}")
            updated_passwords[f] = DEFAULT_PASS
    
    data['passwords'] = updated_passwords

    # 6. Set the Last Updated Date
    data['last_updated'] = DATE_STR
    print(f"📅 Updated database date to: {DATE_STR}")

    # 7. Save Config
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("✅ Website configuration updated successfully.")

if __name__ == "__main__":
    update_website_data()
