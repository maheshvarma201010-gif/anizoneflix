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
        BotCommand("edit", "Manage Series / Episode"),
        BotCommand("change_poster", "Change Series Poster"),
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
    logger.info("Registering Advanced Handlers v2.0...")

    @bot.on_message(filters.command("ping"))
    async def ping_handler(client, message):
        await message.reply("🏓 **Pong!** Bot is online and responsive.")

    @bot.on_message(filters.command("start"))
    async def start_handler(client, message):
        await message.reply_photo(
            photo=Config.LOGO_URL,
            caption=(
                "🔥 **ANIZONEFLIX ULTRA v2.0**\n\n"
                "Welcome to the next-gen Anime Management Bot. I am now equipped with 11+ high-speed APIs to provide a seamless automated posting experience.\n\n"
                "🛠 **Popular Commands:**\n"
                "• `/search <name>` - Ultra Search Aggregator\n"
                "• `/add_post <name>` - Instant One-Shot Post\n"
                "• `/help` - View Full Admin Suite Guide"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Visit Website", url=Config.BASE_URL)],
                [InlineKeyboardButton("📚 Admin Guide", callback_data="help_guide")]
            ])
        )

    @bot.on_message(filters.command("help"))
    async def help_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("❌ **Access Denied.** This area is reserved for authorized administrators.")

        text = (
            "🚀 **ANIZONEFLIX ULTRA: Admin Guide**\n\n"
            "**CORE COMMANDS**\n"
            "• `/search <name>`: Scans 11 APIs (MAL, AniList, etc.) and allows interactive setup.\n"
            "• `/add_post <name>`: Automatically fetches and publishes the #1 match instantly.\n"
            "• `/edit`: Generates a secure token for the **Web Admin Panel**.\n"
            "• `/series <slug>`: Displays all currently loaded episodes for a series.\n\n"
            "**MANAGEMENT**\n"
            "• `/categories`: Manage site genres/tags.\n"
            "• `/del <slug/id>`: Permanently remove a post and its files.\n"
            "• `/cancel`: Terminate any ongoing interactive session.\n\n"
            "**NEW v2.0 FEATURES**\n"
            "✅ Multi-Season Support (e.g., send '1,2,3')\n"
            "✅ Separate Quality Links (480p, 720p, 1080p)\n"
            "✅ Custom Thumbnail Choice (API vs. Manual)\n"
            "✅ Infinite Web Pagination\n"
            "✅ Telegram-Themed Glassmorphism UI"
        )
        await message.reply_text(text)

    @bot.on_callback_query(filters.regex("^help_guide$"))
    async def help_callback(client, callback_query):
        await help_handler(client, callback_query.message)
        await callback_query.answer()

    @bot.on_message(filters.command("search"))
    async def search_handler(client, message, is_retry=False):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("❌ **Unauthorized.**")

        query = " ".join(message.command[1:]) if not is_retry else message.text
        if not query:
            user_state[message.from_user.id] = {"action": "ask_search_query"}
            return await message.reply("🔍 **Ultra-Search Aggregator**\n\nPlease send the **Title** of the anime you want to search for:")

        msg = await message.reply("🔍 **Searching across Ultra-APIs...**")
        try:
            # Set a hard timeout for the entire search operation
            results = await asyncio.wait_for(anime_api.search_all(query), timeout=5)
        except asyncio.TimeoutError:
            results = []
            logger.error("Search timed out")

        if not results:
            user_state[message.from_user.id] = {"action": "ask_search_query"}
            return await msg.edit("😔 **No results found or search timed out.** Try a simpler title:")

        search_results[message.from_user.id] = results
        text = "🎯 **Select series from Ultra-Search:**\n\n"
        for i, res in enumerate(results[:10], 1):
            text += f"**{i}.** {res['title']} ({res['year']}) `[{res['source'].upper()}]`\n"

        await msg.edit(text)
        user_state[message.from_user.id] = {"action": "select_anime"}

    @bot.on_message(filters.command("add_post"))
    async def auto_post_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("❌ **Unauthorized.**")

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

        user_state[message.from_user.id] = {"action": "ask_category", "anime_data": details, "season": "1", "image": details["image"]}

        cats = await db.get_all_categories()
        if not cats:
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

    @bot.on_message(filters.command("edit"))
    async def edit_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("❌ **Unauthorized.**")

        buttons = [
            [InlineKeyboardButton("🌍 Open Web Admin", callback_data="open_web_admin")],
            [InlineKeyboardButton("📦 Edit Series (Bot)", callback_data="bot_edit_series")],
            [InlineKeyboardButton("🎬 Add/Edit Episode", callback_data="bot_edit_episode")]
        ]
        await message.reply("🛠 **Admin Suite v2.0**\nChoose your management method:", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_callback_query(filters.regex("^open_web_admin$"))
    async def web_admin_cb(client, callback_query):
        from utils.auth import create_access_token
        token = create_access_token({"user_id": callback_query.from_user.id, "is_admin": True})
        login_url = f"{Config.BASE_URL}/admin/login?token={token}"
        await callback_query.message.edit_text(
            f"🛠 **Web Admin Portal:**\n\n🔗 [One-Click Login]({login_url})\n\n*Token expires in 24 hours.*",
            disable_web_page_preview=True
        )

    @bot.on_callback_query(filters.regex("^bot_edit_series$"))
    async def bot_edit_series_cb(client, callback_query):
        user_state[callback_query.from_user.id] = {"action": "edit_series_search"}
        await callback_query.message.edit_text("🔍 Enter the **Title** or **Slug** of the series to edit:")

    @bot.on_callback_query(filters.regex("^bot_edit_episode$"))
    async def bot_edit_episode_cb(client, callback_query):
        user_state[callback_query.from_user.id] = {"action": "edit_episode_search"}
        await callback_query.message.edit_text("🔍 Enter the **Title** or **Slug** of the series to add episodes to:")

    @bot.on_message(filters.command("change_poster"))
    async def change_poster_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("❌ **Unauthorized.**")

        args = message.command[1:]
        if len(args) < 1: return await message.reply("❌ Usage: `/change_poster <url>` (Reply to a series message or use after /edit)")

        url = args[0]
        # Logic to update poster depends on context, for now we ask for slug if not in state
        user_state[message.from_user.id] = {"action": "change_poster_slug", "new_url": url}
        await message.reply("🔍 Enter the **Slug** of the series to update:")

    @bot.on_message(filters.command("series"))
    async def series_list_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("❌ **Unauthorized.**")

        args = message.command[1:]
        if not args: return await message.reply("❌ Usage: `/series <slug>`")

        slug = args[0]
        anime = await db.get_anime_by_slug(slug)
        if not anime: return await message.reply("❌ Not found.")

        episodes = await db.get_episodes(anime["mal_id"])
        if not episodes: return await message.reply("❌ No episodes found.")

        episodes.sort(key=lambda x: x.get("episode", 0))

        text = f"📦 **Available Content for: {anime['title']}**\n\n"
        for ep in episodes:
            text += f"• **EP {ep['episode']}** | {ep['quality']} | {ep['audio']}\n"

        await message.reply(text)

    @bot.on_message(filters.command("del"))
    async def delete_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("❌ **Unauthorized.**")

        query = " ".join(message.command[1:])

        # Check if query is a full URL or if reply contains one
        if not query and message.reply_to_message:
            query = message.reply_to_message.text or message.reply_to_message.caption or ""

        if "http" in query and "/anime/" in query:
            # Extract slug from URL like https://domain.com/anime/slug
            query = query.split("/anime/")[-1].split("?")[0].split("\n")[0].strip()

        if not query:
            return await message.reply("❌ Usage: `/del <slug, title, or URL>` (or reply to a series message)")

        # Try slug first
        res = await db.delete_anime_by_slug(query)
        if res.deleted_count > 0:
            return await message.reply(f"✅ **Deleted Series & Content:** `{query}`")

        # Try title search
        anime = await db.anime.find_one({"title": {"$regex": query, "$options": "i"}})
        if anime:
            await db.delete_anime_by_slug(anime["slug"])
            return await message.reply(f"✅ **Deleted (via title search):** `{anime['title']}`")

        await message.reply(f"❓ **Could not find:** `{query}`")

    @bot.on_message(filters.private & filters.text & ~filters.command(["start", "help", "search", "add_post", "edit", "categories", "del", "cancel", "series", "change_poster", "ping"]))
    async def unified_interaction_handler(client, message):
        uid = message.from_user.id
        state = user_state.get(uid)
        if not state: return

        action = state.get("action", "")

        # -1. Ask Search Query
        if action == "ask_search_query":
            return await search_handler(client, message, is_retry=True)

        # 0. Change Poster
        if action == "change_poster_slug":
            slug = message.text.strip()
            res = await db.anime.update_one({"slug": slug}, {"$set": {"image": state["new_url"]}})
            if res.modified_count:
                await message.reply(f"✅ **Poster Updated for:** {slug}")
            else:
                await message.reply("❌ Series not found.")
            del user_state[uid]

        # 0.1 Edit Series / Episode Search
        elif action in ["edit_series_search", "edit_episode_search"]:
            query = message.text.strip()
            anime = await db.get_anime_by_slug(query) or await db.anime.find_one({"title": {"$regex": query, "$options": "i"}})
            if not anime: return await message.reply("❌ Series not found. Try again.")

            if action == "edit_series_search":
                user_state[uid] = {"action": "ask_seasons", "anime_data": anime, "image": anime["image"]}
                await message.reply(f"📦 **Editing:** {anime['title']}\n\n🔢 Send **Season Numbers** (e.g. `1` or `1,2,3`):")
            else:
                user_state[uid] = {"action": "ask_ep_season", "anime_data": anime}
                await message.reply(f"🎬 **Add Episodes to:** {anime['title']}\n\n🔢 Enter **Season Number**:")

        # 0.2 Edit Episode Flow
        elif action == "ask_ep_season":
            user_state[uid]["season"] = message.text.strip()
            user_state[uid]["action"] = "ask_ep_number"
            await message.reply("🔢 Enter **Episode Number**:")

        elif action == "ask_ep_number":
            user_state[uid]["episode"] = message.text.strip()
            user_state[uid]["action"] = "ask_ep_links"
            await message.reply("🔗 Send **Download Link** or **File ID**:")

        elif action == "ask_ep_links":
            # Simplified episode addition
            data = state["anime_data"]
            ep_data = {
                "mal_id": data["mal_id"],
                "season": state["season"],
                "episode": int(state["episode"]),
                "quality": "HD",
                "audio": "Japanese",
                "file_id": message.text,
                "views": 0
            }
            await db.add_episode(ep_data)
            await message.reply(f"✅ **Episode {state['episode']} added to {data['title']}!**")
            del user_state[uid]

        # 1. Select Series
        elif action == "select_anime":
            try:
                idx = int(message.text) - 1
                selected = search_results[uid][idx]
                msg = await message.reply("⏳ **Fetching Industrial-Grade Metadata...**")
                details = await anime_api.get_details(selected["source"], selected["id"])

                if not details:
                    details = {"title": selected["title"], "image": selected["image"], "synopsis": "N/A", "score": 0, "genres": [], "year": selected["year"], "status": "N/A", "episodes": 0, "trailer": None}

                user_state[uid].update({"action": "edit_title", "anime_data": details})
                await msg.edit(f"📝 **Step 1: Edit Title**\n\nCurrent: `{details['title']}`\n\nSend new title or /skip:")
            except:
                await message.reply("❌ Invalid choice. Send a number.")

        # Metadata Edit Flow
        elif action == "edit_title":
            if message.text != "/skip":
                user_state[uid]["anime_data"]["title"] = message.text
            user_state[uid]["action"] = "edit_synopsis"
            await message.reply(f"📝 **Step 2: Edit Synopsis**\n\nCurrent: `{user_state[uid]['anime_data']['synopsis'][:100]}...`\n\nSend new synopsis or /skip:")

        elif action == "edit_synopsis":
            if message.text != "/skip":
                user_state[uid]["anime_data"]["synopsis"] = message.text
            user_state[uid]["action"] = "edit_score"
            await message.reply(f"📝 **Step 3: Edit Score**\n\nCurrent: `{user_state[uid]['anime_data']['score']}`\n\nSend new score (e.g. 8.5) or /skip:")

        elif action == "edit_score":
            if message.text != "/skip":
                try: user_state[uid]["anime_data"]["score"] = float(message.text)
                except: pass

            details = user_state[uid]["anime_data"]
            user_state[uid]["action"] = "ask_image_choice"
            buttons = [
                [InlineKeyboardButton("🖼 Use API Poster", callback_data="img_api")],
                [InlineKeyboardButton("🔗 Manual URL", callback_data="img_manual")]
            ]
            await message.reply_photo(
                photo=details["image"] if details["image"] else Config.LOGO_URL,
                caption=f"📝 **Step 4: Poster Choice**\n\nCurrent Poster shown below. Choose source:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # 2. Manual Image URL
        elif action == "ask_manual_img":
            user_state[uid]["image"] = message.text
            user_state[uid]["action"] = "ask_seasons"
            await message.reply("✅ **Poster Updated.**\n\n📝 **Step 5: Content Groups**\n\nEnter names for your content (e.g. `Season 1, Season 2, Movie`):")

        # 3. Season Numbers (Now Group Names)
        elif action == "ask_seasons":
            groups = [s.strip() for s in message.text.split(",")]
            user_state[uid].update({
                "seasons_list": groups,
                "current_season_idx": 0,
                "seasons_data": {},
                "action": f"ask_480p_{groups[0]}"
            })
            await message.reply(f"📡 **Group: {groups[0]}**\n\nEnter **480p Download Link** (or /skip):")

        # 4. Multi-Quality Links (Chain)
        elif "ask_480p_" in action:
            group = action.split("ask_480p_")[-1]
            user_state[uid]["seasons_data"][group] = {"480p": message.text if message.text != "/skip" else None}
            user_state[uid]["action"] = f"ask_720p_{group}"
            await message.reply(f"📡 **Group: {group}**\n\nEnter **720p Download Link** (or /skip):")

        elif "ask_720p_" in action:
            group = action.split("ask_720p_")[-1]
            user_state[uid]["seasons_data"][group]["720p"] = message.text if message.text != "/skip" else None
            user_state[uid]["action"] = f"ask_1080p_{group}"
            await message.reply(f"📡 **Group: {group}**\n\nEnter **1080p Download Link** (or /skip):")

        elif "ask_1080p_" in action:
            group = action.split("ask_1080p_")[-1]
            user_state[uid]["seasons_data"][group]["1080p"] = message.text if message.text != "/skip" else None

            # Next season or finalize
            user_state[uid]["current_season_idx"] += 1
            if user_state[uid]["current_season_idx"] < len(user_state[uid]["seasons_list"]):
                next_s = user_state[uid]["seasons_list"][user_state[uid]["current_season_idx"]]
                user_state[uid]["action"] = f"ask_480p_{next_s}"
                await message.reply(f"📡 **Group: {next_s}**\n\nEnter **480p Download Link** (or /skip):")
            else:
                user_state[uid]["action"] = "ask_category_final"
                cats = await db.get_all_categories()
                buttons = []
                for c in (cats if cats else [{"name": "Anime"}]):
                    buttons.append([InlineKeyboardButton(c['name'], callback_data=f"finalcat_{c['name']}")])
                await message.reply("📂 **All data collected!**\nSelect a **Category** to publish:", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_callback_query(filters.regex("^img_"))
    async def image_choice_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state or state["action"] != "ask_image_choice": return

        choice = callback_query.data.split("_")[1]
        if choice == "api":
            user_state[uid]["image"] = state["anime_data"]["image"]
            user_state[uid]["action"] = "ask_seasons"
            await callback_query.message.edit_caption(caption="✅ **Using API Poster.**\n\n📝 **Step 5: Content Groups**\n\nEnter names for your content (e.g. `Season 1, Season 2, Movie`):", reply_markup=None)
        else:
            user_state[uid]["action"] = "ask_manual_img"
            await callback_query.message.edit_caption(caption="🖼 Please send the **Direct Image URL**:", reply_markup=None)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^finalcat_"))
    async def final_publish_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state or state["action"] != "ask_category_final": return

        category = callback_query.data.split("_")[1]
        data = state["anime_data"]
        slug = slugify(data["title"])

        main_entry = {
            "mal_id": f"series_{slug}",
            "title": data["title"],
            "slug": slug,
            "synopsis": data["synopsis"],
            "score": data["score"],
            "image": state["image"],
            "genres": data["genres"],
            "category": category,
            "status": data["status"],
            "year": data["year"],
            "trailer": data["trailer"],
            "studios": data.get("studios", []),
            "seasons_links": state["seasons_data"],
            "custom_buttons": []
        }

        try:
            await db.anime.update_one({"slug": slug}, {"$set": main_entry}, upsert=True)
            await callback_query.message.edit_text(text=f"✅ **Series Published!**\n\n🎬 {data['title']}\n📂 {category}\n🔢 {len(state['seasons_data'])} Groups\n\n🌐 URL: {Config.BASE_URL}/anime/{slug}", reply_markup=None)
            del user_state[uid]
        except Exception as e:
            await callback_query.answer(f"DB Error: {e}", show_alert=True)

    @bot.on_callback_query(filters.regex("^setcat_"))
    async def auto_post_set_cat_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state or state["action"] != "ask_category": return

        category = callback_query.data.split("_")[1]
        data = state["anime_data"]
        slug = slugify(data["title"])

        entry = {
            "mal_id": f"auto_{slug}",
            "title": data["title"],
            "slug": slug,
            "synopsis": data["synopsis"],
            "score": data["score"],
            "image": state["image"],
            "genres": data["genres"],
            "category": category,
            "status": data["status"],
            "year": data["year"],
            "trailer": data["trailer"],
            "studios": data.get("studios", []),
            "seasons_links": {"1": {"480p": None, "720p": None, "1080p": None}},
            "custom_buttons": []
        }

        try:
            await db.anime.update_one({"slug": slug}, {"$set": entry}, upsert=True)
            await callback_query.message.edit_caption(caption=f"✅ **Auto-Published to {category}!**\n🌐 URL: {Config.BASE_URL}/anime/{slug}", reply_markup=None)
            del user_state[uid]
        except Exception as e:
            await callback_query.answer(f"DB Error: {e}", show_alert=True)

    @bot.on_message(filters.command("cancel"))
    async def cancel_handler(client, message):
        user_state.pop(message.from_user.id, None)
        await message.reply("Operation cancelled.")

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
