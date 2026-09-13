import re
import unicodedata

def normalize_font_text(text: str) -> str:
    """
    Normalizes text containing fancy mathematical / stylized fonts and small caps
    into standard ASCII uppercase text.
    """
    if not text:
        return ""
    # Normalize NFKD (converts mathematical fancy characters e.g. 𝟺𝟾𝟶 to 480)
    norm = unicodedata.normalize('NFKD', text)
    # Map Latin small caps and stylized Unicode chars to standard ASCII
    small_caps = {
        'ᴀ': 'A', 'ʙ': 'B', 'ᴄ': 'C', 'ᴅ': 'D', 'ᴇ': 'E', 'ꜰ': 'F', 'ɢ': 'G', 'ʜ': 'H', 'ɪ': 'I',
        'ᴊ': 'J', 'ᴋ': 'K', 'ʟ': 'L', 'ᴍ': 'M', 'ɴ': 'N', 'ᴏ': 'O', 'ᴘ': 'P', 'ǫ': 'Q', 'ʀ': 'R',
        's': 'S', 'ꜱ': 'S', 'ᴛ': 'T', 'ᴜ': 'U', 'ᴠ': 'V', 'ᴡ': 'W', 'x': 'X', 'ʏ': 'Y', 'ᴢ': 'Z'
    }
    return "".join(small_caps.get(c, c) for c in norm)

def parse_file_entries(text, entities=None):
    """
    Parses file entries from a message text and optional entities (for deep links).
    Format expected:
    [733.18 MB] Vishwanath and Sons 2026 Telugu HQ HDRip x264 AAC mkv
    Returns a list of dicts:
    [
        {
            "size_val": 733.18,
            "unit": "MB",
            "name": "Vishwanath and Sons...",
            "link": "https://t.me/...",
            "full_line": "..."
        }
    ]
    """
    entries = []
    lines = text.split("\n")

    # Build entity link map if message entities are present
    entity_links = {}
    if entities:
        for ent in entities:
            # Check TextLink or url
            url = getattr(ent, "url", None)
            offset = getattr(ent, "offset", None)
            length = getattr(ent, "length", None)
            if url and offset is not None and length is not None:
                link_text = text[offset:offset+length]
                entity_links[link_text] = url

    pattern = r"\[([\d\.]+)\s*(MB|GB|KB|TB)\]\s*(.+)"
    for line in lines:
        line_str = line.strip()
        match = re.search(pattern, line_str, re.IGNORECASE)
        if match:
            size_val = float(match.group(1))
            unit = match.group(2).upper()
            filename = match.group(3).strip()

            link = entity_links.get(filename) or entity_links.get(line_str)
            entries.append({
                "size_val": size_val,
                "unit": unit,
                "name": filename,
                "link": link,
                "full_line": line_str
            })

    return entries

def filter_highest_mb_file(entries, quality=None):
    """
    Filters entries to select the highest file size in MB only.
    Excludes GB, KB, TB files.
    If quality (e.g. '480P', '720P', '1080P') is provided, filters for name matching quality or accepts all if quality is general.
    """
    mb_entries = [e for e in entries if e["unit"] == "MB"]
    if not mb_entries:
        return None

    if quality:
        norm_qual = normalize_font_text(quality).upper()
        qual_pattern = re.compile(rf"\b{re.escape(norm_qual)}\b", re.IGNORECASE)
        qual_matches = [e for e in mb_entries if qual_pattern.search(normalize_font_text(e["name"]))]
        if qual_matches:
            mb_entries = qual_matches

    # Sort descending by size_val
    mb_entries.sort(key=lambda x: x["size_val"], reverse=True)
    return mb_entries[0]

def extract_download_link(text, entities=None):
    """
    Extracts download link from caption or attached links in reply from /SETLINK bot.
    Handles responses like:
    ➙ Download : https://dd-stream.vercel.app/download?path=...
    📥 Dᴏᴡɴʟᴏᴀᴅ : https://cdn2.linkforge.dpdns.org/download/...
    """
    if not text:
        return None

    norm_text = normalize_font_text(text)

    # 1. Search for explicit Download line with URL
    for line in norm_text.splitlines():
        if "download" in line.lower() and ":" in line:
            urls = re.findall(r"https?://[^\s<>\"]+", line)
            if urls:
                return urls[0]

    # 2. Check for direct URL in entities matching download/stream
    if entities:
        for ent in entities:
            url = getattr(ent, "url", None)
            if url and ("download" in url.lower() or "stream" in url.lower() or "linkforge" in url.lower()):
                return url

    # 3. Search pattern for URLs containing download/stream/linkforge in full text
    url_matches = re.findall(r"https?://[^\s<>\"]+", text)
    for url in url_matches:
        if "download" in url.lower() or "stream" in url.lower() or "linkforge" in url.lower() or "get" in url.lower():
            return url

    # Fallback to first URL found
    return url_matches[0] if url_matches else text.strip()

def parse_setbot_links(text, entities=None):
    """
    Parses quality-specific generated links from /setbot response.
    Example text:
    First Filename: Geetha Govindam 2018 1080p.mkv
    ...
    Here is your link:
    https://telegram.me/MOVIESzoneFLIX_BOT?start=Z2V0LTEz...
    Returns dict mapping quality -> link, e.g. {"480P": link1, "720P": link2, "1080P": link3}
    """
    if not text:
        return {}

    result = {}

    # Build entity link map if entities present
    entity_links = []
    if entities:
        for ent in entities:
            url = getattr(ent, "url", None)
            if url:
                entity_links.append(url)

    # Split text into blocks by sections or lines
    norm_text = normalize_font_text(text)
    blocks = re.split(r"(?:First Filename:|\n\s*\n)", norm_text)

    # Check for quality + link patterns across the text or blocks
    # We can also parse line by line scanning for quality followed by "Here is your link" URL
    lines = norm_text.splitlines()
    current_qual = None

    for i, line in enumerate(lines):
        line_upper = line.upper()
        for q in ["480P", "720P", "1080P"]:
            if q in line_upper:
                current_qual = q
                break

        urls = re.findall(r"https?://[^\s<>\"]+", line)
        if urls and current_qual:
            result[current_qual] = urls[0]
            current_qual = None

    # Fallback entity link assignment if URL line direct match didn't catch all
    all_urls = re.findall(r"https?://[^\s<>\"]+", text) + entity_links
    if len(result) < 3 and all_urls:
        # Match each URL to nearby quality text in original text
        for url in all_urls:
            url_idx = text.find(url)
            if url_idx != -1:
                prefix_sub = text[max(0, url_idx-300):url_idx].upper()
                norm_sub = normalize_font_text(prefix_sub).upper()
                for q in ["480P", "720P", "1080P"]:
                    if q not in result and q in norm_sub:
                        result[q] = url

    return result

def is_matching_file(file_name, caption, admin_name, quality):
    """
    Checks if filename or caption matches '{admin_name} {quality}.mkv' (case-insensitive & font-normalized).
    """
    norm_admin = normalize_font_text(admin_name).strip().lower()
    norm_qual = normalize_font_text(quality).strip().lower()

    target = f"{norm_admin} {norm_qual}.mkv"
    target_no_ext = f"{norm_admin} {norm_qual}"

    norm_fname = normalize_font_text(file_name or "").strip().lower()
    norm_cap = normalize_font_text(caption or "").strip().lower()

    if target in norm_fname or target in norm_cap:
        return True
    if target_no_ext in norm_fname or target_no_ext in norm_cap:
        return True

    # Also match if both admin_name and quality are present in filename or caption
    if norm_admin in norm_fname and norm_qual in norm_fname:
        return True
    if norm_admin in norm_cap and norm_qual in norm_cap:
        return True

    return False

def format_lgroup_command(prefix, download_link, task_name, quality):
    """
    Formats the command to send to /SETLGROUP.
    Example output:
    /l https://download.link -e -n Admin Provided Name 480P.mkv
    """
    clean_prefix = prefix.strip()
    norm_qual = normalize_font_text(quality).upper()
    return f"{clean_prefix} {download_link} -e -n {task_name} {norm_qual}.mkv"
