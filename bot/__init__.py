import asyncio
import logging
import traceback
import os
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
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

# Temporary storage
search_results = {}
user_state = {}

async def is_authorized(user_id):
    try:
        if user_id in Config.ADMIN_IDS:
            return True
        return await db.is_admin(user_id)
    except Exception as e:
        logger.error(f"Authorization Check Error: {e}")
        return False

async def set_commands(client):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("search", "Industrial-Grade Search"),
        BotCommand("add_post", "Rapid One-Shot Post"),
        BotCommand("edit", "Manage Content Groups"),
        BotCommand("change_poster", "Update Series Artwork"),
        BotCommand("categories", "Manage Genres/Tags"),
        BotCommand("schedule", "Manage Airing Schedule"),
        BotCommand("del", "Permanent Archive Erasure"),
        BotCommand("cancel", "Abort Active Process"),
        BotCommand("ping", "System Latency Check")
    ]
    await client.set_bot_commands(commands)
    logger.info("Bot commands synchronized.")

def extract_slug(text):
    """Bulletproof slug extraction from any URL or raw text"""
    if not text: return None
    text = text.strip()
    if "/anime/" in text:
        try:
            # Handle URLs like https://site.com/anime/slug/extra or https://site.com/anime/slug?q=1
            parts = text.split("/anime/")[-1].split("/")
            slug_part = parts[0] if parts[0] else parts[1] # handle trailing slash before anime
            return slug_part.split("?")[0].split("\n")[0].split(" ")[0].rstrip("/").strip()
        except:
            return None
    return text

def register_handlers(bot: Client):
    logger.info("Initializing Hardened Intelligence Suite Handlers...")

    # --- DEBUG LOGGER (GROUP -3) ---
    @bot.on_message(filters.all, group=-3)
    async def debug_logger(client, message):
        logger.debug(f"UPDATE: {message.chat.id} -> {message.text or 'MEDIA'}")
        message.continue_propagation()

    # --- AUTO-LINK HANDLER (GROUP -2) ---
    @bot.on_message(filters.all, group=-2)
    async def auto_file_grouping(client, message):
        if (message.document or message.video) and not message.from_user.is_bot:
            try:
                from utils.parser import parse_filename
                fname = message.document.file_name if message.document else "video.mp4"
                parsed = parse_filename(fname)
                # Ensure DB is connected before query
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

        message.continue_propagation()

    # --- COMMAND HANDLERS (GROUP 0) ---

    @bot.on_message(filters.command("ping"))
    async def ping_handler(client, message):
        db_status = "Connected" if await db.ping() else "Disconnected"
        await message.reply(f"⚡ **System Status:** Operational\n🗄 **Database:** {db_status}\n🏓 **Latency Check:** Minimal/Responsive.")

    @bot.on_message(filters.command("start"))
    async def start_handler(client, message):
        await message.reply_photo(
            photo=Config.LOGO_URL,
            caption=(
                "👑 **ANIZONEFLIX PREMIUM v2.0**\n\n"
                "Welcome to the most advanced Anime Management Suite. Experience the power of industrial-grade automation and 11+ high-speed intelligence feeds.\n\n"
                "⚡ **Quick Start:**\n"
                "• `/search <name>` — Interactive intelligence setup\n"
                "• `/add_post <name>` — Rapid one-shot publication\n"
                "• `/edit <url>` — Content group management\n"
                "• `/help` — Full executive suite documentation"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Access Portal", url=Config.BASE_URL)],
                [InlineKeyboardButton("📚 Executive Guide", callback_data="help_guide")]
            ])
        )

    @bot.on_message(filters.command("help"))
    async def help_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.** This zone is for authorized administrators only.")

        text = (
            "👑 **ANIZONEFLIX ULTRA: Executive Suite**\n\n"
            "**🛠 CORE COMMANDS**\n"
            "• `/search <name>`: Interactive multi-API setup with custom metadata.\n"
            "• `/add_post <name>`: One-shot instant publication.\n"
            "• `/edit <url>`: Add new Content Groups (Movies, Specials, Seasons).\n"
            "• `/change_poster <url>`: Swap series artwork instantly.\n\n"
            "**⚙️ MANAGEMENT**\n"
            "• `/categories`: Manage platform genres & tags.\n"
            "• `/schedule`: Manage Airing Schedules.\n"
            "• `/del <url/slug>`: Permanent removal of series & files.\n"
            "• `/cancel`: Abort any active administrative process.\n\n"
            "**💎 PREMIUM FEATURES**\n"
            "✅ Ultra-Fast Multi-API Aggregator\n"
            "✅ Custom Content Group Labels\n"
            "✅ High-Speed ZIP Download Logic\n"
            "✅ Glassmorphism Web Interface"
        )
        await message.reply_text(text)

    @bot.on_message(filters.command("search"))
    async def search_handler(client, message, is_retry=False):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.**")

        query = " ".join(message.command[1:]) if not is_retry else message.text
        if not query:
            user_state[message.from_user.id] = {"action": "ask_search_query"}
            return await message.reply("🛰 **Intelligence Feed Aggregator**\n\nPlease send the **Title** of the series you wish to locate:")

        msg = await message.reply("📡 **Scanning Industrial-Grade APIs...**")
        try:
            results = await asyncio.wait_for(anime_api.search_all(query), timeout=5)
            if not results:
                user_state[message.from_user.id] = {"action": "ask_search_query"}
                return await msg.edit("😔 **Search Exhausted.** No high-confidence matches found. Try a different keyword:")

            search_results[message.from_user.id] = results
            text = "🎯 **Select Match from Intelligence Feed:**\n\n"
            for i, res in enumerate(results[:10], 1):
                text += f"**{i}.** {res['title']} ({res['year']}) `[{res['source'].upper()}]`\n"

            await msg.edit(text)
            user_state[message.from_user.id] = {"action": "select_anime"}
        except Exception as e:
            logger.error(f"Search Error: {e}")
            await msg.edit("❌ **Intelligence Feed Failure.** Please try again in a moment.")

    @bot.on_message(filters.command("add_post"))
    async def auto_post_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Unauthorized.**")

        query = " ".join(message.command[1:])
        if not query: return await message.reply("💡 **Usage:** `/add_post <name>`")

        msg = await message.reply(f"⚡ **Executing Rapid Publication: {query}...**")
        try:
            results = await anime_api.search_all(query)
            if not results: return await msg.edit("❌ **Publication Failed:** No match found.")

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
            buttons = [[InlineKeyboardButton(c['name'], callback_data=f"setcat_{c['name']}")] for c in (cats if cats else [{"name": "Anime"}])]

            await message.reply_photo(
                photo=details["image"] if details["image"] else Config.LOGO_URL,
                caption=f"🎬 **Archive Ready:** `{details['title']}`\n\nSelect the target **Category** for deployment:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            await msg.delete()
        except Exception as e:
            logger.error(f"Add Post Error: {e}")
            await msg.edit("❌ **Rapid Deployment Failure.**")

    @bot.on_message(filters.command("edit"))
    async def edit_handler(client, message):
        """EXECUTIVE SUITE: Robust Rewrite of /edit"""
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Unauthorized Access Detected.** Execution blocked.")

        query = " ".join(message.command[1:]).strip()
        if not query and message.reply_to_message:
            query = (message.reply_to_message.text or message.reply_to_message.caption or "").strip()

        if not query:
            return await message.reply(
                "💡 **Executive Suite: Edit Command**\n\n"
                "Please provide a **Series Page Link** or a **Title Fragment**.\n"
                "Example: `/edit https://anizoneflix.onrender.com/anime/slug`"
            )

        status_msg = await message.reply("📡 **Accessing Industrial-Grade Persistence Layer...**")

        try:
            # 1. Extraction & Direct Lookup
            identifier = extract_slug(query)
            anime = await db.get_anime_by_slug(identifier)

            # 2. Heuristic Search Fallback
            if not anime:
                await status_msg.edit(f"🔍 **Identifier '{identifier}' mismatch. Running Intelligence Feed...**")
                results = await db.search_anime_db(query)
                if results:
                    anime = results[0]
                    identifier = anime['slug']

            if not anime:
                return await status_msg.edit(f"❌ **Intelligence Failure:** Could not locate series matching `{query}`.")

            # 3. Interactive Management Flow
            buttons = [
                [InlineKeyboardButton("💎 Add Content Group", callback_data=f"add_group_yes_{identifier}")],
                [InlineKeyboardButton("🖼 Change Poster", callback_data=f"trigger_poster_{identifier}")],
                [InlineKeyboardButton("🗑 Purge Series", callback_data=f"confirm_purge_{identifier}")],
                [InlineKeyboardButton("❌ Abort", callback_data="cancel_op")]
            ]

            await status_msg.edit(
                f"🏛 **Executive Management: {anime['title']}**\n\n"
                f"🏷 **Slug:** `{identifier}`\n"
                f"📂 **Archive Status:** Online\n\n"
                f"Select an operation to perform on this content archive:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        except Exception as e:
            logger.error(f"CRITICAL EDIT FAILURE: {e}\n{traceback.format_exc()}")
            await status_msg.edit(
                "❌ **Critical Persistence Failure.**\n\n"
                f"💻 **Diagnostics:** `{str(e)}`\n"
                "🛠 **Action:** Verify MONGO_URI is operational and the database is reachable."
            )

    @bot.on_message(filters.command("change_poster"))
    async def change_poster_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.**")

        query = " ".join(message.command[1:])
        if not query and message.reply_to_message:
            query = message.reply_to_message.text or message.reply_to_message.caption or ""

        slug = extract_slug(query)
        if not slug:
            return await message.reply("💡 **Usage:** `/change_poster <post_page_url>` (or reply to a link)")

        try:
            anime = await db.get_anime_by_slug(slug)
            if not anime:
                return await message.reply(f"🔍 **Not Found!** Could not locate series for identifier: `{slug}`")

            user_state[message.from_user.id] = {"action": "ask_new_poster", "slug": slug}
            await message.reply(f"🖼 **Calibrating Visuals for:** `{anime['title']}`\n\nPlease provide the **New Asset URL**:")
        except Exception as e:
            logger.error(f"Change Poster Error: {e}")
            await message.reply("❌ **Database Access Failure.**")

    @bot.on_message(filters.command("categories"))
    async def categories_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.**")

        try:
            cats = await db.get_all_categories()
            buttons = []
            for c in cats:
                buttons.append([
                    InlineKeyboardButton(f"🏷 {c['name']}", callback_data=f"view_cat_{c['name']}"),
                    InlineKeyboardButton("🗑", callback_data=f"del_cat_{c['name']}")
                ])

            buttons.append([InlineKeyboardButton("➕ Add New Category", callback_data="add_cat_prompt")])

            await message.reply(
                "📂 **Category Management Suite**\n\nManage your site's genres and tags below:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception as e:
            logger.error(f"Categories Error: {e}")
            await message.reply("❌ **Database Access Failure.**")

    @bot.on_message(filters.command("schedule"))
    async def schedule_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.**")

        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        buttons = []
        for i in range(0, len(days), 2):
            row = [InlineKeyboardButton(days[i], callback_data=f"edit_sched_{days[i]}")]
            if i+1 < len(days):
                row.append(InlineKeyboardButton(days[i+1], callback_data=f"edit_sched_{days[i+1]}"))
            buttons.append(row)

        await message.reply(
            "📅 **Airing Schedule Management**\n\nSelect a day to update its schedule:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    @bot.on_message(filters.command("del"))
    async def delete_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.**")

        query = " ".join(message.command[1:])
        if not query and message.reply_to_message:
            query = message.reply_to_message.text or message.reply_to_message.caption or ""

        slug = extract_slug(query)
        if not slug: return await message.reply("💡 **Usage:** `/del <slug, title, or URL>`")

        try:
            res = await db.delete_anime_by_slug(slug)
            if res.deleted_count > 0:
                return await message.reply(f"🗑 **Sanitized:** `{slug}` has been permanently erased.")

            anime = await db.anime.find_one({"title": {"$regex": query, "$options": "i"}})
            if anime:
                await db.delete_anime_by_slug(anime["slug"])
                return await message.reply(f"🗑 **Sanitized (via Title Search):** `{anime['title']}` erased.")

            await message.reply(f"❓ **Search Failed:** `{slug}` is not in the archives.")
        except Exception as e:
            logger.error(f"Delete Error: {e}")
            await message.reply("❌ **Database Erasure Failure.**")

    @bot.on_message(filters.command("cancel"))
    async def cancel_handler(client, message):
        user_state.pop(message.from_user.id, None)
        await message.reply("✨ **Action Cancelled.** Returning to standby.")

    # --- CALLBACK HANDLERS ---

    @bot.on_callback_query(filters.regex("^help_guide$"))
    async def help_cb(client, callback_query):
        await help_handler(client, callback_query.message)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^add_cat_prompt$"))
    async def add_cat_prompt_cb(client, callback_query):
        user_state[callback_query.from_user.id] = {"action": "ask_cat_name"}
        await callback_query.message.edit_text("🏷 **Enter the name of the new category:**", reply_markup=None)

    @bot.on_callback_query(filters.regex("^del_cat_"))
    async def del_cat_cb(client, callback_query):
        try:
            cat_name = callback_query.data.split("del_cat_")[-1]
            await db.delete_category(cat_name)
            await callback_query.answer(f"🗑 Category '{cat_name}' removed.", show_alert=True)
            cats = await db.get_all_categories()
            buttons = [[InlineKeyboardButton(f"🏷 {c['name']}", callback_data=f"view_cat_{c['name']}"), InlineKeyboardButton("🗑", callback_data=f"del_cat_{c['name']}")] for c in cats]
            buttons.append([InlineKeyboardButton("➕ Add New Category", callback_data="add_cat_prompt")])
            await callback_query.message.edit_text("📂 **Category Management Suite**\n\nManage your site's genres and tags below:", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e: logger.error(f"Del Cat CB Error: {e}")

    @bot.on_callback_query(filters.regex("^add_group_yes_"))
    async def add_group_yes_cb(client, callback_query):
        slug = callback_query.data.split("add_group_yes_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_edit_group_name", "slug": slug}
        await callback_query.message.edit_text("📝 **Step 1: Group Identity**\n\nWhat should this content group be named?\n*(e.g. Season 2, Specials, Movie)*", reply_markup=None)

    @bot.on_callback_query(filters.regex("^trigger_poster_"))
    async def trigger_poster_cb(client, callback_query):
        slug = callback_query.data.split("trigger_poster_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_new_poster", "slug": slug}
        await callback_query.message.edit_text("🖼 **Executive Suite: Asset Update**\n\nPlease provide the **Direct Image URL** for the new poster:", reply_markup=None)

    @bot.on_callback_query(filters.regex("^confirm_purge_"))
    async def confirm_purge_cb(client, callback_query):
        slug = callback_query.data.split("confirm_purge_")[-1]
        buttons = [
            [InlineKeyboardButton("🧨 Yes, PURGE EVERYTHING", callback_data=f"execute_purge_{slug}")],
            [InlineKeyboardButton("🛡 Abort", callback_data="cancel_op")]
        ]
        await callback_query.message.edit_text(
            f"⚠️ **CRITICAL WARNING** ⚠️\n\nYou are about to permanently erase the archive for `{slug}`. This action cannot be undone.\n\nContinue?",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    @bot.on_callback_query(filters.regex("^execute_purge_"))
    async def execute_purge_cb(client, callback_query):
        slug = callback_query.data.split("execute_purge_")[-1]
        try:
            await db.delete_anime_by_slug(slug)
            await callback_query.message.edit_text(f"🔥 **Archive Sanitized.** `{slug}` has been removed from the persistence layer.", reply_markup=None)
        except Exception as e:
            await callback_query.answer(f"Purge Failed: {e}", show_alert=True)

    @bot.on_callback_query(filters.regex("^edit_sched_"))
    async def edit_sched_cb(client, callback_query):
        day = callback_query.data.split("edit_sched_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_sched_content", "day": day}
        current = await db.get_schedule(day)
        await callback_query.message.edit_text(
            f"📅 **Updating Schedule: {day}**\n\n🏷 **Current:**\n`{current}`\n\n📥 Please send the new schedule in this format:\n\n1. NAME (TIME)\n2. NAME (TIME)\n\nSend `/skip` to cancel.",
            reply_markup=None
        )

    @bot.on_callback_query(filters.regex("^cancel_op$"))
    async def cancel_op_cb(client, callback_query):
        user_state.pop(callback_query.from_user.id, None)
        await callback_query.message.edit_text("✨ **Executive Order:** Operation cancelled.", reply_markup=None)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^img_"))
    async def image_choice_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state or state["action"] != "ask_image_choice": return
        choice = callback_query.data.split("_")[1]
        if choice == "api":
            user_state[uid]["image"] = state["anime_data"]["image"]
            user_state[uid]["action"] = "ask_seasons"
            await callback_query.message.edit_caption(caption="✅ **Intelligence Asset Selected.**\n\n🛰 **Step 5: Group Architect**\n\nDefine content group names:", reply_markup=None)
        else:
            user_state[uid]["action"] = "ask_manual_img"
            await callback_query.message.edit_caption(caption="🛰 Please provide the **Direct Asset URL**:", reply_markup=None)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^finalcat_"))
    async def final_publish_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state or state["action"] != "ask_category_final": return
        category, data = callback_query.data.split("_")[1], state["anime_data"]
        slug = slugify(data["title"])
        main_entry = {"mal_id": f"series_{slug}", "title": data["title"], "slug": slug, "synopsis": data["synopsis"], "score": data["score"], "image": state["image"], "genres": data["genres"], "category": category, "status": data["status"], "year": data["year"], "trailer": data["trailer"], "studios": data.get("studios", []), "seasons_links": state["seasons_data"], "custom_buttons": []}
        try:
            await db.anime.update_one({"slug": slug}, {"$set": main_entry}, upsert=True)
            await callback_query.message.edit_text(text=f"💎 **Executive Success!**\n\n🎬 `{data['title']}` archive is now LIVE.\n📂 **Category:** {category}\n🔢 **Groups:** {len(state['seasons_data'])}\n\n🌐 **Portal:** {Config.BASE_URL}/anime/{slug}", reply_markup=None)
            del user_state[uid]
        except Exception as e:
            logger.error(f"Final Publish Error: {e}")
            await callback_query.answer(f"DB Error: {e}", show_alert=True)

    @bot.on_callback_query(filters.regex("^setcat_"))
    async def auto_post_set_cat_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state or state["action"] != "ask_category": return
        category, data = callback_query.data.split("_")[1], state["anime_data"]
        slug = slugify(data["title"])
        entry = {"mal_id": f"auto_{slug}", "title": data["title"], "slug": slug, "synopsis": data["synopsis"], "score": data["score"], "image": state["image"], "genres": data["genres"], "category": category, "status": data["status"], "year": data["year"], "trailer": data["trailer"], "studios": data.get("studios", []), "seasons_links": {"1": {"480p": None, "720p": None, "1080p": None}}, "custom_buttons": []}
        try:
            await db.anime.update_one({"slug": slug}, {"$set": entry}, upsert=True)
            await callback_query.message.edit_caption(caption=f"⚡ **Rapid Deployment Success!**\n\n🌐 **Portal:** {Config.BASE_URL}/anime/{slug}", reply_markup=None)
            del user_state[uid]
        except Exception as e:
            logger.error(f"Auto Post CB Error: {e}")
            await callback_query.answer(f"DB Error: {e}", show_alert=True)

    # --- INTERACTION HANDLER (GROUP 1) ---

    @bot.on_message(filters.private & filters.text & ~filters.command(["start", "help", "search", "add_post", "edit", "categories", "del", "cancel", "change_poster", "ping", "schedule"]), group=1)
    async def interaction_handler(client, message):
        uid = message.from_user.id
        state = user_state.get(uid)
        if not state: return

        action = state.get("action", "")

        try:
            if action == "ask_search_query":
                return await search_handler(client, message, is_retry=True)

            elif action == "ask_cat_name":
                cat_name = message.text.strip()
                await db.add_category(cat_name)
                await message.reply(f"✅ **Category Created:** `{cat_name}`\n📂 Use `/categories` to view updated list.")
                del user_state[uid]

            elif action == "ask_sched_content":
                if message.text == "/skip":
                    del user_state[uid]
                    return await message.reply("✨ **Cancelled.**")
                day, content = state["day"], message.text.strip()
                await db.update_schedule(day, content)
                await message.reply(f"✅ **Schedule Updated:** `{day}` is now live.")
                del user_state[uid]

            elif action == "ask_new_poster":
                new_url = message.text.strip()
                slug = state["slug"]
                res = await db.anime.update_one({"slug": slug}, {"$set": {"image": new_url}})
                if res.modified_count:
                    await message.reply(f"✅ **Visual Synchronized:** Poster updated for `{slug}`.")
                else:
                    await message.reply("❌ **Update Failed:** Series could not be updated.")
                del user_state[uid]

            elif action == "ask_edit_group_name":
                group_name = message.text.strip()
                user_state[uid].update({"action": "ask_edit_480p", "group_name": group_name})
                await message.reply(f"📦 **Group: {group_name}**\n\n🛰 Send **480p Access Link** or `/skip`:")

            elif action == "ask_edit_480p":
                user_state[uid]["480p"] = message.text if message.text != "/skip" else None
                user_state[uid]["action"] = "ask_edit_720p"
                await message.reply(f"📦 **Group: {state['group_name']}**\n\n🛰 Send **720p Access Link** or `/skip`:")

            elif action == "ask_edit_720p":
                user_state[uid]["720p"] = message.text if message.text != "/skip" else None
                user_state[uid]["action"] = "ask_edit_1080p"
                await message.reply(f"📦 **Group: {state['group_name']}**\n\n🛰 Send **1080p Access Link** or `/skip`:")

            elif action == "ask_edit_1080p":
                p1080 = message.text if message.text != "/skip" else None
                slug, gname = state["slug"], state["group_name"]
                anime = await db.get_anime_by_slug(slug)
                if anime:
                    links = anime.get("seasons_links", {})
                    links[gname] = {"480p": state.get("480p"), "720p": state.get("720p"), "1080p": p1080}
                    await db.anime.update_one({"slug": slug}, {"$set": {"seasons_links": links}})
                    await message.reply(f"💎 **Premium Update Success!**\n\n📦 Added `{gname}` to `{anime['title']}` archive.\n\n🌐 **Live URL:** {Config.BASE_URL}/anime/{slug}")
                else:
                    await message.reply("❌ **Error:** Archive lost during processing.")
                del user_state[uid]

            elif action == "select_anime":
                try:
                    idx = int(message.text) - 1
                    selected = search_results[uid][idx]
                    msg = await message.reply("📡 **Fetching Industrial-Grade Metadata...**")
                    details = await anime_api.get_details(selected["source"], selected["id"])
                    if not details: details = {"title": selected["title"], "image": selected["image"], "synopsis": "N/A", "score": 0, "genres": [], "year": selected["year"], "status": "N/A", "episodes": 0, "trailer": None}
                    user_state[uid].update({"action": "edit_title", "anime_data": details})
                    await msg.edit(f"✨ **Intelligence Step 1: Title Calibration**\n\n🏷 **Current:** `{details['title']}`\n\n📥 Send the **New Title** or `/skip` to maintain current:")
                except: await message.reply("❌ **Invalid selection.** Send a valid numeric choice.")

            elif action == "edit_title":
                if message.text != "/skip": user_state[uid]["anime_data"]["title"] = message.text
                user_state[uid]["action"] = "edit_synopsis"
                await message.reply(f"✨ **Intelligence Step 2: Synopsis Configuration**\n\n📖 **Current:** `{user_state[uid]['anime_data']['synopsis'][:150]}...`\n\n📥 Send **New Synopsis** or `/skip`:")

            elif action == "edit_synopsis":
                if message.text != "/skip": user_state[uid]["anime_data"]["synopsis"] = message.text
                user_state[uid]["action"] = "edit_score"
                await message.reply(f"✨ **Intelligence Step 3: Rating Adjustment**\n\n⭐ **Current:** `{user_state[uid]['anime_data']['score']}`\n\n📥 Send **New Rating** (e.g. 9.2) or `/skip`:")

            elif action == "edit_score":
                if message.text != "/skip":
                    try: user_state[uid]["anime_data"]["score"] = float(message.text)
                    except: pass
                details = user_state[uid]["anime_data"]
                user_state[uid]["action"] = "ask_image_choice"
                buttons = [[InlineKeyboardButton("🖼 Use intelligence Poster", callback_data="img_api")], [InlineKeyboardButton("🔗 Manual Asset URL", callback_data="img_manual")]]
                await message.reply_photo(photo=details["image"] if details["image"] else Config.LOGO_URL, caption=f"✨ **Intelligence Step 4: Visual Selection**\n\nPreview detected artwork below. Choose source:", reply_markup=InlineKeyboardMarkup(buttons))

            elif action == "ask_manual_img":
                user_state[uid]["image"] = message.text
                user_state[uid]["action"] = "ask_seasons"
                await message.reply("✅ **Asset Registered.**\n\n🛰 **Step 5: Group Architect**\n\nDefine content group names (e.g. `Season 1, Specials, Movie`):")

            elif action == "ask_seasons":
                groups = [s.strip() for s in message.text.split(",")]
                user_state[uid].update({"seasons_list": groups, "current_season_idx": 0, "seasons_data": {}, "action": f"ask_480p_{groups[0]}"})
                await message.reply(f"📦 **Architecting Group: {groups[0]}**\n\n🛰 Send **480p Access Link** or `/skip`:")

            elif "ask_480p_" in action:
                group = action.split("ask_480p_")[-1]
                user_state[uid]["seasons_data"][group] = {"480p": message.text if message.text != "/skip" else None}
                user_state[uid]["action"] = f"ask_720p_{group}"
                await message.reply(f"📦 **Architecting Group: {group}**\n\n🛰 Send **720p Access Link** or `/skip`:")

            elif "ask_720p_" in action:
                group = action.split("ask_720p_")[-1]
                user_state[uid]["seasons_data"][group]["720p"] = message.text if message.text != "/skip" else None
                user_state[uid]["action"] = f"ask_1080p_{group}"
                await message.reply(f"📦 **Architecting Group: {group}**\n\n🛰 Send **1080p Access Link** or `/skip`:")

            elif "ask_1080p_" in action:
                group = action.split("ask_1080p_")[-1]
                user_state[uid]["seasons_data"][group]["1080p"] = message.text if message.text != "/skip" else None
                user_state[uid]["current_season_idx"] += 1
                if user_state[uid]["current_season_idx"] < len(user_state[uid]["seasons_list"]):
                    next_s = user_state[uid]["seasons_list"][user_state[uid]["current_season_idx"]]
                    user_state[uid]["action"] = f"ask_480p_{next_s}"
                    await message.reply(f"📦 **Architecting Group: {next_s}**\n\n🛰 Send **480p Access Link** or `/skip`:")
                else:
                    user_state[uid]["action"] = "ask_category_final"
                    cats = await db.get_all_categories()
                    buttons = [[InlineKeyboardButton(c['name'], callback_data=f"finalcat_{c['name']}")] for c in (cats if cats else [{"name": "Anime"}])]
                    await message.reply("🛰 **Data Aggregation Complete.**\nFinal Step: Choose target **Category** for deployment:", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            logger.error(f"Interaction Error: {e}")
            logger.error(traceback.format_exc())
            await message.reply("❌ **Intelligence Link Severed.** Operation aborted.")
            user_state.pop(uid, None)

    # --- AUTO-LINK HANDLER (BACKGROUND) ---

    @bot.on_message(filters.all, group=-2)
    async def auto_file_grouping(client, message):
        if not message.document and not message.video:
            message.continue_propagation()
            return

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
            logger.info(f"Auto-Link Success: {fname} -> {anime['title']}")

        message.continue_propagation()
