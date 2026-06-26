import asyncio
from pyrogram import Client, filters
from api.anime_api import anime_api
from core.logger import logger
from database.db import db

search_results = {}
user_state = {}

async def is_authorized(user_id):
    from config.config import Config
    try:
        if user_id in Config.ADMIN_IDS:
            return True
        return await db.is_admin(user_id)
    except Exception as e:
        logger.error(f"Authorization Check Error: {e}")
        return False

@Client.on_message(filters.command("search"))
async def search_handler(client, message, is_retry=False):
    if not message.from_user: return
    if not await is_authorized(message.from_user.id):
        return await message.reply("🚫 **Access Denied.**")

    query = " ".join(message.command[1:]) if not is_retry else message.text
    if not query:
        user_state[message.from_user.id] = {"action": "ask_search_query"}
        return await message.reply("🛰 **Intelligence Aggregator**\n\nPlease send the **Title** of the series:")

    msg = await message.reply("📡 **Scanning Intelligence Feeds...**")
    try:
        results = await asyncio.wait_for(anime_api.search_all(query), timeout=5)
        if not results:
            user_state[message.from_user.id] = {"action": "ask_search_query"}
            return await msg.edit("😔 **Search Exhausted.** No matches found. Try again:")

        search_results[message.from_user.id] = results
        text = "🎯 **Select Match from Feed:**\n\n"
        for i, res in enumerate(results[:10], 1):
            text += f"**{i}.** {res['title']} ({res['year']}) `[{res['source'].upper()}]`\n"

        await msg.edit(text)
        user_state[message.from_user.id] = {"action": "select_anime"}
    except Exception as e:
        logger.error(f"Search Error: {e}")
        await msg.edit("❌ **Intelligence Feed Failure.** Try again.")
