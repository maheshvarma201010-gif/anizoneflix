import asyncio
import logging
import traceback
import os
import json
import zipfile
import tempfile
import secrets
from urllib.parse import unquote
from io import BytesIO
from bson import ObjectId
from pyrogram import Client, filters, enums, ContinuePropagation
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from config.config import Config
from api.anime_api import anime_api
from database.db import db
from utils.utils import slugify
from utils.parser import parse_filename

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MZ_BOT")

bot = Client(
    "mz_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    proxy=Config.TG_PROXY,
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
        BotCommand("ping", "System Latency Check"),
        BotCommand("preview", "Preview drafts"),
        BotCommand("editz", "Edit draft metadata"),
        BotCommand("sort", "Sort drafts"),
        BotCommand("done", "Publish drafts")
    ]
    await client.set_bot_commands(commands)
    logger.info("Bot commands synchronized.")

def extract_slug(text):
    """Bulletproof slug extraction from any URL or raw text"""
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
        if (message.document or message.video) and message.from_user and not message.from_user.is_bot:
            state = user_state.get(message.from_user.id)
            if state and state.get("action") == "uploading":
                try:
                    media = message.document or message.video
                    fname = media.file_name or "video.mp4"
                    caption = message.caption or ""

                    # Extract metadata from filename or caption
                    parsed = parse_filename(fname)
                    if caption:
                        # Try to extract from caption if filename fails or to refine
                        c_parsed = parse_filename(caption)
                        if c_parsed["episode"] != 1: parsed["episode"] = c_parsed["episode"]
                        if c_parsed["season"] != 1: parsed["season"] = c_parsed["season"]
                        if c_parsed["quality"] != "HD": parsed["quality"] = c_parsed["quality"]

                    # Forward to BIN_CHANNEL
                    fwd = await message.forward(Config.BIN_CHANNEL)

                    hash_token = secrets.token_hex(12)
                    ep_data = {
                        "mal_id": state["mal_id"],
                        "season": parsed["season"],
                        "episode": parsed["episode"],
                        "quality": parsed["quality"],
                        "audio": parsed["audio"],
                        "codec": parsed["codec"],
                        "file_id": media.file_id,
                        "msg_id": fwd.id,
                        "file_name": fname,
                        "file_size": media.file_size,
                        "hash": hash_token,
                        "status": "draft",
                        "uploaded_by": message.from_user.id,
                        "views": 0,
                        "downloads": 0
                    }

                    if await db.ping():
                        await db.add_episode(ep_data)
                        await message.reply(
                            f"✅ **Draft Saved:** S{parsed['season']} E{parsed['episode']} ({parsed['quality']})\n"
                            f"📂 `{fname}`\n"
                            f"🔗 Token: `{hash_token}`\n\n"
                            "Continue sending files or send /done to publish."
                        )
                except Exception as e:
                    logger.error(f"Upload Error: {e}")
                    await message.reply(f"❌ **Upload Failed:** {str(e)}")

                raise ContinuePropagation

            try:
                fname = message.document.file_name if message.document else "video.mp4"
                parsed = parse_filename(fname)
                if await db.ping():
                    anime = await db.anime.find_one({"title": {"$regex": parsed["title"], "$options": "i"}})
                    if anime:
                        await db.add_episode({
                            "mal_id": anime["mal_id"], "season": parsed["season"], "episode": parsed["episode"],
                            "quality": parsed["quality"], "audio": parsed["audio"], "codec": parsed["codec"],
                            "file_id": message.document.file_id if message.document else message.video.file_id,
                            "file_name": fname, "file_size": "N/A", "views": 0, "downloads": 0,
                            "status": "published"
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
        caption = (
            "👑 **MOVIESZONEFLIX PREMIUM v2.0**\n\n"
            "Welcome to the premier Movies & Series Management Suite. Experience seamless automation and high-speed metadata intelligence.\n\n"
            "⚡ **Quick Start:**\n"
            "• `/search <name>` — Automated series setup\n"
            "• `/add_post <name>` — Rapid one-shot publication\n"
            "• `/add_page` — Manual content creation\n"
            "• `/edit <url>` — Manage content groups\n"
            "• `/help` — View full documentation"
        )
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 Access Portal", url=Config.BASE_URL)],
            [InlineKeyboardButton("📚 Admin Guide", callback_data="help_guide")]
        ])
        try:
            await message.reply_photo(
                photo=Config.LOGO_URL,
                caption=caption,
                reply_markup=reply_markup
            )
        except Exception:
            await message.reply_text(
                text=caption,
                reply_markup=reply_markup
            )

    @bot.on_message(filters.command("help"))
    async def help_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.** This zone is for authorized administrators only.")

        text = (
            "👑 **MOVIESZONEFLIX ULTRA: Executive Suite**\n\n"
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

            caption = f"🎬 **Archive Ready:** `{details['title']}`\n\nTarget **Category**:"
            try:
                await message.reply_photo(
                    photo=details["image"] if details["image"] else Config.LOGO_URL,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            except Exception:
                await message.reply_text(
                    text=caption,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            await msg.delete()
        except Exception as e:
            logger.error(f"Add Post Error: {e}")
            await msg.edit("❌ **Rapid Deployment Failure.**")

    @bot.on_message(filters.command(["edit", "edit_m"]))
    async def unified_edit_handler(client, message):
        if not message.from_user or not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Unauthorized.**")

        query = " ".join(message.command[1:]).strip()
        if not query and message.reply_to_message:
            query = (message.reply_to_message.text or message.reply_to_message.caption or "").strip()

        slug = extract_slug(query)
        if not slug:
            return await message.reply("💡 **Usage:** `/edit <url>` (or reply to a link)")

        try:
            anime = await db.get_anime(slug)
            if not anime:
                results = await db.search_anime_db(query)
                if results: anime = results[0]

            if not anime: return await message.reply(f"❌ **Not Found:** `{slug}`")
            aid = anime["_id"]

            buttons = [
                [InlineKeyboardButton("📤 Upload Media (Draft)", callback_data=f"upload_media_{aid}")],
                [InlineKeyboardButton("📦 Content Groups (Seasons)", callback_data=f"manage_groups_{aid}")],
                [InlineKeyboardButton("🔗 External Redirects (Buttons)", callback_data=f"manage_btns_{aid}")],
                [InlineKeyboardButton("📂 Change Category", callback_data=f"manage_category_{aid}")],
                [InlineKeyboardButton("🏷 Change Title", callback_data=f"edit_title_{aid}")],
                [InlineKeyboardButton("🖼 Change Poster", callback_data=f"trigger_poster_{aid}")],
                [InlineKeyboardButton("🗑 Purge Archive", callback_data=f"confirm_purge_{aid}")],
                [InlineKeyboardButton("❌ Abort", callback_data="cancel_op")]
            ]
            await message.reply(
                f"🏛 **Executive Suite: {anime['title']}**\n"
                f"ID: `{aid}`\n\n"
                "Select a sector to manage:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception as e:
            logger.error(f"Edit Cmd Error: {e}")
            await message.reply("❌ **Intelligence Feed Offline.**")

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
        if not message.from_user or not await is_authorized(message.from_user.id): return
        user_state[message.from_user.id] = {"action": "ask_manual_title"}
        await message.reply("📝 **Step 1: Title**\nSend Title for the custom page:")


    @bot.on_message(filters.command("save"))
    async def save_command_handler(client, message):
        if not message.from_user or not await is_authorized(message.from_user.id):
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
        if message.from_user:
            uid = message.from_user.id
            state = user_state.get(uid)
            if state and state.get("action") == "uploading":
                await db.delete_drafts(state["mal_id"], uid)
                await message.reply("🗑 **Upload Session Purged.** Drafts deleted.")
            user_state.pop(uid, None)
        else:
            await message.reply("✨ **Action Cancelled.** standby.")

    @bot.on_message(filters.command("preview"))
    async def preview_handler(client, message):
        if not message.from_user or not await is_authorized(message.from_user.id): return
        state = user_state.get(message.from_user.id)
        if not state or state.get("action") != "uploading":
            return await message.reply("❌ No active upload session.")

        drafts = await db.get_episodes(state["mal_id"], status="draft")
        if not drafts: return await message.reply("📭 No drafts in current session.")

        text = f"📑 **Preview: {state['title']} (Drafts)**\n\n"
        # Group by season for display
        seasons = {}
        for d in drafts:
            s = d['season']
            if s not in seasons: seasons[s] = []
            seasons[s].append(d)

        for s in sorted(seasons.keys()):
            text += f"**Season {s}**\n"
            for d in sorted(seasons[s], key=lambda x: x['episode']):
                text += f" • E{d['episode']} [{d['quality']}] - {d['file_name'][:30]}...\n"
            text += "\n"

        text += f"🔗 [View on Site]({Config.BASE_URL}/anime/{slugify(state['title'])})\n"
        text += "Send /done to publish or /editz to modify."
        await message.reply(text, disable_web_page_preview=True)

    @bot.on_message(filters.command("done"))
    async def done_handler(client, message):
        if not message.from_user or not await is_authorized(message.from_user.id): return
        uid = message.from_user.id
        state = user_state.get(uid)
        if not state or state.get("action") != "uploading":
            return await message.reply("❌ No active upload session.")

        # Ask for session language before publishing
        buttons = [
            [InlineKeyboardButton("Telugu", callback_data=f"publang_Telugu_{state['mal_id']}")],
            [InlineKeyboardButton("Tamil", callback_data=f"publang_Tamil_{state['mal_id']}")],
            [InlineKeyboardButton("Hindi", callback_data=f"publang_Hindi_{state['mal_id']}")],
            [InlineKeyboardButton("English", callback_data=f"publang_English_{state['mal_id']}")],
            [InlineKeyboardButton("Multi-Audio", callback_data=f"publang_Multi-Audio_{state['mal_id']}")],
            [InlineKeyboardButton("Skip (Use Parsed)", callback_data=f"publang_skip_{state['mal_id']}")]
        ]
        await message.reply(
            f"🌐 **Finalize Session: {state['title']}**\n\nSelect the primary language for this batch of files:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    @bot.on_message(filters.command("editz"))
    async def editz_handler(client, message):
        if not message.from_user or not await is_authorized(message.from_user.id): return
        state = user_state.get(message.from_user.id)
        if not state or state.get("action") != "uploading":
            return await message.reply("❌ No active upload session.")

        drafts = await db.get_episodes(state["mal_id"], status="draft")
        if not drafts: return await message.reply("📭 No drafts to edit.")

        buttons = []
        for d in drafts[:20]: # Limit to 20 for now
            label = f"S{d['season']} E{d['episode']} ({d['quality']})"
            buttons.append([InlineKeyboardButton(label, callback_data=f"edit_draft_{d['_id']}")])

        await message.reply("📝 **Select draft to edit:**", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_message(filters.command("sort"))
    async def sort_handler(client, message):
        if not message.from_user or not await is_authorized(message.from_user.id): return
        state = user_state.get(message.from_user.id)
        if not state or state.get("action") != "uploading":
            return await message.reply("❌ No active upload session.")

        buttons = [
            [InlineKeyboardButton("🔢 Auto Sort (S > E > Q)", callback_data=f"auto_sort_{state['mal_id']}")],
            [InlineKeyboardButton("🛡 Back", callback_data="cancel_op")]
        ]
        await message.reply("⚖️ **Manual & Auto Sorting Logic**\n\nChoose sorting strategy for current drafts:", reply_markup=InlineKeyboardMarkup(buttons))

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
        aid = callback_query.data.split("add_group_yes_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_edit_group_name", "slug": aid}
        await callback_query.message.edit_text("📝 **Group Identity:**\n*(e.g. Season 2, OVA, Movie)*", reply_markup=None)

    @bot.on_callback_query(filters.regex("^trigger_poster_"))
    async def trigger_poster_cb(client, callback_query):
        aid = callback_query.data.split("trigger_poster_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_new_poster", "slug": aid}
        await callback_query.message.edit_text("🖼 **New Asset URL:**", reply_markup=None)

    @bot.on_callback_query(filters.regex("^confirm_purge_"))
    async def confirm_purge_cb(client, callback_query):
        aid = callback_query.data.split("confirm_purge_")[-1]
        buttons = [[InlineKeyboardButton("🧨 PURGE EVERYTHING", callback_data=f"execute_purge_{aid}")],[InlineKeyboardButton("🛡 Abort", callback_data="cancel_op")]]
        await callback_query.message.edit_text(f"⚠️ **CRITICAL:** Purge `{aid}`?", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_callback_query(filters.regex("^execute_purge_"))
    async def execute_purge_cb(client, callback_query):
        aid = callback_query.data.split("execute_purge_")[-1]
        try:
            anime = await db.get_anime(aid)
            if anime:
                await db.delete_anime_by_slug(anime["slug"])
                await callback_query.message.edit_text(f"🔥 **Sanitized:** `{anime['slug']}` purged.", reply_markup=None)
            else:
                await callback_query.answer("❌ Already Deleted", show_alert=True)
        except Exception as e: await callback_query.answer(f"Purge Failed: {e}", show_alert=True)

    @bot.on_callback_query(filters.regex("^edit_sched_"))
    async def edit_sched_cb(client, callback_query):
        day = callback_query.data.split("edit_sched_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_sched_content", "day": day}
        current = await db.get_schedule(day)
        await callback_query.message.edit_text(f"📅 **Update: {day}**\n\nCurrent:\n`{current}`\n\nFormat: 1. NAME (TIME)\nSend `/skip` to cancel.", reply_markup=None)

    @bot.on_callback_query(filters.regex("^manage_groups_"))
    async def manage_groups_cb(client, callback_query):
        aid = callback_query.data.split("manage_groups_")[-1]
        anime = await db.get_anime(aid)
        if not anime: return await callback_query.answer("❌ Not Found", show_alert=True)

        groups = anime.get("seasons_links", {})
        group_list = list(groups.keys())
        user_state[callback_query.from_user.id] = {"slug": aid, "group_names": group_list}

        buttons = [[InlineKeyboardButton("➕ Add New Group", callback_data=f"add_cgrp_start_{aid}")]]
        for idx, gname in enumerate(group_list):
            display_name = (gname[:12] + '..') if len(gname) > 14 else gname
            row = [
                InlineKeyboardButton(f"⚙️ {display_name}", callback_data=f"selgidx_{idx}"),
                InlineKeyboardButton(f"🗑", callback_data=f"remgidx_{idx}")
            ]
            if idx > 0: row.append(InlineKeyboardButton("⬆️", callback_data=f"mvupg_{idx}"))
            if idx < len(group_list) - 1: row.append(InlineKeyboardButton("⬇️", callback_data=f"mvdng_{idx}"))
            buttons.append(row)

        buttons.append([InlineKeyboardButton("🛡 Back", callback_data=f"back_to_edit_{aid}")])
        await callback_query.message.edit_text(f"📝 **Groups: {anime['title']}**\nSelect a group to manage buttons or reorder:", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_callback_query(filters.regex("^selgidx_"))
    async def select_group_cb(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        state = user_state.get(callback_query.from_user.id)
        if not state: return await callback_query.answer("❌ Session Expired")

        gname = state["group_names"][idx]
        aid = state["slug"]
        anime = await db.get_anime(aid)
        group_data = anime.get("seasons_links", {}).get(gname, {})

        user_state[callback_query.from_user.id].update({"group_name": gname, "btn_labels": list(group_data.keys())})

        buttons = [
            [InlineKeyboardButton("➕ Add Button", callback_data=f"add_gbtn_start_{idx}")],
            [InlineKeyboardButton("🏷 Rename Group", callback_data=f"rengidx_{idx}")],
            [InlineKeyboardButton("🗑 Delete Group", callback_data=f"remgidx_{idx}")]
        ]

        for b_idx, label in enumerate(group_data.keys()):
            row = [
                InlineKeyboardButton(f"✏️ {label}", callback_data=f"egbtn_{idx}_{b_idx}"),
                InlineKeyboardButton(f"🗑", callback_data=f"rgbtn_{idx}_{b_idx}")
            ]
            if b_idx > 0: row.append(InlineKeyboardButton("⬆️", callback_data=f"mvupgb_{idx}_{b_idx}"))
            if b_idx < len(group_data) - 1: row.append(InlineKeyboardButton("⬇️", callback_data=f"mvdngb_{idx}_{b_idx}"))
            buttons.append(row)

        buttons.append([InlineKeyboardButton("🛡 Back", callback_data=f"manage_groups_{aid}")])
        await callback_query.message.edit_text(f"📦 **Group: {gname}**\nManage internal buttons:", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_callback_query(filters.regex("^manage_btns_"))
    async def manage_btns_cb(client, callback_query):
        aid = callback_query.data.split("manage_btns_")[-1]
        anime = await db.get_anime(aid)
        if not anime: return await callback_query.answer("❌ Not Found", show_alert=True)

        btns = anime.get("custom_buttons", [])
        user_state[callback_query.from_user.id] = {"slug": aid, "btns": btns}

        buttons = [[InlineKeyboardButton("➕ Add New Button", callback_data=f"add_btn_start_{aid}")]]
        for idx, btn in enumerate(btns):
            display_name = (btn['name'][:12] + '..') if len(btn['name']) > 14 else btn['name']
            row = [
                InlineKeyboardButton(f"✏️ {display_name}", callback_data=f"rebidx_{idx}"),
                InlineKeyboardButton(f"🗑", callback_data=f"rembidx_{idx}")
            ]
            if idx > 0: row.append(InlineKeyboardButton("⬆️", callback_data=f"mvupb_{idx}"))
            if idx < len(btns) - 1: row.append(InlineKeyboardButton("⬇️", callback_data=f"mvdnb_{idx}"))
            buttons.append(row)

        buttons.append([InlineKeyboardButton("🛡 Back", callback_data=f"back_to_edit_{aid}")])
        await callback_query.message.edit_text(f"🖇 **External Redirects: {anime['title']}**\nManage top-level buttons:", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_callback_query(filters.regex("^edit_m_back_"))
    async def edit_m_back_cb(client, callback_query):
        aid = callback_query.data.split("edit_m_back_")[-1]
        anime = await db.get_anime(aid)
        buttons = [
            [InlineKeyboardButton("📦 Add Custom Group", callback_data=f"add_cgrp_start_{aid}")],
            [InlineKeyboardButton("➕ Add Custom Button", callback_data=f"add_btn_start_{aid}")],
            [InlineKeyboardButton("📝 Manage Buttons", callback_data=f"manage_btns_{aid}")],
            [InlineKeyboardButton("🛡 Back to Archive", callback_data=f"back_to_edit_{aid}")],
            [InlineKeyboardButton("❌ Abort", callback_data="cancel_op")]
        ]
        await callback_query.message.edit_text(f"🖇 **Custom Button Management: {anime['title']}**", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_callback_query(filters.regex("^add_cgrp_start_"))
    async def add_cgrp_start_cb(client, callback_query):
        aid = callback_query.data.split("add_cgrp_start_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_cgrp_name", "slug": aid}
        await callback_query.message.edit_text("📦 **Custom Group Name:**\n*(e.g. English Dub, Batch Links)*", reply_markup=None)

    @bot.on_callback_query(filters.regex("^add_btn_start_"))
    async def add_btn_start_cb(client, callback_query):
        aid = callback_query.data.split("add_btn_start_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_new_btn_name", "slug": aid}
        await callback_query.message.edit_text("🖇 **New Button Name:**\n*(e.g. Watch Online, Join Channel)*", reply_markup=None)

    @bot.on_callback_query(filters.regex("^manage_category_"))
    async def manage_category_cb(client, callback_query):
        aid = callback_query.data.split("manage_category_")[-1]
        anime = await db.get_anime(aid)
        if not anime: return await callback_query.answer("❌ Not Found", show_alert=True)

        cats = await db.get_all_categories()
        current_cat = anime.get("category", "N/A")

        buttons = []
        for c in cats:
            name = c['name']
            label = f"✅ {name}" if name == current_cat else name
            buttons.append([InlineKeyboardButton(label, callback_data=f"setncat_{aid}:::{name}")])

        buttons.append([InlineKeyboardButton("🛡 Back", callback_data=f"back_to_edit_{aid}")])
        await callback_query.message.edit_text(
            f"📂 **Migrate Category: {anime['title']}**\n\n"
            f"Current: `{current_cat}`\n\n"
            "Select new destination category:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    @bot.on_callback_query(filters.regex("^setncat_"))
    async def set_new_category_cb(client, callback_query):
        data = callback_query.data.split("setncat_")[-1]
        aid, new_cat = data.split(":::")

        try:
            if await db.ping():
                anime = await db.get_anime(aid)
                if not anime: return await callback_query.answer("❌ Not Found")
                res = await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"category": new_cat}})
                if res.modified_count:
                    await callback_query.answer(f"🚀 Migrated to {new_cat}", show_alert=True)
                    callback_query.data = f"back_to_edit_{aid}"
                    return await back_to_edit_cb(client, callback_query)
                await callback_query.answer("⚠️ Category remains unchanged.")
            else:
                await callback_query.answer("❌ Database Offline", show_alert=True)
        except Exception as e:
            await callback_query.answer(f"❌ Error: {e}", show_alert=True)

    @bot.on_callback_query(filters.regex("^edit_draft_"))
    async def edit_draft_cb(client, callback_query):
        ep_id = callback_query.data.split("edit_draft_")[-1]
        user_state[callback_query.from_user.id].update({"action": "editing_draft", "ep_id": ep_id})
        await callback_query.message.edit_text(
            "✏️ **Draft Metadata Editor**\n\n"
            "Format: `Season | Episode | Quality | Title` (or `/skip` to cancel)\n"
            "Example: `1 | 5 | 1080p | The Hero Awakens`",
            reply_markup=None
        )

    @bot.on_callback_query(filters.regex("^auto_sort_"))
    async def auto_sort_cb(client, callback_query):
        mid = callback_query.data.split("auto_sort_")[-1]
        drafts = await db.get_episodes(mid, status="draft")
        # Sorting logic: Season ASC, Episode ASC, Quality DESC (assuming 1080p > 720p)
        sorted_eps = sorted(drafts, key=lambda x: (x.get('season', 1), x.get('episode', 1), x.get('quality', '')))

        for idx, ep in enumerate(sorted_eps):
            await db.update_episode(ep["_id"], {"sort_order": idx})

        await callback_query.answer("✅ Drafts re-indexed successfully.")
        await callback_query.message.edit_text("🔢 **Automatic indexing complete.** Drafts will follow S > E > Q order.")

    @bot.on_callback_query(filters.regex("^publang_"))
    async def publish_lang_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state or state.get("action") != "uploading":
            return await callback_query.answer("❌ Session Expired", show_alert=True)

        data = callback_query.data.split("_", 2)
        lang = data[1]
        mid = data[2]

        if lang != "skip":
            # Update all drafts with the selected language
            drafts = await db.get_episodes(mid, status="draft")
            for d in drafts:
                if d.get("uploaded_by") == uid:
                    await db.update_episode(d["_id"], {"audio": lang})

        await db.publish_episodes(mid, uid)
        user_state.pop(uid, None)

        await callback_query.message.edit_text(
            f"🚀 **Mission Accomplished!**\n\n"
            f"All drafts for `{state['title']}` are now **LIVE**.\n"
            f"Portal: {Config.BASE_URL}/anime/{slugify(state['title'])}"
        )
        await callback_query.answer("Content Published!")

    @bot.on_callback_query(filters.regex("^back_to_edit_"))
    async def back_to_edit_cb(client, callback_query):
        aid = callback_query.data.split("back_to_edit_")[-1]
        anime = await db.get_anime(aid)
        if not anime: return await callback_query.answer("❌ Not Found")

        buttons = [
            [InlineKeyboardButton("📤 Upload Media (Draft)", callback_data=f"upload_media_{aid}")],
            [InlineKeyboardButton("📦 Content Groups (Seasons)", callback_data=f"manage_groups_{aid}")],
            [InlineKeyboardButton("🔗 External Redirects (Buttons)", callback_data=f"manage_btns_{aid}")],
            [InlineKeyboardButton("📂 Change Category", callback_data=f"manage_category_{aid}")],
            [InlineKeyboardButton("🏷 Change Title", callback_data=f"edit_title_{aid}")],
            [InlineKeyboardButton("🖼 Change Poster", callback_data=f"trigger_poster_{aid}")],
            [InlineKeyboardButton("🗑 Purge Archive", callback_data=f"confirm_purge_{aid}")],
            [InlineKeyboardButton("❌ Abort", callback_data="cancel_op")]
        ]
        await callback_query.message.edit_text(
            f"🏛 **Executive Suite: {anime['title']}**\n"
            f"ID: `{aid}`\n\n"
            "Select a sector to manage:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    @bot.on_callback_query(filters.regex("^setposb_"))
    async def set_pos_btn_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state: return await callback_query.answer("❌ Session Expired")

        data = callback_query.data.split("_")[-1]
        anime = await db.get_anime(state["slug"])
        btns = anime.get("custom_buttons", [])

        if data == "select":
            buttons = []
            for i in range(len(btns) + 1):
                buttons.append(InlineKeyboardButton(str(i+1), callback_data=f"setposb_{i}"))

            # Group buttons in rows of 5
            rows = [buttons[i:i + 5] for i in range(0, len(buttons), 5)]
            return await callback_query.message.edit_text("🎯 **Select insertion point:**", reply_markup=InlineKeyboardMarkup(rows))

        pos = int(data)
        new_btn = {"name": state["btn_name"], "link": state["btn_link"]}
        if pos == -1: btns.append(new_btn)
        else: btns.insert(pos, new_btn)

        aid = state["slug"]
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_buttons": btns}})
        await callback_query.message.edit_text(f"✅ **Button '{state['btn_name']}' synchronized at position {pos if pos != -1 else len(btns)}.**")
        del user_state[uid]

    @bot.on_callback_query(filters.regex("^setposcg_"))
    async def set_pos_custom_group_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state: return await callback_query.answer("❌ Session Expired")

        data = callback_query.data.split("_")[-1]
        anime = await db.get_anime(state["slug"])
        groups = list(anime.get("seasons_links", {}).items())

        if data == "select":
            buttons = []
            for i in range(len(groups) + 1):
                buttons.append(InlineKeyboardButton(str(i+1), callback_data=f"setposcg_{i}"))
            rows = [buttons[i:i + 5] for i in range(0, len(buttons), 5)]
            return await callback_query.message.edit_text("🎯 **Select insertion point:**", reply_markup=InlineKeyboardMarkup(rows))

        pos = int(data)
        new_group = (state["cgrp_name"], state["cgrp_data"])
        if pos == -1: groups.append(new_group)
        else: groups.insert(pos, new_group)

        aid = state["slug"]
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": dict(groups)}})
        await callback_query.message.edit_text(f"✅ **Group '{state['cgrp_name']}' synchronized at position {pos if pos != -1 else len(groups)}.**")
        del user_state[uid]

    @bot.on_callback_query(filters.regex("^setposgb_"))
    async def set_pos_group_btn_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state: return await callback_query.answer("❌ Session Expired")

        data = callback_query.data.split("_")[-1]
        g_idx = state["g_idx"]
        anime = await db.get_anime(state["slug"])
        groups = list(anime.get("seasons_links", {}).items())
        gname, gdata = groups[g_idx]
        items = list(gdata.items())

        if data == "select":
            buttons = []
            for i in range(len(items) + 1):
                buttons.append(InlineKeyboardButton(str(i+1), callback_data=f"setposgb_{i}"))
            rows = [buttons[i:i + 5] for i in range(0, len(buttons), 5)]
            return await callback_query.message.edit_text("🎯 **Select insertion point:**", reply_markup=InlineKeyboardMarkup(rows))

        pos = int(data)
        new_btn = (state["new_label"], state["new_link"])
        if pos == -1: items.append(new_btn)
        else: items.insert(pos, new_btn)

        groups[g_idx] = (gname, dict(items))
        aid = state["slug"]
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": dict(groups)}})
        await callback_query.message.edit_text(f"✅ **Button '{state['new_label']}' synchronized in group '{gname}'.**")
        del user_state[uid]

    @bot.on_callback_query(filters.regex("^setposg_"))
    async def set_pos_group_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state: return await callback_query.answer("❌ Session Expired")

        data = callback_query.data.split("_")[-1]
        anime = await db.get_anime(state["slug"])
        groups = list(anime.get("seasons_links", {}).items())

        if data == "select":
            buttons = []
            for i in range(len(groups) + 1):
                buttons.append(InlineKeyboardButton(str(i+1), callback_data=f"setposg_{i}"))
            rows = [buttons[i:i + 5] for i in range(0, len(buttons), 5)]
            return await callback_query.message.edit_text("🎯 **Select insertion point:**", reply_markup=InlineKeyboardMarkup(rows))

        user_state[uid].update({"action": "ask_edit_480p", "insert_pos": int(data)})
        await callback_query.message.edit_text(f"📦 **Configuring: {state['group_name']}**\n\n🛰 **480p Link** (or /skip):")

    @bot.on_callback_query(filters.regex("^rgbtn_"))
    async def remove_group_btn_cb(client, callback_query):
        parts = callback_query.data.split("_")
        g_idx, b_idx = int(parts[1]), int(parts[2])
        state = user_state.get(callback_query.from_user.id)
        if not state: return await callback_query.answer("❌ Session Expired")

        aid = state["slug"]
        anime = await db.get_anime(aid)
        groups = list(anime.get("seasons_links", {}).items())

        gname, gdata = groups[g_idx]
        btn_labels = list(gdata.keys())
        label = btn_labels[b_idx]

        del gdata[label]
        groups[g_idx] = (gname, gdata)

        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": dict(groups)}})
        await callback_query.answer(f"🗑 Removed {label}")
        await select_group_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^egbtn_"))
    async def edit_group_btn_cb(client, callback_query):
        parts = callback_query.data.split("_")
        user_state[callback_query.from_user.id].update({
            "action": "ask_edit_gbtn_label",
            "g_idx": int(parts[1]),
            "b_idx": int(parts[2])
        })
        await callback_query.message.edit_text("✏️ **New Label for this button:**\n*(or `/skip` to keep current)*", reply_markup=None)

    @bot.on_callback_query(filters.regex("^mvupgb_"))
    async def move_gbtn_up_cb(client, callback_query):
        parts = callback_query.data.split("_")
        g_idx, b_idx = int(parts[1]), int(parts[2])
        if b_idx == 0: return await callback_query.answer("🔝 Already at top")

        state = user_state.get(callback_query.from_user.id)
        aid = state["slug"]
        anime = await db.get_anime(aid)
        groups = list(anime.get("seasons_links", {}).items())
        gname, gdata = groups[g_idx]

        items = list(gdata.items())
        items[b_idx], items[b_idx-1] = items[b_idx-1], items[b_idx]
        groups[g_idx] = (gname, dict(items))

        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": dict(groups)}})
        await select_group_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^mvdngb_"))
    async def move_gbtn_dn_cb(client, callback_query):
        parts = callback_query.data.split("_")
        g_idx, b_idx = int(parts[1]), int(parts[2])

        state = user_state.get(callback_query.from_user.id)
        aid = state["slug"]
        anime = await db.get_anime(aid)
        groups = list(anime.get("seasons_links", {}).items())
        gname, gdata = groups[g_idx]

        items = list(gdata.items())
        if b_idx >= len(items) - 1: return await callback_query.answer("🔚 Already at bottom")

        items[b_idx], items[b_idx+1] = items[b_idx+1], items[b_idx]
        groups[g_idx] = (gname, dict(items))

        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": dict(groups)}})
        await select_group_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^add_gbtn_start_"))
    async def add_gbtn_start_cb(client, callback_query):
        g_idx = int(callback_query.data.split("_")[-1])
        user_state[callback_query.from_user.id].update({"action": "ask_new_gbtn_label", "g_idx": g_idx})
        await callback_query.message.edit_text("➕ **New Button Label:**\n*(e.g. 1080p, Mirror 1)*", reply_markup=None)

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

        gname, aid = state["group_names"][idx], state["slug"]
        anime = await db.get_anime(aid)
        groups = anime.get("seasons_links", {})
        if gname in groups:
            del groups[gname]
            await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": groups}})
            await callback_query.answer(f"🗑 Removed {gname}", show_alert=True)
            return await manage_groups_cb(client, callback_query)
        await callback_query.answer("❌ Group already missing")

    @bot.on_callback_query(filters.regex("^mvupg_"))
    async def move_group_up_cb(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        state = user_state.get(callback_query.from_user.id)
        if not state or "group_names" not in state or idx == 0: return await callback_query.answer("❌ Error")

        aid = state["slug"]
        anime = await db.get_anime(aid)
        groups = anime.get("seasons_links", {})
        items = list(groups.items())
        items[idx], items[idx-1] = items[idx-1], items[idx]
        new_groups = dict(items)
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": new_groups}})
        await manage_groups_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^mvdng_"))
    async def move_group_dn_cb(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        state = user_state.get(callback_query.from_user.id)
        if not state or "group_names" not in state: return await callback_query.answer("❌ Error")

        aid = state["slug"]
        anime = await db.get_anime(aid)
        groups = anime.get("seasons_links", {})
        items = list(groups.items())
        if idx >= len(items) - 1: return await callback_query.answer("❌ Error")

        items[idx], items[idx+1] = items[idx+1], items[idx]
        new_groups = dict(items)
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": new_groups}})
        await manage_groups_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^mvupb_"))
    async def move_btn_up_cb(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        state = user_state.get(callback_query.from_user.id)
        if not state or "btns" not in state or idx == 0: return await callback_query.answer("❌ Error")

        aid = state["slug"]
        anime = await db.get_anime(aid)
        btns = anime.get("custom_buttons", [])
        btns[idx], btns[idx-1] = btns[idx-1], btns[idx]
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_buttons": btns}})
        await manage_btns_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^mvdnb_"))
    async def move_btn_dn_cb(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        state = user_state.get(callback_query.from_user.id)
        if not state or "btns" not in state: return await callback_query.answer("❌ Error")

        aid = state["slug"]
        anime = await db.get_anime(aid)
        btns = anime.get("custom_buttons", [])
        if idx >= len(btns) - 1: return await callback_query.answer("❌ Error")

        btns[idx], btns[idx+1] = btns[idx+1], btns[idx]
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_buttons": btns}})
        await manage_btns_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^rembidx_"))
    async def remove_btn_cb(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        state = user_state.get(callback_query.from_user.id)
        if not state or "btns" not in state: return await callback_query.answer("❌ Session Expired", show_alert=True)

        aid = state["slug"]
        anime = await db.get_anime(aid)
        btns = anime.get("custom_buttons", [])
        if idx < len(btns):
            btn_name = btns[idx]['name']
            btns.pop(idx)
            await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_buttons": btns}})
            await callback_query.answer(f"🗑 Removed {btn_name}", show_alert=True)
            return await manage_btns_cb(client, callback_query)
        await callback_query.answer("❌ Button missing")

    @bot.on_callback_query(filters.regex("^rebidx_"))
    async def edit_btn_cb(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        state = user_state.get(callback_query.from_user.id)
        if not state or "btns" not in state: return await callback_query.answer("❌ Session Expired", show_alert=True)

        btn = state["btns"][idx]
        user_state[callback_query.from_user.id].update({"action": "ask_edit_btn_name", "btn_idx": idx})
        await callback_query.message.edit_text(f"✏️ **Edit Button: {btn['name']}**\n\nSend the **New Name** for this button:", reply_markup=None)

    @bot.on_callback_query(filters.regex("^edit_title_"))
    async def edit_title_cb(client, callback_query):
        aid = callback_query.data.split("edit_title_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_change_series_title", "slug": aid}
        await callback_query.message.edit_text("🏷 **Change Series Title:**\n\nSend the **New Title** for this series:", reply_markup=None)

    @bot.on_callback_query(filters.regex("^upload_media_"))
    async def upload_media_cb(client, callback_query):
        aid = callback_query.data.split("upload_media_")[-1]
        anime = await db.get_anime(aid)
        if not anime: return await callback_query.answer("❌ Not Found")

        user_state[callback_query.from_user.id] = {
            "action": "uploading",
            "mal_id": anime["mal_id"],
            "aid": aid,
            "title": anime["title"]
        }
        await callback_query.message.edit_text(
            f"📤 **Upload Mode Activated: {anime['title']}**\n\n"
            "• Forward/Send video files or media.\n"
            "• Bot will extract metadata & generate stream links.\n"
            "• Files stay in **Draft** until you send /done.\n\n"
            "⚡ **Send files now...**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_op")]])
        )

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
        mal_id = f"series_{slug}"
        entry = {"mal_id": mal_id, "title": data["title"], "slug": slug, "synopsis": data["synopsis"], "score": data["score"], "image": state["image"], "genres": data["genres"], "category": cat, "status": data["status"], "year": data["year"], "trailer": data["trailer"], "studios": data.get("studios", []), "seasons_links": state["seasons_data"], "custom_buttons": []}
        try:
            if await db.ping():
                await db.anime.update_one({"slug": slug}, {"$set": entry}, upsert=True)
                anime = await db.get_anime_by_slug(slug)
                aid = str(anime["_id"])

                # Automatically transition to Upload Mode
                user_state[uid] = {
                    "action": "uploading",
                    "mal_id": mal_id,
                    "aid": aid,
                    "title": data["title"]
                }

                await callback_query.message.edit_text(
                    text=(
                        f"💎 **Page Created:** `{data['title']}`\n"
                        f"Portal: {Config.BASE_URL}/anime/{slug}\n\n"
                        "📤 **Upload Mode Activated Automatically!**\n\n"
                        "• Forward/Send video files or media now.\n"
                        "• Files stay in **Draft** until you send /done."
                    ),
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Stop Uploading", callback_data="cancel_op")]])
                )
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
        mal_id = f"auto_{slug}"
        entry = {"mal_id": mal_id, "title": data["title"], "slug": slug, "synopsis": data["synopsis"], "score": data["score"], "image": state["image"], "genres": data["genres"], "category": cat, "status": data["status"], "year": data["year"], "trailer": data["trailer"], "studios": data.get("studios", []), "seasons_links": {}, "custom_buttons": []}
        try:
            if await db.ping():
                await db.anime.update_one({"slug": slug}, {"$set": entry}, upsert=True)
                anime = await db.get_anime_by_slug(slug)
                aid = str(anime["_id"])

                # Automatically transition to Upload Mode
                user_state[uid] = {
                    "action": "uploading",
                    "mal_id": mal_id,
                    "aid": aid,
                    "title": data["title"]
                }

                await callback_query.message.edit_caption(
                    caption=(
                        f"⚡ **Deployment Success:** `{data['title']}`\n"
                        f"Portal: {Config.BASE_URL}/anime/{slug}\n\n"
                        "📤 **Upload Mode Activated Automatically!**\n\n"
                        "• Forward/Send video files or media now.\n"
                        "• Files stay in **Draft** until you send /done."
                    ),
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Stop Uploading", callback_data="cancel_op")]])
                )
            else:
                await callback_query.answer("❌ Database Offline", show_alert=True)
        except Exception as e: await callback_query.answer(f"DB Error: {e}", show_alert=True)

    # --- INTERACTION HANDLER (GROUP 1) ---

    @bot.on_message(filters.private & (filters.text | filters.document) & ~filters.command(["start", "help", "search", "add_post", "add_page", "edit", "categories", "del", "cancel", "change_poster", "ping", "schedule", "manual", "edit_m", "save"]), group=1)
    async def interaction_handler(client, message):
        if not message.from_user: return
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
                mal_id = f"manual_{slug}"
                entry = {
                    "mal_id": mal_id,
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
                    anime = await db.get_anime_by_slug(slug)
                    aid = str(anime["_id"])

                    # Automatically transition to Upload Mode
                    user_state[uid] = {
                        "action": "uploading",
                        "mal_id": mal_id,
                        "aid": aid,
                        "title": state["title"]
                    }

                    await message.reply(
                        f"🚀 **Custom Page Published!**\n"
                        f"Portal: {Config.BASE_URL}/anime/{slug}\n\n"
                        "📤 **Upload Mode Activated Automatically!**\n\n"
                        "• Forward/Send video files or media now.\n"
                        "• Files stay in **Draft** until you send /done.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Stop Uploading", callback_data="cancel_op")]])
                    )
                else:
                    await message.reply("❌ Database Offline")
            elif action == "ask_rename_group_new_name":
                new_name = message.text.strip()
                aid, old_name = state["slug"], state["old_name"]
                anime = await db.get_anime(aid)
                if anime:
                    groups = anime.get("seasons_links", {})
                    if old_name in groups:
                        groups[new_name] = groups.pop(old_name)
                        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": groups}})
                        await message.reply(f"✅ **Group Renamed:** `{old_name}` → `{new_name}`")
                    else: await message.reply("❌ Group mismatch.")
                else: await message.reply("❌ Series not found.")
                del user_state[uid]
            elif action == "ask_change_series_title":
                new_title = message.text.strip()
                aid = state["slug"]
                new_slug = slugify(new_title)
                if await db.ping():
                    res = await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"title": new_title, "slug": new_slug}})
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
            elif action == "ask_new_btn_name":
                user_state[uid].update({"action": "ask_new_btn_link", "btn_name": message.text.strip()})
                await message.reply(f"🔗 **URL for '{message.text.strip()}':**")
            elif action == "ask_new_btn_link":
                if not message.text.startswith("http"): return await message.reply("❌ Invalid URL.")
                user_state[uid].update({"action": "ask_btn_pos", "btn_link": message.text.strip()})
                buttons = [
                    [InlineKeyboardButton("🔝 Beginning", callback_data="setposb_0"), InlineKeyboardButton("🔚 End", callback_data="setposb_-1")],
                    [InlineKeyboardButton("🎯 Select Position", callback_data="setposb_select")]
                ]
                await message.reply("📍 **Position for the new button:**", reply_markup=InlineKeyboardMarkup(buttons))
            elif action == "ask_cgrp_name":
                user_state[uid].update({"action": "ask_cgrp_btn_count", "cgrp_name": message.text.strip()})
                await message.reply(f"🖇 **How many buttons in '{message.text.strip()}'?**\nSend a number (e.g. 3):")
            elif action == "ask_cgrp_btn_count":
                try:
                    count = int(message.text.strip())
                    if count <= 0: return await message.reply("❌ Must be greater than 0.")
                    user_state[uid].update({"action": "ask_cgrp_b_name", "btn_count": count, "current_idx": 1, "cgrp_data": {}})
                    await message.reply(f"🏷 **Button 1 Label:**")
                except: await message.reply("❌ Invalid number.")
            elif action == "ask_cgrp_b_name":
                user_state[uid].update({"action": "ask_cgrp_b_link", "temp_label": message.text.strip()})
                await message.reply(f"🔗 **URL for '{message.text.strip()}':**")
            elif action == "ask_cgrp_b_link":
                if not message.text.startswith("http"): return await message.reply("❌ Invalid URL.")
                state["cgrp_data"][state["temp_label"]] = message.text.strip()
                if state["current_idx"] < state["btn_count"]:
                    user_state[uid]["current_idx"] += 1
                    user_state[uid]["action"] = "ask_cgrp_b_name"
                    await message.reply(f"🏷 **Button {user_state[uid]['current_idx']} Label:**")
                else:
                    user_state[uid]["action"] = "ask_cgrp_pos"
                    buttons = [
                        [InlineKeyboardButton("🔝 Beginning", callback_data="setposcg_0"), InlineKeyboardButton("🔚 End", callback_data="setposcg_-1")],
                        [InlineKeyboardButton("🎯 Select Position", callback_data="setposcg_select")]
                    ]
                    await message.reply(f"📍 **Position for group '{state['cgrp_name']}':**", reply_markup=InlineKeyboardMarkup(buttons))
            elif action == "ask_new_gbtn_label":
                user_state[uid].update({"action": "ask_new_gbtn_link", "new_label": message.text.strip()})
                await message.reply(f"🔗 **URL for '{message.text.strip()}':**")
            elif action == "ask_new_gbtn_link":
                if not message.text.startswith("http"): return await message.reply("❌ Invalid URL.")
                user_state[uid].update({"action": "ask_gbtn_pos", "new_link": message.text.strip()})
                buttons = [
                    [InlineKeyboardButton("🔝 Beginning", callback_data="setposgb_0"), InlineKeyboardButton("🔚 End", callback_data="setposgb_-1")],
                    [InlineKeyboardButton("🎯 Select Position", callback_data="setposgb_select")]
                ]
                await message.reply("📍 **Position for the new button:**", reply_markup=InlineKeyboardMarkup(buttons))
            elif action == "ask_edit_gbtn_label":
                user_state[uid].update({"action": "ask_edit_gbtn_link", "new_label": message.text.strip()})
                await message.reply("🔗 **New URL:**\n*(or `/skip` to keep current)*")
            elif action == "ask_edit_gbtn_link":
                g_idx, b_idx = state["g_idx"], state["b_idx"]
                aid = state["slug"]
                anime = await db.get_anime(aid)
                groups = list(anime.get("seasons_links", {}).items())
                gname, gdata = groups[g_idx]
                items = list(gdata.items())
                old_label, old_link = items[b_idx]
                new_label = state["new_label"] if state["new_label"] != "/skip" else old_label
                new_link = message.text.strip() if message.text != "/skip" else old_link
                items[b_idx] = (new_label, new_link)
                groups[g_idx] = (gname, dict(items))
                await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": dict(groups)}})
                await message.reply("✅ Button updated.")
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
                aid = state["slug"]
                if await db.ping():
                    res = await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"image": message.text.strip()}})
                    await message.reply("✅ **Visual Synchronized.**" if res.modified_count else "❌ **Update Failed.**")
                else:
                    await message.reply("❌ Database Offline")
                del user_state[uid]
            elif action == "ask_edit_group_name":
                gname = state.get("group_name") or message.text.strip()
                user_state[uid].update({"action": "ask_group_pos", "group_name": gname})
                buttons = [
                    [InlineKeyboardButton("🔝 Beginning", callback_data="setposg_0"), InlineKeyboardButton("🔚 End", callback_data="setposg_-1")],
                    [InlineKeyboardButton("🎯 Select Position", callback_data="setposg_select")]
                ]
                await message.reply(f"📍 **Position for group '{gname}':**", reply_markup=InlineKeyboardMarkup(buttons))
            elif action == "ask_edit_480p":
                user_state[uid]["480p"] = message.text if message.text != "/skip" else None
                user_state[uid]["action"] = "ask_edit_720p"
                await message.reply(f"🛰 **720p Link** (or /skip):")
            elif action == "ask_edit_720p":
                user_state[uid]["720p"] = message.text if message.text != "/skip" else None
                user_state[uid]["action"] = "ask_edit_1080p"
                await message.reply(f"🛰 **1080p Link** (or /skip):")
            elif action == "ask_edit_1080p":
                aid = state["slug"]
                anime = await db.get_anime(aid)
                current_groups = list(anime.get("seasons_links", {}).items()) if anime else []
                new_group_data = (state["group_name"], {"480p": state.get("480p"), "720p": state.get("720p"), "1080p": message.text if message.text != "/skip" else None})

                pos = state.get("insert_pos", -1)
                if pos == -1: current_groups.append(new_group_data)
                else: current_groups.insert(pos, new_group_data)

                new_links = dict(current_groups)
                if await db.ping():
                    await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": new_links}})
                    await message.reply(f"💎 **Success!** Group synchronized.")
                else:
                    await message.reply("❌ Database Offline")
                del user_state[uid]
            elif action == "ask_edit_btn_name":
                user_state[uid].update({"action": "ask_edit_btn_link", "new_name": message.text.strip()})
                await message.reply(f"🔗 **New URL for '{message.text.strip()}':**\n*(or `/skip` to keep current)*")
            elif action == "editing_draft":
                if message.text == "/skip":
                    user_state[uid]["action"] = "uploading"
                    return await message.reply("Action aborted.")

                parts = [p.strip() for p in message.text.split("|")]
                if len(parts) < 3: return await message.reply("❌ Invalid format. Use: `S | E | Q | Title`")

                try:
                    update_data = {
                        "season": int(parts[0]),
                        "episode": int(parts[1]),
                        "quality": parts[2]
                    }
                    if len(parts) > 3: update_data["display_title"] = parts[3]

                    await db.update_episode(state["ep_id"], update_data)
                    user_state[uid]["action"] = "uploading"
                    await message.reply("✅ **Metadata Updated.** back to upload mode.")
                except Exception as e:
                    await message.reply(f"❌ Error: {str(e)}")

            elif action == "ask_edit_btn_link":
                idx, aid = state["btn_idx"], state["slug"]
                anime = await db.get_anime(aid)
                if anime:
                    btns = anime.get("custom_buttons", [])
                    if idx < len(btns):
                        btns[idx]['name'] = state["new_name"]
                        if message.text != "/skip": btns[idx]['link'] = message.text.strip()
                        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_buttons": btns}})
                        await message.reply(f"✅ **Button Updated.**")
                    else: await message.reply("❌ Error.")
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
                # Skip manual link entry, go straight to category
                user_state[uid].update({"seasons_data": {}, "action": "ask_category_final"})
                cats = await db.get_all_categories()
                buttons = [[InlineKeyboardButton(c['name'], callback_data=f"finalcat_{c['name']}")] for c in (cats if cats else [{"name": "Anime"}])]
                await message.reply("🛰 **Metadata Verified.**\nTarget **Category**:", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            logger.error(f"Interaction Error: {e}\n{traceback.format_exc()}")
            await message.reply(f"❌ **System Error:** `{str(e)}`")
            user_state.pop(uid, None)
