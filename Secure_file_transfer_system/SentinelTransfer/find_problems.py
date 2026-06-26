import os
import glob
from html.parser import HTMLParser

class TemplateLinter(HTMLParser):
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        self.tags = []
        self.errors = []
        
    def handle_starttag(self, tag, attrs):
        # Self-closing HTML5 tags do not need closing tags
        self_closing = {'img', 'input', 'br', 'hr', 'meta', 'link', 'kbd', 'wbr'}
        if tag not in self_closing:
            self.tags.append((tag, self.getpos()))
            
    def handle_endtag(self, tag):
        self_closing = {'img', 'input', 'br', 'hr', 'meta', 'link', 'kbd', 'wbr'}
        if tag in self_closing:
            return
        if not self.tags:
            self.errors.append(f"Mismatched end tag </{tag}> at line {self.getpos()[0]} (no open tag)")
            return
        last_tag, pos = self.tags.pop()
        if last_tag != tag:
            self.errors.append(f"Mismatched tag: expected </{last_tag}> (opened at line {pos[0]}), found </{tag}> at line {self.getpos()[0]}")

def check_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Strip Jinja block tags to avoid confusing HTML parser
    import re
    # Remove Jinja comments
    content = re.sub(r'\{#.*?#\}', '', content, flags=re.DOTALL)
    # Replace Jinja blocks {% ... %} with spaces to preserve line numbers
    content = re.sub(r'\{%.*?%\}', lambda m: '\n' * m.group(0).count('\n'), content, flags=re.DOTALL)
    # Replace Jinja variables {{ ... }} with empty strings (unless multiline)
    content = re.sub(r'\{\{.*?\}\}', lambda m: ' ' * len(m.group(0)), content, flags=re.DOTALL)

    linter = TemplateLinter(filepath)
    try:
        linter.feed(content)
        while linter.tags:
            tag, pos = linter.tags.pop()
            linter.errors.append(f"Unclosed tag <{tag}> opened at line {pos[0]}")
    except Exception as e:
        linter.errors.append(f"Parser error: {e}")
        
    return linter.errors

def main():
    templates_dir = "templates"
    all_errors = {}
    for filename in glob.glob(os.path.join(templates_dir, "**/*.html"), recursive=True):
        errors = check_file(filename)
        if errors:
            all_errors[filename] = errors
            
    if all_errors:
        print("Found HTML Template Problems:")
        for fn, errs in all_errors.items():
            print(f"\nFile: {fn}")
            for err in errs:
                print(f"  - {err}")
    else:
        print("No HTML template problems found.")

if __name__ == "__main__":
    main()
