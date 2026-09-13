import pytest
from database.db import db
from utils.task_helpers import (
    normalize_font_text,
    parse_file_options,
    get_best_mb_file,
    get_utf16_substring
)
from utils.task_runner import task_queue_manager

@pytest.mark.asyncio
async def test_db_settings_persistence():
    await db.connect()
    await db.set_setting("test_key", "test_val")
    res = await db.get_setting("test_key")
    assert res == "test_val"

def test_font_normalization():
    fancy_str = "🏷 ᴛɪᴛʟᴇ : task"
    normalized = normalize_font_text(fancy_str)
    assert "TITLE" in normalized.upper()
    assert "task" in normalized

def test_duplicate_line_parsing():
    sample_text = (
        "1. [327.92 MB] Paradise PD S01E08 Task Force 1080p NF WEB DL ENG DDP5 1 mkv\n"
        "2. [327.92 MB] Paradise PD S01E08 Task Force 1080p NF WEB DL ENG DDP5 1 mkv\n"
    )

    class MockEntityType:
        name = "TEXT_LINK"

    class MockEntity:
        type = MockEntityType()
        # Entity attached to line 2 (offset starts after line 1)
        line1_len = len("1. [327.92 MB] Paradise PD S01E08 Task Force 1080p NF WEB DL ENG DDP5 1 mkv\n".encode("utf-16-le")) // 2
        offset = line1_len + 5
        length = 20
        url = "https://t.me/test_bot?start=link2"

    parsed = parse_file_options(sample_text, entities=[MockEntity()])
    assert len(parsed) == 2
    assert parsed[0]["deep_link"] is None
    assert parsed[1]["deep_link"] == "https://t.me/test_bot?start=link2"

def test_file_parsing_and_mb_filter():
    sample_text = """
🏷 ᴛɪᴛʟᴇ : task
🧱 ᴛᴏᴛᴀʟ ꜰɪʟᴇꜱ : 27

Your Requested Files Are Here

1. [327.92 MB] Paradise PD S01E08 Task Force 1080p NF WEB DL ENG DDP5 1 mkv
2. [327.92 MB] Paradise PD S01E08 Task Force 1080p NF WEB DL ENG DDP5 1 mkv
3. [1.13 GB] Bigg Boss S08E02 Day 1 A Task For Third Che mkv
4. [540.48 MB] Bigg Boss S08E02 Day 1 A Task For Third Che mkv
5. [252.51 MB] Bigg Boss S08E02 Day 1 A Task For Third Che mkv
6. [120.84 MB] Bigg Boss S08E02 Day 1 A Task for the Third Chief 360p DSNP mkv
7. [540.48 MB] Bigg Boss S08E02 Day 1 A Task for the Third Chief 720p DSNP mkv
8. [252.51 MB] Bigg Boss S08E02 Day 1 A Task for the Third Chief 480p DSNP mkv
9. [1.28 GB] Bigg Boss S08E02 Day 1 A Task for the Third Chief 1080p DSNP mkv
"""
    parsed = parse_file_options(sample_text)
    assert len(parsed) == 9

    # Test filtering 480p highest MB size
    best_480p = get_best_mb_file(parsed, quality_filter="480p")
    assert best_480p is not None
    assert best_480p["is_mb"] is True
    assert best_480p["size_mb"] == 252.51

    # Test filtering 720p highest MB size
    best_720p = get_best_mb_file(parsed, quality_filter="720p")
    assert best_720p is not None
    assert best_720p["is_mb"] is True
    assert best_720p["size_mb"] == 540.48

@pytest.mark.asyncio
async def test_task_queue_slot_assignment():
    await db.connect()
    await db.set_setting("lgroup_commands", ["/l", "/l2", "/l3"])

    slots = await task_queue_manager.get_configured_slots()
    assert slots == ["/l", "/l2", "/l3"]

    task1 = await task_queue_manager.add_task("Movie 1", "https://link1", "Season 1", 12345)
    assert task1.id in task_queue_manager.tasks
