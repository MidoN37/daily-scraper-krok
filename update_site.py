import os
import json
from datetime import datetime

# --- CONFIG ---
DATE_STR = datetime.now().strftime('%d-%m-%Y')
DAILY_TXT_FOLDER = os.path.join(DATE_STR, "TXT") # e.g. "12-12-2025/TXT"
CONFIG_FILE = "config.json"
DEFAULT_PASS = "12345"

def update_website_config():
    # 1. Check if today's folder exists
    if not os.path.exists(DAILY_TXT_FOLDER):
        print(f"⚠️ Warning: Daily folder {DAILY_TXT_FOLDER} not found. Skipping update.")
        return

    print(f"✅ Found daily folder: {DAILY_TXT_FOLDER}")

    # 2. Load Existing Config
    data = {"files": [], "passwords": {}, "active_folder": ""}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"⚠️ Error reading config.json, starting fresh: {e}")

    # 3. Update 'active_folder' path in JSON
    # This tells HTML where to look
    data['active_folder'] = DAILY_TXT_FOLDER.replace("\\", "/") # Ensure forward slashes for web

    # 4. Scan the daily folder for files
    current_files = sorted([f for f in os.listdir(DAILY_TXT_FOLDER) if f.endswith(".txt")])
    data['files'] = current_files
    print(f"📋 Found {len(current_files)} files in daily folder.")

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
    
    print("✅ Config updated. The website will now read from the new daily folder.")

if __name__ == "__main__":
    update_website_config()
