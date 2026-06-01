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
        BotCommand("add_page", "Manual Content Creation"),
        BotCommand("manual", "Custom Detailed Creation"),
        BotCommand("edit_m", "Manage Custom Buttons"),
        BotCommand("edit", "Manage Content Groups"),
        BotCommand("change_poster", "Update Series Artwork"),
        BotCommand("categories", "Manage Genres/Tags"),
        BotCommand("schedule", "Manage Airing Schedule"),
        BotCommand("del", "Permanent Archive Erasure"),
        BotCommand("save", "Backup & Restore Data"),
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
            parts = text.split("/anime/")[-1].split("/")
            slug_part = parts[0] if parts[0] else parts[1]
            return slug_part.split("?")[0].split("\n")[0].split(" ")[0].rstrip("/").strip()
        except:
            return None
    return text

def register_handlers(bot: Client):
    logger.info("Initializing Hardened Intelligence Suite Handlers...")

    # --- DEBUG LOGGER (GROUP -3) ---
    @bot.on_message(filters.all, group=-3)
    async def debug_logger(client, message):
        # logger.debug(f"UPDATE: {message.chat.id} -> {message.text or 'MEDIA'}")
        raise ContinuePropagation

    # --- AUTO-LINK HANDLER (GROUP -2) ---
    @bot.on_message(filters.all, group=-2)
    async def auto_file_grouping(client, message):
        if (message.document or message.video) and not message.from_user.is_bot:
            try:
                from utils.parser import parse_filename
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
                "• `/add_page` — Manual content creation\n"
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
            "• `/search <name>`: Interactive multi-API setup.\n"
            "• `/add_post <name>`: One-shot instant publication.\n"
            "• `/add_page <name>`: Manual entry creation.\n"
            "• `/edit <url>`: Manage Content Groups.\n"
            "• `/change_poster <url>`: Swap artwork.\n\n"
            "**⚙️ MANAGEMENT**\n"
            "• `/categories`: Manage genres & tags.\n"
            "• `/schedule`: Manage Airing Schedules.\n"
            "• `/del <url/slug>`: Permanent archive removal.\n"
            "• `/cancel`: Abort active processes.\n\n"
            "**💎 PREMIUM FEATURES**\n"
            "✅ Multi-API Aggregator\n"
            "✅ Custom Group Labels\n"
            "✅ High-Speed ZIP Download\n"
            "✅ Glassmorphism Web Interface"
        )
        await message.reply_text(text)

    @bot.on_message(filters.command("add_page"))
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

    @bot.on_message(filters.command("search"))
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

    @bot.on_message(filters.command("add_post"))
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

    @bot.on_message(filters.command("edit"))
    async def edit_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Unauthorized.**")

        query = " ".join(message.command[1:]).strip()
        if not query and message.reply_to_message:
            query = (message.reply_to_message.text or message.reply_to_message.caption or "").strip()

        slug = extract_slug(query)
        if not slug:
            return await message.reply("💡 **Usage:** `/edit <url>` (or reply to a link)")

        try:
            anime = await db.get_anime_by_slug(slug)
            if not anime:
                results = await db.search_anime_db(query)
                if results: anime = results[0]; slug = anime['slug']

            if not anime: return await message.reply(f"❌ **Not Found:** `{slug}`")

            buttons = [
                [InlineKeyboardButton("💎 Add Group", callback_data=f"add_group_yes_{slug}")],
                [InlineKeyboardButton("📝 Edit Groups", callback_data=f"manage_groups_{slug}")],
                [InlineKeyboardButton("🏷 Change Title", callback_data=f"edit_title_{slug}")],
                [InlineKeyboardButton("🖼 Change Poster", callback_data=f"trigger_poster_{slug}")],
                [InlineKeyboardButton("🗑 Purge", callback_data=f"confirm_purge_{slug}")],
                [InlineKeyboardButton("❌ Abort", callback_data="cancel_op")]
            ]
            await message.reply(f"🏛 **Management: {anime['title']}**\nSlug: `{slug}`", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            logger.error(f"Edit Cmd Error: {e}")
            await message.reply("❌ **Database Failure.**")

    @bot.on_message(filters.command("change_poster"))
    async def change_poster_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.**")

        query = " ".join(message.command[1:])
        if not query and message.reply_to_message:
            query = message.reply_to_message.text or message.reply_to_message.caption or ""

        slug = extract_slug(query)
        if not slug: return await message.reply("💡 **Usage:** `/change_poster <url>`")

        try:
            anime = await db.get_anime_by_slug(slug)
            if not anime: return await message.reply(f"🔍 **Not Found:** `{slug}`")
            user_state[message.from_user.id] = {"action": "ask_new_poster", "slug": slug}
            await message.reply(f"🖼 **Artwork Update:** `{anime['title']}`\n\nSend **New Asset URL**:")
        except Exception as e:
            logger.error(f"Change Poster Error: {e}")
            await message.reply("❌ **Database Failure.**")

    @bot.on_message(filters.command("categories"))
    async def categories_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.**")

        try:
            cats = await db.get_all_categories()
            buttons = [[InlineKeyboardButton(f"🏷 {c['name']}", callback_data=f"vcat_{c['name']}"), InlineKeyboardButton("🗑", callback_data=f"del_cat_{c['name']}")] for c in cats]
            buttons.append([InlineKeyboardButton("➕ Add Category", callback_data="add_cat_prompt")])
            await message.reply("📂 **Category Management**", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            logger.error(f"Categories Error: {e}")
            await message.reply("❌ **Database Failure.**")

    @bot.on_message(filters.command("schedule"))
    async def schedule_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.**")

        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        buttons = [[InlineKeyboardButton(days[i], callback_data=f"edit_sched_{days[i]}"), InlineKeyboardButton(days[i+1], callback_data=f"edit_sched_{days[i+1]}")] for i in range(0, 6, 2)]
        buttons.append([InlineKeyboardButton("Sunday", callback_data="edit_sched_Sunday")])
        await message.reply("📅 **Airing Schedule**", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_message(filters.command("del"))
    async def delete_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.**")

        query = " ".join(message.command[1:])
        if not query and message.reply_to_message:
            query = message.reply_to_message.text or message.reply_to_message.caption or ""

        slug = extract_slug(query)
        if not slug: return await message.reply("💡 **Usage:** `/del <url/slug>`")

        try:
            res = await db.delete_anime_by_slug(slug)
            if res and res.deleted_count > 0:
                return await message.reply(f"🗑 **Erased:** `{slug}` removed.")
            anime = await db.anime.find_one({"title": {"$regex": query, "$options": "i"}})
            if anime:
                await db.delete_anime_by_slug(anime["slug"])
                return await message.reply(f"🗑 **Erased:** `{anime['title']}` removed.")
            await message.reply(f"❓ **Failed:** `{slug}` not found.")
        except Exception as e:
            logger.error(f"Delete Error: {e}")
            await message.reply("❌ **Erasure Failure.**")

    @bot.on_message(filters.command("manual"))
    async def manual_handler(client, message):
        if not await is_authorized(message.from_user.id): return
        user_state[message.from_user.id] = {"action": "ask_manual_title"}
        await message.reply("📝 **Step 1: Title**\nSend Title for the custom page:")

    @bot.on_message(filters.command("edit_m"))
    async def edit_m_handler(client, message):
        if not await is_authorized(message.from_user.id): return
        query = message.text.split(" ", 1)[1] if len(message.text.split()) > 1 else ""
        if not query and message.reply_to_message:
            query = message.reply_to_message.text or message.reply_to_message.caption or ""

        slug = extract_slug(query)
        if not slug: return await message.reply("💡 **Usage:** `/edit_m <page_url>`")

        anime = await db.get_anime_by_slug(slug)
        if not anime: return await message.reply("❌ **Page not found in database.**")

        user_state[message.from_user.id] = {"action": "ask_edit_m_count", "slug": slug, "anime": anime}
        await message.reply("🖇 **How many buttons do you want to add?**\nSend a number (e.g., 4):")

    @bot.on_message(filters.command("save"))
    async def save_command_handler(client, message):
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Unauthorized.**")

        buttons = [
            [
                InlineKeyboardButton("📥 BACKUP", callback_data="backup_data"),
                InlineKeyboardButton("📤 RESTORE", callback_data="restore_data")
            ]
        ]
        await message.reply(
            "💾 **Database Management System**\n\n"
            "Choose an action to manage your data safely:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    @bot.on_message(filters.command("cancel"))
    async def cancel_handler(client, message):
        user_state.pop(message.from_user.id, None)
        await message.reply("✨ **Action Cancelled.** standby.")

    # --- CALLBACK HANDLERS ---

    @bot.on_callback_query(filters.regex("^backup_data$"))
    async def backup_data_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        await callback_query.message.edit_text("⏳ **Generating system backup...**")
        try:
            data = await db.export_data()
            if data is None:
                return await callback_query.message.edit_text("❌ **Export Failed:** Database connection offline.")

            if not any(data.values()):
                return await callback_query.message.edit_text("❌ **Export Failed:** No records found in the database.")

            # Create a ZIP in memory
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for coll_name, docs in data.items():
                    json_data = json.dumps(docs, indent=4, default=str)
                    zf.writestr(f"{coll_name}.json", json_data)

            zip_buffer.seek(0)
            zip_buffer.name = "backup.zip"

            await callback_query.message.delete()
            await client.send_document(
                chat_id=callback_query.message.chat.id,
                document=zip_buffer,
                file_name="backup.zip",
                caption=(
                    f"✅ **Backup Generated Successfully**\n\n"
                    f"🌐 **Website:** {Config.BASE_URL}\n"
                    f"📦 **Data:** Total collections exported.\n\n"
                    f"Keep this file secure. You can restore this data anytime using the /save command."
                )
            )
        except Exception as e:
            logger.error(f"Backup Error: {e}")
            await callback_query.message.edit_text(f"❌ **Backup Failed:** `{str(e)}`")

    @bot.on_callback_query(filters.regex("^restore_data$"))
    async def restore_data_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        user_state[callback_query.from_user.id] = {"action": "awaiting_restore_zip"}
        await callback_query.message.edit_text(
            "📤 **Ready to Restore Data**\n\n"
            "Please upload the `backup.zip` file you created earlier.\n\n"
            "⚠️ **Important:** This operation will overwrite all existing records with the data from the ZIP file.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_op")]])
        )

    @bot.on_callback_query(filters.regex("^help_guide$"))
    async def help_cb(client, callback_query):
        await help_handler(client, callback_query.message)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^add_cat_prompt$"))
    async def add_cat_prompt_cb(client, callback_query):
        user_state[callback_query.from_user.id] = {"action": "ask_cat_name"}
        await callback_query.message.edit_text("🏷 **Enter Category Name:**", reply_markup=None)

    @bot.on_callback_query(filters.regex("^del_cat_"))
    async def del_cat_cb(client, callback_query):
        try:
            name = callback_query.data.split("del_cat_")[-1]
            await db.delete_category(name)
            await callback_query.answer(f"🗑 Removed: {name}", show_alert=True)
            await categories_handler(client, callback_query.message)
        except Exception as e: logger.error(f"Del Cat CB Error: {e}")

    @bot.on_callback_query(filters.regex("^add_group_yes_"))
    async def add_group_yes_cb(client, callback_query):
        slug = callback_query.data.split("add_group_yes_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_edit_group_name", "slug": slug}
        await callback_query.message.edit_text("📝 **Group Identity:**\n*(e.g. Season 2, OVA, Movie)*", reply_markup=None)

    @bot.on_callback_query(filters.regex("^trigger_poster_"))
    async def trigger_poster_cb(client, callback_query):
        slug = callback_query.data.split("trigger_poster_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_new_poster", "slug": slug}
        await callback_query.message.edit_text("🖼 **New Asset URL:**", reply_markup=None)

    @bot.on_callback_query(filters.regex("^confirm_purge_"))
    async def confirm_purge_cb(client, callback_query):
        slug = callback_query.data.split("confirm_purge_")[-1]
        buttons = [[InlineKeyboardButton("🧨 PURGE EVERYTHING", callback_data=f"execute_purge_{slug}")],[InlineKeyboardButton("🛡 Abort", callback_data="cancel_op")]]
        await callback_query.message.edit_text(f"⚠️ **CRITICAL:** Purge `{slug}`?", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_callback_query(filters.regex("^execute_purge_"))
    async def execute_purge_cb(client, callback_query):
        slug = callback_query.data.split("execute_purge_")[-1]
        try:
            await db.delete_anime_by_slug(slug)
            await callback_query.message.edit_text(f"🔥 **Sanitized:** `{slug}` purged.", reply_markup=None)
        except Exception as e: await callback_query.answer(f"Purge Failed: {e}", show_alert=True)

    @bot.on_callback_query(filters.regex("^edit_sched_"))
    async def edit_sched_cb(client, callback_query):
        day = callback_query.data.split("edit_sched_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_sched_content", "day": day}
        current = await db.get_schedule(day)
        await callback_query.message.edit_text(f"📅 **Update: {day}**\n\nCurrent:\n`{current}`\n\nFormat: 1. NAME (TIME)\nSend `/skip` to cancel.", reply_markup=None)

    @bot.on_callback_query(filters.regex("^manage_groups_"))
    async def manage_groups_cb(client, callback_query):
        slug = callback_query.data.split("manage_groups_")[-1]
        anime = await db.get_anime_by_slug(slug)
        if not anime: return await callback_query.answer("❌ Not Found", show_alert=True)

        groups = anime.get("seasons_links", {})
        if not groups: return await callback_query.edit_message_text("❌ **No groups available to edit.**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛡 Back", callback_data=f"back_to_edit_{slug}")]]))

        # Store current groups in state for index-based access (prevents 64-byte callback limit issues)
        group_list = list(groups.keys())
        user_state[callback_query.from_user.id] = {"slug": slug, "group_names": group_list}

        buttons = []
        for idx, gname in enumerate(group_list):
            display_name = (gname[:15] + '..') if len(gname) > 17 else gname
            buttons.append([
                InlineKeyboardButton(f"✏️ {display_name}", callback_data=f"rengidx_{idx}"),
                InlineKeyboardButton(f"🔗 Links", callback_data=f"editlidx_{idx}"),
                InlineKeyboardButton(f"🗑", callback_data=f"remgidx_{idx}")
            ])
        buttons.append([InlineKeyboardButton("🛡 Back", callback_data=f"back_to_edit_{slug}")])
        await callback_query.message.edit_text(f"📝 **Manage Groups: {anime['title']}**\nSelect an action:", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_callback_query(filters.regex("^back_to_edit_"))
    async def back_to_edit_cb(client, callback_query):
        slug = callback_query.data.split("back_to_edit_")[-1]
        anime = await db.get_anime_by_slug(slug)
        buttons = [
            [InlineKeyboardButton("💎 Add Group", callback_data=f"add_group_yes_{slug}")],
            [InlineKeyboardButton("📝 Edit Groups", callback_data=f"manage_groups_{slug}")],
            [InlineKeyboardButton("🏷 Change Title", callback_data=f"edit_title_{slug}")],
            [InlineKeyboardButton("🖼 Change Poster", callback_data=f"trigger_poster_{slug}")],
            [InlineKeyboardButton("🗑 Purge", callback_data=f"confirm_purge_{slug}")],
            [InlineKeyboardButton("❌ Abort", callback_data="cancel_op")]
        ]
        await callback_query.message.edit_text(f"🏛 **Management: {anime['title']}**\nSlug: `{slug}`", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_callback_query(filters.regex("^rengidx_"))
    async def rename_group_cb(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        state = user_state.get(callback_query.from_user.id)
        if not state or "group_names" not in state: return await callback_query.answer("❌ Session Expired", show_alert=True)

        gname = state["group_names"][idx]
        user_state[callback_query.from_user.id].update({"action": "ask_rename_group_new_name", "old_name": gname})
        await callback_query.message.edit_text(f"✏️ **Rename Group: {gname}**\n\nSend the **New Name** for this group:", reply_markup=None)

    @bot.on_callback_query(filters.regex("^editlidx_"))
    async def edit_links_cb(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        state = user_state.get(callback_query.from_user.id)
        if not state or "group_names" not in state: return await callback_query.answer("❌ Session Expired", show_alert=True)

        gname = state["group_names"][idx]
        user_state[callback_query.from_user.id].update({"action": "ask_edit_group_name", "group_name": gname})
        await callback_query.message.edit_text(f"🔗 **Updating Links: {gname}**\n\nExisting links for this quality will be replaced.\n🛰 **480p Link** (or `/skip`):", reply_markup=None)

    @bot.on_callback_query(filters.regex("^remgidx_"))
    async def remove_group_cb(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        state = user_state.get(callback_query.from_user.id)
        if not state or "group_names" not in state: return await callback_query.answer("❌ Session Expired", show_alert=True)

        gname, slug = state["group_names"][idx], state["slug"]
        anime = await db.get_anime_by_slug(slug)
        groups = anime.get("seasons_links", {})
        if gname in groups:
            del groups[gname]
            await db.anime.update_one({"slug": slug}, {"$set": {"seasons_links": groups}})
            await callback_query.answer(f"🗑 Removed {gname}", show_alert=True)
            return await manage_groups_cb(client, callback_query)
        await callback_query.answer("❌ Group already missing")

    @bot.on_callback_query(filters.regex("^edit_title_"))
    async def edit_title_cb(client, callback_query):
        slug = callback_query.data.split("edit_title_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_change_series_title", "slug": slug}
        await callback_query.message.edit_text("🏷 **Change Series Title:**\n\nSend the **New Title** for this series:", reply_markup=None)

    @bot.on_callback_query(filters.regex("^cancel_op$"))
    async def cancel_op_cb(client, callback_query):
        user_state.pop(callback_query.from_user.id, None)
        await callback_query.message.edit_text("✨ **Operation Cancelled.**", reply_markup=None)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^img_"))
    async def image_choice_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state or state["action"] != "ask_image_choice": return
        choice = callback_query.data.split("_")[1]
        user_state[uid]["image"] = state["anime_data"]["image"] if choice == "api" else None
        if choice == "api":
            user_state[uid]["action"] = "ask_seasons"
            await callback_query.message.edit_caption(caption="✅ **Asset Selected.**\n\nDefine group names:", reply_markup=None)
        else:
            user_state[uid]["action"] = "ask_manual_img"
            await callback_query.message.edit_caption(caption="🛰 **Direct Asset URL:**", reply_markup=None)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^finalcat_"))
    async def final_publish_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state or state["action"] != "ask_category_final": return
        cat, data = callback_query.data.split("_")[1], state["anime_data"]
        slug = slugify(data["title"])
        entry = {"mal_id": f"series_{slug}", "title": data["title"], "slug": slug, "synopsis": data["synopsis"], "score": data["score"], "image": state["image"], "genres": data["genres"], "category": cat, "status": data["status"], "year": data["year"], "trailer": data["trailer"], "studios": data.get("studios", []), "seasons_links": state["seasons_data"], "custom_buttons": []}
        try:
            if await db.ping():
                await db.anime.update_one({"slug": slug}, {"$set": entry}, upsert=True)
                await callback_query.message.edit_text(text=f"💎 **LIVE:** `{data['title']}`\nPortal: {Config.BASE_URL}/anime/{slug}", reply_markup=None)
                del user_state[uid]
            else:
                await callback_query.answer("❌ Database Offline", show_alert=True)
        except Exception as e: await callback_query.answer(f"DB Error: {e}", show_alert=True)

    @bot.on_callback_query(filters.regex("^setcat_"))
    async def auto_post_set_cat_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state or state["action"] != "ask_category": return
        cat, data = callback_query.data.split("_")[1], state["anime_data"]
        slug = slugify(data["title"])
        entry = {"mal_id": f"auto_{slug}", "title": data["title"], "slug": slug, "synopsis": data["synopsis"], "score": data["score"], "image": state["image"], "genres": data["genres"], "category": cat, "status": data["status"], "year": data["year"], "trailer": data["trailer"], "studios": data.get("studios", []), "seasons_links": {"1": {"480p": None, "720p": None, "1080p": None}}, "custom_buttons": []}
        try:
            if await db.ping():
                await db.anime.update_one({"slug": slug}, {"$set": entry}, upsert=True)
                await callback_query.message.edit_caption(caption=f"⚡ **Deployment Success!**\nPortal: {Config.BASE_URL}/anime/{slug}", reply_markup=None)
                del user_state[uid]
            else:
                await callback_query.answer("❌ Database Offline", show_alert=True)
        except Exception as e: await callback_query.answer(f"DB Error: {e}", show_alert=True)

    # --- INTERACTION HANDLER (GROUP 1) ---

    @bot.on_message(filters.private & (filters.text | filters.document) & ~filters.command(["start", "help", "search", "add_post", "add_page", "edit", "categories", "del", "cancel", "change_poster", "ping", "schedule", "manual", "edit_m", "save"]), group=1)
    async def interaction_handler(client, message):
        uid = message.from_user.id
        state = user_state.get(uid)
        if not state: return

        if not message.text and state.get("action") != "awaiting_restore_zip":
            return await message.reply("❌ **Invalid Input.** Please send text.")

        action = state.get("action", "")
        try:
            if action == "ask_search_query":
                return await search_handler(client, message, is_retry=True)
            elif action == "ask_manual_title":
                user_state[uid].update({"title": message.text.strip(), "action": "ask_manual_synopsis"})
                await message.reply("📝 **Step 2: Synopsis**\nSend Synopsis:")
            elif action == "ask_manual_synopsis":
                user_state[uid].update({"synopsis": message.text.strip(), "action": "ask_manual_genre"})
                await message.reply("📝 **Step 3: Genre**\nSend Genre (e.g. Action, Comedy):")
            elif action == "ask_manual_genre":
                user_state[uid].update({"genre": message.text.strip(), "action": "ask_manual_image"})
                await message.reply("📝 **Step 4: Image URL**\nSend direct link to image:")
            elif action == "ask_manual_image":
                user_state[uid].update({"image": message.text.strip(), "action": "ask_manual_rating"})
                await message.reply("📝 **Step 5: Rating**\nSend Rating (e.g. 8.5):")
            elif action == "ask_manual_rating":
                user_state[uid].update({"rating": message.text.strip(), "action": "ask_manual_btn_count"})
                await message.reply("📝 **Step 6: How many buttons do you want to add?**\nSend a number:")
            elif action == "ask_manual_btn_count":
                try:
                    count = int(message.text.strip())
                    if count < 0: raise ValueError
                    user_state[uid].update({"btn_count": count, "current_btn": 1, "buttons": [], "action": "ask_manual_btn_name" if count > 0 else "manual_publish"})
                    if count > 0:
                        await message.reply(f"🔗 **Button 1 Name:**")
                    else:
                        return await interaction_handler(client, message) # Trigger publish
                except: await message.reply("❌ **Invalid number.** Send a valid integer:")
            elif action == "ask_manual_btn_name":
                user_state[uid]["temp_btn_name"] = message.text.strip()
                user_state[uid]["action"] = "ask_manual_btn_link"
                await message.reply(f"🔗 **Button {state['current_btn']} Link:**")
            elif action == "ask_manual_btn_link":
                if not message.text.strip().startswith("http"):
                    return await message.reply("❌ **Invalid Link.** Must start with http/https. Send again:")
                user_state[uid]["buttons"].append({"name": state["temp_btn_name"], "link": message.text.strip()})
                if state["current_btn"] < state["btn_count"]:
                    user_state[uid]["current_btn"] += 1
                    user_state[uid]["action"] = "ask_manual_btn_name"
                    await message.reply(f"🔗 **Button {user_state[uid]['current_btn']} Name:**")
                else:
                    user_state[uid]["action"] = "manual_publish"
                    return await interaction_handler(client, message)

            # --- PUBLISH MANUAL ---
            elif action == "manual_publish":
                slug = slugify(state["title"])
                entry = {
                    "mal_id": f"manual_{slug}",
                    "title": state["title"],
                    "slug": slug,
                    "synopsis": state["synopsis"],
                    "score": state["rating"],
                    "image": state["image"],
                    "genres": [g.strip() for g in state["genre"].split(",")],
                    "category": state["genre"].split(",")[0].strip(),
                    "status": "Manual",
                    "year": "N/A",
                    "custom_buttons": state.get("buttons", []),
                    "seasons_links": {}
                }
                if await db.ping():
                    await db.anime.update_one({"slug": slug}, {"$set": entry}, upsert=True)
                    await message.reply(f"🚀 **Custom Page Published!**\nPortal: {Config.BASE_URL}/anime/{slug}")
                else:
                    await message.reply("❌ Database Offline")
                del user_state[uid]
            elif action == "ask_rename_group_new_name":
                new_name = message.text.strip()
                slug, old_name = state["slug"], state["old_name"]
                anime = await db.get_anime_by_slug(slug)
                if anime:
                    groups = anime.get("seasons_links", {})
                    if old_name in groups:
                        groups[new_name] = groups.pop(old_name)
                        await db.anime.update_one({"slug": slug}, {"$set": {"seasons_links": groups}})
                        await message.reply(f"✅ **Group Renamed:** `{old_name}` → `{new_name}`")
                    else: await message.reply("❌ Group mismatch.")
                else: await message.reply("❌ Series not found.")
                del user_state[uid]
            elif action == "ask_change_series_title":
                new_title = message.text.strip()
                old_slug = state["slug"]
                new_slug = slugify(new_title)
                if await db.ping():
                    res = await db.anime.update_one({"slug": old_slug}, {"$set": {"title": new_title, "slug": new_slug}})
                    if res.modified_count:
                        await message.reply(f"✅ **Identity Synchronized!**\n🏷 New Title: `{new_title}`\n🔗 New URL: {Config.BASE_URL}/anime/{new_slug}")
                    else:
                        await message.reply("❌ **Update Failed.** Identity already matches or series missing.")
                else:
                    await message.reply("❌ Database Offline")
                del user_state[uid]

            # --- EDIT_M FLOW ---
            elif action == "ask_edit_m_count":
                try:
                    count = int(message.text.strip())
                    if count <= 0: return await message.reply("❌ **Number must be greater than 0.**")
                    user_state[uid].update({"btn_count": count, "current_btn": 1, "new_buttons": [], "action": "ask_edit_m_btn_name"})
                    await message.reply(f"🔗 **Button 1 Name:**")
                except: await message.reply("❌ **Invalid number.** Send a valid integer:")
            elif action == "ask_edit_m_btn_name":
                user_state[uid]["temp_btn_name"] = message.text.strip()
                user_state[uid]["action"] = "ask_edit_m_btn_link"
                await message.reply(f"🔗 **Button {state['current_btn']} Link:**")
            elif action == "ask_edit_m_btn_link":
                if not message.text.strip().startswith("http"):
                    return await message.reply("❌ **Invalid Link.** Must start with http/https. Send again:")
                user_state[uid]["new_buttons"].append({"name": state["temp_btn_name"], "link": message.text.strip()})
                if state["current_btn"] < state["btn_count"]:
                    user_state[uid]["current_btn"] += 1
                    user_state[uid]["action"] = "ask_edit_m_btn_name"
                    await message.reply(f"🔗 **Button {user_state[uid]['current_btn']} Name:**")
                else:
                    # Update database
                    existing_buttons = state["anime"].get("custom_buttons", [])
                    existing_buttons.extend(state["new_buttons"])
                    if await db.ping():
                        await db.anime.update_one({"slug": state["slug"]}, {"$set": {"custom_buttons": existing_buttons}})
                        await message.reply(f"✅ **Buttons Synchronized!**\nPage: {Config.BASE_URL}/anime/{state['slug']}")
                    else:
                        await message.reply("❌ Database Offline")
                    del user_state[uid]

            elif action == "ask_cat_name":
                await db.add_category(message.text.strip())
                await message.reply(f"✅ **Category Created.** Use /categories to view.")
                del user_state[uid]
            elif action == "ask_sched_content":
                if message.text != "/skip": await db.update_schedule(state["day"], message.text.strip())
                await message.reply(f"✅ **Schedule Updated.**")
                del user_state[uid]
            elif action == "awaiting_restore_zip":
                if not message.document or not message.document.file_name.endswith(".zip"):
                    return await message.reply("❌ **Invalid File.** Please upload a valid .zip backup file.")

                msg = await message.reply("⏳ **Restoring database records...**")
                path = None
                try:
                    path = await message.download()
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        with zipfile.ZipFile(path, 'r') as zip_ref:
                            zip_ref.extractall(tmp_dir)

                        restored_data = {}
                        for filename in os.listdir(tmp_dir):
                            if filename.endswith(".json"):
                                coll_name = filename[:-5]
                                with open(os.path.join(tmp_dir, filename), 'r') as f:
                                    restored_data[coll_name] = json.load(f)

                        if not restored_data:
                            return await msg.edit("❌ **Restoration Failed:** No compatible JSON data found within the ZIP.")

                        success = await db.import_data(restored_data)
                        if success:
                            await msg.edit("✅ **Restoration Successful!** The database has been fully synchronized.")
                            del user_state[uid]
                        else:
                            await msg.edit("❌ **Restoration Failed:** An error occurred during database synchronization.")
                except Exception as e:
                    logger.error(f"Restore Error: {e}")
                    await msg.edit(f"❌ **Restoration Failed:** `{str(e)}`")
                finally:
                    if path and os.path.exists(path):
                        os.remove(path)
            elif action == "ask_new_poster":
                slug = state["slug"]
                if await db.ping():
                    res = await db.anime.update_one({"slug": slug}, {"$set": {"image": message.text.strip()}})
                    await message.reply("✅ **Visual Synchronized.**" if res.modified_count else "❌ **Update Failed.**")
                else:
                    await message.reply("❌ Database Offline")
                del user_state[uid]
            elif action == "ask_edit_group_name":
                gname = state.get("group_name") or message.text.strip()
                user_state[uid].update({"action": "ask_edit_480p", "group_name": gname})
                await message.reply(f"📦 **Group: {gname}**\n\n🛰 **480p Link** (or /skip):")
            elif action == "ask_edit_480p":
                user_state[uid]["480p"] = message.text if message.text != "/skip" else None
                user_state[uid]["action"] = "ask_edit_720p"
                await message.reply(f"🛰 **720p Link** (or /skip):")
            elif action == "ask_edit_720p":
                user_state[uid]["720p"] = message.text if message.text != "/skip" else None
                user_state[uid]["action"] = "ask_edit_1080p"
                await message.reply(f"🛰 **1080p Link** (or /skip):")
            elif action == "ask_edit_1080p":
                anime = await db.get_anime_by_slug(state["slug"])
                links = anime.get("seasons_links", {}) if anime else {}
                links[state["group_name"]] = {"480p": state.get("480p"), "720p": state.get("720p"), "1080p": message.text if message.text != "/skip" else None}
                if await db.ping():
                    await db.anime.update_one({"slug": state["slug"]}, {"$set": {"seasons_links": links}})
                    await message.reply(f"💎 **Success!** Added group.")
                else:
                    await message.reply("❌ Database Offline")
                del user_state[uid]
            elif action == "select_anime":
                try:
                    selected = search_results[uid][int(message.text) - 1]
                    details = await anime_api.get_details(selected["source"], selected["id"])
                    if not details: details = {"title": selected["title"], "image": selected["image"], "synopsis": "N/A", "score": 0, "genres": [], "year": selected["year"], "status": "N/A", "episodes": 0, "trailer": None}
                    user_state[uid].update({"action": "edit_title", "anime_data": details})
                    await message.reply(f"✨ **Intelligence Step 1: Title**\n🏷 Current: `{details['title']}`\n\nSend **New Title** or `/skip`:")
                except: await message.reply("❌ **Invalid selection.**")
            elif action == "edit_title":
                if message.text != "/skip": user_state[uid]["anime_data"]["title"] = message.text
                user_state[uid]["action"] = "edit_synopsis"
                await message.reply(f"✨ **Step 2: Synopsis**\n📥 Send **New Synopsis** or `/skip`:")
            elif action == "edit_synopsis":
                if message.text != "/skip": user_state[uid]["anime_data"]["synopsis"] = message.text
                user_state[uid]["action"] = "edit_score"
                await message.reply(f"✨ **Step 3: Rating**\n📥 Send **New Rating** or `/skip`:")
            elif action == "edit_score":
                if message.text != "/skip":
                    try: user_state[uid]["anime_data"]["score"] = float(message.text)
                    except: pass
                user_state[uid]["action"] = "ask_image_choice"
                buttons = [[InlineKeyboardButton("🖼 intelligence Poster", callback_data="img_api")], [InlineKeyboardButton("🔗 Manual Asset", callback_data="img_manual")]]
                await message.reply_photo(photo=user_state[uid]["anime_data"]["image"] or Config.LOGO_URL, caption="✨ **Step 4: Visual Selection**", reply_markup=InlineKeyboardMarkup(buttons))
            elif action == "ask_manual_img":
                user_state[uid]["image"] = message.text.strip()
                user_state[uid]["action"] = "ask_seasons"
                await message.reply("✅ **Asset Registered.**\n\n**Step 5: Groups** (e.g. `Season 1, OVA`):")
            elif action == "ask_seasons":
                groups = [s.strip() for s in message.text.split(",")]
                user_state[uid].update({"seasons_list": groups, "current_season_idx": 0, "seasons_data": {}, "action": f"ask_480p_{groups[0]}"})
                await message.reply(f"📦 **Architecting: {groups[0]}**\n\n🛰 **480p Link** or `/skip`:")
            elif "ask_480p_" in action:
                g = action.split("ask_480p_")[-1]
                user_state[uid]["seasons_data"][g] = {"480p": message.text if message.text != "/skip" else None}
                user_state[uid]["action"] = f"ask_720p_{g}"
                await message.reply(f"🛰 **720p Link** (or /skip):")
            elif "ask_720p_" in action:
                g = action.split("ask_720p_")[-1]
                user_state[uid]["seasons_data"][g]["720p"] = message.text if message.text != "/skip" else None
                user_state[uid]["action"] = f"ask_1080p_{g}"
                await message.reply(f"🛰 **1080p Link** (or /skip):")
            elif "ask_1080p_" in action:
                g = action.split("ask_1080p_")[-1]
                user_state[uid]["seasons_data"][g]["1080p"] = message.text if message.text != "/skip" else None
                user_state[uid]["current_season_idx"] += 1
                if user_state[uid]["current_season_idx"] < len(user_state[uid]["seasons_list"]):
                    next_s = user_state[uid]["seasons_list"][user_state[uid]["current_season_idx"]]
                    user_state[uid]["action"] = f"ask_480p_{next_s}"
                    await message.reply(f"📦 **Architecting: {next_s}**\n\n🛰 **480p Link** or `/skip`:")
                else:
                    user_state[uid]["action"] = "ask_category_final"
                    cats = await db.get_all_categories()
                    buttons = [[InlineKeyboardButton(c['name'], callback_data=f"finalcat_{c['name']}")] for c in (cats if cats else [{"name": "Anime"}])]
                    await message.reply("🛰 **Aggregation Complete.**\nTarget **Category**:", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            logger.error(f"Interaction Error: {e}\n{traceback.format_exc()}")
            await message.reply(f"❌ **System Error:** `{str(e)}`")
            user_state.pop(uid, None)
