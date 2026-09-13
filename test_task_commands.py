import pytest
from database.db import db
from utils.task_helpers import (
    normalize_font_text,
    parse_file_options,
    get_best_mb_file,
    get_utf16_substring,
    extract_download_link_and_quality,
    parse_setbot_result_message
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

def test_linkforge_and_ddbypass_parsing():
    # LinkForge format
    linkforge_msg = """
𝗬𝗼𝘂𝗿 𝗟𝗶𝗻𝗸 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲𝗱 !
📂 Fɪʟᴇ ɴᴀᴍᴇ : Yevade Subramanyam (2015) Telugu JC WEBRip - 480p - AVC - MP.mkv
📦 Fɪʟᴇ ꜱɪᴢᴇ : 398.48 MiB
📥 Dᴏᴡɴʟᴏᴀᴅ : https://cdn1.linkforge.dpdns.org/download/AgADWh51701
🖥ᴡᴀᴛᴄʜ  : https://cdn1.linkforge.dpdns.org/watch/AgADWh51701
"""
    dl_link, quality = extract_download_link_and_quality(linkforge_msg)
    assert dl_link == "https://cdn1.linkforge.dpdns.org/download/AgADWh51701"
    assert quality == "480p"

    # DD Bypass format
    ddbypass_msg = """
DD Bypass Bot 💥:
‣ File Name : Yevade Subramanyam (2015) Telugu.JC.WEBRip.1080p.AVC.[DD+5.1.mkv
‣ File Size : 3.78 GB
➙ Download : https://dd-stream.vercel.app/download?path=6aa65cd31b844f6c759c3caf
➙ Watch Online : https://dd-stream.vercel.app/watch?path=6aa65cd31b844f6c759c3caf
"""
    dl_link2, quality2 = extract_download_link_and_quality(ddbypass_msg)
    assert dl_link2 == "https://dd-stream.vercel.app/download?path=6aa65cd31b844f6c759c3caf"
    assert quality2 == "1080p"

def test_setbot_filtering():
    # Normal command should be ignored
    cmd_msg = "/start get-12345"
    res1 = parse_setbot_result_message(cmd_msg)
    assert res1["is_valid"] is False

    # Valid result message
    valid_setbot_msg = """
First Filename: Darling 2010 720p.mkv
First Caption: Darling 2010 720p.mkv
Last Filename: Darling 2010 720p.mkv
Last Caption: Darling 2010 720p.mkv

Here is your link:
https://telegram.me/MOVIESzoneFLIX_BOT?start=Z2V0LTEzMjk2OTAyNDMxNjUwODQ
"""
    res2 = parse_setbot_result_message(valid_setbot_msg)
    assert res2["is_valid"] is True
    assert res2["quality"] == "720p"
    assert res2["link"] == "https://telegram.me/MOVIESzoneFLIX_BOT?start=Z2V0LTEzMjk2OTAyNDMxNjUwODQ"

def test_duplicate_line_parsing():
    sample_text = (
        "1. [327.92 MB] Paradise PD S01E08 Task Force 1080p NF WEB DL ENG DDP5 1 mkv\n"
        "2. [327.92 MB] Paradise PD S01E08 Task Force 1080p NF WEB DL ENG DDP5 1 mkv\n"
    )

    class MockEntityType:
        name = "TEXT_LINK"

    class MockEntity:
        type = MockEntityType()
        line1_len = len("1. [327.92 MB] Paradise PD S01E08 Task Force 1080p NF WEB DL ENG DDP5 1 mkv\n".encode("utf-16-le")) // 2
        offset = line1_len + 5
        length = 20
        url = "https://t.me/test_bot?start=link2"

    parsed = parse_file_options(sample_text, entities=[MockEntity()])
    assert len(parsed) == 2
    assert parsed[0]["deep_link"] is None
    assert parsed[1]["deep_link"] == "https://t.me/test_bot?start=link2"

@pytest.mark.asyncio
async def test_task_queue_slot_assignment():
    await db.connect()
    await db.set_setting("lgroup_commands", ["/l", "/l2", "/l3"])

    slots = await task_queue_manager.get_configured_slots()
    assert slots == ["/l", "/l2", "/l3"]

    task1 = await task_queue_manager.add_task("Movie 1", "https://link1", "Season 1", 12345, files=[(123, 456)])
    assert task1.id in task_queue_manager.tasks
    assert len(task1.files) == 1

@pytest.mark.asyncio
async def test_monitorbots_setting_persistence():
    await db.connect()
    bots = ["@test_bot1", "@test_bot2", "@test_bot3"]
    await db.set_setting("monitorbots", ",".join(bots))

    res = await db.get_setting("monitorbots")
    assert res == "@test_bot1,@test_bot2,@test_bot3"
