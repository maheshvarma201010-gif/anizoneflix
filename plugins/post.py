from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config.config import Config
from api.anime_api import anime_api
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

@Client.on_message(filters.command("add_post"))
async def auto_post_handler(client, message):
    if not message.from_user: return
    if not await is_authorized(message.from_user.id):
        return await message.reply("🚫 **Unauthorized.**")

    query = " ".join(message.command[1:])
    if not query: return await message.reply("💡 **Usage:** `/add_post <name>`")

    msg = await message.reply(f"⚡ **Rapid Publication: {query}...**")
    try:
        results = await anime_api.search_all(query)
        if not results: return await msg.edit("❌ **Publication Failed:** No match found.")

        best_match = results[0]
        details = await anime_api.get_details(best_match["source"], best_match["id"])
        if not details:
            details = {"title": best_match["title"], "synopsis": "N/A", "score": 0, "image": best_match["image"], "genres": [], "status": "N/A", "year": best_match["year"], "episodes": 0, "trailer": None, "studios": []}

        user_state[message.from_user.id] = {"action": "ask_category", "anime_data": details, "season": "1", "image": details["image"]}
        cats = await db.get_all_categories()
        buttons = [[InlineKeyboardButton(c['name'], callback_data=f"setcat_{c['name']}")] for c in (cats if cats else [{"name": "Anime"}])]
        await message.reply_photo(photo=details["image"] if details["image"] else Config.LOGO_URL, caption=f"🎬 **Archive Ready:** `{details['title']}`\n\nTarget **Category**:", reply_markup=InlineKeyboardMarkup(buttons))
        await msg.delete()
    except Exception as e:
        logger.error(f"Add Post Error: {e}")
        await msg.edit("❌ **Rapid Deployment Failure.**")
