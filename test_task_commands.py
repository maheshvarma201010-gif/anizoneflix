import asyncio
from database.db import Database
from utils.task_helpers import (
    parse_file_entries,
    filter_highest_mb_file,
    extract_download_link,
    format_lgroup_command
)

async def test_settings_storage():
    db = Database()
    await db.connect()

    print("--- Test 1: Settings Storage & Retrieval ---")
    await db.set_setting("setgroup", "-100123456789")
    g = await db.get_setting("setgroup")
    assert g == "-100123456789", f"Expected -100123456789, got {g}"

    await db.set_setting("setmoviebot", "@my_movie_bot")
    mb = await db.get_setting("setmoviebot")
    assert mb == "@my_movie_bot", f"Expected @my_movie_bot, got {mb}"

    await db.set_setting("session_string", "test_session_str")
    ss = await db.get_setting("session_string")
    assert ss == "test_session_str", f"Expected test_session_str, got {ss}"

    lgroup_data = {"target": "@lgroup", "commands": ["/l", "/l2", "/l3"]}
    await db.set_setting("setlgroup", lgroup_data)
    lg = await db.get_setting("setlgroup")
    assert lg["target"] == "@lgroup"
    assert lg["commands"] == ["/l", "/l2", "/l3"]

    print("Settings persistence tests passed successfully!")

def test_file_parsing_and_filtering():
    print("--- Test 2: File Parsing & MB Selection ---")
    sample_text = """
🏷 ᴛɪᴛʟᴇ : Vishwanath and Sons
🧱 ᴛᴏᴛᴀʟ ꜰɪʟᴇꜱ : 7
⏰ ʀᴇsᴜʟᴛ ɪɴ : 1.60 Sᴇᴄᴏɴᴅs
📝 ʀᴇǫᴜᴇsᴛᴇᴅ ʙʏ : Sudheer
⚜️ ᴘᴏᴡᴇʀᴇᴅ ʙʏ : ⚡ 𝐓𝐌𝐖 𝐌ᴏ𝐯ɪᴇs 𝐆ʀᴏᴜᴘ

Your Requested Files Are Here

1. [1.78 GB] Vishwanath and Sons 2026 Telugu HQ HDRip 1080p HEV mkv
2. [2.93 GB] Vishwanath and Sons 2026 Telugu TRUE WEB DL 1080p mkv
3. [1.64 GB] Vishwanath and Sons 2026 Telugu HQ HDRip 720p x264 mkv
4. [1.19 GB] Vishwanath and Sons 2026 Telugu HQ HDRip 720p x265 mkv
5. [733.18 MB] Vishwanath and Sons 2026 Telugu HQ HDRip x264 AAC mkv
6. [438.56 MB] Vishwanath and Sons 2026 Telugu HQ HDRip x264 AAC mkv
7. [302.98 MB] Vishwanath and Sons 2026 Telugu HQ HDRip x264 AAC mkv
"""

    entries = parse_file_entries(sample_text)
    assert len(entries) == 7

    # Find highest MB file (ignoring GB)
    best = filter_highest_mb_file(entries)
    assert best["unit"] == "MB"
    assert best["size_val"] == 733.18
    print("MB filtering test passed successfully!")

def test_command_formatting():
    print("--- Test 3: Command Formatting ---")
    formatted = format_lgroup_command("/l", "https://download.link/file123", "Sardar 2", "720P")
    assert formatted == "/l https://download.link/file123 -e -n Sardar 2 720P.mkv"

    formatted_l2 = format_lgroup_command("/l2", "https://download.link/file456", "Vishwanath and Sons", "1080P")
    assert formatted_l2 == "/l2 https://download.link/file456 -e -n Vishwanath and Sons 1080P.mkv"
    print("Command formatting test passed successfully!")

async def test_task_queueing():
    print("--- Test 4: Task Queue Manager ---")
    from utils.task_runner import TaskQueueManager
    tqm = TaskQueueManager()

    p1 = await tqm._acquire_prefix()
    assert p1 == "/l"

    tqm.release_prefix(p1)
    print("Task Queue Manager test passed successfully!")

async def main():
    await test_settings_storage()
    test_file_parsing_and_filtering()
    test_command_formatting()
    await test_task_queueing()
    print("\nALL TASK COMMAND TESTS PASSED SUCCESSFULLY! 🚀")

if __name__ == "__main__":
    asyncio.run(main())
