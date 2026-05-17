import asyncio
import logging
import traceback
import os
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config.config import Config
from api.anime_api import anime_api
from database.db import db
from utils.utils import slugify

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ANIZONEFLIX_BOT")

bot = Client(
    "anizoneflix_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    in_memory=True
)

async def set_commands(client):
    from pyrogram.types import BotCommand
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("search", "Advanced Multi-API Search"),
        BotCommand("add_post", "Automated Post (Speed Mode)"),
        BotCommand("edit", "Edit Website Post"),
        BotCommand("categories", "Manage Categories"),
        BotCommand("del", "Delete Content"),
        BotCommand("cancel", "Cancel current operation")
    ]
    await client.set_bot_commands(commands)
    logger.info("Bot commands set successfully!")

# Temporary storage
search_results = {}
user_state = {}

async def is_authorized(user_id):
    return user_id in Config.ADMIN_IDS or await db.is_admin(user_id)

def register_handlers(bot: Client):
    logger.info("Registering Advanced Handlers...")

    @bot.on_message(filters.command("start"))
    async def start_handler(client, message):
        await message.reply_text(
            "🔥 **ANIZONEFLIX ULTRA BOT READY**\n\n"
            "System connected to 10+ High-Speed Anime APIs.\n\n"
            "🛠 **Admin Commands:**\n"
            "• `/search <name>` - Ultimate Search & Add\n"
            "• `/add_post <name>` - One-Shot Auto-Post\n"
            "• `/edit <id/slug>` - Web Admin Panel Link\n"
            "• `/categories` - Website Genres\n"
            "• `/del <id>` - Remove Content"
        )

    @bot.on_message(filters.command("search"))
    async def search_handler(client, message):
        if not await is_authorized(message.from_user.id): return
        query = " ".join(message.command[1:])
        if not query: return await message.reply("❌ Usage: `/search Naruto`")

        msg = await message.reply("🚀 **Aggregating 10+ APIs (Jikan, AniList, Kitsu, TMDb, etc)...**")
        results = await anime_api.search_all(query)

        if not results:
            return await msg.edit("😔 **Zero results found.** Try another name.")

        search_results[message.from_user.id] = results
        text = "🎯 **Select correct series from Ultra-Search:**\n\n"
        for i, res in enumerate(results[:10], 1):
            text += f"**{i}.** {res['title']} ({res['year']}) `[{res['source'].upper()}]`\n"

        await msg.edit(text)
        user_state[message.from_user.id] = {"action": "select_anime"}

    @bot.on_message(filters.command("add_post"))
    async def auto_post_handler(client, message):
        if not await is_authorized(message.from_user.id): return
        query = " ".join(message.command[1:])
        if not query: return await message.reply("❌ Usage: `/add_post One Piece`")

        msg = await message.reply(f"⚡ **One-Shot Posting: {query}...**")
        results = await anime_api.search_all(query)
        if not results: return await msg.edit("❌ Not found.")

        best_match = results[0]
        details = await anime_api.get_details(best_match["source"], best_match["id"])

        if not details:
            details = {
                "title": best_match["title"], "synopsis": "N/A",
                "score": 0, "image": best_match["image"], "genres": [],
                "status": "N/A", "year": best_match["year"], "episodes": 0, "trailer": None, "studios": []
            }

        user_state[message.from_user.id] = {"action": "ask_category", "anime_data": details, "season": "1"}

        # Fetch categories for selection
        cats = await db.get_all_categories()
        if not cats:
            # Create a default "Anime" category if none exist
            await db.add_category("Anime")
            cats = [{"name": "Anime"}]

        buttons = []
        for c in cats:
            buttons.append([InlineKeyboardButton(c['name'], callback_data=f"setcat_{c['name']}")])

        await message.reply_photo(
            photo=details["image"] if details["image"] else Config.LOGO_URL,
            caption=f"🎬 **{details['title']}**\n\nSelect a **Category** to publish in:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        await msg.delete()

    @bot.on_callback_query(filters.regex("^setcat_"))
    async def set_category_callback(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state or state["action"] != "ask_category": return

        category = callback_query.data.split("_")[1]
        data = state["anime_data"]
        season = state["season"]
        slug = slugify(f"{data['title']} S{season}")

        anime_entry = {
            "mal_id": f"auto_{slug}",
            "title": data["title"],
            "slug": slug,
            "season": season,
            "synopsis": data["synopsis"],
            "score": data["score"],
            "image": data["image"],
            "genres": data["genres"],
            "category": category,
            "status": data["status"],
            "year": data["year"],
            "episodes": data["episodes"],
            "trailer": data["trailer"],
            "studios": data.get("studios", []),
            "custom_buttons": []
        }

        try:
            await db.anime.update_one({"slug": slug}, {"$set": anime_entry}, upsert=True)
            await callback_query.message.edit_caption(
                caption=f"✅ **Published to {category}!**\n🌐 URL: {Config.BASE_URL}/anime/{slug}",
                reply_markup=None
            )
            del user_state[uid]
        except Exception as e:
            await callback_query.answer(f"DB Error: {e}", show_alert=True)

    @bot.on_message(filters.command("series"))
    async def series_list_handler(client, message):
        if not await is_authorized(message.from_user.id): return
        args = message.command[1:]
        if not args: return await message.reply("❌ Usage: `/series <slug>`")

        slug = args[0]
        anime = await db.get_anime_by_slug(slug)
        if not anime: return await message.reply("❌ Not found.")

        episodes = await db.get_episodes(anime["mal_id"])
        if not episodes: return await message.reply("❌ No episodes found.")

        # Sort number wise
        episodes.sort(key=lambda x: x.get("episode", 0))

        text = f"📦 **Available Content for: {anime['title']}**\n\n"
        for ep in episodes:
            text += f"• **EP {ep['episode']}** | {ep['quality']} | {ep['audio']}\n"

        await message.reply(text)

    @bot.on_message(filters.command("edit"))
    async def edit_handler(client, message):
        if not await is_authorized(message.from_user.id): return
        from utils.auth import create_access_token
        token = create_access_token({"user_id": message.from_user.id, "is_admin": True})
        login_url = f"{Config.BASE_URL}/admin/login?token={token}"
        await message.reply(f"🛠 **Admin Portal Access:**\n\n🔗 [Open Web Dashboard]({login_url})", disable_web_page_preview=True)

    @bot.on_message(filters.private & filters.text & ~filters.command(["start", "help", "search", "add_post", "edit", "categories", "del", "cancel"]))
    async def interaction_handler(client, message):
        uid = message.from_user.id
        state = user_state.get(uid)
        if not state: return

        if state["action"] == "select_anime":
            try:
                idx = int(message.text) - 1
                selected = search_results[uid][idx]
                msg = await message.reply("⏳ **Fetching High-Speed Metadata...**")
                details = await anime_api.get_details(selected["source"], selected["id"])

                if not details:
                    details = {"title": selected["title"], "image": selected["image"], "synopsis": "N/A", "score": 0, "genres": [], "year": selected["year"], "status": "N/A", "episodes": 0, "trailer": None}

                user_state[uid] = {"action": "ask_season", "anime_data": details}
                await message.reply_photo(photo=details["image"] if details["image"] else Config.LOGO_URL, caption=f"🎬 **{details['title']}**\n\nPlease send the **Season Number** (e.g. 1)")
                await msg.delete()
            except:
                await message.reply("❌ Invalid choice. Send a number.")

        elif state["action"] == "ask_season":
            user_state[uid]["season"] = message.text
            user_state[uid]["action"] = "ask_category"

            # Fetch categories
            cats = await db.get_all_categories()
            if not cats:
                await db.add_category("Anime")
                cats = [{"name": "Anime"}]

            buttons = []
            for c in cats:
                buttons.append([InlineKeyboardButton(c['name'], callback_data=f"setcat_{c['name']}")])

            await message.reply("📂 **Select Category:**", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_message(filters.all, group=-2)
    async def auto_file_grouping(client, message):
        if not message.document and not message.video: return
        from utils.parser import parse_filename
        fname = message.document.file_name if message.document else "video.mp4"
        parsed = parse_filename(fname)

        anime = await db.anime.find_one({"title": {"$regex": parsed["title"], "$options": "i"}})
        if anime:
            await db.add_episode({
                "mal_id": anime["mal_id"], "season": parsed["season"], "episode": parsed["episode"],
                "quality": parsed["quality"], "audio": parsed["audio"], "codec": parsed["codec"],
                "file_id": message.document.file_id if message.document else message.video.file_id,
                "file_name": fname, "file_size": "N/A", "views": 0, "downloads": 0
            })
            logger.info(f"Auto-Link: {fname} -> {anime['title']}")

    @bot.on_message(filters.command("cancel"))
    async def cancel_handler(client, message):
        user_state.pop(message.from_user.id, None)
        await message.reply("Operation cancelled.")
