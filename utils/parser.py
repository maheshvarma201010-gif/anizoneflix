import re

def parse_filename(filename):
    """
    Intelligently extracts metadata from Movie/Series filenames.
    Optimized for high-accuracy year, resolution, and language extraction.
    """
    data = {
        "season": 1,
        "episode": 1,
        "quality": "HD",
        "audio": "Hindi",
        "codec": "H.264",
        "title": filename,
        "type": "movie",
        "year": "N/A"
    }

    # Detect Type
    if re.search(r'S\d+|E\d+|Season|Episode|TV\.Series', filename, re.IGNORECASE):
        data["type"] = "tv"

    # Extract Year (19xx or 20xx)
    year_match = re.search(r'(19\d{2}|20\d{2})', filename)
    if year_match:
        data["year"] = year_match.group(1)

    # Extract Episode & Season
    ep_match = re.search(r'(?:EP|Episode|E| -)\s*(\d+)', filename, re.IGNORECASE)
    if ep_match:
        data["episode"] = int(ep_match.group(1))

    s_match = re.search(r'(?:S|Season)\s*(\d+)', filename, re.IGNORECASE)
    if s_match:
        data["season"] = int(s_match.group(1))

    # Extract Quality
    quality_patterns = {
        "480p": r'480p',
        "720p": r'720p',
        "1080p": r'1080p',
        "4K": r'2160p|4K|UHD',
        "BluRay": r'BluRay|BRRip',
        "Web-DL": r'Web-DL|WEB\.DL|WEBRip'
    }
    for q, p in quality_patterns.items():
        if re.search(p, filename, re.IGNORECASE):
            data["quality"] = q

    # Extract Audio
    audio_patterns = {
        "Multi-Audio": r'Dual|Multi|DDP5\.1',
        "English": r'English|Eng|ESub',
        "Hindi": r'Hindi|Hin|HSub',
        "Tamil": r'Tamil|Tam',
        "Telugu": r'Telugu|Tel',
        "Korean": r'Korean|Kor'
    }
    for a, p in audio_patterns.items():
        if re.search(p, filename, re.IGNORECASE):
            data["audio"] = a

    # Clean Title
    t = filename
    # Remove bracketed tags and common technical terms
    t = re.sub(r'\[.*?\]|\(.*?\)', '', t)
    # Split by year or technical markers
    parts = re.split(r'19\d{2}|20\d{2}|S\d+|E\d+|Season|Episode|\d{3,4}p|Web-DL|BluRay|AVC|HEVC|x264|x265', t, flags=re.IGNORECASE)
    data["title"] = parts[0].replace('.', ' ').strip(" .-_")

    return data
