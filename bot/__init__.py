import asyncio
import logging
import os
import traceback
from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, CallbackQuery
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from config.config import Config
from api.media_api import media_api
from database.db import db
from utils.utils import slugify

# Setup Logging
logger = logging.getLogger("OTT_BOT")
logger.setLevel(logging.INFO)

# Global bot instance
bot = Client(
    "movie_ott_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    in_memory=True
)

user_state = {}

async def is_authorized(user_id):
    if not user_id: return False
    if user_id in Config.ADMIN_IDS:
        return True
    try:
        # Check DB Admins
        user = await db.users.find_one({"user_id": user_id, "is_admin": True})
        return user is not None
    except Exception as e:
        logger.error(f"Auth check error for {user_id}: {e}")
        return False

# --- Handler Functions ---

async def log_all_updates(client: Client, message: Message):
    logger.info(f"BOT RECEIVED: Chat={message.chat.id} User={message.from_user.id if message.from_user else 'None'} Text='{message.text or 'Media'}'")
    raise ContinuePropagation

async def start_handler(client: Client, message: Message):
    logger.info(f"Start command from {message.from_user.id}")
    await message.reply_text(
        "🎬 **MovieOTT Management Bot**\n\n"
        "Status: **ONLINE** 🚀\n\n"
        "Commands:\n"
        "• `/search <query>` - Find and import from TMDB\n"
        "• `/add_movie` - Manual Movie Entry\n"
        "• `/add_series` - Manual Series Entry\n"
        "• `/help` - Admin Help\n"
        "• `/ping` - Status Check"
    )

async def ping_handler(client: Client, message: Message):
    await message.reply_text("🏓 **Pong!** Bot is alive and responsive.")

async def help_handler(client: Client, message: Message):
    await message.reply_text(
        "🛠 **Admin Information**\n\n"
        "• Use `/search <name>` to find media on TMDB.\n"
        "• Select the 'Import' button to add it to the platform.\n"
        "• Manual entries: `/add_movie` or `/add_series`.\n"
        "• Use `/cancel` to abort any active process."
    )

async def search_handler(client: Client, message: Message):
    if not await is_authorized(message.from_user.id):
        return await message.reply("🚫 **Access Denied.** Admins only.")

    query = " ".join(message.command[1:])
    if not query:
        return await message.reply("💡 Usage: `/search <name>`")

    msg = await message.reply("🔍 **Searching TMDB...**")
    try:
        results = await media_api.search_tmdb(query)
        if not results:
            return await msg.edit("😔 No matches found on TMDB.")

        text = "🎯 **TMDB Results:**\n\n"
        buttons = []
        for i, res in enumerate(results[:8], 1):
            text += f"**{i}.** {res['title']} ({res['year']}) `[{res['type'].upper()}]`\n"
            buttons.append([InlineKeyboardButton(f"Import {i}", callback_data=f"add_{res['type']}_{res['id']}")])

        await msg.edit(text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Search Error: {e}")
        await msg.edit(f"❌ **Error:** `{e}`")

async def add_media_callback(client: Client, callback_query: CallbackQuery):
    if not await is_authorized(callback_query.from_user.id):
        return await callback_query.answer("Unauthorized", show_alert=True)

    try:
        data_parts = callback_query.data.split("_")
        m_type = data_parts[1]
        m_id = data_parts[2]

        await callback_query.message.edit_text(f"⏳ **Importing {m_type} ID {m_id}...**")

        details = await media_api.get_tmdb_details(m_type, m_id)
        if not details:
            return await callback_query.message.edit_text("❌ Failed to fetch details.")

        title = details.get("title") or details.get("name")
        slug = slugify(title)

        media_data = {
            "id": str(m_id),
            "tmdb_id": int(m_id),
            "title": title,
            "slug": slug,
            "type": "movie" if m_type == "movie" else "tv",
            "image": f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}" if details.get('poster_path') else Config.LOGO_URL,
            "backdrop": f"https://image.tmdb.org/t/p/original{details.get('backdrop_path')}" if details.get('backdrop_path') else None,
            "synopsis": details.get("overview"),
            "score": details.get("vote_average", 0),
            "year": (details.get("release_date") or details.get("first_air_date") or "0000")[:4],
            "genres": [g["name"] for g in details.get("genres", [])],
            "runtime": f"{details.get('runtime', 0)} min" if m_type == "movie" else f"{details.get('number_of_seasons')} Seasons",
            "seasons_links": {}
        }

        await db.add_media(media_data)
        await callback_query.message.edit_text(
            f"✅ **Import Successful!**\n\n"
            f"🎬 **Title:** `{title}`\n"
            f"🔗 **URL:** {Config.BASE_URL}/watch/{slug}"
        )
    except Exception as e:
        logger.error(f"Import Error: {e}")
        await callback_query.message.edit_text(f"❌ **System Error:** `{e}`")

async def manual_add_handler(client: Client, message: Message):
    if not message.from_user or not await is_authorized(message.from_user.id): return
    m_type = "movie" if "movie" in message.text else "tv"
    user_state[message.from_user.id] = {"action": "ask_title", "type": m_type}
    await message.reply(f"📝 Send **Title** for the {m_type}:")

async def interaction_handler(client: Client, message: Message):
    if not message.from_user: return
    state = user_state.get(message.from_user.id)
    if not state: return

    uid = message.from_user.id
    if state["action"] == "ask_title":
        user_state[uid].update({"title": message.text, "action": "ask_year"})
        await message.reply("📅 Send **Release Year**:")
    elif state["action"] == "ask_year":
        user_state[uid].update({"year": message.text, "action": "ask_poster"})
        await message.reply("🖼 Send **Poster URL**:")
    elif state["action"] == "ask_poster":
        data = user_state[uid]
        slug = slugify(data["title"])
        await db.add_media({
            "id": f"man_{slug}", "title": data["title"], "slug": slug,
            "type": data["type"], "year": data["year"], "image": message.text, "seasons_links": {}
        })
        await message.reply(f"🚀 **Published!**\nURL: {Config.BASE_URL}/watch/{slug}")
        del user_state[uid]

async def cancel_handler(client: Client, message: Message):
    if message.from_user:
        user_state.pop(message.from_user.id, None)
    await message.reply("✨ Process cancelled.")

# --- Registration ---

def register_handlers(client: Client):
    logger.info("Registering all bot handlers...")

    # Global logger (group -1)
    client.add_handler(MessageHandler(log_all_updates, filters.all), group=-1)

    # Command handlers (group 0)
    client.add_handler(MessageHandler(start_handler, filters.command("start")))
    client.add_handler(MessageHandler(ping_handler, filters.command("ping")))
    client.add_handler(MessageHandler(help_handler, filters.command("help")))
    client.add_handler(MessageHandler(search_handler, filters.command("search")))
    client.add_handler(MessageHandler(manual_add_handler, filters.command(["add_movie", "add_series"])))
    client.add_handler(MessageHandler(cancel_handler, filters.command("cancel")))

    # Callback query handler
    client.add_handler(CallbackQueryHandler(add_media_callback, filters.regex(r"^add_")))

    # Text interaction handler (group 1)
    client.add_handler(MessageHandler(interaction_handler, filters.private & filters.text & ~filters.command(["start", "ping", "help", "search", "add_movie", "add_series", "cancel"])), group=1)

    logger.info("All bot handlers registered successfully.")

async def set_commands(client: Client):
    try:
        await client.set_bot_commands([
            BotCommand("start", "Start the bot"),
            BotCommand("ping", "Check bot status"),
            BotCommand("search", "Search and Import Media"),
            BotCommand("add_movie", "Add movie manually"),
            BotCommand("add_series", "Add series manually"),
            BotCommand("help", "Admin help"),
            BotCommand("cancel", "Cancel process")
        ])
        logger.info("Bot commands synchronized.")
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}")
