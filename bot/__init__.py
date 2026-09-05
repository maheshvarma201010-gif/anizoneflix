import asyncio
import logging
import traceback
import os
import json
import zipfile
import tempfile
import re
from urllib.parse import unquote
from io import BytesIO
from bson import ObjectId
from pyrogram import Client, filters, enums, ContinuePropagation
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.errors import MessageNotModified, FloodWait
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
        BotCommand("category_page", "Migrate Page Category"),
        BotCommand("songs", "Manage Background Songs"),
        BotCommand("uptime", "24/7 Bot Uptime Monitor"),
        BotCommand("setbot", "Configure Link Generator Bot"),
        BotCommand("ss", "Configure Pyrogram Session String"),
        BotCommand("save", "Backup & Restore Data"),
        BotCommand("cancel", "Abort Active Process"),
        BotCommand("ping", "System Latency Check")
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

def parse_buttons_string(text, expected_count):
    if not text:
        return None
    text = text.strip()
    # Split only on separator colons (not protocol colons)
    pattern = r'(?<!\bhttps)(?<!\bhttp)(?<!\btg):'
    parts = re.split(pattern, text)
    if len(parts) != expected_count + 1:
        return None  # Invalid colon count

    buttons = {}
    curr_name = parts[0].strip()
    if not curr_name:
        return None

    for i in range(1, len(parts)):
        part = parts[i].strip()
        if i < len(parts) - 1:
            subparts = part.rsplit(None, 1)
            if len(subparts) < 2:
                return None
            link, next_name = subparts
            link = link.strip()
            next_name = next_name.strip()

            if not link.startswith("http") and not link.startswith("tg"):
                return None

            buttons[curr_name] = link
            curr_name = next_name
        else:
            link = part
            if not link.startswith("http") and not link.startswith("tg"):
                return None
            buttons[curr_name] = link

    return buttons


def parse_range_link(text):
    if not text:
        return None
    text = text.strip()
    pattern1 = r'https?://(?:t\.me|telegram\.me|telegram\.dog)/([a-zA-Z0-9_]+)/(\d+)-https?://(?:t\.me|telegram\.me|telegram\.dog)/\1/(\d+)'
    m1 = re.search(pattern1, text)
    if m1:
        return m1.group(1), int(m1.group(2)), int(m1.group(3))

    pattern2 = r'https?://(?:t\.me|telegram\.me|telegram\.dog)/([a-zA-Z0-9_]+)/(\d+)-(\d+)'
    m2 = re.search(pattern2, text)
    if m2:
        return m2.group(1), int(m2.group(2)), int(m2.group(3))

    pattern3 = r'https?://(?:t\.me|telegram\.me|telegram\.dog)/c/(\d+)/(\d+)-https?://(?:t\.me|telegram\.me|telegram\.dog)/c/\1/(\d+)'
    m3 = re.search(pattern3, text)
    if m3:
        return f"c/{m3.group(1)}", int(m3.group(2)), int(m3.group(3))

    pattern4 = r'https?://(?:t\.me|telegram\.me|telegram\.dog)/c/(\d+)/(\d+)-(\d+)'
    m4 = re.search(pattern4, text)
    if m4:
        return f"c/{m4.group(1)}", int(m4.group(2)), int(m4.group(3))

    return None

def parse_genlink_bot_response(text):
    """
    Parses output returned by genlink bot.
    Extracts video quality (e.g. 480p, 720p, 1080p, 4k), episode number if present,
    and generated link (https://telegram.me/... or https://t.me/...).
    Returns dict or None.
    """
    if not text:
        return None

    # Extract link
    link_match = re.search(r'https?://(?:telegram\.me|t\.me|telegram\.dog)/[^\s"]+', text)
    if not link_match:
        return None
    link = link_match.group(0).strip('"\').,()')

    # Extract quality
    quality = "720P" # default quality if unspecified
    q_match = re.search(r'(480p|720p|1080p|2160p|4k)', text, re.IGNORECASE)
    if q_match:
        quality = q_match.group(1).upper()
        if quality == "4K":
            quality = "2160P"

    # Extract episode number if present
    episode = None
    ep_match = re.search(r'(?:S\d+)?E(\d+)|Episode\s*(\d+)|EP\s*(\d+)', text, re.IGNORECASE)
    if ep_match:
        ep_str = ep_match.group(1) or ep_match.group(2) or ep_match.group(3)
        if ep_str:
            episode = int(ep_str)

    return {
        "link": link,
        "quality": quality,
        "episode": episode
    }

async def process_range_link_task(bot_client, status_msg, aid, chat_slug, start_id, end_id, group_names):
    """
    Background processing task for range link processing.
    Sends /genlink https://t.me/<chat_slug>/<msg_id> for each message ID in range,
    collects output link & quality, organizes by serial-numbered groups,
    and updates database.
    """
    try:
        configured_bot = await db.get_configured_bot()
        configured_ss = await db.get_configured_session()

        if not configured_bot:
            return await status_msg.edit_text("❌ **Automation Aborted:** Bot username not set. Please set it using `/setbot`.")
        if not configured_ss:
            return await status_msg.edit_text("❌ **Automation Aborted:** Pyrogram session string not set. Please set it using `/ss`.")

        await status_msg.edit_text(
            f"🔄 **Starting Link Generation Process...**\n\n"
            f"🤖 **Bot:** `@{configured_bot}`\n"
            f"🔢 **IDs:** `{start_id}` to `{end_id}`\n\n"
            "Connecting user session client..."
        )

        user_client = Client(
            "genlink_user_session",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            session_string=configured_ss,
            in_memory=True
        )

        await user_client.start()

        # Temporary storage for collected outputs
        # List of collected parsed dicts in sequence
        collected_outputs = []
        failed_ids = []

        total_msgs = end_id - start_id + 1

        for current_idx, msg_id in enumerate(range(start_id, end_id + 1), 1):
            if current_idx % 5 == 0 or current_idx == total_msgs:
                try:
                    await status_msg.edit_text(
                        f"⏳ **Processing Messages ({current_idx}/{total_msgs})...**\n\n"
                        f"Current Message ID: `{msg_id}`\n"
                        f"Collected: `{len(collected_outputs)}`"
                    )
                except Exception:
                    pass

            target_link = f"https://t.me/{chat_slug}/{msg_id}"
            cmd_text = f"/genlink {target_link}"

            try:
                # Send command to configured bot
                sent_req = await user_client.send_message(configured_bot, cmd_text)

                # Wait for response from configured bot
                bot_reply = None
                for _ in range(15):
                    await asyncio.sleep(1)
                    async for history_msg in user_client.get_chat_history(configured_bot, limit=5):
                        if history_msg.id > sent_req.id and not history_msg.outgoing:
                            bot_reply = history_msg
                            break
                    if bot_reply:
                        break

                if bot_reply and (bot_reply.text or bot_reply.caption):
                    reply_text = bot_reply.text or bot_reply.caption
                    parsed = parse_genlink_bot_response(reply_text)
                    if parsed:
                        collected_outputs.append({
                            "msg_id": msg_id,
                            "link": parsed["link"],
                            "quality": parsed["quality"],
                            "episode": parsed["episode"]
                        })
                    else:
                        failed_ids.append(msg_id)
                else:
                    failed_ids.append(msg_id)

            except Exception as msg_err:
                logger.error(f"Error processing message {msg_id}: {msg_err}")
                failed_ids.append(msg_id)

            await asyncio.sleep(1) # polite delay between requests

        try:
            await user_client.stop()
        except Exception:
            pass

        if not collected_outputs:
            return await status_msg.edit_text(
                "❌ **Process Failed:** No links could be generated from the target bot.\n"
                "Please check if the session string and bot username are correct."
            )

        # Organize outputs into groups based on serial numbers provided by admin
        # Serial 1 -> Group 1, Serial 2 -> Group 2 ...
        # If there are outputs for episodes/qualities, group them logically
        # Group format: Serial 1 = group_names[0], Serial 2 = group_names[1], ...
        # Group contents:
        # If outputs have distinct qualities (e.g. 480P, 720P, 1080P), button name = quality.
        # If multiple episodes/qualities, map sequentially or by episode to serial groups.

        anime = await db.get_anime(aid)
        if not anime:
            return await status_msg.edit_text("❌ **Error:** Target anime page no longer exists.")

        # Structure calculated groups
        # Every serial group (1. Group Name) gets its respective outputs
        # Group outputs count / distribution:
        num_groups = len(group_names)

        # If num_groups == 1, all collected outputs belong to Group 1
        # If outputs can be grouped by episode or chunks across serial groups:
        # e.g., Group 1 for Serial 1, Group 2 for Serial 2...
        # Each serial group will contain buttons labeled by video quality ("480P", "720P", "1080P", etc.)

        # Build group_dict: { group_name: { "480P": link, "720P": link, ... } }
        structured_seasons_links = anime.get("seasons_links", {})
        if not isinstance(structured_seasons_links, dict):
            structured_seasons_links = {}

        # Chunk outputs across groups or map sequentially per serial group
        # Each group gets its outputs
        chunk_size = max(1, (len(collected_outputs) + num_groups - 1) // num_groups)

        for g_idx, g_name in enumerate(group_names):
            g_outputs = collected_outputs[g_idx * chunk_size : (g_idx + 1) * chunk_size]
            if not g_outputs and g_idx < len(collected_outputs):
                g_outputs = [collected_outputs[g_idx]]

            if g_name not in structured_seasons_links or not isinstance(structured_seasons_links[g_name], dict):
                structured_seasons_links[g_name] = {}

            for out in g_outputs:
                q_label = out["quality"]
                # Avoid button label collision if multiple same quality in same group
                if q_label in structured_seasons_links[g_name]:
                    dup_count = 2
                    while f"{q_label} ({dup_count})" in structured_seasons_links[g_name]:
                        dup_count += 1
                    q_label = f"{q_label} ({dup_count})"

                structured_seasons_links[g_name][q_label] = out["link"]

        # Save to database
        if db._anime is not None:
            await db._anime.update_one(
                {"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid},
                {
                    "$set": {
                        "seasons_links": structured_seasons_links,
                        "newly_added_groups": group_names
                    },
                    "$currentDate": {"updated_at": True}
                }
            )

        summary = (
            "🎉 **Range Link Processing Completed Successfully!**\n\n"
            f"🎬 **Anime:** `{anime['title']}`\n"
            f"📊 **Total Processed:** `{total_msgs}` messages\n"
            f"✅ **Links Generated:** `{len(collected_outputs)}` link(s)\n"
            f"⚠️ **Failed:** `{len(failed_ids)}`\n"
            f"👥 **Groups Added/Updated:** `{len(group_names)}`\n\n"
            f"🔗 **Web Link:** {Config.BASE_URL}/anime/{anime['slug']}"
        )

        await status_msg.edit_text(summary)

    except Exception as err:
        logger.error(f"Range Link Task Error: {err}\n{traceback.format_exc()}")
        await status_msg.edit_text(f"❌ **Range Link Processing Error:** `{str(err)}`")

def parse_group_names_list(text):
    if not text or not text.strip():
        return None
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    groups = []
    for line in lines:
        match = re.match(r'^\s*(\d+)\s*\.\s*(.*)$', line)
        if match:
            gname = match.group(2).strip()
            if gname:
                groups.append(gname)
            else:
                return None
        else:
            return None
    return groups if groups else None

def parse_advanced_group_message(text):
    """
    Parses a text block into structured custom box groups and buttons.
    Returns:
        tuple: (groups_dict, error_message)
        where groups_dict is { "Group Name": { "Button Label": "Link", ... }, ... }
        or (None, "Error description pointing to the specific group/button")
    """
    if not text:
        return None, "Empty message received."

    lines = text.strip().split("\n")
    groups = {}
    current_group_name = None
    current_buttons = {}
    group_num = 0

    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Check if line starts a new group, e.g. "1. Season 1" or "1."
        match = re.match(r"^\s*(\d+)\s*\.\s*(.*)$", line)
        if match:
            # Save previous group if active
            if current_group_name:
                if not current_buttons:
                    return None, f"Group '{current_group_name}' (Entry #{group_num}) has no buttons defined."
                groups[current_group_name] = current_buttons
                current_buttons = {}

            group_num = int(match.group(1))
            gname_part = match.group(2).strip()

            if gname_part:
                current_group_name = gname_part
            else:
                # Group name must be on next non-empty line
                i += 1
                next_gname = None
                while i < n:
                    next_line = lines[i].strip()
                    if next_line:
                        next_gname = next_line
                        break
                    i += 1
                if not next_gname:
                    return None, f"Group #{group_num} has a missing or empty Group Name."
                current_group_name = next_gname

            current_buttons = {}
            i += 1
            continue

        if not current_group_name:
            return None, f"Found button definition '{line}' before any group was defined (e.g. '1. Group Name')."

        if ":" not in line:
            return None, f"Invalid format in Group '{current_group_name}' (Entry #{group_num}): '{line}'. Missing ':' separator."

        parts = line.split(":", 1)
        btn_name = parts[0].strip()
        btn_link = parts[1].strip()

        if not btn_name:
            return None, f"Invalid button label in Group '{current_group_name}' (Entry #{group_num}): '{line}'."

        if not (btn_link.startswith("http://") or btn_link.startswith("https://")):
            return None, f"Invalid URL in Group '{current_group_name}' (Entry #{group_num}) for button '{btn_name}': '{btn_link}'."

        current_buttons[btn_name] = btn_link
        i += 1

    if current_group_name:
        if not current_buttons:
            return None, f"Group '{current_group_name}' (Entry #{group_num}) has no buttons defined."
        groups[current_group_name] = current_buttons

    if not groups:
        return None, "No valid groups or buttons found. Please follow the required format (e.g. starting with '1. Season 1')."

    return groups, None

def register_handlers(bot: Client):
    logger.info("Initializing Hardened Intelligence Suite Handlers...")

    # --- ADDBOT PLUGIN HANDLER ---
    from bot.plugins.addbot import addbot_command_handler
    bot.add_handler(MessageHandler(addbot_command_handler, filters.command("addbot") & filters.private))

    # --- DEBUG LOGGER (GROUP -3) ---
    @bot.on_message(filters.all, group=-3)
    async def debug_logger(client, message):
        # logger.debug(f"UPDATE: {message.chat.id} -> {message.text or 'MEDIA'}")
        raise ContinuePropagation

    # --- AUTO-LINK HANDLER (GROUP -2) ---
    @bot.on_message(filters.all, group=-2)
    async def auto_file_grouping(client, message):
        if (message.document or message.video) and message.from_user and not message.from_user.is_bot:
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
                "Welcome to the premier Anime Management Suite. Experience seamless automation and high-speed metadata intelligence.\n\n"
                "⚡ **Quick Start:**\n"
                "• `/search <name>` — Automated series setup\n"
                "• `/add_post <name>` — Rapid one-shot publication\n"
                "• `/add_page` — Manual content creation\n"
                "• `/edit <url>` — Manage content groups\n"
                "• `/help` — View full documentation"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Access Portal", url=Config.BASE_URL)],
                [InlineKeyboardButton("📚 Admin Guide", callback_data="help_guide")]
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
            "• `/songs`: Manage Background Songs.\n"
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
            aid = str(anime["_id"])

            if message.command[0] == "edit_m":
                buttons = [
                    [InlineKeyboardButton("📦 Add Custom Group", callback_data=f"add_cgrp_start_{aid}")],
                    [InlineKeyboardButton("➕ Add Custom Button", callback_data=f"add_btn_start_{aid}")],
                    [InlineKeyboardButton("🗃 Add Custom Box", callback_data=f"add_box_start_{aid}")],
                    [InlineKeyboardButton("🚀 Advanced Group", callback_data=f"adv_grp_start_{aid}")],
                    [InlineKeyboardButton("🔥 Ultra Advanced Group", callback_data=f"ultra_adv_grp_start_{aid}")],
                    [InlineKeyboardButton("📋 Manage Boxes", callback_data=f"manage_boxes_{aid}")],
                    [InlineKeyboardButton("📝 Manage Buttons", callback_data=f"manage_btns_{aid}")],
                    [InlineKeyboardButton("🔄 Refresh", callback_data=f"edit_m_back_{aid}")],
                    [InlineKeyboardButton("🛡 Back to Archive", callback_data=f"back_to_edit_{aid}"), InlineKeyboardButton("❌ Abort", callback_data="cancel_op")]
                ]
                await message.reply(
                    f"🖇 **Custom Management: {anime['title']}**\n\nSelect a sector to manage:",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            else:
                buttons = [
                    [InlineKeyboardButton("👑 Admin Choice (Manage Content Groups)", callback_data=f"manage_groups_{aid}")],
                    [InlineKeyboardButton("📦 Content Groups (Seasons)", callback_data=f"manage_groups_{aid}")],
                    [InlineKeyboardButton("🗃 Custom Boxes", callback_data=f"manage_boxes_{aid}")],
                    [InlineKeyboardButton("🔗 External Redirects (Buttons)", callback_data=f"manage_btns_{aid}")],
                    [InlineKeyboardButton("🚀 Advanced Group", callback_data=f"adv_grp_start_{aid}")],
                    [InlineKeyboardButton("🔥 Ultra Advanced Group", callback_data=f"ultra_adv_grp_start_{aid}")],
                    [InlineKeyboardButton("📂 Change Category", callback_data=f"manage_category_{aid}")],
                    [InlineKeyboardButton("🏷 Change Title", callback_data=f"edit_title_{aid}")],
                    [InlineKeyboardButton("🖼 Change Poster", callback_data=f"trigger_poster_{aid}")],
                    [InlineKeyboardButton("🗑 Purge Archive", callback_data=f"confirm_purge_{aid}")],
                    [InlineKeyboardButton("🔄 Refresh", callback_data=f"back_to_edit_{aid}"), InlineKeyboardButton("❌ Abort", callback_data="cancel_op")]
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
            buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="categories_refresh")])
            await message.reply("📂 **Category Management**", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            logger.error(f"Categories Error: {e}")
            await message.reply("❌ **Database Failure.**")

    @bot.on_message(filters.command("schedule"))
    async def schedule_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.**")

        args = message.text.split(None, 2)
        if len(args) > 1:
            time = args[1]
            image = None
            remaining = args[2] if len(args) > 2 else ""

            # Split remaining into name and potential image URL
            parts = remaining.rsplit(None, 1)
            if len(parts) > 1 and parts[1].startswith("http"):
                name = parts[0]
                image = parts[1]
            else:
                name = remaining

            if not name:
                return await message.reply("💡 **Usage:** `/schedule {TIME} {NAME} {OPTIONAL_IMAGE_URL}`")

            user_state[message.from_user.id] = {
                "action": "add_sched_entry",
                "entry": {"time": time, "name": name, "image": image}
            }

            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            buttons = [[InlineKeyboardButton(days[i], callback_data=f"addsched_{days[i]}"), InlineKeyboardButton(days[i+1], callback_data=f"addsched_{days[i+1]}")] for i in range(0, 6, 2)]
            buttons.append([InlineKeyboardButton("Sunday", callback_data="addsched_Sunday")])
            buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_op")])

            return await message.reply(
                f"📅 **Adding Entry:**\n\n"
                f"🕒 **Time:** `{time}`\n"
                f"🎬 **Name:** `{name}`\n"
                f"🖼 **Image:** `{'Yes' if image else 'No'}`\n\n"
                "Select the day to add this entry:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        buttons = [[InlineKeyboardButton(days[i], callback_data=f"edit_sched_{days[i]}"), InlineKeyboardButton(days[i+1], callback_data=f"edit_sched_{days[i+1]}")] for i in range(0, 6, 2)]
        buttons.append([InlineKeyboardButton("Sunday", callback_data="edit_sched_Sunday")])
        buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="schedule_refresh")])
        await message.reply("📅 **Airing Schedule Management**\nSelect a day to manually update (overwrites with text):", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_callback_query(filters.regex("^schedule_refresh$"))
    async def schedule_refresh_cb(client, callback_query):
        try:
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            buttons = [[InlineKeyboardButton(days[i], callback_data=f"edit_sched_{days[i]}"), InlineKeyboardButton(days[i+1], callback_data=f"edit_sched_{days[i+1]}")] for i in range(0, 6, 2)]
            buttons.append([InlineKeyboardButton("Sunday", callback_data="edit_sched_Sunday")])
            buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="schedule_refresh")])
            await callback_query.message.edit_text("📅 **Airing Schedule**", reply_markup=InlineKeyboardMarkup(buttons))
            await callback_query.answer("Schedule Synchronized")
        except MessageNotModified:
            await callback_query.answer("Already Synchronized")
        except Exception as e:
            logger.error(f"Schedule Refresh Error: {e}")
            await callback_query.answer("Sync Failed", show_alert=True)

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

    @bot.on_message(filters.command(["uptime", "UPTIME"]))
    async def uptime_command_handler(client, message):
        if not message.from_user or not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.** Unauthorized user.")

        await send_uptime_menu(client, message)

    async def send_uptime_menu(client, message_or_cb):
        bots = await db.get_all_monitored_bots()

        text = "⚡ **24/7 Bot Uptime Monitoring Suite**\n\n"
        text += f"📊 **Monitored Bots:** `{len(bots)}` (Continuous 1s check)\n\n"

        if bots:
            text += "**Live Monitor Feed:**\n"
            for idx, b in enumerate(bots, 1):
                status = b.get("status", "pending")
                icon = "🟢" if status == "online" else ("🔴" if status == "offline" else "🟡")
                code_str = f" [HTTP {b.get('status_code')}]" if b.get('status_code') else ""
                ms_str = f" ({b.get('response_time_ms')}ms)" if b.get('response_time_ms') is not None else ""
                url_str = b.get("url", "")
                text += f"**{idx}.** {icon} **{b.get('name', 'Bot')}**{code_str}{ms_str}\n🔗 `{url_str}`\n\n"
        else:
            text += "ℹ️ *No bots currently monitored. Click 'Add Bot' below to register a bot URL for continuous 24/7 uptime monitoring.*"

        buttons = [
            [InlineKeyboardButton("➕ Add Bot", callback_data="add_uptime_bot_prompt")]
        ]

        if bots:
            for idx, b in enumerate(bots, 1):
                bid = b.get("bot_id") or str(b.get("_id"))
                bname = (b.get("name", f"Bot {idx}")[:14] + "..") if len(b.get("name", "")) > 16 else b.get("name", f"Bot {idx}")
                buttons.append([
                    InlineKeyboardButton(f"🔄 Replace {bname}", callback_data=f"replace_uptime_{bid}"),
                    InlineKeyboardButton(f"🗑", callback_data=f"del_uptime_{bid}")
                ])

        buttons.append([InlineKeyboardButton("🔄 Refresh Status", callback_data="uptime_refresh"), InlineKeyboardButton("❌ Close", callback_data="cancel_op")])

        if isinstance(message_or_cb, CallbackQuery):
            try:
                await message_or_cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
                await message_or_cb.answer()
            except MessageNotModified:
                await message_or_cb.answer("Already Up-to-date")
        else:
            await message_or_cb.reply(text, reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_callback_query(filters.regex("^uptime_refresh$"))
    async def uptime_refresh_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)
        await send_uptime_menu(client, callback_query)

    @bot.on_callback_query(filters.regex("^add_uptime_bot_prompt$"))
    async def add_uptime_bot_prompt_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        user_state[callback_query.from_user.id] = {"action": "ask_uptime_bot_url"}
        await callback_query.message.edit_text(
            "➕ **Add Bot for Uptime Monitoring**\n\n"
            "Please send the **HTTP / HTTPS URL** of the bot/service to monitor 24/7:\n\n"
            "Example: `https://my-telegram-bot.onrender.com`\n\n"
            "Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_op")]])
        )
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^replace_uptime_"))
    async def replace_uptime_bot_prompt_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        bot_id = callback_query.data.split("replace_uptime_")[-1]
        b = await db.get_monitored_bot(bot_id)
        if not b:
            return await callback_query.answer("❌ Monitored bot not found", show_alert=True)

        user_state[callback_query.from_user.id] = {"action": "ask_replace_uptime_url", "bot_id": bot_id}
        await callback_query.message.edit_text(
            f"🔄 **Replace Monitored Bot: {b.get('name', 'Bot')}**\n\n"
            f"Current URL: `{b.get('url')}`\n\n"
            "Please send the new **HTTP / HTTPS URL**:\n\n"
            "Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_op")]])
        )
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^del_uptime_"))
    async def del_uptime_bot_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        bot_id = callback_query.data.split("del_uptime_")[-1]
        b = await db.get_monitored_bot(bot_id)
        if b:
            await db.delete_monitored_bot(bot_id)
            await callback_query.answer(f"🗑 Stopped monitoring '{b.get('name', 'Bot')}'", show_alert=True)
        else:
            await callback_query.answer("❌ Bot record already deleted", show_alert=True)

        await send_uptime_menu(client, callback_query)

    @bot.on_message(filters.command("setbot"))
    async def setbot_command_handler(client, message):
        if not message.from_user or not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.** Unauthorized user.")

        args = message.text.split(None, 1)
        if len(args) > 1:
            bot_username = args[1].strip().lstrip("@")
            await db.set_configured_bot(bot_username)
            return await message.reply(f"✅ **Configured Bot Username Saved:** `@{bot_username}`")

        user_state[message.from_user.id] = {"action": "ask_setbot_username"}
        await message.reply("🤖 **Configure Genlink Bot**\n\nPlease send the **Bot Username** (e.g., `@AniZoneFlix_bot`):")

    @bot.on_message(filters.command("ss"))
    async def ss_command_handler(client, message):
        if not message.from_user or not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.** Unauthorized user.")

        args = message.text.split(None, 1)
        if len(args) > 1:
            session_str = args[1].strip()
            await db.set_configured_session(session_str)
            return await message.reply("✅ **Pyrogram Session String Saved Successfully!**")

        user_state[message.from_user.id] = {"action": "ask_ss_string"}
        await message.reply("🔑 **Configure Pyrogram Session String**\n\nPlease send the **Session String**:")

    @bot.on_message(filters.command(["songs", "SONGS"]))
    async def songs_command_handler(client, message):
        if not message.from_user or not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.** Unauthorized user.")

        await send_songs_menu(client, message)

    async def send_songs_menu(client, message_or_cb):
        songs = await db.get_all_songs()
        channel_id = await db.get_song_channel()

        text = "🎵 **Background Songs Management**\n\n"
        text += f"📢 **Dedicated Song Channel:** `{channel_id or 'Not Configured'}`\n"
        text += f"🎼 **Total Songs:** `{len(songs)}`\n\n"

        if songs:
            text += "**Current Playlist:**\n"
            for idx, song in enumerate(songs, 1):
                text += f"**{idx}.** {song.get('title', 'Untitled Song')}\n"
        else:
            text += "ℹ️ *No background songs found. Upload a song to enable web audio playback.*"

        buttons = [
            [InlineKeyboardButton("➕ Add New Song", callback_data="add_song_prompt")],
            [InlineKeyboardButton("📢 Set Song Channel", callback_data="set_song_channel_prompt")]
        ]

        if songs:
            for idx, song in enumerate(songs, 1):
                sid = song.get("song_id") or str(song.get("_id"))
                stitle = (song.get("title", f"Song {idx}")[:15] + "..") if len(song.get("title", "")) > 18 else song.get("title", f"Song {idx}")
                buttons.append([
                    InlineKeyboardButton(f"🔄 Replace {stitle}", callback_data=f"replace_song_{sid}"),
                    InlineKeyboardButton(f"🗑", callback_data=f"del_song_{sid}")
                ])

        buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="songs_refresh"), InlineKeyboardButton("❌ Close", callback_data="cancel_op")])

        if isinstance(message_or_cb, CallbackQuery):
            try:
                await message_or_cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
                await message_or_cb.answer()
            except MessageNotModified:
                await message_or_cb.answer("Already Up-to-date")
        else:
            await message_or_cb.reply(text, reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_callback_query(filters.regex("^songs_refresh$"))
    async def songs_refresh_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)
        await send_songs_menu(client, callback_query)

    @bot.on_callback_query(filters.regex("^add_song_prompt$"))
    async def add_song_prompt_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        user_state[callback_query.from_user.id] = {"action": "ask_song_file"}
        await callback_query.message.edit_text(
            "🎵 **Add Background Song**\n\n"
            "Please send or upload the **Audio** or **Video** document (MP3, M4A, WAV, MP4, etc.) for the background music:\n\n"
            "Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_op")]])
        )
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^replace_song_"))
    async def replace_song_prompt_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        song_id = callback_query.data.split("replace_song_")[-1]
        song = await db.get_song(song_id)
        if not song:
            return await callback_query.answer("❌ Song not found", show_alert=True)

        user_state[callback_query.from_user.id] = {"action": "ask_replace_song_file", "song_id": song_id}
        await callback_query.message.edit_text(
            f"🔄 **Replace Song: {song.get('title', 'Untitled')}**\n\n"
            "Please send or upload the new **Audio** or **Video** document (MP3, M4A, WAV, MP4, etc.) to replace this song:\n\n"
            "Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_op")]])
        )
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^del_song_"))
    async def del_song_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        song_id = callback_query.data.split("del_song_")[-1]
        song = await db.get_song(song_id)
        if song:
            file_path = song.get("file_path", "")
            if file_path and file_path.startswith("/static/"):
                full_path = os.path.join(".", file_path.lstrip("/"))
                if os.path.exists(full_path):
                    try: os.remove(full_path)
                    except: pass
            await db.delete_song(song_id)
            await callback_query.answer(f"🗑 Deleted '{song.get('title', 'Song')}'", show_alert=True)
        else:
            await callback_query.answer("❌ Song already deleted", show_alert=True)

        await send_songs_menu(client, callback_query)

    @bot.on_callback_query(filters.regex("^set_song_channel_prompt$"))
    async def set_song_channel_prompt_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        user_state[callback_query.from_user.id] = {"action": "ask_song_channel"}
        await callback_query.message.edit_text(
            "📢 **Configure Dedicated Song Channel**\n\n"
            "Please send the **Channel Username** or **Numeric Channel ID** (e.g., `@anizone_songs` or `-1001234567890`):\n\n"
            "Make sure the bot is an admin in the song channel!\n"
            "Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_op")]])
        )
        await callback_query.answer()

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

    @bot.on_message(filters.command("category_page"))
    async def category_page_handler(client, message):
        if not message.from_user: return
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 **Access Denied.** This zone is for authorized administrators only.")

        query = " ".join(message.command[1:]).strip()
        if not query and message.reply_to_message:
            query = (message.reply_to_message.text or message.reply_to_message.caption or "").strip()

        slug = extract_slug(query)
        if not slug:
            return await message.reply("💡 **Usage:** `/category_page <url>` (or reply to a link)")

        try:
            anime = await db.get_anime(slug)
            if not anime:
                results = await db.search_anime_db(query)
                if results: anime = results[0]

            if not anime: return await message.reply(f"❌ **Not Found:** `{slug}`")
            aid = str(anime["_id"])
            current_cat = anime.get("category", "N/A")

            cats = await db.get_all_categories()
            buttons = []
            for c in cats:
                name = c['name']
                label = f"✅ {name}" if name == current_cat else name
                buttons.append([InlineKeyboardButton(label, callback_data=f"move_cat_{aid}:::{name}")])

            buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_op")])
            await message.reply(
                f"📂 **Move Category: {anime['title']}**\n\n"
                f"Current Category: `{current_cat}`\n\n"
                "Select the destination category to move this page:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception as e:
            logger.error(f"Category Page Cmd Error: {e}")
            await message.reply("❌ **Intelligence Feed Offline.**")

    @bot.on_message(filters.command("cancel"))
    async def cancel_handler(client, message):
        if message.from_user:
            user_state.pop(message.from_user.id, None)
        await message.reply("✨ **Action Cancelled.** standby.")

    # --- CALLBACK HANDLERS ---

    @bot.on_callback_query(filters.regex("^move_cat_"))
    async def move_cat_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        data = callback_query.data.split("move_cat_")[-1]
        aid, new_cat = data.split(":::")

        try:
            if await db.ping():
                anime = await db.get_anime(aid)
                if not anime: return await callback_query.answer("❌ Not Found", show_alert=True)
                res = await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"category": new_cat}, "$currentDate": {"updated_at": True}})
                if res.modified_count:
                    await callback_query.answer(f"🚀 Moved to {new_cat}", show_alert=True)
                    await callback_query.message.edit_text(
                        f"✅ **Category Updated Successfully!**\n\n"
                        f"🎬 **Anime:** `{anime['title']}`\n"
                        f"📂 **Moved To:** `{new_cat}`",
                        reply_markup=None
                    )
                else:
                    await callback_query.answer("⚠️ Category remains unchanged.", show_alert=True)
                    await callback_query.message.edit_text(
                        f"⚠️ **Category Unchanged**\n\n"
                        f"🎬 **Anime:** `{anime['title']}`\n"
                        f"📂 **Category:** `{new_cat}`",
                        reply_markup=None
                    )
            else:
                await callback_query.answer("❌ Database Offline", show_alert=True)
        except Exception as e:
            logger.error(f"Move Cat Callback Error: {e}")
            await callback_query.answer(f"❌ Error: {e}", show_alert=True)

    @bot.on_callback_query(filters.regex("^backup_data$"))
    async def backup_data_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        await callback_query.message.edit_text("⏳ **Generating system backup...**")
        await callback_query.answer()
        try:
            data = await db.export_data()
            if data is None:
                return await callback_query.message.edit_text("❌ **Export Failed:** Database connection offline.")

            if not data or not any(data.values()):
                return await callback_query.message.edit_text("❌ **Export Failed:** No records found in the database.")

            # Create a ZIP in memory
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for coll_name, docs in data.items():
                    if docs:
                        json_data = json.dumps(docs, indent=4, default=str)
                        zf.writestr(f"{coll_name}.json", json_data)

            zip_buffer.seek(0)

            # Using a temporary file to ensure Pyrogram handles it correctly
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(zip_buffer.getvalue())
                tmp_path = tmp.name

            try:
                await callback_query.message.delete()
                await client.send_document(
                    chat_id=callback_query.message.chat.id,
                    document=tmp_path,
                    file_name=f"backup_{Config.DB_NAME}.zip",
                    caption=(
                        f"✅ **Backup Generated Successfully**\n\n"
                        f"🌐 **Website:** {Config.BASE_URL}\n"
                        f"📦 **Collections:** {', '.join(data.keys())}\n\n"
                        f"Keep this file secure. You can restore this data anytime using the /save command."
                    )
                )
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

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

    @bot.on_callback_query(filters.regex("^categories_refresh$"))
    async def categories_refresh_cb(client, callback_query):
        try:
            cats = await db.get_all_categories()
            buttons = [[InlineKeyboardButton(f"🏷 {c['name']}", callback_data=f"vcat_{c['name']}"), InlineKeyboardButton("🗑", callback_data=f"del_cat_{c['name']}")] for c in cats]
            buttons.append([InlineKeyboardButton("➕ Add Category", callback_data="add_cat_prompt")])
            buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="categories_refresh")])
            await callback_query.message.edit_text("📂 **Category Management**", reply_markup=InlineKeyboardMarkup(buttons))
            await callback_query.answer("Categories Synchronized")
        except MessageNotModified:
            await callback_query.answer("Already Up-to-date")
        except Exception as e:
            logger.error(f"Categories Refresh Error: {e}")
            await callback_query.answer("Sync Failed")

    @bot.on_callback_query(filters.regex("^add_cat_prompt$"))
    async def add_cat_prompt_cb(client, callback_query):
        user_state[callback_query.from_user.id] = {"action": "ask_cat_name"}
        await callback_query.message.edit_text("🏷 **Enter Category Name:**", reply_markup=None)
        await callback_query.answer()

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
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^trigger_poster_"))
    async def trigger_poster_cb(client, callback_query):
        aid = callback_query.data.split("trigger_poster_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_new_poster", "slug": aid}
        await callback_query.message.edit_text("🖼 **New Asset URL:**", reply_markup=None)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^confirm_purge_"))
    async def confirm_purge_cb(client, callback_query):
        aid = callback_query.data.split("confirm_purge_")[-1]
        buttons = [[InlineKeyboardButton("🧨 PURGE EVERYTHING", callback_data=f"execute_purge_{aid}")],[InlineKeyboardButton("🛡 Abort", callback_data="cancel_op")]]
        await callback_query.message.edit_text(f"⚠️ **CRITICAL:** Purge `{aid}`?", reply_markup=InlineKeyboardMarkup(buttons))
        await callback_query.answer()

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

    @bot.on_callback_query(filters.regex("^addsched_"))
    async def addsched_cb(client, callback_query):
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state or state.get("action") != "add_sched_entry":
            return await callback_query.answer("❌ Session Expired", show_alert=True)

        day = callback_query.data.split("addsched_")[-1]
        entry = state["entry"]

        try:
            current = await db.get_schedule(day)
            if not isinstance(current, list):
                current = []

            current.append(entry)
            await db.update_schedule(day, current)

            await callback_query.message.edit_text(
                f"✅ **Entry Added to {day}!**\n\n"
                f"🕒 {entry['time']} - {entry['name']}"
            )
            del user_state[uid]
        except Exception as e:
            logger.error(f"Add Sched CB Error: {e}")
            await callback_query.answer("Failed to update schedule.")

    @bot.on_callback_query(filters.regex("^edit_sched_"))
    async def edit_sched_cb(client, callback_query):
        day = callback_query.data.split("edit_sched_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_sched_content", "day": day}
        current = await db.get_schedule(day)

        display_text = ""
        if isinstance(current, list):
            for item in current:
                display_text += f"• {item.get('name')} ({item.get('time')})\n"
        else:
            display_text = str(current)

        await callback_query.message.edit_text(
            f"📅 **Manual Override: {day}**\n\n"
            f"Current:\n`{display_text or 'Empty'}`\n\n"
            "⚠️ **Note:** Sending text here will convert the schedule to a simple list and remove images.\n"
            "Send NEW schedule text or `/skip` to cancel.",
            reply_markup=None
        )
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^manage_groups_"))
    async def manage_groups_cb(client, callback_query):
        try:
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

            buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"manage_groups_{aid}")])
            buttons.append([InlineKeyboardButton("🛡 Back", callback_data=f"back_to_edit_{aid}")])
            await callback_query.message.edit_text(f"📝 **Groups: {anime['title']}**\nSelect a group to manage buttons or reorder:", reply_markup=InlineKeyboardMarkup(buttons))
            await callback_query.answer()
        except MessageNotModified:
            await callback_query.answer("Refresh Complete")
        except Exception as e:
            logger.error(f"Manage Groups Error: {e}")
            await callback_query.answer("Sync Error")

    @bot.on_callback_query(filters.regex("^selgidx_|^select_group_refresh_"))
    async def select_group_cb(client, callback_query):
        try:
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

            buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"select_group_refresh_{idx}")])
            buttons.append([InlineKeyboardButton("🛡 Back", callback_data=f"manage_groups_{aid}")])
            await callback_query.message.edit_text(f"📦 **Group: {gname}**\nManage internal buttons:", reply_markup=InlineKeyboardMarkup(buttons))
            await callback_query.answer()
        except MessageNotModified:
            await callback_query.answer("Refresh Complete")
        except Exception as e:
            logger.error(f"Select Group Error: {e}")
            await callback_query.answer("Sync Error")

    @bot.on_callback_query(filters.regex("^manage_btns_"))
    async def manage_btns_cb(client, callback_query):
        try:
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

            buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"manage_btns_{aid}")])
            buttons.append([InlineKeyboardButton("🛡 Back", callback_data=f"back_to_edit_{aid}")])
            await callback_query.message.edit_text(f"🖇 **External Redirects: {anime['title']}**\nManage top-level buttons:", reply_markup=InlineKeyboardMarkup(buttons))
            await callback_query.answer()
        except MessageNotModified:
            await callback_query.answer("Refresh Complete")
        except Exception as e:
            logger.error(f"Manage Btns Error: {e}")
            await callback_query.answer("Sync Error")

    @bot.on_callback_query(filters.regex("^edit_m_back_"))
    async def edit_m_back_cb(client, callback_query):
        try:
            aid = callback_query.data.split("edit_m_back_")[-1]
            anime = await db.get_anime(aid)
            if not anime: return await callback_query.answer("❌ Not Found")

            buttons = [
                [InlineKeyboardButton("📦 Add Custom Group", callback_data=f"add_cgrp_start_{aid}")],
                [InlineKeyboardButton("➕ Add Custom Button", callback_data=f"add_btn_start_{aid}")],
                [InlineKeyboardButton("🗃 Add Custom Box", callback_data=f"add_box_start_{aid}")],
                [InlineKeyboardButton("🚀 Advanced Group", callback_data=f"adv_grp_start_{aid}")],
                [InlineKeyboardButton("🔥 Ultra Advanced Group", callback_data=f"ultra_adv_grp_start_{aid}")],
                [InlineKeyboardButton("📋 Manage Boxes", callback_data=f"manage_boxes_{aid}")],
                [InlineKeyboardButton("📝 Manage Buttons", callback_data=f"manage_btns_{aid}")],
                [InlineKeyboardButton("🔄 Refresh", callback_data=f"edit_m_back_{aid}")],
                [InlineKeyboardButton("🛡 Back to Archive", callback_data=f"back_to_edit_{aid}"), InlineKeyboardButton("❌ Abort", callback_data="cancel_op")]
            ]
            await callback_query.message.edit_text(f"🖇 **Custom Management: {anime['title']}**", reply_markup=InlineKeyboardMarkup(buttons))
            await callback_query.answer()
        except MessageNotModified:
            await callback_query.answer("Refresh Complete")
        except Exception as e:
            logger.error(f"Edit M Back Error: {e}")
            await callback_query.answer("Sync Error")

    @bot.on_callback_query(filters.regex("^add_cgrp_start_"))
    async def add_cgrp_start_cb(client, callback_query):
        aid = callback_query.data.split("add_cgrp_start_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_cgrp_btn_count", "slug": aid}
        await callback_query.message.edit_text("How many buttons do you want to add?", reply_markup=None)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^add_box_start_"))
    async def add_box_start_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        aid = callback_query.data.split("add_box_start_")[-1]

        # Detect origin (edit_m vs edit)
        origin = "edit"
        curr_text = callback_query.message.text or ""
        if "Custom Management" in curr_text:
            origin = "edit_m"

        user_state[callback_query.from_user.id] = {
            "action": "ask_box_name",
            "slug": aid,
            "origin": origin
        }

        cancel_callback = f"cancel_bulkbox_{origin}:::{aid}"

        instruction_text = (
            "🗃 **Bulk Box Creation**\n\n"
            "You can add multiple boxes at once!\n"
            "Please send your box names in the following format:\n\n"
            "1. Naruto\n"
            "2. One Piece\n"
            "3. Bleach\n"
            "4. Jujutsu Kaisen\n"
            "5. Demon Slayer\n\n"
            "Send your list of box names now or click Cancel to abort:"
        )

        await callback_query.message.edit_text(
            instruction_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data=cancel_callback)
            ]])
        )
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^cancel_bulkbox_(edit|edit_m):::"))
    async def cancel_bulkbox_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        data = callback_query.data.split("cancel_bulkbox_")[-1]
        origin, aid = data.split(":::", 1)

        uid = callback_query.from_user.id
        user_state.pop(uid, None)

        await callback_query.answer("Operation Cancelled")

        if origin == "edit_m":
            callback_query.data = f"edit_m_back_{aid}"
            return await edit_m_back_cb(client, callback_query)
        else:
            callback_query.data = f"back_to_edit_{aid}"
            return await back_to_edit_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^ultra_adv_grp_start_"))
    async def ultra_adv_grp_start_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        try:
            aid = callback_query.data.split("ultra_adv_grp_start_")[-1]
            anime = await db.get_anime(aid)
            if not anime: return await callback_query.answer("❌ Anime Not Found", show_alert=True)

            uid = callback_query.from_user.id

            # Record the origin callback (whether it came from edit or edit_m)
            # We can detect this based on the current message text/caption or state.
            # Usually `/edit_m` has "Custom Management" in its title, and `/edit` has "Executive Suite" or similar.
            origin = "edit"
            curr_text = callback_query.message.text or ""
            if "Custom Management" in curr_text:
                origin = "edit_m"

            user_state[uid] = {
                "action": "ask_ultra_adv_grp_message",
                "slug": aid,
                "origin": origin
            }

            cancel_callback = f"cancel_uag_{origin}:::{aid}"

            instruction_text = (
                f"🔥 **Ultra Advanced Group: {anime['title']}**\n\n"
                "Please send the custom box groups and buttons in this format:\n\n"
                "`I. BOX NAME: Naruto` (Roman-numbered existing box)\n\n"
                "`1. Quality` (Serial number + Group Name)\n"
                "`480P : https://example.com/480` (Button Name : Link)\n"
                "`720P : https://example.com/720`\n\n"
                "`2. Languages`\n"
                "`Telugu : https://example.com/telugu`\n\n"
                "`II. BOX NAME: One Piece`\n\n"
                "`1. Quality`\n"
                "`480P : https://example.com/480`\n\n"
                "⚠️ **Rules & Guidelines:**\n"
                "• **Ultra Advanced Group must NEVER create a new box.** It only updates existing boxes.\n"
                "• Any boxes not found in this series will be marked as failed/not found, but other valid boxes will continue processing.\n"
                "• All groups and buttons will be appended to the existing box without overwriting other unrelated groups.\n"
                "• The parser splits only on the **first colon (:)** for button links to avoid corrupting URLs containing colons.\n\n"
                "Send your formatted input now or click Cancel to abort:"
            )

            await callback_query.message.edit_text(
                instruction_text,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Cancel", callback_data=cancel_callback)
                ]])
            )
            await callback_query.answer()
        except Exception as e:
            logger.error(f"Ultra Advanced Group Start Error: {e}")
            await callback_query.answer("Error initiating Ultra Advanced Group flow", show_alert=True)

    @bot.on_callback_query(filters.regex("^cancel_uag_(edit|edit_m):::"))
    async def cancel_uag_cb(client, callback_query):
        if not await is_authorized(callback_query.from_user.id):
            return await callback_query.answer("🚫 Unauthorized", show_alert=True)

        data = callback_query.data.split("cancel_uag_")[-1]
        origin, aid = data.split(":::", 1)

        uid = callback_query.from_user.id
        user_state.pop(uid, None)

        await callback_query.answer("Operation Cancelled")

        if origin == "edit_m":
            # Simulate back to edit_m callback
            callback_query.data = f"edit_m_back_{aid}"
            return await edit_m_back_cb(client, callback_query)
        else:
            # Simulate back to edit callback
            callback_query.data = f"back_to_edit_{aid}"
            return await back_to_edit_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^adv_grp_start_"))
    async def adv_grp_start_cb(client, callback_query):
        try:
            aid = callback_query.data.split("adv_grp_start_")[-1]
            anime = await db.get_anime(aid)
            if not anime: return await callback_query.answer("❌ Anime Not Found", show_alert=True)

            boxes = anime.get("custom_boxes", [])
            if not boxes:
                buttons = [
                    [InlineKeyboardButton("🗃 Create Custom Box", callback_data=f"add_box_start_{aid}")],
                    [InlineKeyboardButton("🛡 Back", callback_data=f"back_to_edit_{aid}")]
                ]
                await callback_query.message.edit_text(
                    "⚠️ **No Custom Boxes Found!**\n\n"
                    "You need to create at least one Custom Box on this page before using the Advanced Group feature.",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                return await callback_query.answer()

            buttons = []
            for idx, box in enumerate(boxes):
                buttons.append([InlineKeyboardButton(f"🗃 {box['name']}", callback_data=f"adv_box_sel_{idx}_{aid}")])

            buttons.append([InlineKeyboardButton("🛡 Back", callback_data=f"back_to_edit_{aid}")])

            await callback_query.message.edit_text(
                f"🚀 **Advanced Group: {anime['title']}**\n\n"
                "Select the target Custom Box to add groups and buttons into:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            await callback_query.answer()
        except Exception as e:
            logger.error(f"Advanced Group Start Error: {e}")
            await callback_query.answer("Error initiating Advanced Group flow", show_alert=True)

    @bot.on_callback_query(filters.regex("^adv_box_sel_"))
    async def adv_box_sel_cb(client, callback_query):
        try:
            parts = callback_query.data.split("_")
            b_idx = int(parts[3])
            aid = parts[4]

            anime = await db.get_anime(aid)
            if not anime: return await callback_query.answer("❌ Anime Not Found", show_alert=True)

            boxes = anime.get("custom_boxes", [])
            if b_idx >= len(boxes): return await callback_query.answer("❌ Box Not Found", show_alert=True)
            box_name = boxes[b_idx]["name"]

            uid = callback_query.from_user.id
            user_state[uid] = {
                "action": "ask_adv_grp_message",
                "slug": aid,
                "box_idx": b_idx
            }

            instruction_text = (
                f"🚀 **Advanced Group setup for: {anime['title']}**\n"
                f"Target Box: **{box_name}**\n\n"
                "Please send one or more groups in a single message following this format exactly:\n\n"
                "`1. Season 1` (A number, a dot, space, followed by the Group Name)\n\n"
                "`Button Name : Link` (Any number of buttons, one per line)\n"
                "`Button Name : Link`\n\n"
                "Example:\n"
                "```\n"
                "1. Season 1\n\n"
                "480P : https://example.com/480p\n"
                "720P : https://example.com/720p\n"
                "1080P : https://example.com/1080p\n\n"
                "2. Season 2\n\n"
                "480P : https://example.com/480p\n"
                "720P : https://example.com/720p\n"
                "1080P : https://example.com/1080p\n"
                "```\n\n"
                "⚠️ **Formatting Rules:**\n"
                "• Each numbered entry represents a new Group.\n"
                "• The first line after the number is the Group Name.\n"
                "• Every following line must use the format: `Button Name : Link`\n"
                "• Ignore empty lines automatically.\n"
                "• All buttons and URLs will be verified before saving.\n\n"
                "Send your message now or send /cancel to abort:"
            )

            await callback_query.message.edit_text(instruction_text, reply_markup=None)
            await callback_query.answer()
        except Exception as e:
            logger.error(f"Advanced Box Select Error: {e}")
            await callback_query.answer("Error setting up Advanced Box target", show_alert=True)

    @bot.on_callback_query(filters.regex("^manage_boxes_"))
    async def manage_boxes_cb(client, callback_query):
        try:
            aid = callback_query.data.split("manage_boxes_")[-1]
            if not aid or aid.startswith("remboxidx_") or aid.startswith("mvupbox_") or aid.startswith("mvdnbox_"):
                # If called internally after an action, retrieve from state
                state = user_state.get(callback_query.from_user.id)
                if state: aid = state["slug"]
                else: return await callback_query.answer("❌ Session Expired")

            anime = await db.get_anime(aid)
            if not anime: return await callback_query.answer("❌ Not Found", show_alert=True)

            boxes = anime.get("custom_boxes", [])
            user_state[callback_query.from_user.id] = {"slug": aid, "boxes": boxes}

            buttons = [[InlineKeyboardButton("➕ Add New Box", callback_data=f"add_box_start_{aid}")]]
            for idx, box in enumerate(boxes):
                display_name = (box['name'][:12] + '..') if len(box['name']) > 14 else box['name']
                row = [
                    InlineKeyboardButton(f"⚙️ {display_name}", callback_data=f"selboxidx_{idx}"),
                    InlineKeyboardButton(f"🗑", callback_data=f"remboxidx_{idx}")
                ]
                if idx > 0: row.append(InlineKeyboardButton("⬆️", callback_data=f"mvupbox_{idx}"))
                if idx < len(boxes) - 1: row.append(InlineKeyboardButton("⬇️", callback_data=f"mvdnbox_{idx}"))
                buttons.append(row)

            buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"manage_boxes_{aid}")])
            buttons.append([InlineKeyboardButton("🛡 Back", callback_data=f"edit_m_back_{aid}")])
            await callback_query.message.edit_text(f"📋 **Custom Boxes: {anime['title']}**", reply_markup=InlineKeyboardMarkup(buttons))
            await callback_query.answer()
        except MessageNotModified:
            await callback_query.answer("Refresh Complete")
        except Exception as e:
            logger.error(f"Manage Boxes Error: {e}")
            await callback_query.answer("Sync Error")

    @bot.on_callback_query(filters.regex("^selboxidx_|^select_box_refresh_"))
    async def select_box_cb(client, callback_query):
        try:
            data = callback_query.data.split("_")
            if len(data) > 1:
                idx = int(data[-1])
            else:
                # Fallback if called internally
                state = user_state.get(callback_query.from_user.id)
                if state and "box_idx" in state: idx = state["box_idx"]
                else: return await callback_query.answer("❌ Error")

            state = user_state.get(callback_query.from_user.id)
            if not state: return await callback_query.answer("❌ Session Expired")

            box = state["boxes"][idx]
            aid = state["slug"]

            user_state[callback_query.from_user.id].update({"box_idx": idx})

            buttons = [
                [InlineKeyboardButton("🏷 Rename Box", callback_data=f"renbox_{idx}")],
                [InlineKeyboardButton("🔗 Edit Page Link", callback_data=f"edboxlink_{idx}")],
                [InlineKeyboardButton("📦 Add Group to Box", callback_data=f"box_add_grp_{idx}")],
                [InlineKeyboardButton("🗑 Delete Box", callback_data=f"remboxidx_{idx}")]
            ]

            groups = box.get("groups", {})
            for g_idx, g_name in enumerate(groups.keys()):
                buttons.append([
                    InlineKeyboardButton(f"⚙️ {g_name}", callback_data=f"selboxg_{idx}_{g_idx}"),
                    InlineKeyboardButton("🗑", callback_data=f"remboxg_{idx}_{g_idx}")
                ])

            buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"select_box_refresh_{idx}")])
            buttons.append([InlineKeyboardButton("🛡 Back", callback_data=f"manage_boxes_{aid}")])
            await callback_query.message.edit_text(f"🗃 **Box: {box['name']}**\nManage box settings and groups:", reply_markup=InlineKeyboardMarkup(buttons))
            await callback_query.answer()
        except MessageNotModified:
            await callback_query.answer("Refresh Complete")
        except Exception as e:
            logger.error(f"Select Box Error: {e}")
            await callback_query.answer("Sync Error")

    @bot.on_callback_query(filters.regex("^box_add_grp_"))
    async def box_add_grp_cb(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        aid = user_state[callback_query.from_user.id]["slug"]
        user_state[callback_query.from_user.id].update({"action": "ask_box_cgrp_name", "box_idx": idx})
        await callback_query.message.edit_text("📦 **Group Name for Box:**\n*(e.g. 1080p [Dual], Zip File)*", reply_markup=None)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^box_grp_yes$"))
    async def box_grp_yes_cb(client, callback_query):
        # Part of the box creation flow
        state = user_state.get(callback_query.from_user.id)
        if not state: return await callback_query.answer("❌ Session Expired")
        user_state[callback_query.from_user.id].update({"action": "ask_box_initial_grp_name"})
        await callback_query.message.edit_text("📦 **First Group Name:**", reply_markup=None)

    @bot.on_callback_query(filters.regex("^box_grp_no$"))
    async def box_grp_no_cb(client, callback_query):
        # Part of the box creation flow
        uid = callback_query.from_user.id
        state = user_state.get(uid)
        if not state: return await callback_query.answer("❌ Session Expired")

        aid = state["slug"]
        new_box = {
            "name": state["box_name"],
            "link": state["box_link"],
            "groups": {}
        }

        anime = await db.get_anime(aid)
        boxes = anime.get("custom_boxes", [])
        boxes.append(new_box)

        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_boxes": boxes}, "$currentDate": {"updated_at": True}})
        await callback_query.message.edit_text(f"✅ **Box '{state['box_name']}' created successfully (Empty).**")
        del user_state[uid]

    @bot.on_callback_query(filters.regex("^remboxidx_"))
    async def remove_box_cb(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        state = user_state.get(callback_query.from_user.id)
        if not state: return await callback_query.answer("❌ Session Expired")

        aid = state["slug"]
        anime = await db.get_anime(aid)
        boxes = anime.get("custom_boxes", [])
        if idx < len(boxes):
            name = boxes[idx]['name']
            boxes.pop(idx)
            await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_boxes": boxes}, "$currentDate": {"updated_at": True}})
            await callback_query.answer(f"🗑 Box '{name}' Removed", show_alert=True)
            return await manage_boxes_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^mvupbox_"))
    async def move_box_up_cb(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        state = user_state.get(callback_query.from_user.id)
        if not state or idx == 0: return await callback_query.answer("❌ Error")

        aid = state["slug"]
        anime = await db.get_anime(aid)
        boxes = anime.get("custom_boxes", [])
        boxes[idx], boxes[idx-1] = boxes[idx-1], boxes[idx]
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_boxes": boxes}, "$currentDate": {"updated_at": True}})
        await manage_boxes_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^mvdnbox_"))
    async def move_box_dn_cb(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        state = user_state.get(callback_query.from_user.id)
        if not state: return await callback_query.answer("❌ Error")

        aid = state["slug"]
        anime = await db.get_anime(aid)
        boxes = anime.get("custom_boxes", [])
        if idx >= len(boxes) - 1: return await callback_query.answer("❌ Error")

        boxes[idx], boxes[idx+1] = boxes[idx+1], boxes[idx]
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_boxes": boxes}, "$currentDate": {"updated_at": True}})
        await manage_boxes_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^remboxg_"))
    async def remove_box_grp_cb(client, callback_query):
        parts = callback_query.data.split("_")
        if len(parts) < 3: return await callback_query.answer("❌ Error")
        b_idx, g_idx = int(parts[1]), int(parts[2])
        state = user_state.get(callback_query.from_user.id)
        if not state: return await callback_query.answer("❌ Session Expired")

        aid = state["slug"]
        anime = await db.get_anime(aid)
        boxes = anime.get("custom_boxes", [])
        if b_idx < len(boxes):
            groups = boxes[b_idx]["groups"]
            if g_idx < len(groups):
                g_name = list(groups.keys())[g_idx]
                del groups[g_name]
                await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_boxes": boxes}, "$currentDate": {"updated_at": True}})
                await callback_query.answer(f"🗑 Group '{g_name}' Removed", show_alert=True)
                return await select_box_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^selboxg_|^select_box_grp_refresh_"))
    async def select_box_grp_cb(client, callback_query):
        try:
            if callback_query.data.startswith("select_box_grp_refresh_"):
                parts = callback_query.data.split("_refresh_", 1)[1].split("_")
                b_idx, g_idx = int(parts[0]), int(parts[1])
            else:
                parts = callback_query.data.split("_")
                if len(parts) >= 3:
                    b_idx, g_idx = int(parts[1]), int(parts[2])
                else:
                    state = user_state.get(callback_query.from_user.id)
                    if state and "box_idx" in state and "box_g_idx" in state:
                        b_idx, g_idx = state["box_idx"], state["box_g_idx"]
                    else: return await callback_query.answer("❌ Error")

            state = user_state.get(callback_query.from_user.id)
            if not state: return await callback_query.answer("❌ Session Expired")

            aid = state["slug"]
            anime = await db.get_anime(aid)
            box = anime.get("custom_boxes", [])[b_idx]
            g_name = list(box["groups"].keys())[g_idx]
            group_data = box["groups"][g_name]

            user_state[callback_query.from_user.id].update({"box_idx": b_idx, "box_g_idx": g_idx, "box_g_name": g_name})

            buttons = [
                [InlineKeyboardButton("➕ Add Button to Group", callback_data=f"box_g_add_btn_{b_idx}_{g_idx}")],
                [InlineKeyboardButton("🏷 Rename Group", callback_data=f"renboxg_{b_idx}_{g_idx}")],
                [InlineKeyboardButton("🗑 Delete Group", callback_data=f"remboxg_{b_idx}_{g_idx}")]
            ]

            for btn_label in group_data.keys():
                buttons.append([
                InlineKeyboardButton(f"✏️ {btn_label}", callback_data=f"eboxgbtn_{b_idx}_{g_idx}_{btn_label}"),
                InlineKeyboardButton("🗑", callback_data=f"rboxgbtn_{b_idx}_{g_idx}_{btn_label}")
                ])

            buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"select_box_grp_refresh_{b_idx}_{g_idx}")])
            buttons.append([InlineKeyboardButton("🛡 Back", callback_data=f"selboxidx_{b_idx}")])
            await callback_query.message.edit_text(f"📦 **Group: {g_name}** (Box: {box['name']})", reply_markup=InlineKeyboardMarkup(buttons))
            await callback_query.answer()
        except MessageNotModified:
            await callback_query.answer("Refresh Complete")
        except Exception as e:
            logger.error(f"Select Box Group Error: {e}")
            await callback_query.answer("Sync Error")

    @bot.on_callback_query(filters.regex("^box_g_add_btn_"))
    async def box_g_add_btn_cb(client, callback_query):
        parts = callback_query.data.split("_")
        b_idx, g_idx = int(parts[4]), int(parts[5])
        state = user_state.get(callback_query.from_user.id)
        anime = await db.get_anime(state["slug"])
        box = anime["custom_boxes"][b_idx]
        g_name = list(box["groups"].keys())[g_idx]
        user_state[callback_query.from_user.id].update({"action": "ask_box_g_btn_label", "box_idx": b_idx, "box_g_idx": g_idx, "box_g_name": g_name})
        await callback_query.message.edit_text("🏷 **Button Label:**", reply_markup=None)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^renbox_"))
    async def rename_box_cb_prompt(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        user_state[callback_query.from_user.id].update({"action": "ask_renbox_name", "box_idx": idx})
        await callback_query.message.edit_text("✏️ **New Box Name:**", reply_markup=None)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^edboxlink_"))
    async def edit_box_link_cb_prompt(client, callback_query):
        idx = int(callback_query.data.split("_")[-1])
        user_state[callback_query.from_user.id].update({"action": "ask_edbox_link", "box_idx": idx})
        await callback_query.message.edit_text("🔗 **New Page Link for Box:**\n*(Send URL or /skip to remove)*", reply_markup=None)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^renboxg_"))
    async def rename_box_grp_cb_prompt(client, callback_query):
        parts = callback_query.data.split("_")
        b_idx, g_idx = int(parts[1]), int(parts[2])
        state = user_state.get(callback_query.from_user.id)
        anime = await db.get_anime(state["slug"])
        box = anime["custom_boxes"][b_idx]
        g_name = list(box["groups"].keys())[g_idx]
        user_state[callback_query.from_user.id].update({"action": "ask_renbox_g_name", "box_idx": b_idx, "box_g_idx": g_idx, "old_g_name": g_name})
        await callback_query.message.edit_text(f"✏️ **New Name for Group '{g_name}':**", reply_markup=None)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^eboxgbtn_"))
    async def edit_box_gbtn_cb_prompt(client, callback_query):
        parts = callback_query.data.split("_", 3)
        b_idx, g_idx, label = int(parts[1]), int(parts[2]), parts[3]
        state = user_state.get(callback_query.from_user.id)
        anime = await db.get_anime(state["slug"])
        box = anime["custom_boxes"][b_idx]
        g_name = list(box["groups"].keys())[g_idx]
        user_state[callback_query.from_user.id].update({"action": "ask_ebox_gbtn_label", "box_idx": b_idx, "box_g_idx": g_idx, "box_g_name": g_name, "old_label": label})
        await callback_query.message.edit_text(f"✏️ **New Label for '{label}':**\n*(or /skip)*", reply_markup=None)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^rboxgbtn_"))
    async def remove_box_gbtn_cb(client, callback_query):
        parts = callback_query.data.split("_", 3)
        b_idx, g_idx, label = int(parts[1]), int(parts[2]), parts[3]
        state = user_state.get(callback_query.from_user.id)
        if not state: return await callback_query.answer("❌ Session Expired")

        aid = state["slug"]
        anime = await db.get_anime(aid)
        boxes = anime.get("custom_boxes", [])
        if b_idx < len(boxes):
            g_name = list(boxes[b_idx]["groups"].keys())[g_idx]
            if g_name in boxes[b_idx]["groups"] and label in boxes[b_idx]["groups"][g_name]:
                del boxes[b_idx]["groups"][g_name][label]
                await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_boxes": boxes}, "$currentDate": {"updated_at": True}})
                await callback_query.answer(f"🗑 Button '{label}' Removed")
                return await select_box_grp_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^add_btn_start_"))
    async def add_btn_start_cb(client, callback_query):
        aid = callback_query.data.split("add_btn_start_")[-1]
        user_state[callback_query.from_user.id] = {"action": "ask_new_btn_name", "slug": aid}
        await callback_query.message.edit_text("🖇 **New Button Name:**\n*(e.g. Watch Online, Join Channel)*", reply_markup=None)
        await callback_query.answer()

    @bot.on_callback_query(filters.regex("^manage_category_"))
    async def manage_category_cb(client, callback_query):
        try:
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

            buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"manage_category_{aid}")])
            buttons.append([InlineKeyboardButton("🛡 Back", callback_data=f"back_to_edit_{aid}")])
            await callback_query.message.edit_text(
                f"📂 **Migrate Category: {anime['title']}**\n\n"
                f"Current: `{current_cat}`\n\n"
                "Select new destination category:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            await callback_query.answer()
        except MessageNotModified:
            await callback_query.answer("Refresh Complete")
        except Exception as e:
            logger.error(f"Manage Category Error: {e}")
            await callback_query.answer("Sync Error")

    @bot.on_callback_query(filters.regex("^setncat_"))
    async def set_new_category_cb(client, callback_query):
        data = callback_query.data.split("setncat_")[-1]
        aid, new_cat = data.split(":::")

        try:
            if await db.ping():
                anime = await db.get_anime(aid)
                if not anime: return await callback_query.answer("❌ Not Found")
                res = await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"category": new_cat}, "$currentDate": {"updated_at": True}})
                if res.modified_count:
                    await callback_query.answer(f"🚀 Migrated to {new_cat}", show_alert=True)
                    callback_query.data = f"back_to_edit_{aid}"
                    return await back_to_edit_cb(client, callback_query)
                await callback_query.answer("⚠️ Category remains unchanged.")
            else:
                await callback_query.answer("❌ Database Offline", show_alert=True)
        except Exception as e:
            await callback_query.answer(f"❌ Error: {e}", show_alert=True)

    @bot.on_callback_query(filters.regex("^back_to_edit_"))
    async def back_to_edit_cb(client, callback_query):
        try:
            aid = callback_query.data.split("back_to_edit_")[-1]
            anime = await db.get_anime(aid)
            if not anime: return await callback_query.answer("❌ Not Found")

            buttons = [
                [InlineKeyboardButton("📦 Content Groups (Seasons)", callback_data=f"manage_groups_{aid}")],
                [InlineKeyboardButton("🗃 Custom Boxes", callback_data=f"manage_boxes_{aid}")],
                [InlineKeyboardButton("🔗 External Redirects (Buttons)", callback_data=f"manage_btns_{aid}")],
                [InlineKeyboardButton("🚀 Advanced Group", callback_data=f"adv_grp_start_{aid}")],
                [InlineKeyboardButton("🔥 Ultra Advanced Group", callback_data=f"ultra_adv_grp_start_{aid}")],
                [InlineKeyboardButton("📂 Change Category", callback_data=f"manage_category_{aid}")],
                [InlineKeyboardButton("🏷 Change Title", callback_data=f"edit_title_{aid}")],
                [InlineKeyboardButton("🖼 Change Poster", callback_data=f"trigger_poster_{aid}")],
                [InlineKeyboardButton("🗑 Purge Archive", callback_data=f"confirm_purge_{aid}")],
                [InlineKeyboardButton("🔄 Refresh", callback_data=f"back_to_edit_{aid}"), InlineKeyboardButton("❌ Abort", callback_data="cancel_op")]
            ]
            await callback_query.message.edit_text(
                f"🏛 **Executive Suite: {anime['title']}**\n"
                f"ID: `{aid}`\n\n"
                "Select a sector to manage:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            await callback_query.answer()
        except MessageNotModified:
            await callback_query.answer("Refresh Complete")
        except Exception as e:
            logger.error(f"Back to Edit Error: {e}")
            await callback_query.answer("Sync Error")

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
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_buttons": btns}, "$currentDate": {"updated_at": True}})
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
        await db.anime.update_one(
            {"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid},
            {
                "$set": {
                    "seasons_links": dict(groups),
                    "newly_added_groups": [state["cgrp_name"]]
                },
                "$currentDate": {"updated_at": True}
            }
        )
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
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": dict(groups)}, "$currentDate": {"updated_at": True}})
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

        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": dict(groups)}, "$currentDate": {"updated_at": True}})
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
        await callback_query.answer()

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

        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": dict(groups)}, "$currentDate": {"updated_at": True}})
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

        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": dict(groups)}, "$currentDate": {"updated_at": True}})
        await select_group_cb(client, callback_query)

    @bot.on_callback_query(filters.regex("^add_gbtn_start_"))
    async def add_gbtn_start_cb(client, callback_query):
        g_idx = int(callback_query.data.split("_")[-1])
        user_state[callback_query.from_user.id].update({"action": "ask_new_gbtn_label", "g_idx": g_idx})
        await callback_query.message.edit_text("➕ **New Button Label:**\n*(e.g. 1080p, Mirror 1)*", reply_markup=None)
        await callback_query.answer()

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
            await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": groups}, "$currentDate": {"updated_at": True}})
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
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": new_groups}, "$currentDate": {"updated_at": True}})
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
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": new_groups}, "$currentDate": {"updated_at": True}})
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
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_buttons": btns}, "$currentDate": {"updated_at": True}})
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
        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_buttons": btns}, "$currentDate": {"updated_at": True}})
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
            await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_buttons": btns}, "$currentDate": {"updated_at": True}})
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
        await callback_query.answer()

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
                await db.anime.update_one({"slug": slug}, {"$set": entry, "$currentDate": {"updated_at": True}}, upsert=True)
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
                await db.anime.update_one({"slug": slug}, {"$set": entry, "$currentDate": {"updated_at": True}}, upsert=True)
                await callback_query.message.edit_caption(caption=f"⚡ **Deployment Success!**\nPortal: {Config.BASE_URL}/anime/{slug}", reply_markup=None)
                del user_state[uid]
            else:
                await callback_query.answer("❌ Database Offline", show_alert=True)
        except Exception as e: await callback_query.answer(f"DB Error: {e}", show_alert=True)

    # --- INTERACTION HANDLER (GROUP 1) ---

    @bot.on_message(filters.private & (filters.text | filters.document | filters.audio | filters.video) & ~filters.command(["start", "help", "search", "add_post", "add_page", "edit", "categories", "del", "cancel", "change_poster", "ping", "schedule", "manual", "edit_m", "save", "category_page", "addbot", "songs", "SONGS", "uptime", "UPTIME", "setbot", "ss"]), group=1)
    async def interaction_handler(client, message):
        if not message.from_user: return
        uid = message.from_user.id
        if not await is_authorized(uid):
            return await message.reply("🚫 **Access Denied.** Unauthorized user.")
        state = user_state.get(uid)
        if not state:
            # Check if admin sent a range link directly
            if message.text:
                parsed_range = parse_range_link(message.text)
                if parsed_range:
                    chat_slug, start_id, end_id = parsed_range
                    if start_id > end_id:
                        start_id, end_id = end_id, start_id

                    user_state[uid] = {
                        "action": "ask_range_groups",
                        "chat_slug": chat_slug,
                        "start_id": start_id,
                        "end_id": end_id
                    }
                    return await message.reply(
                        f"🔗 **Range Link Received:** `{chat_slug}` (Message IDs: `{start_id}` to `{end_id}`)\n\n"
                        "Please send the **Group Names** in this format:\n\n"
                        "1. Group name\n"
                        "2. Group name\n"
                        "3. Group name\n\n"
                        "Send /cancel to abort."
                    )
            return

        action = state.get("action", "")

        if not message.text and action not in ["awaiting_restore_zip", "ask_song_file", "ask_replace_song_file"]:
            return await message.reply("❌ **Invalid Input.** Please send text.")

        if action == "ask_range_groups":
            parsed_groups = parse_group_names_list(message.text)
            if not parsed_groups:
                return await message.reply(
                    "❌ **Invalid Group Names Format.** Please send in serial number format:\n\n"
                    "1. Group name\n"
                    "2. Group name\n"
                    "3. Group name\n\n"
                    "Send /cancel to abort."
                )

            user_state[uid].update({
                "action": "ask_range_page_link",
                "group_names": parsed_groups
            })
            return await message.reply(
                f"✅ **{len(parsed_groups)} Groups Registered.**\n\n"
                "Please send the **Page Link** (e.g. `https://anizoneflix-six.vercel.app/anime/naruto` or `/anime/naruto` or `naruto`):"
            )

        elif action == "ask_range_page_link":
            page_input = message.text.strip()
            slug = extract_slug(page_input)
            if not slug:
                return await message.reply("❌ **Invalid Page Link or Title.** Please send a valid link or slug:")

            anime = await db.get_anime(slug)
            if not anime:
                results = await db.search_anime_db(page_input)
                if results:
                    anime = results[0]

            if not anime:
                return await message.reply(f"❌ **Page Not Found in Database:** `{slug}`. Please send a valid page link or slug:")

            aid = str(anime["_id"])
            chat_slug = state["chat_slug"]
            start_id = state["start_id"]
            end_id = state["end_id"]
            group_names = state["group_names"]

            del user_state[uid]

            status_msg = await message.reply(
                f"🚀 **Range Link Automation Initiated!**\n\n"
                f"🎬 **Target Page:** `{anime['title']}` (`{aid}`)\n"
                f"💬 **Channel/Chat:** `{chat_slug}`\n"
                f"🔢 **Message Range:** `{start_id}` to `{end_id}` ({end_id - start_id + 1} messages)\n"
                f"👥 **Groups Configured:** {len(group_names)}\n\n"
                "⏳ Processing sequentially..."
            )

            asyncio.create_task(process_range_link_task(client, status_msg, aid, chat_slug, start_id, end_id, group_names))
            return

        if action == "ask_setbot_username":
            bot_username = message.text.strip().lstrip("@")
            if not bot_username:
                return await message.reply("❌ **Invalid Username.** Please send a valid Telegram bot username:")
            await db.set_configured_bot(bot_username)
            del user_state[uid]
            return await message.reply(f"✅ **Configured Bot Username Saved:** `@{bot_username}`")

        elif action == "ask_ss_string":
            session_str = message.text.strip()
            if not session_str:
                return await message.reply("❌ **Invalid Session String.** Please send a valid session string:")
            await db.set_configured_session(session_str)
            del user_state[uid]
            return await message.reply("✅ **Pyrogram Session String Saved Successfully!**")

        if action == "ask_uptime_bot_url":
            url = message.text.strip()
            if not (url.startswith("http://") or url.startswith("https://")):
                return await message.reply("❌ **Invalid URL.** Must begin with `http://` or `https://`. Please send again:")

            bot_id = await db.add_monitored_bot(url)
            del user_state[uid]
            await message.reply(f"✅ **Bot Registered for 24/7 Monitoring!**\n🔗 **URL:** `{url}`\n\nThe continuous 1-second ping monitor is active.")
            return

        elif action == "ask_replace_uptime_url":
            url = message.text.strip()
            if not (url.startswith("http://") or url.startswith("https://")):
                return await message.reply("❌ **Invalid URL.** Must begin with `http://` or `https://`. Please send again:")

            bot_id = state.get("bot_id")
            await db.replace_monitored_bot(bot_id, url)
            del user_state[uid]
            await message.reply(f"✅ **Monitored Bot URL Successfully Replaced!**\n🔗 **New URL:** `{url}`")
            return

        if action == "ask_song_channel":
            channel_input = message.text.strip()
            await db.set_song_channel(channel_input)
            del user_state[uid]
            await message.reply(f"✅ **Dedicated Song Channel set to:** `{channel_input}`")
            return

        elif action in ["ask_song_file", "ask_replace_song_file"]:
            media = message.audio or message.video or message.document
            if not media and not (message.text and message.text.startswith("http")):
                return await message.reply("❌ **Invalid Media.** Please send/upload an audio or video file (MP3, M4A, WAV, MP4, etc.) or a direct media URL.")

            msg = await message.reply("⏳ **Processing & storing background song...**")
            file_name = "background_song"
            file_id = None

            if media:
                file_id = getattr(media, "file_id", None)
                file_name = getattr(media, "file_name", None) or getattr(media, "title", None) or "song.mp3"
            elif message.text:
                file_name = message.text.split("/")[-1].split("?")[0] or "song.mp3"

            # Create media directory
            songs_dir = os.path.join("static", "uploads", "songs")
            os.makedirs(songs_dir, exist_ok=True)

            song_id = state.get("song_id") or str(ObjectId())
            safe_filename = f"{song_id}_{slugify(file_name)}".strip("_")
            if not safe_filename.endswith((".mp3", ".m4a", ".wav", ".mp4", ".ogg", ".aac")):
                safe_filename += ".mp3"

            dest_path = os.path.join(songs_dir, safe_filename)
            file_path = f"/static/uploads/songs/{safe_filename}"

            try:
                if media:
                    await message.download(file_name=dest_path)
                elif message.text:
                    import httpx
                    async with httpx.AsyncClient(timeout=30.0) as http_client:
                        resp = await http_client.get(message.text.strip())
                        if resp.status_code == 200:
                            with open(dest_path, "wb") as f:
                                f.write(resp.content)

                # Post file to dedicated channel if configured
                song_channel = await db.get_song_channel()
                channel_msg_id = None
                if song_channel:
                    try:
                        sent_msg = await client.send_document(
                            chat_id=song_channel,
                            document=dest_path,
                            caption=f"🎵 **Background Song:** {file_name}\nID: `{song_id}`"
                        )
                        channel_msg_id = sent_msg.id
                    except Exception as ch_err:
                        logger.error(f"Failed to send song to channel: {ch_err}")

                song_data = {
                    "song_id": song_id,
                    "title": file_name,
                    "file_id": file_id,
                    "file_path": file_path,
                    "channel_msg_id": channel_msg_id,
                    "created_at": message.date.timestamp() if message.date else 0
                }

                if action == "ask_replace_song_file":
                    await db.replace_song(song_id, song_data)
                    await msg.edit(f"✅ **Song Successfully Replaced!**\n🎵 **Title:** `{file_name}`")
                else:
                    await db.add_song(song_data)
                    await msg.edit(f"✅ **Song Successfully Added!**\n🎵 **Title:** `{file_name}`")

                del user_state[uid]
                return
            except Exception as e:
                logger.error(f"Error saving song file: {e}")
                await msg.edit(f"❌ **Failed to process song:** `{str(e)}`")
                del user_state[uid]
                return
        try:
            if action == "addbot_await_group":
                # Safely resolve group/chat username or numeric ID or invite links
                group_input = message.text.strip()

                # Safely parse and resolve Telegram invite link to its username/ID representation
                if "t.me/+" in group_input or "joinchat" in group_input:
                    await message.reply("⚠️ **Direct Invite Links cannot be resolved via getChat directly.** Please send the exact **Group Username** (e.g. `@mygroup`) or **Numeric Group ID** (e.g. `-100...`):")
                    return

                if "t.me/" in group_input:
                    group_input = "@" + group_input.split("t.me/")[-1].split("/")[0]

                # Automatically normalize positive numbers / missing -100 prefix for supergroups
                if group_input.replace("-", "").isdigit():
                    raw_num = group_input.replace("-", "")
                    if len(raw_num) >= 10 and not raw_num.startswith("100"):
                        raw_num = "100" + raw_num
                    group_input = f"-{raw_num}"

                await message.reply("⏳ **Resolving and verifying group properties...**")

                # Verify that group/username is valid
                from bot.bot_manager import added_bot_manager
                import httpx

                # Check permissions and bot existence inside the group
                # We can perform a dynamic check using Telegram Bot API directly or via a transient Client
                tg_bot_api_url = f"https://api.telegram.org/bot{state['token']}"
                try:
                    async with httpx.AsyncClient(timeout=15.0) as http_client:
                        # 1. Resolve Chat to get exact Chat ID
                        chat_res = await http_client.get(f"{tg_bot_api_url}/getChat", params={"chat_id": group_input})
                        if chat_res.status_code != 200:
                            await message.reply(f"❌ **Chat Not Found:** Telegram cannot find or access `{group_input}`. Make sure the bot is already added to the chat.")
                            return

                        chat_data = chat_res.json().get("result", {})
                        resolved_group_id = chat_data.get("id")
                        resolved_title = chat_data.get("title") or chat_data.get("username")

                        # 2. Check if Bot is an Administrator in the chat
                        member_res = await http_client.get(f"{tg_bot_api_url}/getChatMember", params={"chat_id": resolved_group_id, "user_id": state["bot_info"]["id"]})
                        if member_res.status_code != 200:
                            await message.reply("❌ **Bot is not in the group.** Please add the bot as an administrator first.")
                            return

                        member_data = member_res.json().get("result", {})
                        status = member_data.get("status")
                        if status not in ["administrator", "creator"]:
                            await message.reply("❌ **Bot is in the group but is NOT an Administrator.** Please grant admin privileges.")
                            return

                        # 3. Check Required Admin Permissions
                        # Required: Read Messages (can_be_edited / implicit), Send Messages, Delete Messages
                        # Pyrogram / Bot API specific permissions:
                        can_post = member_data.get("can_post_messages", True)
                        can_delete = member_data.get("can_delete_messages", False)

                        missing_perms = []
                        if not can_delete:
                            missing_perms.append("Delete Messages")

                        if missing_perms:
                            await message.reply(
                                f"⚠️ **Warning: Missing Admin Permissions:**\n\n"
                                f"• {', '.join(missing_perms)}\n\n"
                                f"Please grant these permissions to @{state['bot_info']['username']} in the group for optimal performance."
                            )

                        # Save Bot configuration into added_bots collection
                        await db.added_bots.update_one(
                            {"token": state["token"]},
                            {"$set": {
                                "token": state["token"],
                                "group_id": resolved_group_id,
                                "group_title": resolved_title,
                                "bot_info": state["bot_info"]
                            }},
                            upsert=True
                        )

                        # Dynamic Boot/Start the newly added bot
                        started = await added_bot_manager.start_bot(state["token"], resolved_group_id, state["bot_info"])
                        if started:
                            await message.reply(
                                f"🎉 **Success! Bot Configuration Activated.**\n\n"
                                f"🤖 **Bot:** @{state['bot_info']['username']}\n"
                                f"👥 **Configured Chat:** `{resolved_title}` ({resolved_group_id})\n"
                                f"⚡ **Status:** Active & Scanning group query inputs 24/7."
                            )
                        else:
                            await message.reply("⚠️ **Configuration saved, but the bot client failed to boot.** Ensure API keys are active.")

                        del user_state[uid]
                except Exception as e:
                    logger.error(f"Error during addbot validation flow: {e}")
                    await message.reply(f"❌ **An unexpected error occurred during validation:** {e}")
                    try:
                        from bot.bot_manager import report_addbot_issue
                        await report_addbot_issue(state.get("token", "")[:15] + "...", f"Addbot group validation failure: {str(e)}")
                    except: pass
                return
            elif action == "ask_search_query":
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
                    await db.anime.update_one({"slug": slug}, {"$set": entry, "$currentDate": {"updated_at": True}}, upsert=True)
                    await message.reply(f"🚀 **Custom Page Published!**\nPortal: {Config.BASE_URL}/anime/{slug}")
                else:
                    await message.reply("❌ Database Offline")
                del user_state[uid]
            elif action == "ask_rename_group_new_name":
                new_name = message.text.strip()
                aid, old_name = state["slug"], state["old_name"]
                anime = await db.get_anime(aid)
                if anime:
                    groups = anime.get("seasons_links", {})
                    if old_name in groups:
                        groups[new_name] = groups.pop(old_name)
                        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": groups}, "$currentDate": {"updated_at": True}})
                        await message.reply(f"✅ **Group Renamed:** `{old_name}` → `{new_name}`")
                    else: await message.reply("❌ Group mismatch.")
                else: await message.reply("❌ Series not found.")
                del user_state[uid]
            elif action == "ask_change_series_title":
                new_title = message.text.strip()
                aid = state["slug"]
                new_slug = slugify(new_title)
                if await db.ping():
                    res = await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"title": new_title, "slug": new_slug}, "$currentDate": {"updated_at": True}})
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
                        await db.anime.update_one({"slug": state["slug"]}, {"$set": {"custom_buttons": existing_buttons}, "$currentDate": {"updated_at": True}})
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
            elif action == "ask_cgrp_btn_count":
                try:
                    count = int(message.text.strip())
                    if count <= 0:
                        return await message.reply("❌ **Number must be greater than 0. Please try again:**")
                    user_state[uid].update({
                        "action": "ask_cgrp_links_format",
                        "btn_count": count
                    })
                    await message.reply(
                        "Please send the button names and links in the following format:\n\n"
                        "GROUP NAME\n"
                        "Button Name : Link Button Name : Link\n\n"
                        "Example:\n"
                        "EP15\n\n"
                        "480p : https://example.com/480p 720p : https://example.com/720p 1080p : https://example.com/1080p"
                    )
                except:
                    await message.reply("❌ **Invalid number.** Send a valid integer:")
            elif action == "ask_cgrp_links_format":
                btn_count = state["btn_count"]
                # Split message into non-empty lines
                lines = [line.strip() for line in message.text.split("\n") if line.strip()]
                if len(lines) < 2:
                    return await message.reply(
                        f"❌ **Invalid Format.** Please send the Group Name on the first line, followed by exactly {btn_count} buttons on the next line:\n\n"
                        "GROUP NAME\n"
                        "Button Name : Link Button Name : Link\n\n"
                        "Example:\n"
                        "EP15\n\n"
                        "480p : https://example.com/480p 720p : https://example.com/720p 1080p : https://example.com/1080p"
                    )

                gname = lines[0]
                buttons_text = "\n".join(lines[1:])
                parsed_buttons = parse_buttons_string(buttons_text, btn_count)
                if parsed_buttons is None:
                    return await message.reply(
                        f"❌ **Invalid Format or Link.** Please send exactly {btn_count} buttons in the correct format:\n\n"
                        "GROUP NAME\n"
                        "Button Name : Link Button Name : Link\n\n"
                        "Example:\n"
                        "EP15\n\n"
                        "480p : https://example.com/480p 720p : https://example.com/720p 1080p : https://example.com/1080p"
                    )

                user_state[uid].update({
                    "cgrp_name": gname,
                    "cgrp_data": parsed_buttons,
                    "action": "ask_cgrp_pos"
                })
                buttons = [
                    [InlineKeyboardButton("🔝 Beginning", callback_data="setposcg_0"), InlineKeyboardButton("🔚 End", callback_data="setposcg_-1")],
                    [InlineKeyboardButton("🎯 Select Position", callback_data="setposcg_select")]
                ]
                await message.reply(f"📍 **Position for group '{gname}':**", reply_markup=InlineKeyboardMarkup(buttons))
            elif action == "ask_cgrp_name_after_links":
                # Kept as fallback in case any existing state is active
                gname = message.text.strip()
                user_state[uid].update({
                    "cgrp_name": gname,
                    "action": "ask_cgrp_pos"
                })
                buttons = [
                    [InlineKeyboardButton("🔝 Beginning", callback_data="setposcg_0"), InlineKeyboardButton("🔚 End", callback_data="setposcg_-1")],
                    [InlineKeyboardButton("🎯 Select Position", callback_data="setposcg_select")]
                ]
                await message.reply(f"📍 **Position for group '{gname}':**", reply_markup=InlineKeyboardMarkup(buttons))
            elif action == "ask_ultra_adv_grp_message":
                from utils.parser import parse_ultra_advanced_group
                parsed_boxes, parsing_errors = parse_ultra_advanced_group(message.text)
                if parsing_errors:
                    await message.reply(
                        f"❌ **Formatting Error in Ultra Advanced Group:**\n\n"
                        f"{chr(10).join(parsing_errors[:10])}\n"
                        f"{'...and more' if len(parsing_errors) > 10 else ''}\n\n"
                        "Please correct the formatting and resend the complete message (or send /cancel to abort):"
                    )
                    return

                aid = state["slug"]
                anime = await db.get_anime(aid)
                if not anime:
                    await message.reply("❌ **Error:** Anime page not found in database anymore.")
                    user_state.pop(uid, None)
                    return

                boxes = anime.get("custom_boxes", [])

                # We need to process sequentially
                boxes_processed = len(parsed_boxes)
                successful_boxes = 0
                failed_boxes_list = []
                groups_added = 0
                buttons_added = 0

                # Convert existing box names to lowercase for robust case-insensitive matching
                box_name_map = {}
                for idx, box in enumerate(boxes):
                    box_name_map[box["name"].strip().lower()] = idx

                for item in parsed_boxes:
                    box_name_ref = item["box_name"].strip()
                    lower_ref = box_name_ref.lower()

                    if lower_ref not in box_name_map:
                        failed_boxes_list.append(box_name_ref)
                        continue

                    # Found the existing box!
                    b_idx = box_name_map[lower_ref]
                    target_box = boxes[b_idx]

                    if "groups" not in target_box or not isinstance(target_box["groups"], dict):
                        target_box["groups"] = {}

                    # Add groups
                    for grp in item["groups"]:
                        grp_name = grp["group_name"]
                        buttons_dict = grp["buttons"]

                        if grp_name not in target_box["groups"]:
                            target_box["groups"][grp_name] = {}

                        # Append newly supplied buttons to existing/new groups
                        target_box["groups"][grp_name].update(buttons_dict)
                        groups_added += 1
                        buttons_added += len(buttons_dict)

                    successful_boxes += 1

                if successful_boxes > 0:
                    new_grp_names = []
                    for item in parsed_boxes:
                        for grp in item["groups"]:
                            new_grp_names.append(grp["group_name"])

                    await db.anime.update_one(
                        {"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid},
                        {
                            "$set": {
                                "custom_boxes": boxes,
                                "newly_added_groups": new_grp_names
                            },
                            "$currentDate": {"updated_at": True}
                        }
                    )

                failed_boxes_count = len(failed_boxes_list)

                summary = (
                    "✅ **Ultra Advanced Group Completed**\n\n"
                    f"📦 **Boxes Processed:** {boxes_processed}\n"
                    f"✅ **Successful Boxes:** {successful_boxes}\n"
                    f"❌ **Boxes Not Found:** {failed_boxes_count}\n"
                    f"➕ **Groups Added:** {groups_added}\n"
                    f"🔘 **Buttons Added:** {buttons_added}\n"
                )

                if failed_boxes_list:
                    summary += "\n**Not Found:**\n" + "\n".join(f"• {name}" for name in failed_boxes_list)

                user_state.pop(uid, None)
                await message.reply(summary)

            elif action == "ask_adv_grp_message":
                parsed_groups, error_msg = parse_advanced_group_message(message.text)
                if error_msg:
                    await message.reply(
                        f"❌ **Formatting Error:**\n{error_msg}\n\n"
                        "Please correct the formatting and resend the complete message (or send /cancel to abort):"
                    )
                    return

                aid, b_idx = state["slug"], state["box_idx"]
                anime = await db.get_anime(aid)
                if not anime:
                    await message.reply("❌ **Error:** Anime page not found in database anymore.")
                    del user_state[uid]
                    return

                boxes = anime.get("custom_boxes", [])
                if b_idx >= len(boxes):
                    await message.reply("❌ **Error:** Target box not found in database anymore.")
                    del user_state[uid]
                    return

                if "groups" not in boxes[b_idx] or not isinstance(boxes[b_idx]["groups"], dict):
                    boxes[b_idx]["groups"] = {}

                boxes[b_idx]["groups"].update(parsed_groups)

                await db.anime.update_one(
                    {"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid},
                    {
                        "$set": {
                            "custom_boxes": boxes,
                            "newly_added_groups": list(parsed_groups.keys())
                        },
                        "$currentDate": {"updated_at": True}
                    }
                )

                g_count = len(parsed_groups)
                btn_count = sum(len(btn_map) for btn_map in parsed_groups.values())

                success_text = (
                    "✅ **Advanced Group Import Successful!**\n\n"
                    f"📦 **Custom Box:** {boxes[b_idx]['name']}\n"
                    f"📂 **Groups added/updated:** {g_count}\n"
                    f"🔗 **Buttons added/updated:** {btn_count}\n\n"
                    "All changes have been safely saved and instantly synchronized with the website."
                )

                del user_state[uid]
                await message.reply(success_text)
            elif action == "ask_box_name":
                from utils.parser import parse_bulk_box_names
                box_names, parsing_errors = parse_bulk_box_names(message.text)
                if parsing_errors:
                    await message.reply(
                        f"❌ **Formatting Error in Bulk Box format:**\n\n"
                        f"{chr(10).join(parsing_errors[:10])}\n"
                        f"{'...and more' if len(parsing_errors) > 10 else ''}\n\n"
                        "Please correct the formatting and send again (or send /cancel to abort):"
                    )
                    return

                aid = state["slug"]
                anime = await db.get_anime(aid)
                if not anime:
                    await message.reply("❌ **Error:** Anime page not found in database.")
                    user_state.pop(uid, None)
                    return

                existing_boxes = anime.get("custom_boxes", [])
                existing_box_names_lower = {b["name"].strip().lower() for b in existing_boxes}

                total_submitted = len(box_names)
                added_boxes = []
                already_exists = []
                failed = 0

                for bname in box_names:
                    bname_clean = bname.strip()
                    if bname_clean.lower() in existing_box_names_lower:
                        already_exists.append(bname_clean)
                    else:
                        new_box = {
                            "name": bname_clean,
                            "link": None,
                            "groups": {}
                        }
                        existing_boxes.append(new_box)
                        added_boxes.append(bname_clean)

                if added_boxes:
                    await db.anime.update_one(
                        {"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid},
                        {"$set": {"custom_boxes": existing_boxes}, "$currentDate": {"updated_at": True}}
                    )

                summary = (
                    "✅ **Bulk Box Creation Completed**\n\n"
                    f"📦 **Total Submitted:** {total_submitted}\n"
                    f"✅ **Added:** {len(added_boxes)}\n"
                    f"⚠️ **Already Exists:** {len(already_exists)}\n"
                    f"❌ **Failed:** {failed}\n"
                )

                if already_exists:
                    summary += "\n**Already Exists:**\n" + "\n".join(f"• {name}" for name in already_exists)

                user_state.pop(uid, None)
                await message.reply(summary)
            elif action == "ask_box_link":
                link = message.text.strip() if message.text != "/skip" else None
                user_state[uid].update({"box_link": link, "action": "ask_box_group_check"})
                buttons = [
                    [InlineKeyboardButton("✅ Yes", callback_data="box_grp_yes"), InlineKeyboardButton("❌ No", callback_data="box_grp_no")]
                ]
                await message.reply("📦 **Do you want to add a group to this box?**\n*(Reply Y/N or use buttons)*", reply_markup=InlineKeyboardMarkup(buttons))
            elif action == "ask_box_group_check":
                text = message.text.strip().upper()
                if text in ["Y", "YES"]:
                    user_state[uid].update({"action": "ask_box_initial_grp_name"})
                    await message.reply("📦 **First Group Name:**")
                elif text in ["N", "NO"]:
                    aid = state["slug"]
                    new_box = {"name": state["box_name"], "link": state["box_link"], "groups": {}}
                    anime = await db.get_anime(aid)
                    boxes = anime.get("custom_boxes", [])
                    boxes.append(new_box)
                    await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_boxes": boxes}, "$currentDate": {"updated_at": True}})
                    await message.reply(f"✅ **Box '{state['box_name']}' created successfully (Empty).**")
                    del user_state[uid]
                else:
                    await message.reply("❌ **Invalid Input.** Please send Y or N:")
            elif action == "ask_box_initial_grp_name":
                user_state[uid].update({"action": "ask_box_initial_grp_btn_count", "temp_grp_name": message.text.strip()})
                await message.reply(f"🖇 **How many buttons in '{message.text.strip()}'?**")
            elif action == "ask_box_initial_grp_btn_count":
                try:
                    count = int(message.text.strip())
                    user_state[uid].update({"action": "ask_box_initial_grp_btn_label", "btn_count": count, "current_idx": 1, "temp_grp_data": {}})
                    await message.reply(f"🏷 **Button 1 Label:**")
                except: return await message.reply("❌ **Invalid number.** Send a valid integer:")
            elif action == "ask_box_initial_grp_btn_label":
                user_state[uid].update({"action": "ask_box_initial_grp_btn_link", "temp_btn_label": message.text.strip()})
                await message.reply(f"🔗 **URL for '{message.text.strip()}':**")
            elif action == "ask_box_initial_grp_btn_link":
                if not message.text.startswith("http"): return await message.reply("❌ Invalid URL.")
                state["temp_grp_data"][state["temp_btn_label"]] = message.text.strip()
                if state["current_idx"] < state["btn_count"]:
                    user_state[uid]["current_idx"] += 1
                    user_state[uid]["action"] = "ask_box_initial_grp_btn_label"
                    await message.reply(f"🏷 **Button {user_state[uid]['current_idx']} Label:**")
                else:
                    # Finalize BOX with initial group
                    aid = state["slug"]
                    new_box = {
                        "name": state["box_name"],
                        "link": state["box_link"],
                        "groups": {state["temp_grp_name"]: state["temp_grp_data"]}
                    }
                    anime = await db.get_anime(aid)
                    boxes = anime.get("custom_boxes", [])
                    boxes.append(new_box)
                    await db.anime.update_one(
                        {"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid},
                        {
                            "$set": {
                                "custom_boxes": boxes,
                                "newly_added_groups": [state["temp_grp_name"]]
                            },
                            "$currentDate": {"updated_at": True}
                        }
                    )
                    await message.reply(f"✅ **Box '{state['box_name']}' created with group '{state['temp_grp_name']}'.**")
                    del user_state[uid]
            elif action == "ask_box_cgrp_name":
                user_state[uid].update({"action": "ask_box_cgrp_btn_count", "temp_grp_name": message.text.strip()})
                await message.reply(f"🖇 **How many buttons in '{message.text.strip()}'?**")
            elif action == "ask_box_cgrp_btn_count":
                try:
                    count = int(message.text.strip())
                    user_state[uid].update({"action": "ask_box_cgrp_btn_label", "btn_count": count, "current_idx": 1, "temp_grp_data": {}})
                    await message.reply(f"🏷 **Button 1 Label:**")
                except: return await message.reply("❌ **Invalid number.** Send a valid integer:")
            elif action == "ask_box_cgrp_btn_label":
                user_state[uid].update({"action": "ask_box_cgrp_btn_link", "temp_btn_label": message.text.strip()})
                await message.reply(f"🔗 **URL for '{message.text.strip()}':**")
            elif action == "ask_box_cgrp_btn_link":
                if not message.text.startswith("http"): return await message.reply("❌ Invalid URL.")
                state["temp_grp_data"][state["temp_btn_label"]] = message.text.strip()
                if state["current_idx"] < state["btn_count"]:
                    user_state[uid]["current_idx"] += 1
                    user_state[uid]["action"] = "ask_box_cgrp_btn_label"
                    await message.reply(f"🏷 **Button {user_state[uid]['current_idx']} Label:**")
                else:
                    aid, b_idx = state["slug"], state["box_idx"]
                    anime = await db.get_anime(aid)
                    boxes = anime.get("custom_boxes", [])
                    boxes[b_idx]["groups"][state["temp_grp_name"]] = state["temp_grp_data"]
                    await db.anime.update_one(
                        {"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid},
                        {
                            "$set": {
                                "custom_boxes": boxes,
                                "newly_added_groups": [state["temp_grp_name"]]
                            },
                            "$currentDate": {"updated_at": True}
                        }
                    )
                    await message.reply(f"✅ **Group '{state['temp_grp_name']}' added to box '{boxes[b_idx]['name']}'.**")
                    del user_state[uid]
            elif action == "ask_renbox_name":
                idx, aid = state["box_idx"], state["slug"]
                anime = await db.get_anime(aid)
                boxes = anime.get("custom_boxes", [])
                boxes[idx]["name"] = message.text.strip()
                await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_boxes": boxes}, "$currentDate": {"updated_at": True}})
                await message.reply("✅ Box Renamed.")
                del user_state[uid]
            elif action == "ask_edbox_link":
                idx, aid = state["box_idx"], state["slug"]
                anime = await db.get_anime(aid)
                boxes = anime.get("custom_boxes", [])
                boxes[idx]["link"] = message.text.strip() if message.text != "/skip" else None
                await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_boxes": boxes}, "$currentDate": {"updated_at": True}})
                await message.reply("✅ Box Link Updated.")
                del user_state[uid]
            elif action == "ask_box_g_btn_label":
                user_state[uid].update({"action": "ask_box_g_btn_link", "temp_btn_label": message.text.strip()})
                await message.reply(f"🔗 **URL for '{message.text.strip()}':**")
            elif action == "ask_box_g_btn_link":
                if not message.text.startswith("http"): return await message.reply("❌ Invalid URL.")
                aid, b_idx, g_name = state["slug"], state["box_idx"], state["box_g_name"]
                anime = await db.get_anime(aid)
                boxes = anime.get("custom_boxes", [])
                boxes[b_idx]["groups"][g_name][state["temp_btn_label"]] = message.text.strip()
                await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_boxes": boxes}, "$currentDate": {"updated_at": True}})
                await message.reply(f"✅ Button added to group '{g_name}'.")
                del user_state[uid]
            elif action == "ask_renbox_g_name":
                idx, aid, old_name = state["box_idx"], state["slug"], state["old_name"] if "old_name" in state else state["old_g_name"]
                new_name = message.text.strip()
                anime = await db.get_anime(aid)
                boxes = anime.get("custom_boxes", [])
                if old_name in boxes[idx]["groups"]:
                    # Order-preserving rename
                    groups = boxes[idx]["groups"]
                    new_groups = {}
                    for k, v in groups.items():
                        if k == old_name: new_groups[new_name] = v
                        else: new_groups[k] = v
                    boxes[idx]["groups"] = new_groups
                    await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_boxes": boxes}, "$currentDate": {"updated_at": True}})
                    await message.reply(f"✅ Group Renamed: {old_name} -> {new_name}")
                del user_state[uid]
            elif action == "ask_ebox_gbtn_label":
                user_state[uid].update({"action": "ask_ebox_gbtn_link", "new_label": message.text.strip()})
                await message.reply("🔗 **New URL:**\n*(or /skip)*")
            elif action == "ask_ebox_gbtn_link":
                idx, aid, g_name, old_label = state["box_idx"], state["slug"], state["box_g_name"], state["old_label"]
                anime = await db.get_anime(aid)
                boxes = anime.get("custom_boxes", [])
                group = boxes[idx]["groups"][g_name]

                new_label = state["new_label"] if state["new_label"] != "/skip" else old_label
                new_link = message.text.strip() if message.text != "/skip" else group[old_label]

                if new_label != old_label:
                    del group[old_label]
                group[new_label] = new_link

                await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_boxes": boxes}, "$currentDate": {"updated_at": True}})
                await message.reply("✅ Button Updated.")
                del user_state[uid]
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
                await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"seasons_links": dict(groups)}, "$currentDate": {"updated_at": True}})
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
                    res = await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"image": message.text.strip()}, "$currentDate": {"updated_at": True}})
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
                    await db.anime.update_one(
                        {"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid},
                        {
                            "$set": {
                                "seasons_links": new_links,
                                "newly_added_groups": [state["group_name"]]
                            },
                            "$currentDate": {"updated_at": True}
                        }
                    )
                    await message.reply(f"💎 **Success!** Group synchronized.")
                else:
                    await message.reply("❌ Database Offline")
                del user_state[uid]
            elif action == "ask_edit_btn_name":
                user_state[uid].update({"action": "ask_edit_btn_link", "new_name": message.text.strip()})
                await message.reply(f"🔗 **New URL for '{message.text.strip()}':**\n*(or `/skip` to keep current)*")
            elif action == "ask_edit_btn_link":
                idx, aid = state["btn_idx"], state["slug"]
                anime = await db.get_anime(aid)
                if anime:
                    btns = anime.get("custom_buttons", [])
                    if idx < len(btns):
                        btns[idx]['name'] = state["new_name"]
                        if message.text != "/skip": btns[idx]['link'] = message.text.strip()
                        await db.anime.update_one({"_id": ObjectId(aid)} if ObjectId.is_valid(aid) else {"slug": aid}, {"$set": {"custom_buttons": btns}, "$currentDate": {"updated_at": True}})
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
