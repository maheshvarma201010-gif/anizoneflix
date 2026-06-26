import re

def validate_phone(phone: str):
    """
    Validates the phone number format: +91XXXXXXXXXX
    """
    pattern = r"^\+\d{10,15}$"
    return bool(re.match(pattern, phone))

def parse_telegram_link(link: str):
    """
    Parses a Telegram message link and returns (chat_id, message_id).
    Supports:
    - https://t.me/c/123456789/100
    - https://t.me/username/100
    """
    # Regex for private channel links
    private_pattern = r"https://t\.me/c/(\d+)/(\d+)"
    match = re.match(private_pattern, link)
    if match:
        chat_id = int("-100" + match.group(1)) if not match.group(1).startswith("-100") else int(match.group(1))
        return chat_id, int(match.group(2))

    # Regex for public channel links
    public_pattern = r"https://t\.me/([a-zA-Z0-9_]+)/(\d+)"
    match = re.match(public_pattern, link)
    if match:
        return match.group(1), int(match.group(2))

    return None, None

def is_valid_telegram_id(text: str):
    """
    Checks if the text is a valid Telegram username or ID.
    """
    if text.startswith("@"):
        return True
    try:
        int(text)
        return True
    except ValueError:
        return False
