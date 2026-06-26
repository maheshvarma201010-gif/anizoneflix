from pyrogram import Client, filters
from config.config import Config
from database.db import db
from core.logger import logger

user_state = {}

async def is_authorized(user_id):
    try:
        if user_id in Config.ADMIN_IDS:
            return True
        return await db.is_admin(user_id)
    except Exception as e:
        logger.error(f"Authorization Check Error: {e}")
        return False

@Client.on_message(filters.command("add_page"))
async def add_page_handler(client, message):
    if not message.from_user: return
    if not await is_authorized(message.from_user.id):
        return await message.reply("🚫 **Unauthorized.**")

    title = " ".join(message.command[1:])
    user_state[message.from_user.id] = {
        "action": "edit_title",
        "anime_data": {
            "title": title or "Untitled Content",
            "synopsis": "N/A",
            "score": 8.5,
            "image": Config.LOGO_URL,
            "genres": [],
            "status": "Airing",
            "year": "2024",
            "trailer": None,
            "studios": []
        }
    }

    await message.reply(
        "📝 **Manual Page Creation**\n\n"
        f"Step 1: Calibration for `{user_state[message.from_user.id]['anime_data']['title']}`\n\n"
        "📥 Please send the **New Title** or `/skip` to maintain current:"
    )

@Client.on_message(filters.command("manual"))
async def manual_handler(client, message):
    if not message.from_user or not await is_authorized(message.from_user.id): return
    user_state[message.from_user.id] = {"action": "ask_manual_title"}
    await message.reply("📝 **Step 1: Title**\nSend Title for the custom page:")
