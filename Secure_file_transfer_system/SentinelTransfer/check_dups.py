import re
import collections

def check_duplicate_ids(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Strip Jinja template blocks to avoid checking inactive blocks
    content = re.sub(r'\{#.*?#\}', '', content, flags=re.DOTALL)
    # Match id="..." or id='...'
    ids = re.findall(r'\bid=["\']([^"\']+)["\']', content)
    
    # Count duplicates
    counter = collections.Counter(ids)
    duplicates = [item for item, count in counter.items() if count > 1]
    return duplicates

def main():
    import glob
    for filename in glob.glob("templates/**/*.html", recursive=True):
        dups = check_duplicate_ids(filename)
        if dups:
            print(f"File: {filename} has duplicate IDs: {dups}")

if __name__ == "__main__":
    main()
