import pytest
import asyncio
from database.db import Database
from utils.task_runner import detect_quality, extract_download_url

@pytest.mark.asyncio
async def test_detect_quality():
    assert detect_quality("Yevade Subramanyam (2015) - 480p - AVC.mkv") == "480p"
    assert detect_quality("Yevade.Subramanyam.2015.720p.mkv") == "720p"
    assert detect_quality("Yevade Subramanyam 2015 1080p.mkv") == "1080p"
    assert detect_quality("Unknown quality filename.mkv") == "720p"

@pytest.mark.asyncio
async def test_extract_download_url():
    text1 = (
        "DD Bypass Bot 💥:\n"
        "‣ File Name : Yevade Subramanyam (2015) 480p.mkv\n"
        "‣ File Size : 398.48 MB\n"
        "➙ Download : https://dd-stream.vercel.app/download?path=123\n"
        "➙ Watch Online : https://dd-stream.vercel.app/watch?path=123"
    )
    assert extract_download_url(text1) == "https://dd-stream.vercel.app/download?path=123"

    text2 = (
        "LinkForge X Gen:\n"
        "𝗬𝗼𝘂𝗿 𝗟𝗶𝗻𝗸 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲𝗱 !\n"
        "📂 Fɪʟᴇ ɴᴀᴍᴇ : Yevade Subramanyam 2015 1080p.mkv\n"
        "📥 Dᴏᴡɴʟᴏᴀᴅ : https://cdn2.linkforge.dpdns.org/download/abc"
    )
    assert extract_download_url(text2) == "https://cdn2.linkforge.dpdns.org/download/abc"

@pytest.mark.asyncio
async def test_task_db_crud():
    db = Database()
    await db.connect()

    await db.set_setting("monitorbots", ["@bot1", "@bot2"])
    bots = await db.get_setting("monitorbots")
    assert bots == ["@bot1", "@bot2"]

    task_doc = {
        "task_id": "test_t1",
        "admin_id": 12345,
        "name": "Test Movie",
        "page_link": "https://example.com/movie",
        "group_name": "Test Group",
        "collected_files": [],
        "status": "PROCESSING_FILES",
        "step": "PROCESSING_FILES"
    }

    await db.add_task(task_doc)
    t = await db.get_task("test_t1")
    assert t is not None
    assert t["name"] == "Test Movie"

    await db.update_task("test_t1", {"status": "COMPLETED"})
    t_updated = await db.get_task("test_t1")
    assert t_updated["status"] == "COMPLETED"

    await db.delete_task("test_t1")
    t_deleted = await db.get_task("test_t1")
    assert t_deleted is None
