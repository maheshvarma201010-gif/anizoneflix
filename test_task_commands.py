import pytest
import asyncio
from database.db import Database
from bot.task_manager import parse_file_options, extract_download_link, detect_quality_buttons, TaskManager

@pytest.mark.asyncio
async def test_db_settings():
    db = Database()
    await db._connect_mock()

    await db.set_setting("setgroup", "-100123456789")
    val = await db.get_setting("setgroup")
    assert val == "-100123456789"

    lgroup_data = {"target": "@my_lgroup", "commands": ["/l", "/l2", "/l3"]}
    await db.set_setting("setlgroup", lgroup_data)
    val2 = await db.get_setting("setlgroup")
    assert val2 == lgroup_data
    assert val2["commands"] == ["/l", "/l2", "/l3"]


def test_parse_file_options_mb_only_and_max_size():
    sample_text = """
🏷 ᴛɪᴛʟᴇ : Vishwanath and Sons
🧱 ᴛᴏᴛᴀʟ ꜰɪʟᴇꜱ : 7
⏰ ʀᴇsᴜʟᴛ ɪɴ : 1.60 Sᴇᴄᴏɴᴅs
📝 ʀᴇǫᴜᴇsᴛᴇᴅ ʙʏ : Sudheer
⚜️ ᴘᴏᴡᴇʀᴇᴅ ʙʏ : ⚡ 𝐓𝐌𝐖 𝐌𝐨𝐯𝐢𝐞𝐬 𝐆𝐫𝐨𝐮𝐩

Your Requested Files Are Here

1. [1.78 GB] Vishwanath and Sons 2026 Telugu HQ HDRip 1080p HEV mkv
2. [2.93 GB] Vishwanath and Sons 2026 Telugu TRUE WEB DL 1080p mkv
3. [1.64 GB] Vishwanath and Sons 2026 Telugu HQ HDRip 720p x264 mkv
4. [1.19 GB] Vishwanath and Sons 2026 Telugu HQ HDRip 720p x265 mkv
5. [733.18 MB] Vishwanath and Sons 2026 Telugu HQ HDRip x264 AAC mkv
6. [438.56 MB] Vishwanath and Sons 2026 Telugu HQ HDRip x264 AAC mkv
7. [302.98 MB] Vishwanath and Sons 2026 Telugu HQ HDRip x264 AAC mkv
    """

    results = parse_file_options(sample_text)
    # GB files must be ignored
    assert len(results) == 3
    for r in results:
        assert r["unit"] == "MB"

    # The files parsed should be 733.18 MB, 438.56 MB, 302.98 MB
    sizes = [r["size_mb"] for r in results]
    assert sizes == [733.18, 438.56, 302.98]

    # Pick the largest MB file size
    largest = max(results, key=lambda f: f["size_mb"])
    assert largest["index"] == 5
    assert largest["size_mb"] == 733.18


def test_extract_download_link():
    text = "Here is your stream / download link: https://t.me/c/1234/5678 - Enjoy!"
    link = extract_download_link(text)
    assert link == "https://t.me/c/1234/5678"


def test_detect_quality_buttons():
    text = "Available qualities: 480P, 720P, 1080P"
    qualities = detect_quality_buttons(None, text=text)
    labels = [q["label"] for q in qualities]
    assert "480P" in labels
    assert "720P" in labels
    assert "1080P" in labels


@pytest.mark.asyncio
async def test_task_manager_prefix_queue():
    tm = TaskManager()
    # Mock settings
    db = Database()
    await db._connect_mock()
    await db.set_setting("setlgroup", {"target": "group1", "commands": ["/l", "/l2"]})

    res1 = await tm.add_task("Movie 1", "https://link1.com", "Group A")
    res2 = await tm.add_task("Movie 2", "https://link2.com", "Group B")

    assert res1["position"] == 1
    assert res2["position"] == 2
