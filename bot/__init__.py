import asyncio
import logging
import traceback
import os
import json
import zipfile
import tempfile
from io import BytesIO
from pyrogram import Client, filters, enums, ContinuePropagation
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand
from config.config import Config
from api.media_api import media_api
from database.db import db
from utils.utils import slugify

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OTT_BOT")

bot = Client(
    "ott_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    in_memory=True
)

user_state = {}

async def is_authorized(user_id):
    if user_id in Config.ADMIN_IDS: return True
    return await db.is_admin(user_id)

async def set_commands(client):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("search", "Search Movies/Series"),
        BotCommand("add_movie", "Add a Movie"),
        BotCommand("add_series", "Add a Web Series"),
        BotCommand("categories", "Manage Categories"),
        BotCommand("del", "Remove Content"),
        BotCommand("save", "Backup/Restore"),
        BotCommand("cancel", "Cancel Process")
    ]
    await client.set_bot_commands(commands)

def register_handlers(bot: Client):
    @bot.on_message(filters.command("start"))
    async def start_handler(client, message):
        await message.reply_text(
            "🎬 **MovieOTT Management Bot**\n\n"
            "Welcome to the Movie & Web Series control center.\n\n"
            "Commands:\n"
            "• `/search <query>` - Find and add content\n"
            "• `/add_movie` - Manual movie entry\n"
            "• `/add_series` - Manual series entry\n"
            "• `/categories` - Manage genres/platforms"
        )

    @bot.on_message(filters.command("search"))
    async def search_handler(client, message):
        if not await is_authorized(message.from_user.id): return
        query = " ".join(message.command[1:])
        if not query: return await message.reply("Please provide a search query.")

        msg = await message.reply("🔍 Searching TMDB...")
        results = await media_api.search_tmdb(query)
        if not results: return await msg.edit("No results found.")

        text = "🎯 **Results from TMDB:**\n\n"
        buttons = []
        for i, res in enumerate(results[:8], 1):
            text += f"**{i}.** {res['title']} ({res['year']}) `[{res['type'].upper()}]`\n"
            buttons.append([InlineKeyboardButton(f"Add {i}", callback_data=f"add_{res['type']}_{res['id']}")])

        await msg.edit(text, reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_callback_query(filters.regex(r"^add_(movie|tv)_(\d+)"))
    async def add_media_callback(client, callback_query):
        m_type, m_id = callback_query.matches[0].groups()
        await callback_query.message.edit_text(f"⏳ Fetching details for {m_type} ID: {m_id}...")

        details = await media_api.get_tmdb_details(m_type, m_id)
        if not details: return await callback_query.message.edit_text("Failed to fetch details.")

        title = details.get("title") or details.get("name")
        slug = slugify(title)

        media_data = {
            "id": str(m_id),
            "tmdb_id": m_id,
            "title": title,
            "slug": slug,
            "type": "movie" if m_type == "movie" else "tv",
            "image": f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}",
            "backdrop": f"https://image.tmdb.org/t/p/original{details.get('backdrop_path')}",
            "synopsis": details.get("overview"),
            "score": details.get("vote_average"),
            "year": (details.get("release_date") or details.get("first_air_date") or "0000")[:4],
            "genres": [g["name"] for g in details.get("genres", [])],
            "runtime": f"{details.get('runtime', 0)} min" if m_type == "movie" else f"{details.get('number_of_seasons')} Seasons",
            "seasons_links": {}
        }

        await db.add_media(media_data)
        await callback_query.message.edit_text(f"✅ **Success!** Added `{title}`.\nURL: {Config.BASE_URL}/watch/{slug}")

    @bot.on_message(filters.command("add_movie"))
    async def add_movie_handler(client, message):
        if not await is_authorized(message.from_user.id): return
        user_state[message.from_user.id] = {"action": "ask_manual_title", "type": "movie"}
        await message.reply("📝 **Manual Movie Entry**\nSend the **Title** of the movie:")

    @bot.on_message(filters.command("add_series"))
    async def add_series_handler(client, message):
        if not await is_authorized(message.from_user.id): return
        user_state[message.from_user.id] = {"action": "ask_manual_title", "type": "tv"}
        await message.reply("📝 **Manual Series Entry**\nSend the **Title** of the web series:")

    @bot.on_message(filters.private & filters.text & ~filters.command(["start", "help", "search", "add_movie", "add_series", "categories", "del", "cancel", "save"]))
    async def interaction_handler(client, message):
        uid = message.from_user.id
        state = user_state.get(uid)
        if not state: return

        action = state.get("action")
        if action == "ask_manual_title":
            user_state[uid].update({"title": message.text, "action": "ask_manual_year"})
            await message.reply("📅 Send **Release Year**:")
        elif action == "ask_manual_year":
            user_state[uid].update({"year": message.text, "action": "ask_manual_poster"})
            await message.reply("🖼 Send **Poster URL**:")
        elif action == "ask_manual_poster":
            user_state[uid].update({"image": message.text, "action": "publish_manual"})

            data = user_state[uid]
            slug = slugify(data["title"])
            media_data = {
                "id": f"manual_{slug}",
                "title": data["title"],
                "slug": slug,
                "type": data["type"],
                "image": data["image"],
                "year": data["year"],
                "genres": ["Manual"],
                "seasons_links": {}
            }
            await db.add_media(media_data)
            await message.reply(f"🚀 **Published!** `{data['title']}`\nURL: {Config.BASE_URL}/watch/{slug}")
            del user_state[uid]

    @bot.on_message(filters.command("cancel"))
    async def cancel_handler(client, message):
        user_state.pop(message.from_user.id, None)
        await message.reply("Cancelled.")
