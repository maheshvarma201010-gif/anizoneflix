import re

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
        qual_pattern = re.compile(rf"\b{re.escape(quality)}\b", re.IGNORECASE)
        qual_matches = [e for e in mb_entries if qual_pattern.search(e["name"])]
        if qual_matches:
            mb_entries = qual_matches

    # Sort descending by size_val
    mb_entries.sort(key=lambda x: x["size_val"], reverse=True)
    return mb_entries[0]

def extract_download_link(text, entities=None):
    """
    Extracts download link from caption or attached links in reply from /SETLINK bot.
    """
    if not text:
        return None

    # Check for direct URL in entities
    if entities:
        for ent in entities:
            url = getattr(ent, "url", None)
            if url and ("download" in url.lower() or "stream" in url.lower() or "http" in url.lower()):
                return url

    # Search pattern for URLs in text
    url_matches = re.findall(r"https?://[^\s<>\"]+", text)
    for url in url_matches:
        if "download" in url.lower() or "stream" in url.lower() or "get" in url.lower():
            return url

    # Fallback to first URL found
    return url_matches[0] if url_matches else text.strip()

def format_lgroup_command(prefix, download_link, task_name, quality):
    """
    Formats the command to send to /SETLGROUP.
    Example output:
    /l https://download.link -e -n Admin Provided Name 480P.mkv
    """
    clean_prefix = prefix.strip()
    return f"{clean_prefix} {download_link} -e -n {task_name} {quality}.mkv"
