import asyncio
import logging
import os
import json
import zipfile
import tempfile
import traceback
import re
from urllib.parse import urljoin
from io import BytesIO
from pyrogram import Client, filters, enums, ContinuePropagation
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, CallbackQuery
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from config.config import Config
from api.media_api import media_api
from database.db import db
from utils.utils import slugify

# Setup Logging
logger = logging.getLogger("MZ_BOT")
logger.setLevel(logging.INFO)

# Initialize the bot client
bot = Client(
    "movieszoneflix_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    in_memory=True
)

user_state = {}
search_cache = {}

def build_search_page(cache_id, results, page=1, items_per_page=6):
    total = len(results)
    total_pages = max(1, (total + items_per_page - 1) // items_per_page)
    if page < 1: page = 1
    if page > total_pages: page = total_pages

    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    page_items = results[start_idx:end_idx]

    text = f"🎯 **Select Media to Import (Page {page}/{total_pages} • Total {total} Results):**\n\n"
    buttons = []
    for i, res in enumerate(page_items, start_idx + 1):
        title_disp = res['title'][:22] + "..." if len(res['title']) > 25 else res['title']
        text += f"**{i}.** {res['title']} ({res['year']}) `[{res['type'].upper()}]` • _via {res['source']}_\n"

        if res["source"] == "TMDb":
            cb_data = f"add_tmdb_{res['type']}_{res['id']}"
        elif res["source"] == "TVmaze":
            cb_data = f"add_tvmaze_tv_{res['id']}"
        elif res["source"] == "OMDb":
            cb_data = f"add_omdb_{res['type']}_{res['id']}"

        buttons.append([InlineKeyboardButton(f"Import {i}. {title_disp} ({res['source']})", callback_data=cb_data)])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️ Previous", callback_data=f"srchp_{cache_id}_{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"srchp_{cache_id}_{page + 1}"))

    if nav_row:
        buttons.append(nav_row)

    return text, InlineKeyboardMarkup(buttons)

async def is_authorized(user_id):
    if not user_id: return False
    if user_id in Config.ADMIN_IDS: return True
    try:
        if not await db.ping(): return False
        user = await db.users.find_one({"user_id": user_id, "is_admin": True})
        return user is not None
    except: return False

def extract_slug(text):
    if not text: return None
    text = text.strip()
    for indicator in ["/watch/", "/anime/"]:
        if indicator in text:
            try:
                return text.split(indicator)[1].split("?")[0].split("/")[0].strip()
            except: pass
    if text.startswith("http://") or text.startswith("https://"):
        try:
            from urllib.parse import urlparse
            path = urlparse(text).path
            parts = [p for p in path.split("/") if p]
            if parts:
                return parts[-1]
        except: pass
    return text

def parse_groups_message(text: str):
    """
    Parses a multiline message of groups and buttons.
    Returns: dict { "Group Name": { "Button Name": "Link" } } or None if validation fails.
    """
    lines = [line.strip() for line in text.strip().split("\n")]
    groups = {}
    current_group = None

    for line in lines:
        if not line:
            continue
        # Check if it is a group header, e.g. "1. Season 1"
        header_match = re.match(r"^\d+\.\s*(.+)$", line)
        if header_match:
            current_group = header_match.group(1).strip()
            groups[current_group] = {}
        else:
            # Must be a button line: "Button Name : Link"
            if ":" not in line:
                return None # Invalid format
            parts = line.split(":", 1)
            btn_name = parts[0].strip()
            btn_link = parts[1].strip()

            if not btn_name or not btn_link:
                return None # Invalid format
            if not (btn_link.startswith("http://") or btn_link.startswith("https://")):
                return None # Invalid format

            if current_group is None:
                return None # Button declared before any group header

            groups[current_group][btn_name] = btn_link

    # Must have at least one group with at least one button
    if not groups:
        return None
    for gname, buttons in groups.items():
        if not buttons:
            return None

    return groups

def register_handlers(bot: Client):
    logger.info("Registering bot handlers...")

    @bot.on_message(filters.all, group=-100)
    async def log_updates(client, message):
        raise ContinuePropagation

    @bot.on_message(filters.command("start") & filters.private)
    async def start_cmd(client, message):
        await message.reply_text(
            "💎 **MoviesZoneFlix Premium Management Core** 💎\n\n"
            "Welcome, Administrator! Use the following tools to manage your database, metadata, servers, and channels with absolute ease.\n\n"
            "👑 **Administrative Commands:**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔍 `/search <query>` — Import title details directly from TMDB\n"
            "✏️ `/edit <url/slug>` — Update titles, posters, descriptions, and metadata\n"
            "🔗 `/edit_m <url/slug>` — Manage media servers, link groups, and mirrors\n"
            "🎬 `/add_movie` — Manually add a movie to the portal\n"
            "📺 `/add_series` — Manually add a TV show/series\n"
            "🗑️ `/del <url/slug>` — Safely remove media content from the catalog\n"
            "📂 `/categories` — Create and manage movie genres & categories\n"
            "📢 `/posttochannel <id> <link>` — Post professional structured media card to channel\n"
            "💾 `/save` — Perform secure database backup or JSON restoration\n"
            "📡 `/ping` — Check current bot operational status and latency\n"
            "❌ `/cancel` — Instantly abort any active conversational sequence\n\n"
            "⚡ *Powered by MoviesZoneFlix High-Performance Core*"
        )

    @bot.on_message(filters.command("ping") & filters.private)
    async def ping_cmd(client, message):
        await message.reply_text("📡 **Pong!** MoviesZoneFlix Engine is fully operational and responsive.")

    @bot.on_message(filters.command("search") & filters.private)
    async def search_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        query = " ".join(message.command[1:])
        if not query: return await message.reply("Usage: `/search <name>`")
        msg = await message.reply("🔍 Searching Configured APIs...")
        try:
            results = []

            # 1. TMDB Search (Page 1 & Page 2 for comprehensive coverage)
            if Config.TMDB_API_KEY:
                try:
                    for p in [1, 2]:
                        tmdb_res = await media_api.search_tmdb(query, page=p)
                        for r in tmdb_res:
                            r["source"] = "TMDb"
                            results.append(r)
                except Exception as e:
                    logger.error(f"TMDb Search failed: {e}")

            # 2. TVmaze Search
            try:
                tvmaze_res = await media_api.search_tvmaze(query)
                for r in tvmaze_res:
                    r["source"] = "TVmaze"
                    results.append(r)
            except Exception as e:
                logger.error(f"TVmaze Search failed: {e}")

            # 3. OMDb Search
            if Config.OMDB_API_KEY:
                try:
                    omdb_data = await media_api.get_omdb_metadata(query)
                    if omdb_data and omdb_data.get("Response") == "True":
                        results.append({
                            "id": omdb_data.get("imdbID"),
                            "title": omdb_data.get("Title"),
                            "type": "movie" if omdb_data.get("Type") == "movie" else "tv",
                            "year": omdb_data.get("Year")[:4] if omdb_data.get("Year") else "0000",
                            "source": "OMDb"
                        })
                except Exception as e:
                    logger.error(f"OMDb Search failed: {e}")

            if not results: return await msg.edit("😔 No matches found on any configured APIs.")

            # Deduplicate results by (title lower, year, source)
            seen = set()
            unique_results = []
            for r in results:
                key = (r.get("title", "").lower().strip(), str(r.get("year")), r.get("source"))
                if key not in seen:
                    seen.add(key)
                    unique_results.append(r)

            import uuid
            cache_id = str(uuid.uuid4())[:8]
            search_cache[cache_id] = unique_results

            text, markup = build_search_page(cache_id, unique_results, page=1)
            await msg.edit(text, reply_markup=markup)
        except Exception as e: await msg.edit(f"❌ Error: {e}")

    @bot.on_message(filters.command("edit") & filters.private)
    async def edit_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        query = " ".join(message.command[1:])
        if not query and message.reply_to_message:
            query = message.reply_to_message.text or message.reply_to_message.caption or ""
        slug = extract_slug(query)
        if not slug: return await message.reply("💡 **Usage:** `/edit <url/slug>` or reply to a link/slug.")
        media = await db.get_media_by_slug(slug)
        if not media: return await message.reply("❌ Not found.")
        buttons = [
            [InlineKeyboardButton("🖼 Poster", callback_data=f"et_poster_{slug}"),
             InlineKeyboardButton("🏷 Title", callback_data=f"et_title_{slug}")],
            [InlineKeyboardButton("📅 Year", callback_data=f"et_year_{slug}"),
             InlineKeyboardButton("📂 Genres", callback_data=f"et_genres_{slug}")],
            [InlineKeyboardButton("🎬 Director", callback_data=f"et_director_{slug}"),
             InlineKeyboardButton("🎭 Cast", callback_data=f"et_cast_{slug}")],
            [InlineKeyboardButton("⭐ Score", callback_data=f"et_score_{slug}"),
             InlineKeyboardButton("⏱ Runtime", callback_data=f"et_runtime_{slug}")],
            [InlineKeyboardButton("📺 Trailer", callback_data=f"et_trailer_{slug}"),
             InlineKeyboardButton("📊 Status", callback_data=f"et_status_{slug}")],
            [InlineKeyboardButton("📝 Synopsis", callback_data=f"et_syno_{slug}"),
             InlineKeyboardButton("🎥 Type", callback_data=f"et_type_{slug}")],
            [InlineKeyboardButton("📂 Change Category", callback_data=f"et_movecat_{slug}")],
            [InlineKeyboardButton("🗑 DELETE MEDIA", callback_data=f"confirm_del_{slug}")]
        ]
        await message.reply_text(f"🛠 **Editing:** `{media['title']}`", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_message(filters.command(["edit_m", "edt_m"]) & filters.private)
    async def edit_m_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        query = " ".join(message.command[1:])
        if not query and message.reply_to_message:
            query = message.reply_to_message.text or message.reply_to_message.caption or ""
        slug = extract_slug(query)
        if not slug: return await message.reply("💡 **Usage:** `/edit_m <url/slug>` or reply to a link/slug.")
        media = await db.get_media_by_slug(slug)
        if not media: return await message.reply("❌ Not found.")
        buttons = [
            [InlineKeyboardButton("➕ Add New Group", callback_data=f"m_addg_{slug}")],
            [InlineKeyboardButton("📂 Change Category", callback_data=f"et_movecat_{slug}")]
        ]
        links = media.get("seasons_links", {})
        if isinstance(links, dict):
            for gname in links.keys():
                buttons.append([
                    InlineKeyboardButton(f"⚙️ {gname}", callback_data=f"m_mgrg_{slug}_{gname}"),
                    InlineKeyboardButton("🗑", callback_data=f"m_delg_{slug}_{gname}")
                ])
        await message.reply_text(f"🔗 **Servers:** `{media['title']}`", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_message(filters.command("del") & filters.private)
    async def del_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        query = " ".join(message.command[1:])
        if not query and message.reply_to_message:
            query = message.reply_to_message.text or message.reply_to_message.caption or ""
        slug = extract_slug(query)
        if not slug: return await message.reply("💡 **Usage:** `/del <url/slug>` or reply to a link/slug.")
        media = await db.get_media_by_slug(slug)
        if not media: return await message.reply("❌ Not found.")
        buttons = [[InlineKeyboardButton("🔥 PURGE IT", callback_data=f"execute_del_{slug}"), InlineKeyboardButton("🛡 ABORT", callback_data="cancel_op")]]
        await message.reply(f"⚠️ **Confirm Delete:** `{media['title']}`?", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_message(filters.command("save") & filters.private)
    async def save_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        buttons = [
            [InlineKeyboardButton("📥 BACKUP DATABASE", callback_data="db_backup"),
             InlineKeyboardButton("📤 RESTORE BACKUP", callback_data="db_restore")]
        ]
        await message.reply_text("💾 **MoviesZoneFlix Backup & Migration Center**\n\nSecurely archive your media database or upload an existing ZIP archive to restore.", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_message(filters.command("categories") & filters.private)
    async def categories_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        cats = await db.get_all_categories()
        text = "📂 **Active Categories & Genres:**\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        for c in cats: text += f"🔹 {c['name']}\n"
        text += "\n✍️ **To register a new category, send its name below:**"
        user_state[message.from_user.id] = {"action": "ask_new_cat"}
        await message.reply(text)

    @bot.on_message(filters.command(["add_movie", "add_series"]) & filters.private)
    async def manual_add_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        m_type = "Movie" if "movie" in message.text else "TV Series"
        user_state[message.from_user.id] = {"action": "ask_title", "type": "movie" if m_type == "Movie" else "tv"}
        await message.reply(f"🎬 **Creating Manual Entry**\n\n✍️ Please send the **Title** of the new {m_type}:")

    @bot.on_message(filters.command("posttochannel", ["/", "$"]) & filters.private)
    async def post_to_channel_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        if len(message.command) < 3:
            return await message.reply("💡 Usage: `/posttochannel <channel_id> <link>`")

        arg1 = message.command[1]
        arg2 = message.command[2]

        if arg1.startswith("http"):
            link = arg1
            channel_id_str = arg2
        else:
            channel_id_str = arg1
            link = arg2

        slug = extract_slug(link)
        if not slug: return await message.reply("❌ Invalid Link. Must be from this website.")

        try:
            channel_id = int(channel_id_str)
        except ValueError:
            channel_id = channel_id_str

        msg = await message.reply("⏳ Fetching database metadata...")

        try:
            media = await db.get_media_by_slug(slug)
            if not media: return await msg.edit("❌ Media not found in database.")

            # Helper for Unicode Sans Bold
            def to_sans_bold(text):
                res = []
                for c in str(text):
                    code = ord(c)
                    if 65 <= code <= 90: res.append(chr(0x1D5D4 + (code - 65)))
                    elif 97 <= code <= 122: res.append(chr(0x1D5EE + (code - 97)))
                    elif 48 <= code <= 57: res.append(chr(0x1D7EC + (code - 48)))
                    else: res.append(c)
                return ''.join(res)

            # Format fields gracefully
            title = media.get('title') or 'N/A'
            year = media.get('year') or 'N/A'
            director = media.get('director') or 'N/A'

            raw_cast = media.get('cast')
            if isinstance(raw_cast, list) and raw_cast:
                cast = ", ".join(raw_cast)
            elif isinstance(raw_cast, str) and raw_cast and raw_cast != 'N/A':
                cast = raw_cast
            else:
                cast = 'N/A'

            raw_genres = media.get('genres')
            if isinstance(raw_genres, list) and raw_genres:
                genres = ", ".join(raw_genres)
            elif isinstance(raw_genres, str) and raw_genres and raw_genres != 'N/A':
                genres = raw_genres
            else:
                genres = 'N/A'

            score = media.get('score')
            score_str = f"⭐ {score} / 10" if score and score != 'N/A' else 'N/A'

            runtime = media.get('runtime') or 'N/A'
            synopsis = media.get('synopsis') or 'No description available.'
            image = media.get('image')

            # Build Telegram HTML structured card with blockquotes and clickable hyperlink
            import html
            safe_title = html.escape(title)
            safe_year = html.escape(str(year))
            safe_director = html.escape(director)
            safe_cast = html.escape(cast)
            safe_genres = html.escape(genres)
            safe_score = html.escape(str(score_str))
            safe_runtime = html.escape(str(runtime))
            safe_synopsis = html.escape(synopsis)
            safe_link = html.escape(link)

            sans_title = html.escape(to_sans_bold(title))

            # Blockquote block for metadata
            metadata_block = (
                f"🎬 <b>Title:</b> <b>{sans_title}</b>  📅 <b>Year:</b> <i>{safe_year}</i>\n"
                f"📝 <b>Director:</b> <i>{safe_director}</i>\n"
                f"🎭 <b>Cast:</b> <i>{safe_cast}</i>\n"
                f"📂 <b>Genres:</b> <i>{safe_genres}</i>\n"
                f"⭐ <b>Score:</b> <b>{safe_score}</b>\n"
                f"⏱ <b>Runtime:</b> <i>{safe_runtime}</i>"
            )

            caption = (
                f"<blockquote>{metadata_block}</blockquote>\n\n"
                f"<b><u>📝 Synopsis / Description:</u></b>\n"
                f"<blockquote>{safe_synopsis}</blockquote>\n\n"
                f"🍿 <b>Watch / Download Full Movie:</b>\n"
                f"👉 <a href=\"{safe_link}\">🎬 Watch {sans_title} Now</a>"
            )

            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🍿 Watch {title} On MoviesZoneFlix", url=link)]
            ])

            try:
                if image:
                    await client.send_photo(
                        channel_id,
                        image,
                        caption=caption,
                        parse_mode=enums.ParseMode.HTML,
                        reply_markup=reply_markup
                    )
                else:
                    await client.send_message(
                        channel_id,
                        caption,
                        parse_mode=enums.ParseMode.HTML,
                        reply_markup=reply_markup,
                        disable_web_page_preview=False
                    )
                await msg.edit(f"🚀 **Successfully posted premium card to channel:** `{channel_id}`")
            except Exception as e:
                await msg.edit(f"❌ **Telegram Error:** {str(e)}\n\n💡 *Make sure the bot is an admin in the channel and the ID is correct.*")

        except Exception as e:
            await msg.edit(f"❌ **Database Error:** {str(e)}")
            logger.error(traceback.format_exc())

    @bot.on_message(filters.command("uptime", ["/", "$"]) & filters.private)
    async def uptime_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        bots = await db.get_all_uptime_bots()

        text = (
            "⚡ **MoviesZoneFlix 24/7 Uptime Monitor Core** ⚡\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 **Monitored Services:** `{len(bots)}`\n"
            "⏱ **Monitoring Frequency:** `Every 1 second (24/7)`\n\n"
        )

        if not bots:
            text += "📂 *No bot/server URLs currently added for 24/7 monitoring.*"
        else:
            text += "🟢 **Active Uptime Targets:**\n"
            for i, b in enumerate(bots, 1):
                status_emoji = "🟢" if b.get("status") == "online" else "🟡" if b.get("status") == "degraded" else "🔴"
                text += f"{status_emoji} **{i}.** `{b.get('name', 'Bot')}`\n🌐 {b['url']}\n⚡ Status: `{b.get('status', 'checking').upper()}` • Latency: `{b.get('latency', 0)}ms`\n\n"

        buttons = [
            [InlineKeyboardButton("➕ Add Bot / Server URL", callback_data="upt_add")],
            [InlineKeyboardButton("📋 Manage / Replace / Delete", callback_data="upt_list_1"),
             InlineKeyboardButton("🔄 Refresh Status", callback_data="upt_refresh")]
        ]
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)

    @bot.on_message(filters.command("songs", ["/", "$"]) & filters.private)
    async def songs_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        songs = await db.get_all_songs()
        channel_id = await db.get_song_channel()
        channel_info = f"`{channel_id}`" if channel_id else "❌ *Not Configured*"

        text = (
            "🎵 **Background Music & Song Management Core**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📡 **Storage Channel:** {channel_info}\n"
            f"🎶 **Active Songs in Catalog:** `{len(songs)}`\n\n"
            "Choose an action below to manage website background songs:"
        )

        buttons = [
            [InlineKeyboardButton("➕ Add New Song", callback_data="song_add"),
             InlineKeyboardButton("📋 Manage/Delete Songs", callback_data="song_list_1")],
            [InlineKeyboardButton("📢 Configure Storage Channel", callback_data="song_set_channel")]
        ]
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_message(filters.command("addbot") & filters.private)
    async def addbot_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        user_state[message.from_user.id] = {"action": "ask_bot_token"}
        await message.reply(
            "🤖 **Add a Multi-Bot Listener**\n\n"
            "This command registers a new Telegram bot that will listen inside a specified group chat and automatically reply with movie page links whenever users ask for them.\n\n"
            "✍️ **Step 1:** Please send the **Bot Token**:"
        )

    @bot.on_message(filters.command("cancel") & filters.private)
    async def cancel_cmd(client, message):
        user_state.pop(message.from_user.id, None)
        await message.reply("✨ Action cancelled.")

    # --- Callbacks ---

    @bot.on_callback_query()
    async def bot_callbacks(client: Client, cb: CallbackQuery):
        if not await is_authorized(cb.from_user.id): return
        data = cb.data
        uid = cb.from_user.id

        if data.startswith("add_") and not (data.startswith("add_tmdb_") or data.startswith("add_tvmaze_") or data.startswith("add_omdb_")):
            parts = data.split("_")
            m_type = parts[1]
            m_id = parts[2]
            data = f"add_tmdb_{m_type}_{m_id}"

        if data.startswith("add_tmdb_"):
            parts = data.split("_")
            m_type = parts[2]
            m_id = parts[3]
            await cb.message.edit_text("⏳ Importing from TMDb...")
            try:
                details = await media_api.get_tmdb_details(m_type, m_id)
                if not details: return await cb.message.edit_text("❌ Failed to fetch TMDb details.")
                title = details.get("title") or details.get("name")
                slug = slugify(title)

                director = None
                cast = []
                runtime = None
                if details.get("runtime"):
                    runtime = f"{details['runtime']} min"
                elif details.get("episode_run_time") and len(details["episode_run_time"]) > 0:
                    runtime = f"{details['episode_run_time'][0]} min"

                # Parse credits from TMDb
                credits = details.get("credits") or {}
                crew = credits.get("crew") or []
                for member in crew:
                    if member.get("job") == "Director":
                        director = member.get("name")
                        break
                cast_members = credits.get("cast") or []
                cast = [c.get("name") for c in cast_members[:6] if c.get("name")]

                score = round(details.get("vote_average", 0), 1)
                year = (details.get("release_date") or details.get("first_air_date") or "")[:4]

                # Fallback to OMDb if director/cast/runtime missing
                if Config.OMDB_API_KEY and (not director or not cast or not runtime):
                    try:
                        omdb_data = await media_api.get_omdb_metadata(title, year)
                        if omdb_data and omdb_data.get("Response") == "True":
                            if not director and omdb_data.get("Director") and omdb_data["Director"] != "N/A":
                                director = omdb_data["Director"]
                            if not cast and omdb_data.get("Actors") and omdb_data["Actors"] != "N/A":
                                cast = [c.strip() for c in omdb_data["Actors"].split(",") if c.strip()]
                            if not runtime and omdb_data.get("Runtime") and omdb_data["Runtime"] != "N/A":
                                runtime = omdb_data["Runtime"]
                            if not score and omdb_data.get("imdbRating") and omdb_data["imdbRating"] != "N/A":
                                try: score = float(omdb_data["imdbRating"])
                                except: pass
                    except Exception as e:
                        logger.error(f"OMDb fallback error: {e}")

                media_doc = {
                    "id": f"tmdb_{m_id}", "tmdb_id": int(m_id), "title": title, "slug": slug,
                    "type": "movie" if m_type == "movie" else "tv",
                    "image": f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}" if details.get('poster_path') else None,
                    "backdrop": f"https://image.tmdb.org/t/p/original{details.get('backdrop_path')}" if details.get('backdrop_path') else None,
                    "synopsis": details.get("overview") or "",
                    "score": score,
                    "year": year or "N/A",
                    "genres": [g["name"] for g in details.get("genres", [])] if details.get("genres") else [],
                    "director": director or "N/A",
                    "cast": cast,
                    "runtime": runtime or "N/A",
                    "seasons_links": {}
                }
                await db.add_media(media_doc)
                added = await db.get_media_by_id(f"tmdb_{m_id}")
                final_slug = added["slug"] if added else slug
                await cb.message.edit_text(f"✅ Imported from TMDb: `{added['title'] if added else title}`\nURL: {Config.BASE_URL}/watch/{final_slug}")
            except Exception as e: await cb.message.edit_text(f"❌ Error: {e}")

        elif data.startswith("add_tvmaze_"):
            parts = data.split("_")
            m_id = parts[3]
            await cb.message.edit_text("⏳ Importing from TVmaze...")
            try:
                details = await media_api.get_tvmaze_details(m_id)
                if not details: return await cb.message.edit_text("❌ Failed to fetch TVmaze details.")
                title = details.get("name")
                slug = slugify(title)
                summary = details.get("summary") or ""
                summary = re.sub(r'<[^>]*>', '', summary)
                image_obj = details.get("image") or {}
                image_url = image_obj.get("original") or image_obj.get("medium")

                runtime = f"{details['runtime']} min" if details.get("runtime") else "N/A"
                score = details.get("rating", {}).get("average", 0) or 0.0
                year = (details.get("premiered") or "")[:4] or "N/A"

                cast = []
                if details.get("_embedded") and details["_embedded"].get("cast"):
                    cast = [c["person"]["name"] for c in details["_embedded"]["cast"][:6] if c.get("person")]

                media_doc = {
                    "id": f"tvmaze_{m_id}", "title": title, "slug": slug,
                    "type": "tv",
                    "image": image_url,
                    "synopsis": summary,
                    "score": score,
                    "year": year,
                    "genres": details.get("genres", []),
                    "director": "N/A",
                    "cast": cast,
                    "runtime": runtime,
                    "seasons_links": {}
                }
                await db.add_media(media_doc)
                added = await db.get_media_by_id(f"tvmaze_{m_id}")
                final_slug = added["slug"] if added else slug
                await cb.message.edit_text(f"✅ Imported from TVmaze: `{added['title'] if added else title}`\nURL: {Config.BASE_URL}/watch/{final_slug}")
            except Exception as e: await cb.message.edit_text(f"❌ Error: {e}")

        elif data.startswith("add_omdb_"):
            parts = data.split("_")
            m_type = parts[2]
            imdb_id = parts[3]
            await cb.message.edit_text("⏳ Importing from OMDb...")
            try:
                details = await media_api.get_omdb_metadata(title=None, imdb_id=imdb_id)
                if not details or details.get("Response") != "True":
                    return await cb.message.edit_text("❌ Failed to fetch OMDb details.")
                title = details.get("Title")
                slug = slugify(title)
                score = 0.0
                try:
                    score = float(details.get("imdbRating", 0.0))
                except: pass
                genres = [g.strip() for g in details.get("Genre", "").split(",") if g.strip() and g.strip() != "N/A"]
                cast = [c.strip() for c in details.get("Actors", "").split(",") if c.strip() and c.strip() != "N/A"]
                director = details.get("Director") if details.get("Director") != "N/A" else "N/A"
                runtime = details.get("Runtime") if details.get("Runtime") != "N/A" else "N/A"
                synopsis = details.get("Plot") if details.get("Plot") != "N/A" else ""
                year = details.get("Year")[:4] if details.get("Year") else "N/A"

                media_doc = {
                    "id": f"omdb_{imdb_id}", "title": title, "slug": slug,
                    "type": "movie" if m_type == "movie" else "tv",
                    "image": details.get("Poster") if details.get("Poster") != "N/A" else None,
                    "synopsis": synopsis,
                    "score": score,
                    "year": year,
                    "genres": genres,
                    "director": director,
                    "cast": cast,
                    "runtime": runtime,
                    "seasons_links": {}
                }
                await db.add_media(media_doc)
                added = await db.get_media_by_id(f"omdb_{imdb_id}")
                final_slug = added["slug"] if added else slug
                await cb.message.edit_text(f"✅ Imported from OMDb: `{added['title'] if added else title}`\nURL: {Config.BASE_URL}/watch/{final_slug}")
            except Exception as e: await cb.message.edit_text(f"❌ Error: {e}")

        elif data == "db_backup":
            await cb.message.edit_text("⏳ Generating backup...")
            try:
                data = await db.export_data()
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for name, docs in data.items():
                        zf.writestr(f"{name}.json", json.dumps(docs, indent=4, default=str))
                zip_buffer.seek(0)
                zip_buffer.name = "backup.zip"
                await cb.message.delete()
                await client.send_document(cb.message.chat.id, zip_buffer, file_name="backup.zip", caption="✅ **Database Backup Complete**")
            except Exception as e: await cb.message.edit_text(f"❌ Backup failed: {e}")

        elif data == "db_restore":
            user_state[uid] = {"action": "awaiting_restore_zip"}
            await cb.message.edit_text("📤 Please upload the `backup.zip` file.")

        elif data.startswith("et_movecat_"):
            slug = data.replace("et_movecat_", "")
            media = await db.get_media_by_slug(slug)
            cats = await db.get_all_categories()
            buttons = []
            row = []
            for c in cats:
                row.append(InlineKeyboardButton(f"📁 {c['name']}", callback_data=f"setcat_{slug}_{c['name']}"))
                if len(row) == 2:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
            buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"et_main_{slug}")])
            await cb.message.edit_text(
                f"📂 **Select Category for:** `{media['title']}`\n\n*Current Genres:* `{', '.join(media.get('genres', []))}`",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        elif data.startswith("setcat_"):
            parts = data.split("_", 2)
            slug = parts[1]
            cat_name = parts[2]
            await db.media.update_one({"slug": slug}, {"$set": {"genres": [cat_name], "admin_edited": True}})
            await cb.answer(f"✅ Category changed to {cat_name}!", show_alert=True)
            media = await db.get_media_by_slug(slug)
            buttons = [
                [InlineKeyboardButton("🖼 Poster", callback_data=f"et_poster_{slug}"),
                 InlineKeyboardButton("🏷 Title", callback_data=f"et_title_{slug}")],
                [InlineKeyboardButton("📅 Year", callback_data=f"et_year_{slug}"),
                 InlineKeyboardButton("📂 Genres", callback_data=f"et_genres_{slug}")],
                [InlineKeyboardButton("🎬 Director", callback_data=f"et_director_{slug}"),
                 InlineKeyboardButton("🎭 Cast", callback_data=f"et_cast_{slug}")],
                [InlineKeyboardButton("⭐ Score", callback_data=f"et_score_{slug}"),
                 InlineKeyboardButton("⏱ Runtime", callback_data=f"et_runtime_{slug}")],
                [InlineKeyboardButton("📺 Trailer", callback_data=f"et_trailer_{slug}"),
                 InlineKeyboardButton("📊 Status", callback_data=f"et_status_{slug}")],
                [InlineKeyboardButton("📝 Synopsis", callback_data=f"et_syno_{slug}"),
                 InlineKeyboardButton("🎥 Type", callback_data=f"et_type_{slug}")],
                [InlineKeyboardButton("📂 Change Category", callback_data=f"et_movecat_{slug}")],
                [InlineKeyboardButton("🗑 DELETE MEDIA", callback_data=f"confirm_del_{slug}")]
            ]
            await cb.message.edit_text(f"🛠 **Editing:** `{media['title']}`", reply_markup=InlineKeyboardMarkup(buttons))

        elif data.startswith("et_"):
            parts = data.split("_", 2)
            cmd, slug = parts[1], parts[2]
            back_btn = [[InlineKeyboardButton("⬅️ Back", callback_data=f"et_main_{slug}")]]
            if cmd == "poster":
                user_state[uid] = {"action": "ask_poster", "slug": slug}
                await cb.message.edit_text("🖼 Send **New Poster URL**:", reply_markup=InlineKeyboardMarkup(back_btn))
            elif cmd == "title":
                user_state[uid] = {"action": "ask_title_edit", "slug": slug}
                await cb.message.edit_text("🏷 Send **New Title**:", reply_markup=InlineKeyboardMarkup(back_btn))
            elif cmd == "syno":
                user_state[uid] = {"action": "ask_syno", "slug": slug}
                await cb.message.edit_text("📝 Send **New Synopsis**:", reply_markup=InlineKeyboardMarkup(back_btn))
            elif cmd == "year":
                user_state[uid] = {"action": "ask_year_edit", "slug": slug}
                await cb.message.edit_text("📅 Send **New Year**:", reply_markup=InlineKeyboardMarkup(back_btn))
            elif cmd == "genres":
                user_state[uid] = {"action": "ask_genres_edit", "slug": slug}
                await cb.message.edit_text("📂 Send **New Genres** (comma separated):", reply_markup=InlineKeyboardMarkup(back_btn))
            elif cmd == "director":
                user_state[uid] = {"action": "ask_director", "slug": slug}
                await cb.message.edit_text("🎬 Send **Director Name**:", reply_markup=InlineKeyboardMarkup(back_btn))
            elif cmd == "cast":
                user_state[uid] = {"action": "ask_cast", "slug": slug}
                await cb.message.edit_text("🎭 Send **Cast** (comma separated):", reply_markup=InlineKeyboardMarkup(back_btn))
            elif cmd == "score":
                user_state[uid] = {"action": "ask_score", "slug": slug}
                await cb.message.edit_text("⭐ Send **Score** (e.g. 8.5):", reply_markup=InlineKeyboardMarkup(back_btn))
            elif cmd == "runtime":
                user_state[uid] = {"action": "ask_runtime", "slug": slug}
                await cb.message.edit_text("⏱ Send **Runtime** (e.g. 120 min):", reply_markup=InlineKeyboardMarkup(back_btn))
            elif cmd == "trailer":
                user_state[uid] = {"action": "ask_trailer", "slug": slug}
                await cb.message.edit_text("📺 Send **Trailer URL**:", reply_markup=InlineKeyboardMarkup(back_btn))
            elif cmd == "status":
                user_state[uid] = {"action": "ask_status", "slug": slug}
                await cb.message.edit_text("📊 Send **Status** (e.g. Ongoing, Completed):", reply_markup=InlineKeyboardMarkup(back_btn))
            elif cmd == "type":
                user_state[uid] = {"action": "ask_type", "slug": slug}
                await cb.message.edit_text("🎥 Send **Type** (movie/tv):", reply_markup=InlineKeyboardMarkup(back_btn))
            elif cmd == "main":
                user_state.pop(uid, None)
                media = await db.get_media_by_slug(slug)
                buttons = [
                    [InlineKeyboardButton("🖼 Poster", callback_data=f"et_poster_{slug}"),
                     InlineKeyboardButton("🏷 Title", callback_data=f"et_title_{slug}")],
                    [InlineKeyboardButton("📅 Year", callback_data=f"et_year_{slug}"),
                     InlineKeyboardButton("📂 Genres", callback_data=f"et_genres_{slug}")],
                    [InlineKeyboardButton("🎬 Director", callback_data=f"et_director_{slug}"),
                     InlineKeyboardButton("🎭 Cast", callback_data=f"et_cast_{slug}")],
                    [InlineKeyboardButton("⭐ Score", callback_data=f"et_score_{slug}"),
                     InlineKeyboardButton("⏱ Runtime", callback_data=f"et_runtime_{slug}")],
                    [InlineKeyboardButton("📺 Trailer", callback_data=f"et_trailer_{slug}"),
                     InlineKeyboardButton("📊 Status", callback_data=f"et_status_{slug}")],
                    [InlineKeyboardButton("📝 Synopsis", callback_data=f"et_syno_{slug}"),
                     InlineKeyboardButton("🎥 Type", callback_data=f"et_type_{slug}")],
                    [InlineKeyboardButton("📂 Change Category", callback_data=f"et_movecat_{slug}")],
                    [InlineKeyboardButton("🗑 DELETE MEDIA", callback_data=f"confirm_del_{slug}")]
                ]
                await cb.message.edit_text(f"🛠 **Editing:** `{media['title']}`", reply_markup=InlineKeyboardMarkup(buttons))

        elif data.startswith("m_addg_"):
            slug = data.replace("m_addg_", "")
            user_state[uid] = {"action": "ask_groups_bulk", "slug": slug}
            back_btn = [[InlineKeyboardButton("⬅️ Back", callback_data=f"m_back_{slug}")]]

            prompt_text = (
                "Please send one or more groups with buttons in a single message in the following format:\n\n"
                "1. Group Name\n"
                "Button Name : Link\n"
                "Button Name : Link\n\n"
                "Example:\n"
                "1. Season 1\n"
                "480P : https://example.com/480p\n"
                "720P : https://example.com/720p\n"
                "1080P : https://example.com/1080p\n\n"
                "2. Season 2\n"
                "480P : https://example.com/480p\n"
                "720P : https://example.com/720p\n"
                "1080P : https://example.com/1080p\n\n"
                "⚠️ Format Notes:\n"
                "• Each group must start with a numbered line (e.g. 1. Season 1)\n"
                "• Button links must start with http:// or https:// admin can add unlimited groups using serial numbers"
            )
            await cb.message.edit_text(prompt_text, reply_markup=InlineKeyboardMarkup(back_btn))

        elif data.startswith("m_mgrg_"):
            parts = data.split("_")
            slug, gname = parts[2], "_".join(parts[3:])
            buttons = [
                [InlineKeyboardButton("🏷 Rename Group", callback_data=f"m_reng_{slug}_{gname}")],
                [InlineKeyboardButton("➕ Add/Update Links", callback_data=f"m_addl_{slug}_{gname}")],
                [InlineKeyboardButton("⬅️ Back", callback_data=f"m_back_{slug}")]
            ]
            await cb.message.edit_text(f"⚙️ **Managing Group:** `{gname}`", reply_markup=InlineKeyboardMarkup(buttons))

        elif data.startswith("m_reng_"):
            parts = data.split("_")
            slug, gname = parts[2], "_".join(parts[3:])
            user_state[uid] = {"action": "ask_regname", "slug": slug, "old_gname": gname}
            back_btn = [[InlineKeyboardButton("⬅️ Back", callback_data=f"m_mgrg_{slug}_{gname}")]]
            await cb.message.edit_text(f"📝 Send **New Name** for group `{gname}`:", reply_markup=InlineKeyboardMarkup(back_btn))

        elif data.startswith("m_addl_"):
            parts = data.split("_")
            slug, gname = parts[2], "_".join(parts[3:])
            user_state[uid] = {"action": "ask_btn_count", "slug": slug, "gname": gname}
            back_btn = [[InlineKeyboardButton("⬅️ Back", callback_data=f"m_mgrg_{slug}_{gname}")]]
            await cb.message.edit_text(f"🔢 How many buttons in group `{gname}`?", reply_markup=InlineKeyboardMarkup(back_btn))

        elif data.startswith("m_delg_"):
            parts = data.split("_")
            slug, gname = parts[2], "_".join(parts[3:])
            media = await db.get_media_by_slug(slug)
            links = media.get("seasons_links", {})
            if gname in links:
                del links[gname]
                await db.media.update_one({"slug": slug}, {"$set": {"seasons_links": links}})
                await cb.answer(f"🗑 Group {gname} deleted.")
                # Refresh UI
                buttons = [[InlineKeyboardButton("➕ Add New Group", callback_data=f"m_addg_{slug}")]]
                for gn in links.keys():
                    buttons.append([
                        InlineKeyboardButton(f"⚙️ {gn}", callback_data=f"m_mgrg_{slug}_{gn}"),
                        InlineKeyboardButton("🗑", callback_data=f"m_delg_{slug}_{gn}")
                    ])
                await cb.message.edit_text(f"🔗 **Servers:** `{media['title']}`", reply_markup=InlineKeyboardMarkup(buttons))

        elif data.startswith("m_back_"):
            slug = data.replace("m_back_", "")
            media = await db.get_media_by_slug(slug)
            buttons = [[InlineKeyboardButton("➕ Add New Group", callback_data=f"m_addg_{slug}")]]
            links = media.get("seasons_links", {})
            for gn in links.keys():
                buttons.append([
                    InlineKeyboardButton(f"⚙️ {gn}", callback_data=f"m_mgrg_{slug}_{gn}"),
                    InlineKeyboardButton("🗑", callback_data=f"m_delg_{slug}_{gn}")
                ])
            await cb.message.edit_text(f"🔗 **Servers:** `{media['title']}`", reply_markup=InlineKeyboardMarkup(buttons))

        elif data.startswith("execute_del_"):
            slug = data.replace("execute_del_", "")
            await db.delete_media_by_slug(slug)
            await cb.message.edit_text(f"🗑 **Deleted:** `{slug}` has been removed.")

        elif data.startswith("save_bulk_"):
            slug = data.replace("save_bulk_", "")
            state = user_state.get(uid)
            if not state or "parsed_groups" not in state:
                return await cb.answer("❌ Error: Session expired or invalid state.", show_alert=True)

            parsed_groups = state["parsed_groups"]
            media = await db.get_media_by_slug(slug)
            if not media:
                return await cb.message.edit_text("❌ Media not found.")

            links = media.get("seasons_links", {})
            if not isinstance(links, dict):
                links = {}

            # Merge/Update the new groups
            for gname, buttons in parsed_groups.items():
                links[gname] = buttons

            await db.media.update_one({"slug": slug}, {"$set": {"seasons_links": links}})
            user_state.pop(uid, None)

            # Show success and go back to server manager
            buttons = [[InlineKeyboardButton("➕ Add New Group", callback_data=f"m_addg_{slug}")]]
            for gn in links.keys():
                buttons.append([
                    InlineKeyboardButton(f"⚙️ {gn}", callback_data=f"m_mgrg_{slug}_{gn}"),
                    InlineKeyboardButton("🗑", callback_data=f"m_delg_{slug}_{gn}")
                ])
            await cb.message.edit_text(
                f"✅ **Bulk Groups Saved Successfully!**\n\nMedia: `{media['title']}`\n\nManage servers:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        elif data.startswith("srchp_"):
            parts = data.split("_")
            cache_id = parts[1]
            page = int(parts[2])
            cached = search_cache.get(cache_id)
            if not cached:
                return await cb.answer("❌ Search session expired. Please search again.", show_alert=True)
            text, markup = build_search_page(cache_id, cached, page=page)
            await cb.message.edit_text(text, reply_markup=markup)

        elif data == "noop":
            await cb.answer()

        elif data == "song_add":
            user_state[uid] = {"action": "ask_song_file"}
            back_btn = [[InlineKeyboardButton("⬅️ Back", callback_data="song_main")]]
            await cb.message.edit_text(
                "🎵 **Add New Background Song**\n\n"
                "✍️ Please send or forward an **audio file, MP3, document, or video** containing the song:",
                reply_markup=InlineKeyboardMarkup(back_btn)
            )

        elif data.startswith("song_list_"):
            page = int(data.split("_")[2])
            songs = await db.get_all_songs()
            if not songs:
                buttons = [[InlineKeyboardButton("➕ Add New Song", callback_data="song_add"),
                            InlineKeyboardButton("⬅️ Back", callback_data="song_main")]]
                return await cb.message.edit_text("📂 **No background songs available.**", reply_markup=InlineKeyboardMarkup(buttons))

            per_page = 5
            total_pages = max(1, (len(songs) + per_page - 1) // per_page)
            if page < 1: page = 1
            if page > total_pages: page = total_pages

            start_idx = (page - 1) * per_page
            items = songs[start_idx:start_idx + per_page]

            text = f"📋 **Manage Songs (Page {page}/{total_pages} • Total {len(songs)}):**\n\n"
            buttons = []
            for s in items:
                text += f"🎵 **{s.get('title', 'Song')}** (`{s['id']}`)\n"
                buttons.append([
                    InlineKeyboardButton(f"🔄 Replace {s.get('title', '')[:15]}", callback_data=f"song_repl_{s['id']}"),
                    InlineKeyboardButton("🗑 Delete", callback_data=f"song_del_{s['id']}")
                ])

            nav_row = []
            if page > 1: nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"song_list_{page - 1}"))
            nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))
            if page < total_pages: nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"song_list_{page + 1}"))

            if nav_row: buttons.append(nav_row)
            buttons.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="song_main")])

            await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

        elif data.startswith("song_del_"):
            song_id = data.replace("song_del_", "")
            song = await db.get_song_by_id(song_id)
            if song and song.get("filename"):
                file_p = os.path.join("static/songs", song["filename"])
                if os.path.exists(file_p):
                    try: os.remove(file_p)
                    except: pass
            await db.delete_song(song_id)
            await cb.answer("🗑 Song deleted successfully!", show_alert=True)
            # Reload list
            songs = await db.get_all_songs()
            if not songs:
                buttons = [[InlineKeyboardButton("➕ Add New Song", callback_data="song_add"),
                            InlineKeyboardButton("⬅️ Back", callback_data="song_main")]]
                return await cb.message.edit_text("📂 **No background songs available.**", reply_markup=InlineKeyboardMarkup(buttons))
            # Refresh list page 1
            cb.data = "song_list_1"
            await bot_callbacks(client, cb)

        elif data.startswith("song_repl_"):
            song_id = data.replace("song_repl_", "")
            user_state[uid] = {"action": "ask_replace_song_file", "replace_id": song_id}
            back_btn = [[InlineKeyboardButton("⬅️ Back", callback_data="song_list_1")]]
            await cb.message.edit_text(
                f"🔄 **Replace Song (`{song_id}`)**\n\n"
                "✍️ Please send or forward the new **audio file, MP3, document, or video** to replace this song:",
                reply_markup=InlineKeyboardMarkup(back_btn)
            )

        elif data == "song_set_channel":
            user_state[uid] = {"action": "ask_song_channel"}
            back_btn = [[InlineKeyboardButton("⬅️ Back", callback_data="song_main")]]
            await cb.message.edit_text(
                "📢 **Configure Song Storage Channel**\n\n"
                "✍️ Please send the **Channel ID** (e.g. `-1001234567890`) where songs will be stored & backed up:",
                reply_markup=InlineKeyboardMarkup(back_btn)
            )

        elif data == "upt_add":
            user_state[uid] = {"action": "ask_upt_url"}
            back_btn = [[InlineKeyboardButton("⬅️ Back", callback_data="upt_main")]]
            await cb.message.edit_text(
                "➕ **Add Bot / Server URL for 24/7 Uptime Monitoring**\n\n"
                "✍️ Please send the **URL** (e.g. `https://my-telegram-bot.onrender.com/ping` or `https://mybot.com`):",
                reply_markup=InlineKeyboardMarkup(back_btn)
            )

        elif data.startswith("upt_list_"):
            page = int(data.split("_")[2])
            bots = await db.get_all_uptime_bots()
            if not bots:
                buttons = [[InlineKeyboardButton("➕ Add Bot", callback_data="upt_add"),
                            InlineKeyboardButton("⬅️ Back", callback_data="upt_main")]]
                return await cb.message.edit_text("📂 **No monitored bots/servers available.**", reply_markup=InlineKeyboardMarkup(buttons))

            per_page = 5
            total_pages = max(1, (len(bots) + per_page - 1) // per_page)
            if page < 1: page = 1
            if page > total_pages: page = total_pages

            start_idx = (page - 1) * per_page
            items = bots[start_idx:start_idx + per_page]

            text = f"📋 **Manage Uptime Targets (Page {page}/{total_pages} • Total {len(bots)}):**\n\n"
            buttons = []
            for b in items:
                status_emoji = "🟢" if b.get("status") == "online" else "🔴"
                text += f"{status_emoji} **{b.get('name', 'Bot')}** (`{b['id']}`)\n🌐 {b['url']}\n\n"
                buttons.append([
                    InlineKeyboardButton(f"🔄 Replace {b.get('name', '')[:12]}", callback_data=f"upt_repl_{b['id']}"),
                    InlineKeyboardButton("🗑 Delete", callback_data=f"upt_del_{b['id']}")
                ])

            nav_row = []
            if page > 1: nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"upt_list_{page - 1}"))
            nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))
            if page < total_pages: nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"upt_list_{page + 1}"))

            if nav_row: buttons.append(nav_row)
            buttons.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="upt_main")])

            await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)

        elif data.startswith("upt_del_"):
            bot_id = data.replace("upt_del_", "")
            await db.delete_uptime_bot(bot_id)
            await cb.answer("🗑 Bot URL deleted from 24/7 monitor!", show_alert=True)
            bots = await db.get_all_uptime_bots()
            if not bots:
                buttons = [[InlineKeyboardButton("➕ Add Bot", callback_data="upt_add"),
                            InlineKeyboardButton("⬅️ Back", callback_data="upt_main")]]
                return await cb.message.edit_text("📂 **No monitored bots/servers available.**", reply_markup=InlineKeyboardMarkup(buttons))
            cb.data = "upt_list_1"
            await bot_callbacks(client, cb)

        elif data.startswith("upt_repl_"):
            bot_id = data.replace("upt_repl_", "")
            user_state[uid] = {"action": "ask_replace_upt_url", "replace_id": bot_id}
            back_btn = [[InlineKeyboardButton("⬅️ Back", callback_data="upt_list_1")]]
            await cb.message.edit_text(
                f"🔄 **Replace Bot URL (`{bot_id}`)**\n\n"
                "✍️ Please send the new **URL** to replace this bot target:",
                reply_markup=InlineKeyboardMarkup(back_btn)
            )

        elif data in ["upt_main", "upt_refresh"]:
            user_state.pop(uid, None)
            bots = await db.get_all_uptime_bots()

            text = (
                "⚡ **MoviesZoneFlix 24/7 Uptime Monitor Core** ⚡\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Monitored Services:** `{len(bots)}`\n"
                "⏱ **Monitoring Frequency:** `Every 1 second (24/7)`\n\n"
            )

            if not bots:
                text += "📂 *No bot/server URLs currently added for 24/7 monitoring.*"
            else:
                text += "🟢 **Active Uptime Targets:**\n"
                for i, b in enumerate(bots, 1):
                    status_emoji = "🟢" if b.get("status") == "online" else "🟡" if b.get("status") == "degraded" else "🔴"
                    text += f"{status_emoji} **{i}.** `{b.get('name', 'Bot')}`\n🌐 {b['url']}\n⚡ Status: `{b.get('status', 'checking').upper()}` • Latency: `{b.get('latency', 0)}ms`\n\n"

            buttons = [
                [InlineKeyboardButton("➕ Add Bot / Server URL", callback_data="upt_add")],
                [InlineKeyboardButton("📋 Manage / Replace / Delete", callback_data="upt_list_1"),
                 InlineKeyboardButton("🔄 Refresh Status", callback_data="upt_refresh")]
            ]
            await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)

        elif data == "song_main":
            user_state.pop(uid, None)
            songs = await db.get_all_songs()
            channel_id = await db.get_song_channel()
            channel_info = f"`{channel_id}`" if channel_id else "❌ *Not Configured*"

            text = (
                "🎵 **Background Music & Song Management Core**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📡 **Storage Channel:** {channel_info}\n"
                f"🎶 **Active Songs in Catalog:** `{len(songs)}`\n\n"
                "Choose an action below to manage website background songs:"
            )

            buttons = [
                [InlineKeyboardButton("➕ Add New Song", callback_data="song_add"),
                 InlineKeyboardButton("📋 Manage/Delete Songs", callback_data="song_list_1")],
                [InlineKeyboardButton("📢 Configure Storage Channel", callback_data="song_set_channel")]
            ]
            await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

        elif data == "cancel_op":
            user_state.pop(uid, None)
            await cb.message.edit_text("✨ Operation cancelled.")

    # --- Interaction Handler ---

    @bot.on_message(filters.private & (filters.text | filters.document | filters.audio | filters.video | filters.voice) & ~filters.command(["start", "ping", "help", "search", "edit", "edit_m", "save", "del", "categories", "add_movie", "add_series", "addbot", "songs", "cancel"]), group=1)
    async def interaction_msg(client, message):
        state = user_state.get(message.from_user.id)
        if not state: return
        uid = message.from_user.id
        action = state["action"]
        slug = state.get("slug")

        if action == "awaiting_restore_zip":
            if not message.document or not message.document.file_name.endswith(".zip"): return
            msg = await message.reply("⏳ Restoring...")
            path = await message.download()
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    with zipfile.ZipFile(path, 'r') as zip_ref:
                        zip_ref.extractall(tmp_dir)
                    restored_data = {}
                    for f in os.listdir(tmp_dir):
                        if f.endswith(".json"):
                            with open(os.path.join(tmp_dir, f), 'r') as j:
                                restored_data[f[:-5]] = json.load(j)
                    if await db.import_data(restored_data): await msg.edit("✅ **Database restored!**")
                    else: await msg.edit("❌ Restoration failed.")
            except Exception as e: await msg.edit(f"❌ Error: {e}")
            finally:
                if os.path.exists(path): os.remove(path)
                user_state.pop(uid, None)
            return

        if action == "ask_title":
            user_state[uid].update({"title": message.text, "action": "ask_year"})
            await message.reply("📅 Send Year:")
        elif action == "ask_year":
            user_state[uid].update({"year": message.text, "action": "ask_poster_man"})
            await message.reply("🖼 Send Poster URL:")
        elif action == "ask_poster_man":
            data = user_state[uid]
            slug = slugify(data["title"])
            await db.add_media({"id": f"man_{slug}", "title": data["title"], "slug": slug, "type": data["type"], "year": data["year"], "image": message.text, "seasons_links": {}})
            await message.reply(f"🚀 Published! {Config.BASE_URL}/watch/{slug}")
            user_state.pop(uid, None)
        elif action == "ask_poster":
            await db.media.update_one({"slug": slug}, {"$set": {"image": message.text.strip(), "admin_edited": True}})
            await message.reply("✅ Poster updated.")
            user_state.pop(uid, None)
        elif action == "ask_title_edit":
            nt = message.text.strip()
            media = await db.get_media_by_slug(slug)
            m_id = media.get("id") if media else None
            unique_title, unique_slug = await db.resolve_unique_title_and_slug(nt, media_id=m_id)
            await db.media.update_one({"slug": slug}, {"$set": {"title": unique_title, "slug": unique_slug, "admin_edited": True}})
            await message.reply(f"✅ Title updated to '{unique_title}'.")
            user_state.pop(uid, None)
        elif action == "ask_syno":
            await db.media.update_one({"slug": slug}, {"$set": {"synopsis": message.text.strip(), "admin_edited": True}})
            await message.reply("✅ Synopsis updated.")
            user_state.pop(uid, None)
        elif action == "ask_year_edit":
            await db.media.update_one({"slug": slug}, {"$set": {"year": message.text.strip(), "admin_edited": True}})
            await message.reply("✅ Year updated.")
            user_state.pop(uid, None)
        elif action == "ask_genres_edit":
            genres = [g.strip() for g in message.text.split(",") if g.strip()]
            await db.media.update_one({"slug": slug}, {"$set": {"genres": genres, "admin_edited": True}})
            await message.reply(f"✅ Genres updated: {', '.join(genres)}")
            user_state.pop(uid, None)
        elif action == "ask_director":
            await db.media.update_one({"slug": slug}, {"$set": {"director": message.text.strip(), "admin_edited": True}})
            await message.reply("✅ Director updated.")
            user_state.pop(uid, None)
        elif action == "ask_cast":
            cast = [c.strip() for c in message.text.split(",") if c.strip()]
            await db.media.update_one({"slug": slug}, {"$set": {"cast": cast, "admin_edited": True}})
            await message.reply("✅ Cast updated.")
            user_state.pop(uid, None)
        elif action == "ask_score":
            try:
                score = float(message.text.strip())
                await db.media.update_one({"slug": slug}, {"$set": {"score": score, "admin_edited": True}})
                await message.reply("✅ Score updated.")
            except:
                await message.reply("❌ Invalid score.")
            user_state.pop(uid, None)
        elif action == "ask_runtime":
            await db.media.update_one({"slug": slug}, {"$set": {"runtime": message.text.strip(), "admin_edited": True}})
            await message.reply("✅ Runtime updated.")
            user_state.pop(uid, None)
        elif action == "ask_trailer":
            await db.media.update_one({"slug": slug}, {"$set": {"trailer": message.text.strip(), "admin_edited": True}})
            await message.reply("✅ Trailer updated.")
            user_state.pop(uid, None)
        elif action == "ask_status":
            await db.media.update_one({"slug": slug}, {"$set": {"status": message.text.strip(), "admin_edited": True}})
            await message.reply("✅ Status updated.")
            user_state.pop(uid, None)
        elif action == "ask_type":
            mtype = message.text.strip().lower()
            if mtype in ["movie", "tv"]:
                await db.media.update_one({"slug": slug}, {"$set": {"type": mtype, "admin_edited": True}})
                await message.reply(f"✅ Type updated to {mtype}.")
            else:
                await message.reply("❌ Type must be 'movie' or 'tv'.")
            user_state.pop(uid, None)
        elif action == "ask_groups_bulk":
            parsed = parse_groups_message(message.text)
            if not parsed:
                error_text = (
                    "❌ **Invalid Format!** Please ensure you use the exact format below:\n\n"
                    "1. Group Name\n"
                    "Button Name : Link\n"
                    "Button Name : Link\n\n"
                    "Example:\n"
                    "1. Season 1\n"
                    "480P : https://example.com/480p\n"
                    "720P : https://example.com/720p\n"
                    "1080P : https://example.com/1080p\n\n"
                    "2. Season 2\n"
                    "480P : https://example.com/480p\n"
                    "720P : https://example.com/720p\n"
                    "1080P : https://example.com/1080p\n\n"
                    "⚠️ **Format Notes:**\n"
                    "• Each group must start with a numbered line (e.g. 1. Season 1)\n"
                    "• Button links must start with http:// or https://"
                )
                return await message.reply(error_text)

            # Show a beautiful preview of detected groups & buttons
            preview_text = "👀 **Preview of Detected Groups & Buttons:**\n\n"
            for gname, buttons in parsed.items():
                preview_text += f"📦 **{gname}**\n"
                for bname, blink in buttons.items():
                    preview_text += f" ├ 🏷 {bname}: {blink}\n"
                preview_text += "\n"

            # Store in state
            user_state[uid]["parsed_groups"] = parsed

            inline_buttons = [
                [
                    InlineKeyboardButton("✅ Confirm & Save", callback_data=f"save_bulk_{slug}"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_op")
                ]
            ]
            await message.reply(preview_text, reply_markup=InlineKeyboardMarkup(inline_buttons))
        elif action == "ask_regname":
            new_gname = message.text.strip()
            old_gname = state["old_gname"]
            media = await db.get_media_by_slug(slug)
            links = media.get("seasons_links", {})
            if old_gname in links:
                links[new_gname] = links.pop(old_gname)
                await db.media.update_one({"slug": slug}, {"$set": {"seasons_links": links}})
                await message.reply(f"✅ Group renamed to `{new_gname}`")
            user_state.pop(uid, None)
        elif action == "ask_btn_count":
            try:
                count = int(message.text.strip())
                user_state[uid].update({"btn_count": count, "current_btn": 1, "new_links": {}, "action": "ask_btn_name"})
                await message.reply(f"🏷 Send Name for Button 1:")
            except:
                await message.reply("❌ Send a valid number.")
        elif action == "ask_btn_name":
            user_state[uid]["temp_btn_name"] = message.text.strip()
            user_state[uid]["action"] = "ask_btn_link"
            await message.reply(f"🔗 Send Link for `{message.text}`:")
        elif action == "ask_btn_link":
            name = state["temp_btn_name"]
            link = message.text.strip()
            user_state[uid]["new_links"][name] = link

            if state["current_btn"] < state["btn_count"]:
                user_state[uid]["current_btn"] += 1
                user_state[uid]["action"] = "ask_btn_name"
                await message.reply(f"🏷 Send Name for Button {user_state[uid]['current_btn']}:")
            else:
                media = await db.get_media_by_slug(slug)
                links = media.get("seasons_links", {})
                links[state["gname"]] = user_state[uid]["new_links"]
                await db.media.update_one({"slug": slug}, {"$set": {"seasons_links": links}})
                await message.reply(f"✅ Group `{state['gname']}` updated with {state['btn_count']} buttons.")
                user_state.pop(uid, None)
        elif action == "ask_new_cat":
            await db.add_category(message.text.strip())
            await message.reply(f"✅ Category `{message.text}` added.")
            user_state.pop(uid, None)
        elif action == "ask_bot_token":
            token = message.text.strip()
            if not re.match(r"^\d+:[A-Za-z0-9_-]{35,}$", token):
                return await message.reply("❌ **Invalid Bot Token!** Please send a valid Telegram bot token (e.g., `123456:ABC-DEF1234ghIkl-zyx57W2v1u1`).")
            user_state[uid].update({"bot_token": token, "action": "ask_group_id"})
            await message.reply(
                "👥 **Configure Target Group Chat**\n\n"
                "✍️ **Step 2:** Please send the **Group ID** (e.g., `-1002345678901`) where this bot will listen and reply to user requests:"
            )
        elif action == "ask_group_id":
            group_id = message.text.strip()
            token = state["bot_token"]
            await db.bots.update_one({"token": token}, {"$set": {"token": token, "group_id": group_id}}, upsert=True)
            from bot.bot_manager import multibot_manager
            asyncio.create_task(multibot_manager.start_bot(token, group_id))
            await message.reply(
                "🚀 **Multi-Bot Configured and Live!**\n\n"
                f"🔹 **Bot Token:** `{token}`\n"
                f"🔹 **Target Group:** `{group_id}`\n\n"
                "The bot is now active and will reply with MoviesZoneFlix page links inside the group."
            )
            user_state.pop(uid, None)

        elif action in ["ask_upt_url", "ask_replace_upt_url"]:
            url = message.text.strip()
            if not (url.startswith("http://") or url.startswith("https://")):
                return await message.reply("❌ Invalid URL! Must start with `http://` or `https://`.")

            from urllib.parse import urlparse
            parsed = urlparse(url)
            name = parsed.netloc or url[:20]

            import uuid, time
            bot_id = state.get("replace_id") or str(uuid.uuid4())[:8]
            bot_doc = {
                "id": bot_id,
                "name": name,
                "url": url,
                "status": "checking",
                "latency": 0,
                "created_at": time.time()
            }
            await db.add_uptime_bot(bot_doc)
            await message.reply(f"🚀 **Bot / Server URL Saved for 24/7 Monitoring!**\n\n🔹 **Name:** `{name}`\n🔹 **URL:** {url}\n⚡ Monitoring active every 1 second.")
            user_state.pop(uid, None)

        elif action in ["ask_song_file", "ask_replace_song_file"]:
            media_obj = message.audio or message.document or message.video or message.voice
            if not media_obj:
                return await message.reply("❌ Please send or forward an **audio, MP3 document, or video** file.")

            msg = await message.reply("⏳ **Downloading and saving song file...**")
            import uuid, time
            ext = ".mp3"
            file_name = getattr(media_obj, "file_name", None)
            title = getattr(media_obj, "title", None) or getattr(media_obj, "file_name", None) or "Background Song"
            if file_name and "." in file_name:
                ext = f".{file_name.rsplit('.', 1)[-1].lower()}"

            song_id = state.get("replace_id") or str(uuid.uuid4())[:8]
            saved_filename = f"{song_id}{ext}"
            os.makedirs("static/songs", exist_ok=True)
            dest_path = os.path.join("static/songs", saved_filename)

            try:
                await client.download_media(message, file_name=dest_path)
                song_url = f"{Config.BASE_URL}/api/songs/file/{saved_filename}"

                song_doc = {
                    "id": song_id,
                    "title": title,
                    "filename": saved_filename,
                    "url": song_url,
                    "created_at": time.time()
                }

                # Forward / Upload to dedicated song channel if configured
                song_channel = await db.get_song_channel()
                if song_channel:
                    try:
                        chan_id = int(song_channel) if song_channel.startswith("-") or song_channel.isdigit() else song_channel
                        fwd_msg = await client.send_document(
                            chan_id,
                            dest_path,
                            caption=f"🎵 **MoviesZoneFlix Song Backup**\n\n🔹 **Title:** `{title}`\n🔹 **Song ID:** `{song_id}`\n🌐 **URL:** {song_url}"
                        )
                        if fwd_msg:
                            song_doc["channel_message_id"] = fwd_msg.id
                    except Exception as ce:
                        logger.error(f"Failed to post song to channel {song_channel}: {ce}")

                await db.add_song(song_doc)
                await msg.edit(f"✅ **Song Successfully Saved & Set for Website Background Playback!**\n\n🎵 **Title:** `{title}`\n🆔 **ID:** `{song_id}`\n🌐 **File URL:** {song_url}")
            except Exception as e:
                logger.error(f"Song download error: {e}")
                await msg.edit(f"❌ **Failed to download song file:** {e}")
            finally:
                user_state.pop(uid, None)

        elif action == "ask_song_channel":
            cid = message.text.strip()
            await db.set_song_channel(cid)
            await message.reply(f"🚀 **Song Storage Channel Configured:** `{cid}`")
            user_state.pop(uid, None)

async def set_commands(client: Client):
    try:
        await client.set_bot_commands([
            BotCommand("start", "Start Bot"),
            BotCommand("search", "Import from TMDB"),
            BotCommand("edit", "Edit Metadata"),
            BotCommand("edit_m", "Manage Servers"),
            BotCommand("del", "Delete Content"),
            BotCommand("save", "Backup/Restore"),
            BotCommand("posttochannel", "Post link to channel"),
            BotCommand("categories", "Manage Genres"),
            BotCommand("addbot", "Add a Multi-Bot listener"),
            BotCommand("songs", "Manage Background Songs"),
            BotCommand("uptime", "24/7 Uptime Monitor"),
            BotCommand("cancel", "Cancel Process")
        ])
    except: pass
