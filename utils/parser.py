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

    # Extract Episode
    ep_match = re.search(r'(?:EP|Episode|E| -)\s*(\d+)', filename, re.IGNORECASE)
    if ep_match:
        data["episode"] = int(ep_match.group(1))
    else:
        # Fallback to loose digit if it looks like an episode
        ep_match_alt = re.search(r'\s+(\d{1,3})(?:\s+|\[|\()', filename)
        if ep_match_alt:
            data["episode"] = int(ep_match_alt.group(1))

    # Extract Season
    s_match = re.search(r'(?:S|Season)\s*(\d+)', filename, re.IGNORECASE)
    if s_match:
        data["season"] = int(s_match.group(1))

    # Extract Quality
    if re.search(r'480p', filename): data["quality"] = "480p"
    elif re.search(r'720p', filename): data["quality"] = "720p"
    elif re.search(r'1080p', filename): data["quality"] = "1080p"
    elif re.search(r'2160p|4K', filename, re.IGNORECASE): data["quality"] = "4K"

    # Extract Audio
    if re.search(r'Dual|Multi', filename, re.IGNORECASE): data["audio"] = "Multi-Audio"
    elif re.search(r'Hindi|Hin|HIN', filename): data["audio"] = "Hindi"
    elif re.search(r'Telugu|Tel|TEL', filename): data["audio"] = "Telugu"
    elif re.search(r'Tamil|Tam|TAM', filename): data["audio"] = "Tamil"
    elif re.search(r'Malayalam|Mal|MAL', filename): data["audio"] = "Malayalam"
    elif re.search(r'Kannada|Kan|KAN', filename): data["audio"] = "Kannada"
    elif re.search(r'English|Eng|ENG', filename): data["audio"] = "English"

    # Extract Codec
    if re.search(r'HEVC|x265|H\.265', filename, re.IGNORECASE): data["codec"] = "HEVC"
    elif re.search(r'AVC|x264|H\.264', filename, re.IGNORECASE): data["codec"] = "AVC"

    # Attempt to clean title
    t = filename
    # Remove leading tags like [SubsPlease]
    t = re.sub(r'^\[.*?\]\s*', '', t)
    # Split by common markers
    clean_title = re.split(r'S\d+|E\d+|EP\d+|Episode\s*\d+|\[|\(|\d{3,4}p| - ', t, flags=re.IGNORECASE)[0]
    data["title"] = clean_title.strip(" .-_")

    return data
