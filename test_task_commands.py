import asyncio
from database.db import Database
from utils.task_helpers import (
    parse_file_entries,
    filter_highest_mb_file,
    extract_download_link,
    format_lgroup_command,
    parse_setbot_links,
    is_matching_file
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

    await db.set_setting("monitorbots", ["bot1", "bot2", "bot3"])
    mbots = await db.get_setting("monitorbots")
    assert mbots == ["bot1", "bot2", "bot3"], f"Expected ['bot1', 'bot2', 'bot3'], got {mbots}"

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

def test_font_normalization():
    print("--- Test 4: Font Normalization ---")
    from utils.task_helpers import normalize_font_text
    styled = "𝟺𝟾𝟶ᴘ 720ᴘ 1080ᴘ"
    norm = normalize_font_text(styled)
    assert norm == "480P 720P 1080P", f"Expected '480P 720P 1080P', got '{norm}'"
    print("Font normalization test passed successfully!")

def test_extract_download_link_formats():
    print("--- Test 5: Extract Download Link ---")
    txt1 = """
‣ File Name : Salaar.Part.1.Ceasefire.2023.PROPER.480p.BluRay.x264.mkv
‣ File Size : 750.14 MB
➙ Download : https://dd-stream.vercel.app/download?path=6aa59561dedfe998dc9c5889
➙ Watch Online : https://dd-stream.vercel.app/watch?path=6aa59561dedfe998dc9c5889
💡 Tip :- Use IDM
"""
    link1 = extract_download_link(txt1)
    assert link1 == "https://dd-stream.vercel.app/download?path=6aa59561dedfe998dc9c5889"

    txt2 = """
📂 Fɪʟᴇ ɴᴀᴍᴇ : Varsham (2004) Telugu AMZN HYBRID WEBRip - 480p - AVC - MP3 .mkv
📦 Fɪʟᴇ ꜱɪᴢᴇ : 398.91 MiB
📥 Dᴏᴡɴʟᴏᴀᴅ : https://cdn2.linkforge.dpdns.org/download/AgADsB141272
🖥ᴡᴀᴛᴄʜ : https://cdn2.linkforge.dpdns.org/watch/AgADsB141272
"""
    link2 = extract_download_link(txt2)
    assert link2 == "https://cdn2.linkforge.dpdns.org/download/AgADsB141272"
    print("Extract download link test passed successfully!")

def test_parse_setbot_links():
    print("--- Test 6: Parse Setbot Links ---")
    setbot_resp = """
MOVIES:
First Filename: Geetha Govindam 2018 1080p.mkv
First Caption: Geetha Govindam 2018 1080p.mkv
Last Filename: Geetha Govindam 2018 1080p.mkv
Last Caption: Geetha Govindam 2018 1080p.mkv

Here is your link:

https://telegram.me/MOVIESzoneFLIX_BOT?start=Z2V0LTEzMjE2NTU4NjEwMzExNTY

First Filename: Geetha Govindam 2018 480p.mkv
First Caption: Geetha Govindam 2018 480p.mkv
Last Filename: Geetha Govindam 2018 480p.mkv
Last Caption: Geetha Govindam 2018 480p.mkv

Here is your link:

https://telegram.me/MOVIESzoneFLIX_BOT?start=Z2V0LTEzMjI2NjAxNTg3OTc4OTc

First Filename: Geetha Govindam 2018 720p.mkv
First Caption: Geetha Govindam 2018 720p.mkv
Last Filename: Geetha Govindam 2018 720p.mkv
Last Caption: Geetha Govindam 2018 720p.mkv

Here is your link:

https://telegram.me/MOVIESzoneFLIX_BOT?start=Z2V0LTEzMjM2NjQ0NTY1NjQ2Mzg
"""
    parsed = parse_setbot_links(setbot_resp)
    assert parsed.get("480P") == "https://telegram.me/MOVIESzoneFLIX_BOT?start=Z2V0LTEzMjI2NjAxNTg3OTc4OTc"
    assert parsed.get("720P") == "https://telegram.me/MOVIESzoneFLIX_BOT?start=Z2V0LTEzMjM2NjQ0NTY1NjQ2Mzg"
    assert parsed.get("1080P") == "https://telegram.me/MOVIESzoneFLIX_BOT?start=Z2V0LTEzMjE2NTU4NjEwMzExNTY"
    print("Parse setbot links test passed successfully!")

def test_is_matching_file():
    print("--- Test 7: Is Matching File ---")
    assert is_matching_file("Geetha Govindam 2018 480p.mkv", "", "Geetha Govindam 2018", "480p") is True
    assert is_matching_file("", "Geetha Govindam 2018 720p.mkv", "Geetha Govindam 2018", "720p") is True
    assert is_matching_file("Other Movie 1080p.mkv", "", "Geetha Govindam 2018", "1080p") is False
    print("Is matching file test passed successfully!")

async def test_task_cancellation_flow():
    print("--- Test 5: Task Queue Manager Cancellation ---")
    from utils.task_runner import TaskQueueManager
    tqm = TaskQueueManager()

    t1_id = await tqm.add_task({"name": "Movie Task 1"})
    t2_id = await tqm.add_task({"name": "Movie Task 2"})

    all_tasks = tqm.get_all_tasks()
    assert len(all_tasks) == 2, f"Expected 2 tasks, got {len(all_tasks)}"

    cancelled = tqm.cancel_task(t1_id)
    assert cancelled is True, "Expected t1_id cancellation to succeed"

    remaining = tqm.get_all_tasks()
    assert len(remaining) == 1, f"Expected 1 task remaining, got {len(remaining)}"
    assert remaining[0]["id"] == t2_id, "Expected remaining task to be t2_id"
    print("Task Queue Manager cancellation test passed successfully!")

async def test_task_queueing():
    print("--- Test 6: Task Queue Manager ---")
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
