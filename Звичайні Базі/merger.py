import os
import re

# The specific directories defined in your request
TARGET_DIRECTORIES = [
    "/Users/mehdinih/Downloads/BazaAll-main/English/Krok M/Nursing",
    "/Users/mehdinih/Downloads/BazaAll-main/English/Krok B/Nursing",
    "/Users/mehdinih/Downloads/BazaAll-main/English/Krok 2/Pharmacy",
    "/Users/mehdinih/Downloads/BazaAll-main/English/Krok 2/Medicine",
    "/Users/mehdinih/Downloads/BazaAll-main/English/Krok 2/Dentistry",
    "/Users/mehdinih/Downloads/BazaAll-main/English/Krok 1/Pharmacy",
    "/Users/mehdinih/Downloads/BazaAll-main/English/Krok 1/Medicine",
    "/Users/mehdinih/Downloads/BazaAll-main/English/Krok 1/Dentistry",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок 1/Лечебное дело",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок 1/Стоматология",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок 1/Фармация",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок 2/Клиническая фармация",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок 2/Косметология",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок 2/Лабораторная диагностика",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок 2/Лечебное дело",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок 2/Медицинская психология",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок 2/Стоматология",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок 2/Фармация",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок 3/Лабораторная диагностика",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок 3/Лечебное дело",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок 3/Стоматология",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок 3/Фармация",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок M/Акушерство",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок M/Лечебное дело",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок M/Медпрофилактика",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок M/Сестринское дело",
    "/Users/mehdinih/Downloads/BazaAll-main/Московська/Крок Б/Лабораторная диагностика"
]

def read_file_safe(filepath):
    """
    Tries to read a file with UTF-8, then falls back to CP1251 (Windows Cyrillic), 
    then CP1252 (Western European).
    """
    encodings = ['utf-8', 'cp1251', 'windows-1251', 'cp1252', 'latin1']
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    print(f"Error: Could not decode {filepath}")
    return ""

def parse_questions_from_text(text):
    """
    Splits the full text into individual question blocks based on the "1. " pattern.
    """
    # Pattern looks for a number, a dot, and a space at the start of a line
    # or preceded by a newline.
    pattern = re.compile(r'(?:^|\n)\s*(\d+\..*?)(?=(?:^|\n)\s*\d+\.|$)', re.DOTALL)
    
    matches = pattern.findall(text)
    cleaned_questions = [m.strip() for m in matches if m.strip()]
    return cleaned_questions

def get_question_fingerprint(question_text):
    """
    Creates a unique string for a question to detect duplicates.
    Removes leading number and normalizes whitespace.
    """
    text_no_number = re.sub(r'^\d+\.\s*', '', question_text)
    normalized = re.sub(r'\s+', ' ', text_no_number).strip()
    return normalized

def get_smart_group_name(filepath):
    """
    Determines the output filename based on the input filepath.
    1. Detects 'Booklets'/'Буклети'/'Буклеты' folders to name the all-in-one file.
    2. Strips "Part" numbers (e.g., "Surgery, 1.txt" -> "Surgery.txt").
    """
    path_parts = filepath.split(os.sep)
    filename = os.path.basename(filepath)
    name_no_ext = os.path.splitext(filename)[0]
    
    # Convert path parts to lowercase for case-insensitive checking
    lower_parts = [p.lower() for p in path_parts]

    # Check for Booklet folders (Parent directory check)
    if 'booklets' in lower_parts:
        return "All Booklets.txt"
    if 'буклети' in lower_parts:
        return "Усі буклети.txt"
    if 'буклеты' in lower_parts:
        return "Все буклеты.txt"

    # Smart Normalization Logic for Bases/Subject files
    # Matches: comma or space followed by digits at end of string
    # e.g., "Surgery, 1" -> "Surgery"
    # e.g., "Терапия, 2" -> "Терапия"
    normalized_name = re.sub(r'[, ]+\d+$', '', name_no_ext)
    
    # Also strip accidental trailing whitespace
    normalized_name = normalized_name.strip()
    
    return normalized_name + ".txt"

def process_directory(base_dir):
    if not os.path.exists(base_dir):
        print(f"Skipping (not found): {base_dir}")
        return

    print(f"Processing Directory: {base_dir}")
    
    merged_dir = os.path.join(base_dir, "Merged")
    if not os.path.exists(merged_dir):
        os.makedirs(merged_dir)

    # Dictionary to map { "NormalizedName.txt": [path1, path2, path3] }
    files_by_group = {}

    # Walk through the directory to find all TXT files
    for root, dirs, files in os.walk(base_dir):
        if "Merged" in root:
            continue

        for file in files:
            if file.lower().endswith('.txt'):
                full_path = os.path.join(root, file)
                group_name = get_smart_group_name(full_path)
                
                if group_name not in files_by_group:
                    files_by_group[group_name] = []
                files_by_group[group_name].append(full_path)

    # Process each group
    for output_filename, file_paths in files_by_group.items():
        unique_questions = []
        seen_fingerprints = set()
        
        # print(f"  -> Merging into '{output_filename}' ({len(file_paths)} source files)")

        # Sort paths for consistency
        file_paths.sort()

        for file_path in file_paths:
            content = read_file_safe(file_path)
            questions = parse_questions_from_text(content)
            
            for q in questions:
                fingerprint = get_question_fingerprint(q)
                if fingerprint not in seen_fingerprints:
                    seen_fingerprints.add(fingerprint)
                    unique_questions.append(q)

        # Write the merged file
        if unique_questions:
            output_path = os.path.join(merged_dir, output_filename)
            
            with open(output_path, 'w', encoding='utf-8') as out_f:
                for index, q_text in enumerate(unique_questions, 1):
                    # Strip original number
                    text_content = re.sub(r'^\d+\.\s*', '', q_text)
                    # Write with new sequential number
                    out_f.write(f"{index}. {text_content}\n\n")
            
            print(f"     [Created] {output_filename} ({len(unique_questions)} questions) from {len(file_paths)} files.")

def main():
    for directory in TARGET_DIRECTORIES:
        process_directory(directory)
    print("\nAll operations completed.")

if __name__ == "__main__":
    main()