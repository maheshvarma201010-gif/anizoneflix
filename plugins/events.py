from pyrogram import Client, filters, ContinuePropagation
from database.db import db
from core.logger import logger
from utils.parser import parse_filename

@Client.on_message(filters.all, group=-3)
async def debug_logger(client, message):
    # logger.debug(f"UPDATE: {message.chat.id} -> {message.text or 'MEDIA'}")
    raise ContinuePropagation

@Client.on_message(filters.all, group=-2)
async def auto_file_grouping(client, message):
    if (message.document or message.video) and message.from_user and not message.from_user.is_bot:
        try:
            fname = message.document.file_name if message.document else "video.mp4"
            parsed = parse_filename(fname)
            if await db.ping():
                anime = await db.anime.find_one({"title": {"$regex": parsed["title"], "$options": "i"}})
                if anime:
                    await db.add_episode({
                        "mal_id": anime["mal_id"], "season": parsed["season"], "episode": parsed["episode"],
                        "quality": parsed["quality"], "audio": parsed["audio"], "codec": parsed["codec"],
                        "file_id": message.document.file_id if message.document else message.video.file_id,
                        "file_name": fname, "file_size": "N/A", "views": 0, "downloads": 0
                    })
                    logger.info(f"Auto-Link Success: {fname} -> {anime['title']}")
        except Exception as e:
            logger.error(f"Auto-Link Error: {e}")

    raise ContinuePropagation
