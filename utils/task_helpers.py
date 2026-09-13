import re
import unicodedata

def normalize_font_text(text: str) -> str:
    """
    Normalizes fancy Unicode mathematical alphanumeric symbols and small caps
    into standard ASCII uppercase/lowercase text for matching.
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)

    small_caps = {
        'ᴀ': 'A', 'ʙ': 'B', 'ᴄ': 'C', 'ᴅ': 'D', 'ᴇ': 'E', 'ꜰ': 'F', 'ɢ': 'G',
        'ʜ': 'H', 'ɪ': 'I', 'ᴊ': 'J', 'ᴋ': 'K', 'ʟ': 'L', 'ᴍ': 'M', 'ɴ': 'N',
        'ᴏ': 'O', 'ᴘ': 'P', 'ǫ': 'Q', 'ʀ': 'R', 'ꜱ': 'S', 'ᴛ': 'T',
        'ᴜ': 'U', 'ᴠ': 'V', 'ᴡ': 'W', 'ʏ': 'Y', 'ᴢ': 'Z'
    }

    res = []
    for ch in text:
        if ch in small_caps:
            res.append(small_caps[ch])
        else:
            res.append(ch)

    return "".join(res)

def get_utf16_substring(text: str, offset: int, length: int) -> str:
    """
    Telegram Message Entity offsets are measured in UTF-16 code units.
    This safely extracts the substring corresponding to (offset, length).
    """
    utf16_bytes = text.encode("utf-16-le")
    start_byte = offset * 2
    end_byte = (offset + length) * 2
    sub_bytes = utf16_bytes[start_byte:end_byte]
    return sub_bytes.decode("utf-16-le", errors="ignore")

def extract_download_link_and_quality(text: str, filename_override: str = None):
    """
    Extracts the download link and quality tag (480p, 720p, 1080p) from /SETLINK replies.
    Supports LinkForge format (📥 Dᴏᴡɴʟᴏᴀᴅ : <url>) and DD Bypass format (➙ Download : <url>).

    Returns tuple: (download_link, quality)
    """
    if not text:
        return None, None

    normalized_text = normalize_font_text(text)

    # 1. Extract download URL
    download_link = None

    # LinkForge format: 📥 Dᴏᴡɴʟᴏᴀᴅ : <url>
    lf_match = re.search(r"(?:DOWNLOAD|Dᴏᴡɴʟᴏᴀᴅ)\s*:\s*(https?://[^\s]+)", normalized_text, re.IGNORECASE)
    if lf_match:
        download_link = lf_match.group(1).strip()

    # DD Bypass format: ➙ Download : <url>
    if not download_link:
        dd_match = re.search(r"Download\s*:\s*(https?://[^\s]+)", normalized_text, re.IGNORECASE)
        if dd_match:
            download_link = dd_match.group(1).strip()

    # Fallback regex for any http/https URL in text
    if not download_link:
        urls = re.findall(r"https?://[^\s]+", text)
        if urls:
            download_link = urls[0]

    # 2. Extract Quality tag
    quality = None
    target_str = f"{filename_override or ''} {normalized_text}".lower()

    if "1080p" in target_str or "1080" in target_str:
        quality = "1080p"
    elif "720p" in target_str or "720" in target_str:
        quality = "720p"
    elif "480p" in target_str or "480" in target_str:
        quality = "480p"
    elif "360p" in target_str or "360" in target_str:
        quality = "360p"
    elif "2160p" in target_str or "4k" in target_str:
        quality = "2160p"

    return download_link, quality

def parse_setbot_result_message(text: str):
    """
    Validates /SETBOT output messages and extracts filename and Telegram deep link.
    Filters out normal Telegram bot commands / unrelated messages.

    Expected format contains fields like:
      First Filename: ...
      First Caption: ...
      Last Filename: ...
      Last Caption: ...
      Here is your link:
      https://telegram.me/...

    Returns dict:
      {
        "is_valid": bool,
        "filename": str or None,
        "quality": str or None,
        "link": str or None
      }
    """
    if not text:
        return {"is_valid": False, "filename": None, "quality": None, "link": None}

    # Filter out normal commands
    if text.strip().startswith("/"):
        return {"is_valid": False, "filename": None, "quality": None, "link": None}

    normalized = normalize_font_text(text)

    # Check for expected /SETBOT marker strings
    has_filename_marker = "FIRST FILENAME:" in normalized.upper() or "LAST FILENAME:" in normalized.upper() or "FILENAME:" in normalized.upper()
    has_link_marker = "HERE IS YOUR LINK:" in normalized.upper() or "LINK:" in normalized.upper() or "TELEGRAM.ME" in normalized.lower() or "T.ME" in normalized.lower()

    if not (has_filename_marker or has_link_marker):
        return {"is_valid": False, "filename": None, "quality": None, "link": None}

    # Extract filename
    fn_match = re.search(r"(?:FIRST FILENAME|LAST FILENAME|FILENAME)\s*:\s*(.+)", normalized, re.IGNORECASE)
    filename = fn_match.group(1).strip() if fn_match else None

    # Extract Telegram deep link
    link_match = re.search(r"(https?://t(?:elegram)?\.me/[^\s]+)", text)
    link = link_match.group(1).strip() if link_match else None

    # Detect quality from filename or text
    quality = None
    target_str = f"{filename or ''} {text}".lower()
    if "1080p" in target_str or "1080" in target_str:
        quality = "1080p"
    elif "720p" in target_str or "720" in target_str:
        quality = "720p"
    elif "480p" in target_str or "480" in target_str:
        quality = "480p"

    return {
        "is_valid": True,
        "filename": filename,
        "quality": quality,
        "link": link
    }

def parse_file_options(text: str, entities=None):
    """
    Parses file entries from the Telegram result message.
    Format example:
      1. [327.92 MB] Paradise PD S01E08 Task Force 1080p NF WEB DL ENG DDP5 1 mkv
      3. [1.13 GB] Bigg Boss S08E02 Day 1 A Task For Third Che mkv

    Returns list of dicts:
      {
        "index": int,
        "size_str": str,
        "size_mb": float or None (None if GB or unparseable),
        "is_mb": bool,
        "filename": str,
        "line_text": str,
        "deep_link": str or None (deep link attached to this line/item)
      }
    """
    results = []
    if not text:
        return results

    lines_with_ends = text.splitlines(keepends=True)
    current_utf16_offset = 0

    for line_raw in lines_with_ends:
        line_len_utf16 = len(line_raw.encode("utf-16-le")) // 2
        line_clean = line_raw.strip()

        if line_clean:
            match = re.match(r"^(\d+)\.\s*\[([^\]]+)\]\s*(.+)$", line_clean)
            if match:
                idx = int(match.group(1))
                size_raw = match.group(2).strip()
                filename = match.group(3).strip()

                is_mb = False
                size_mb = None

                size_match = re.search(r"([\d.]+)\s*(MB|GB)", size_raw, re.IGNORECASE)
                if size_match:
                    val = float(size_match.group(1))
                    unit = size_match.group(2).upper()
                    if unit == "MB":
                        is_mb = True
                        size_mb = val
                    else:
                        is_mb = False
                        size_mb = None

                deep_link = None
                if entities:
                    line_start_utf16 = current_utf16_offset
                    line_end_utf16 = current_utf16_offset + line_len_utf16

                    for ent in entities:
                        ent_url = getattr(ent, "url", None)
                        ent_type_name = getattr(ent.type, "name", str(ent.type))
                        if ent_url and ("TEXT_LINK" in ent_type_name or "text_link" in ent_type_name):
                            if (ent.offset >= line_start_utf16 and ent.offset < line_end_utf16) or \
                               (line_start_utf16 >= ent.offset and line_start_utf16 < ent.offset + ent.length):
                                deep_link = ent_url
                                break

                results.append({
                    "index": idx,
                    "size_str": size_raw,
                    "size_mb": size_mb,
                    "is_mb": is_mb,
                    "filename": filename,
                    "line_text": line_clean,
                    "deep_link": deep_link
                })

        current_utf16_offset += line_len_utf16

    return results

def get_best_mb_file(file_options, quality_filter=None, name_filter=None):
    """
    Selects the item with the HIGHEST size in MB only (excluding GB files).
    Optionally filters by quality (e.g. '480p') and/or name.
    """
    valid_items = []

    for item in file_options:
        if not item["is_mb"] or item["size_mb"] is None:
            continue

        fn = item["filename"].lower()

        if quality_filter:
            q_clean = quality_filter.lower().replace("p", "")
            if f"{q_clean}p" not in fn and f" {q_clean} " not in fn and not fn.endswith(q_clean):
                if q_clean not in fn:
                    continue

        if name_filter:
            name_words = [w.lower() for w in name_filter.split() if len(w) > 2]
            if name_words:
                match_count = sum(1 for w in name_words if w in fn)
                if match_count == 0:
                    continue

        valid_items.append(item)

    if not valid_items:
        valid_items = [item for item in file_options if item["is_mb"] and item["size_mb"] is not None]

    if not valid_items:
        return None

    valid_items.sort(key=lambda x: x["size_mb"], reverse=True)
    return valid_items[0]
