from pyrogram import Client, filters, enums, ContinuePropagation
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config.config import Config
from api.anime_api import anime_api
from database.db import db
from utils.utils import slugify
from bot import is_authorized, user_state, logger
import asyncio
import time

def extract_slug(text):
    from urllib.parse import unquote
    if not text: return None
    text = unquote(text.strip())
    if "/anime/" in text:
        try:
            parts = text.split("/anime/")[-1].split("/")
            slug_part = parts[0] if parts[0] else parts[1]
            return slug_part.split("?")[0].split("\n")[0].split(" ")[0].rstrip("/").strip()
        except:
            return None
    return text

@Client.on_message(filters.command("search") & filters.private)
async def search_handler(client, message, is_retry=False):
    if not await is_authorized(message.from_user.id):
        return await message.reply("🚫 **Access Denied.**")
    query = " ".join(message.command[1:]) if not is_retry else message.text
    if not query:
        user_state[message.from_user.id] = {"action": "ask_search_query"}
        return await message.reply("🛰 **Intelligence Aggregator**\n\nPlease send the **Title** of the series:")
    msg = await message.reply("📡 **Scanning Intelligence Feeds...**")
    try:
        from bot import search_results
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

@Client.on_message(filters.command("add_post") & filters.private)
async def auto_post_handler(client, message):
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

# ... More anime handlers should be added here
