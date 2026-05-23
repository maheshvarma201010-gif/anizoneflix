import re

def slugify(text):
    text = text.lower()
    # Replace common extensions before stripping symbols
    for ext in ['.mkv', '.mp4', '.avi', '.mov']:
        if text.endswith(ext):
            text = text[:-len(ext)]
            break
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = text.strip('-')
    return text
