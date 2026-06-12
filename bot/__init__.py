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
import aiohttp
from bs4 import BeautifulSoup

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
    if "/watch/" in text:
        try:
            return text.split("/watch/")[1].split("?")[0].split("/")[0].strip()
        except: return None
    return text

def register_handlers(bot: Client):
    logger.info("Registering bot handlers...")

    @bot.on_message(filters.all, group=-100)
    async def log_updates(client, message):
        raise ContinuePropagation

    @bot.on_message(filters.command("start") & filters.private)
    async def start_cmd(client, message):
        await message.reply_text(
            "🎬 **MoviesZoneFlix Management Bot**\n\n"
            "Admin Commands:\n"
            "• `/search <query>` — Import from TMDB\n"
            "• `/edit <url/slug>` — Edit metadata/poster\n"
            "• `/edit_m <url/slug>` — Manage servers/links\n"
            "• `/add_movie` — Manual Movie\n"
            "• `/add_series` — Manual Series\n"
            "• `/del <url/slug>` — Delete content\n"
            "• `/save` — Backup/Restore Database\n"
            "• `/posttochannel <id> <link>` — Post to channel\n"
            "• `/categories` — Manage Genres\n"
            "• `/ping` — Status Check"
        )

    @bot.on_message(filters.command("ping") & filters.private)
    async def ping_cmd(client, message):
        await message.reply_text("🏓 **Pong!** Bot is online and responsive.")

    @bot.on_message(filters.command("search") & filters.private)
    async def search_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        query = " ".join(message.command[1:])
        if not query: return await message.reply("Usage: `/search <name>`")
        msg = await message.reply("🔍 Searching TMDB...")
        try:
            results = await media_api.search_tmdb(query)
            if not results: return await msg.edit("😔 No matches found.")
            text = "🎯 **Select Media to Import:**\n\n"
            buttons = []
            for i, res in enumerate(results[:8], 1):
                text += f"**{i}.** {res['title']} ({res['year']}) `[{res['type'].upper()}]`\n"
                buttons.append([InlineKeyboardButton(f"Import {i}", callback_data=f"add_{res['type']}_{res['id']}")])
            await msg.edit(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e: await msg.edit(f"❌ Error: {e}")

    @bot.on_message(filters.command("edit") & filters.private)
    async def edit_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        query = " ".join(message.command[1:])
        slug = extract_slug(query)
        if not slug: return await message.reply("💡 Usage: `/edit <url/slug>`")
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
            [InlineKeyboardButton("🗑 DELETE MEDIA", callback_data=f"confirm_del_{slug}")]
        ]
        await message.reply_text(f"🛠 **Editing:** `{media['title']}`", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_message(filters.command("edit_m") & filters.private)
    async def edit_m_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        query = " ".join(message.command[1:])
        slug = extract_slug(query)
        if not slug: return await message.reply("💡 Usage: `/edit_m <url/slug>`")
        media = await db.get_media_by_slug(slug)
        if not media: return await message.reply("❌ Not found.")
        buttons = [[InlineKeyboardButton("➕ Add New Group", callback_data=f"m_addg_{slug}")]]
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
        slug = extract_slug(query)
        if not slug: return await message.reply("💡 Usage: `/del <url/slug>`")
        media = await db.get_media_by_slug(slug)
        if not media: return await message.reply("❌ Not found.")
        buttons = [[InlineKeyboardButton("🔥 PURGE IT", callback_data=f"execute_del_{slug}"), InlineKeyboardButton("🛡 ABORT", callback_data="cancel_op")]]
        await message.reply(f"⚠️ **Confirm Delete:** `{media['title']}`?", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_message(filters.command("save") & filters.private)
    async def save_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        buttons = [
            [InlineKeyboardButton("📥 BACKUP", callback_data="db_backup"),
             InlineKeyboardButton("📤 RESTORE", callback_data="db_restore")]
        ]
        await message.reply_text("💾 **Database Management**", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_message(filters.command("categories") & filters.private)
    async def categories_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        cats = await db.get_all_categories()
        text = "📂 **Current Categories:**\n\n"
        for c in cats: text += f"• {c['name']}\n"
        text += "\nTo add a category, just send the name below:"
        user_state[message.from_user.id] = {"action": "ask_new_cat"}
        await message.reply(text)

    @bot.on_message(filters.command(["add_movie", "add_series"]) & filters.private)
    async def manual_add_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        m_type = "movie" if "movie" in message.text else "tv"
        user_state[message.from_user.id] = {"action": "ask_title", "type": m_type}
        await message.reply(f"📝 Send **Title** for the {m_type}:")

    @bot.on_message(filters.command("posttochannel", ["/", "$"]) & filters.private)
    async def post_to_channel_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        if len(message.command) < 3:
            return await message.reply("💡 Usage: `/posttochannel <channel_id> <link>`")

        channel_id_str = message.command[1]
        link = message.command[2]

        try:
            channel_id = int(channel_id_str)
        except ValueError:
            channel_id = channel_id_str
        msg = await message.reply("⏳ Fetching metadata...")

        try:
            async with aiohttp.ClientSession(headers={"User-Agent": "MoviesZoneFlix/1.0"}) as session:
                async with session.get(link, timeout=15, ssl=False) as resp:
                    if resp.status != 200:
                        return await msg.edit(f"❌ Error: Status code {resp.status}")
                    html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")

            def get_meta(property_name):
                tag = soup.find("meta", property=property_name) or soup.find("meta", attrs={"name": property_name})
                return tag.get("content") if tag else None

            title = get_meta("og:title") or soup.title.string if soup.title else "N/A"
            image_raw = get_meta("og:image")
            image = urljoin(link, image_raw) if image_raw else None
            description = get_meta("og:description") or "No description available."

            # Try to extract year and language from metadata or content
            # These are usually in custom meta tags or within the title
            year = "N/A"
            language = "N/A"

            # Simple heuristic for year (4 digits in title)
            year_match = re.search(r"\((\d{4})\)", title) or re.search(r"\b(19|20)\d{2}\b", title)
            if year_match:
                year = year_match.group(0).strip("()")

            # Check for language in title or specific meta
            for lang in ["Hindi", "English", "Tamil", "Telugu", "Malayalam", "Kannada", "Bengali"]:
                if lang.lower() in title.lower():
                    language = lang
                    break

            caption = (
                f"🎬 **Title:** {title}\n"
                f"📅 **Year:** {year}\n"
                f"🌐 **Language:** {language}\n\n"
                f"📝 **Description:**\n{description}\n\n"
                f"🔗 **Watch Now:**\n{link}\n\n"
                f"━━━━━━━━━━━━━━\n"
                f"⚡ **Posted via Auto Bot (Image + Caption)**"
            )

            try:
                if image:
                    try:
                        await client.send_photo(channel_id, image, caption=caption)
                    except Exception as pe:
                        logger.warning(f"send_photo failed: {pe}")
                        await client.send_message(channel_id, caption)
                else:
                    await client.send_message(channel_id, caption)

                await msg.edit(f"🚀 **Successfully posted to channel:** `{channel_id}`")
            except Exception as e:
                await msg.edit(f"❌ **Telegram Error:** {str(e)}\n\n💡 *Make sure the bot is an admin in the channel and the ID is correct.*")

        except Exception as e:
            await msg.edit(f"❌ **Scraping Error:** {str(e)}")
            logger.error(traceback.format_exc())

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

        if data.startswith("add_"):
            _, m_type, m_id = data.split("_")
            await cb.message.edit_text("⏳ Importing metadata...")
            try:
                details = await media_api.get_tmdb_details(m_type, m_id)
                if not details: return await cb.message.edit_text("❌ Failed.")
                title = details.get("title") or details.get("name")
                slug = slugify(title)
                await db.add_media({
                    "id": str(m_id), "tmdb_id": int(m_id), "title": title, "slug": slug,
                    "type": "movie" if m_type == "movie" else "tv",
                    "image": f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}",
                    "backdrop": f"https://image.tmdb.org/t/p/original{details.get('backdrop_path')}",
                    "synopsis": details.get("overview"), "score": details.get("vote_average", 0),
                    "year": (details.get("release_date") or details.get("first_air_date") or "0000")[:4],
                    "genres": [g["name"] for g in details.get("genres", [])], "seasons_links": {}
                })
                await cb.message.edit_text(f"✅ Imported: `{title}`\nURL: {Config.BASE_URL}/watch/{slug}")
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
                    [InlineKeyboardButton("🗑 DELETE MEDIA", callback_data=f"confirm_del_{slug}")]
                ]
                await cb.message.edit_text(f"🛠 **Editing:** `{media['title']}`", reply_markup=InlineKeyboardMarkup(buttons))

        elif data.startswith("m_addg_"):
            slug = data.replace("m_addg_", "")
            user_state[uid] = {"action": "ask_gname", "slug": slug}
            back_btn = [[InlineKeyboardButton("⬅️ Back", callback_data=f"m_back_{slug}")]]
            await cb.message.edit_text("📦 Send **Group Name** (e.g. 1080p, Season 1):", reply_markup=InlineKeyboardMarkup(back_btn))

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

        elif data == "cancel_op":
            user_state.pop(uid, None)
            await cb.message.edit_text("✨ Operation cancelled.")

    # --- Interaction Handler ---

    @bot.on_message(filters.private & (filters.text | filters.document) & ~filters.command(["start", "ping", "help", "search", "edit", "edit_m", "save", "del", "categories", "add_movie", "add_series", "cancel"]), group=1)
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
            await db.media.update_one({"slug": slug}, {"$set": {"image": message.text.strip()}})
            await message.reply("✅ Poster updated.")
            user_state.pop(uid, None)
        elif action == "ask_title_edit":
            nt = message.text.strip()
            ns = slugify(nt)
            await db.media.update_one({"slug": slug}, {"$set": {"title": nt, "slug": ns}})
            await message.reply(f"✅ Title updated.")
            user_state.pop(uid, None)
        elif action == "ask_syno":
            await db.media.update_one({"slug": slug}, {"$set": {"synopsis": message.text.strip()}})
            await message.reply("✅ Synopsis updated.")
            user_state.pop(uid, None)
        elif action == "ask_year_edit":
            await db.media.update_one({"slug": slug}, {"$set": {"year": message.text.strip()}})
            await message.reply("✅ Year updated.")
            user_state.pop(uid, None)
        elif action == "ask_genres_edit":
            genres = [g.strip() for g in message.text.split(",") if g.strip()]
            await db.media.update_one({"slug": slug}, {"$set": {"genres": genres}})
            await message.reply(f"✅ Genres updated: {', '.join(genres)}")
            user_state.pop(uid, None)
        elif action == "ask_director":
            await db.media.update_one({"slug": slug}, {"$set": {"director": message.text.strip()}})
            await message.reply("✅ Director updated.")
            user_state.pop(uid, None)
        elif action == "ask_cast":
            cast = [c.strip() for c in message.text.split(",") if c.strip()]
            await db.media.update_one({"slug": slug}, {"$set": {"cast": cast}})
            await message.reply("✅ Cast updated.")
            user_state.pop(uid, None)
        elif action == "ask_score":
            try:
                score = float(message.text.strip())
                await db.media.update_one({"slug": slug}, {"$set": {"score": score}})
                await message.reply("✅ Score updated.")
            except:
                await message.reply("❌ Invalid score.")
            user_state.pop(uid, None)
        elif action == "ask_runtime":
            await db.media.update_one({"slug": slug}, {"$set": {"runtime": message.text.strip()}})
            await message.reply("✅ Runtime updated.")
            user_state.pop(uid, None)
        elif action == "ask_trailer":
            await db.media.update_one({"slug": slug}, {"$set": {"trailer": message.text.strip()}})
            await message.reply("✅ Trailer updated.")
            user_state.pop(uid, None)
        elif action == "ask_status":
            await db.media.update_one({"slug": slug}, {"$set": {"status": message.text.strip()}})
            await message.reply("✅ Status updated.")
            user_state.pop(uid, None)
        elif action == "ask_type":
            mtype = message.text.strip().lower()
            if mtype in ["movie", "tv"]:
                await db.media.update_one({"slug": slug}, {"$set": {"type": mtype}})
                await message.reply(f"✅ Type updated to {mtype}.")
            else:
                await message.reply("❌ Type must be 'movie' or 'tv'.")
            user_state.pop(uid, None)
        elif action == "ask_gname":
            user_state[uid].update({"gname": message.text.strip(), "action": "ask_btn_count"})
            await message.reply(f"🔢 How many buttons in group `{message.text}`?")
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
            BotCommand("cancel", "Cancel Process")
        ])
    except: pass
