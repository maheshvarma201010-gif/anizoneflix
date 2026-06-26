import math

def get_progress_bar(percentage: float):
    """
    Returns a visual progress bar string.
    """
    total_blocks = 10
    filled_blocks = int(percentage / 10)
    empty_blocks = total_blocks - filled_blocks

    bar = "▰" * filled_blocks + "▱" * empty_blocks
    return f"[{bar}]"

def format_eta(seconds: float):
    """
    Formats seconds into a human-readable ETA string.
    """
    if seconds <= 0:
        return "N/A"

    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"

def format_time(seconds: float):
    """
    Formats elapsed time into a human-readable string.
    """
    return format_eta(seconds)
