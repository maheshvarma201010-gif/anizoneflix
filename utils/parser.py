import re

def parse_filename(filename):
    """
    Intelligently extracts metadata from filename/caption.
    Returns: { season, episode, quality, audio, codec, title }
    """
    data = {
        "season": 1,
        "episode": 1,
        "quality": "HD",
        "audio": "Japanese",
        "codec": "H.264",
        "title": filename
    }

    # Extract Quality
    if re.search(r'480p', filename): data["quality"] = "480p"
    elif re.search(r'720p', filename): data["quality"] = "720p"
    elif re.search(r'1080p', filename): data["quality"] = "1080p"
    elif re.search(r'2160p|4K', filename, re.IGNORECASE): data["quality"] = "4K"

    # Extract Audio
    if re.search(r'Dual|Multi', filename, re.IGNORECASE): data["audio"] = "Multi-Audio"
    elif re.search(r'Hindi|Hin', filename, re.IGNORECASE): data["audio"] = "Hindi"
    elif re.search(r'English|Eng', filename, re.IGNORECASE): data["audio"] = "English"

    # Extract Codec
    if re.search(r'HEVC|x265|H\.265', filename, re.IGNORECASE): data["codec"] = "HEVC"
    elif re.search(r'AVC|x264|H\.264', filename, re.IGNORECASE): data["codec"] = "AVC"

    # Extract Episode
    # Matches EP01, Episode 01, E01, - 01
    ep_match = re.search(r'(?:EP|Episode|E| -)\s*(\d+)', filename, re.IGNORECASE)
    if ep_match:
        data["episode"] = int(ep_match.group(1))
    else:
        # Fallback to loose digit if it looks like an episode (e.g., "[Title] 01 [720p]")
        # We avoid quality strings here
        ep_match_alt = re.search(r'(?:^|[\s_])(\d{1,3})(?:[\s_]|\[|\()', filename)
        if ep_match_alt:
            data["episode"] = int(ep_match_alt.group(1))

    # Extract Season
    # Matches S01, Season 01
    s_match = re.search(r'(?:S|Season)\s*(\d+)', filename, re.IGNORECASE)
    if s_match:
        data["season"] = int(s_match.group(1))

    # Attempt to clean title
    t = filename
    # Remove leading tags like [SubsPlease]
    t = re.sub(r'^\[.*?\]\s*', '', t)
    # Split by common markers to get the base title
    # It stops at S01, E01, EP01, Episode 01, [, (, 720p, etc.
    # Updated to be more careful with Season/Episode at the start
    clean_title = re.split(r'S\d+|E\d+|EP\d+|Episode\s*\d+|Season\s*\d+|\[|\(|\d{3,4}p| - ', t, flags=re.IGNORECASE)

    # If the first part is empty (e.g. filename starts with Season 01), take the next non-empty part or keep original
    title = t
    for part in clean_title:
        if part.strip():
            title = part.strip(" .-_")
            break

    data["title"] = title

    return data
