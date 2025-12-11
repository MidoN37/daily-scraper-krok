import os
import json
import re
from datetime import datetime

# --- CONFIG ---
CONFIG_FILE = "config.json"
DEFAULT_PASS = "12345"

def update_website_config():
    # 1. Load Existing Config (to keep passwords)
    data = {"dates": {}, "passwords": {}, "latest_date": ""}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                data['passwords'] = old_data.get('passwords', {})
        except Exception as e:
            print(f"⚠️ Error reading config.json: {e}")

    # 2. Scan Repository for Date Folders (Format: DD-MM-YYYY)
    all_dates = {}
    
    # Regex to match "10-12-2025"
    date_pattern = re.compile(r"^\d{2}-\d{2}-\d{4}$")
    
    for item in os.listdir('.'):
        if os.path.isdir(item) and date_pattern.match(item):
            txt_path = os.path.join(item, "TXT")
            if os.path.exists(txt_path):
                # Found a valid date folder with a TXT subfolder
                files = sorted([f for f in os.listdir(txt_path) if f.endswith(".txt")])
                if files:
                    all_dates[item] = files
                    print(f"✅ Found database: {item} ({len(files)} tests)")

    if not all_dates:
        print("❌ No date folders found.")
        return

    data['dates'] = all_dates

    # 3. Determine Latest Date (for default selection)
    # Sort keys by converting to datetime objects
    sorted_dates = sorted(all_dates.keys(), key=lambda x: datetime.strptime(x, '%d-%m-%Y'), reverse=True)
    data['latest_date'] = sorted_dates[0]
    print(f"📅 Latest database is: {data['latest_date']}")

    # 4. Update Passwords (Global list)
    # We iterate through ALL files in ALL dates to ensure passwords exist
    for date, files in all_dates.items():
        for f in files:
            if f not in data['passwords']:
                print(f"   🆕 New file: {f} -> Password: {DEFAULT_PASS}")
                data['passwords'][f] = DEFAULT_PASS

    # 5. Save Config
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("✅ Config updated with multi-date support.")

if __name__ == "__main__":
    update_website_config()
