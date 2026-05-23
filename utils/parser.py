import re

def parse_caption(caption):
    """
    STRICTLY extracts metadata from Telegram media caption.
    Example: Agents of the Four Seasons Dance of Spring - S01E04 - Morning Calm - [Tam + Tel + Hin + Eng + Jap] - 720p HDRip x265 - Multi-Subs.mkv
    """
    data = {
        "season": 1,
        "episode": 1,
        "episode_title": "Episode",
        "quality": "HD",
        "title": "Unknown"
    }

    if not caption:
        return data

    # 1. Extract Season & Episode (SxxExx)
    se_match = re.search(r'S(\d+)E(\d+)', caption, re.IGNORECASE)
    if se_match:
        data["season"] = int(se_match.group(1))
        data["episode"] = int(se_match.group(2))

    # 2. Extract Quality (480p, 720p, 1080p, 4K, etc.)
    q_match = re.search(r'(\d{3,4}p)', caption, re.IGNORECASE)
    if q_match:
        data["quality"] = q_match.group(1).lower()
    elif re.search(r'4K|2160p', caption, re.IGNORECASE):
        data["quality"] = "4k"

    # 3. Extract Title and Episode Title by splitting
    # Format: Title - SxxExx - Episode Title - ...
    parts = [p.strip() for p in caption.split(' - ')]

    if len(parts) >= 1:
        data["title"] = parts[0]

    if len(parts) >= 3:
        # The part after SxxExx is usually the episode title
        # parts[0] = Title, parts[1] = SxxExx, parts[2] = Episode Title
        data["episode_title"] = parts[2]
    else:
        data["episode_title"] = f"Episode {data['episode']}"

    return data

def parse_filename(filename):
    """Legacy wrapper, but now redirects to parse_caption if it looks like a caption"""
    # The user strictly wants caption parsing.
    return parse_caption(filename)
