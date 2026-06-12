import asyncio
import logging
import os
import json
import zipfile
import tempfile
import traceback
from io import BytesIO
from pyrogram import Client, filters, enums, ContinuePropagation
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, CallbackQuery
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
        # logger.info(f"Update: {message.chat.id} | {message.from_user.id if message.from_user else 'NoUser'} | {message.text or 'Media'}")
        raise ContinuePropagation

    @bot.on_message(filters.command("start") & filters.private)
    async def start_cmd(client, message):
        await message.reply_text(
            "🎬 **MovieOTT Management Bot**\n\n"
            "Bot is active and ready.\n\n"
            "Admin Commands:\n"
            "• `/search <query>` - Import from TMDB\n"
            "• `/edit <url/slug>` - Edit metadata/poster\n"
            "• `/edit_m <url/slug>` - Manage server groups\n"
            "• `/add_movie` - Manual Movie\n"
            "• `/add_series` - Manual Series\n"
            "• `/save` - Backup/Restore DB\n"
            "• `/ping` - Status Check"
        )

    @bot.on_message(filters.command("ping") & filters.private)
    async def ping_cmd(client, message):
        await message.reply_text("🏓 **Pong!** Bot is alive and responsive.")

    @bot.on_message(filters.command("help") & filters.private)
    async def help_cmd(client, message):
        await message.reply_text(
            "🛠 **Admin Information**\n\n"
            "• Use `/search <name>` to find media on TMDB.\n"
            "• `/edit <URL>`: Change metadata of existing content.\n"
            "• `/edit_m <URL>`: Manage servers/links for content.\n"
            "• `/save`: Create a backup or restore from ZIP."
        )

    @bot.on_message(filters.command("search") & filters.private)
    async def search_cmd(client, message):
        if not await is_authorized(message.from_user.id):
            return await message.reply("🚫 Unauthorized.")

        query = " ".join(message.command[1:])
        if not query:
            return await message.reply("Usage: `/search <name>`")

        msg = await message.reply("🔍 Searching TMDB...")
        try:
            results = await media_api.search_tmdb(query)
            if not results:
                return await msg.edit("No results found.")

            text = "🎯 **Select Media to Import:**\n\n"
            buttons = []
            for i, res in enumerate(results[:8], 1):
                text += f"**{i}.** {res['title']} ({res['year']}) `[{res['type'].upper()}]`\n"
                buttons.append([InlineKeyboardButton(f"Import {i}", callback_data=f"add_{res['type']}_{res['id']}")])

            await msg.edit(text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            await msg.edit(f"Error: {e}")

    @bot.on_message(filters.command("edit") & filters.private)
    async def edit_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        query = " ".join(message.command[1:])
        slug = extract_slug(query)
        if not slug: return await message.reply("Usage: `/edit <url/slug>`")

        media = await db.get_media_by_slug(slug)
        if not media: return await message.reply("❌ Not found.")

        buttons = [
            [InlineKeyboardButton("🖼 Change Poster", callback_data=f"et_poster_{slug}")],
            [InlineKeyboardButton("🏷 Change Title", callback_data=f"et_title_{slug}")],
            [InlineKeyboardButton("📝 Change Synopsis", callback_data=f"et_syno_{slug}")],
            [InlineKeyboardButton("🗑 Delete Media", callback_data=f"confirm_del_{slug}")]
        ]
        await message.reply_text(f"🛠 **Editing:** `{media['title']}`", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_message(filters.command("edit_m") & filters.private)
    async def edit_m_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        query = " ".join(message.command[1:])
        slug = extract_slug(query)
        if not slug: return await message.reply("Usage: `/edit_m <url/slug>`")

        media = await db.get_media_by_slug(slug)
        if not media: return await message.reply("❌ Not found.")

        buttons = [[InlineKeyboardButton("➕ Add Server Group", callback_data=f"m_addg_{slug}")]]
        for gname in media.get("seasons_links", {}).keys():
            buttons.append([
                InlineKeyboardButton(f"⚙️ {gname}", callback_data=f"m_mgrg_{slug}_{gname}"),
                InlineKeyboardButton("🗑", callback_data=f"m_delg_{slug}_{gname}")
            ])

        await message.reply_text(f"🔗 **Servers:** `{media['title']}`", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_message(filters.command("save") & filters.private)
    async def save_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        buttons = [
            [InlineKeyboardButton("📥 BACKUP", callback_data="db_backup"),
             InlineKeyboardButton("📤 RESTORE", callback_data="db_restore")]
        ]
        await message.reply_text("💾 **Database Management**", reply_markup=InlineKeyboardMarkup(buttons))

    @bot.on_message(filters.command(["add_movie", "add_series"]) & filters.private)
    async def manual_add_cmd(client, message):
        if not await is_authorized(message.from_user.id): return
        m_type = "movie" if "movie" in message.text else "tv"
        user_state[message.from_user.id] = {"action": "ask_title", "type": m_type}
        await message.reply(f"📝 Send **Title** for the {m_type}:")

    @bot.on_message(filters.command("cancel") & filters.private)
    async def cancel_cmd(client, message):
        user_state.pop(message.from_user.id, None)
        await message.reply("✨ Action cancelled.")

    # --- Callbacks ---

    @bot.on_callback_query(filters.regex(r"^add_"))
    async def add_cb(client, cb: CallbackQuery):
        if not await is_authorized(cb.from_user.id): return
        _, m_type, m_id = cb.data.split("_")
        await cb.message.edit_text("⏳ Importing metadata...")
        try:
            details = await media_api.get_tmdb_details(m_type, m_id)
            if not details: return await cb.message.edit_text("Failed.")
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
            await cb.message.edit_text(f"✅ Imported: `{title}`\n{Config.BASE_URL}/watch/{slug}")
        except Exception as e:
            await cb.message.edit_text(f"Error: {e}")

    @bot.on_callback_query(filters.regex(r"^db_"))
    async def db_cb(client, cb: CallbackQuery):
        if not await is_authorized(cb.from_user.id): return
        if cb.data == "db_backup":
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
                await client.send_document(cb.message.chat.id, zip_buffer, file_name="backup.zip", caption="✅ Database Backup")
            except Exception as e:
                await cb.message.edit_text(f"❌ Backup failed: {e}")
        elif cb.data == "db_restore":
            user_state[cb.from_user.id] = {"action": "awaiting_restore_zip"}
            await cb.message.edit_text("📤 Upload the `backup.zip` file.")

    @bot.on_callback_query(filters.regex(r"^et_"))
    async def et_cb(client, cb: CallbackQuery):
        if not await is_authorized(cb.from_user.id): return
        parts = cb.data.split("_", 2)
        cmd, slug = parts[1], parts[2]
        if cmd == "poster":
            user_state[cb.from_user.id] = {"action": "ask_poster", "slug": slug}
            await cb.message.edit_text("🖼 Send **New Poster URL**:")
        elif cmd == "title":
            user_state[cb.from_user.id] = {"action": "ask_title_edit", "slug": slug}
            await cb.message.edit_text("🏷 Send **New Title**:")
        elif cmd == "syno":
            user_state[cb.from_user.id] = {"action": "ask_syno", "slug": slug}
            await cb.message.edit_text("📝 Send **New Synopsis**:")

    @bot.on_callback_query(filters.regex(r"^m_addg_"))
    async def m_addg_cb(client, cb: CallbackQuery):
        if not await is_authorized(cb.from_user.id): return
        slug = cb.data.replace("m_addg_", "")
        user_state[cb.from_user.id] = {"action": "ask_gname", "slug": slug}
        await cb.message.edit_text("📦 Send **Group Name** (e.g. 1080p, Season 1):")

    @bot.on_callback_query(filters.regex(r"^execute_del_"))
    async def exec_del_cb(client, cb: CallbackQuery):
        if not await is_authorized(cb.from_user.id): return
        slug = cb.data.replace("execute_del_", "")
        await db.delete_media_by_slug(slug)
        await cb.message.edit_text(f"🗑 Deleted `{slug}`")

    # --- Interaction Handler ---

    @bot.on_message(filters.private & (filters.text | filters.document) & ~filters.command(["start", "ping", "help", "search", "edit", "edit_m", "save", "add_movie", "add_series", "cancel"]), group=1)
    async def interaction_msg(client, message):
        state = user_state.get(message.from_user.id)
        if not state: return

        uid = message.from_user.id
        action = state["action"]
        slug = state.get("slug")

        if action == "awaiting_restore_zip":
            if not message.document or not message.document.file_name.endswith(".zip"):
                return await message.reply("❌ Please send a valid `.zip` file.")
            msg = await message.reply("⏳ Restoring data...")
            path = await message.download()
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    with zipfile.ZipFile(path, 'r') as zip_ref:
                        zip_ref.extractall(tmp_dir)
                    restored_data = {}
                    for filename in os.listdir(tmp_dir):
                        if filename.endswith(".json"):
                            coll_name = filename[:-5]
                            with open(os.path.join(tmp_dir, filename), 'r') as f:
                                restored_data[coll_name] = json.load(f)
                    if await db.import_data(restored_data):
                        await msg.edit("✅ **Database restored successfully!**")
                    else: await msg.edit("❌ Restoration failed.")
            except Exception as e: await msg.edit(f"❌ Error: {e}")
            finally:
                if os.path.exists(path): os.remove(path)
                user_state.pop(uid, None)
            return

        if action == "ask_title":
            user_state[uid].update({"title": message.text, "action": "ask_year"})
            await message.reply("📅 Send **Release Year**:")
        elif action == "ask_year":
            user_state[uid].update({"year": message.text, "action": "ask_poster_man"})
            await message.reply("🖼 Send **Poster URL**:")
        elif action == "ask_poster_man":
            data = user_state[uid]
            slug = slugify(data["title"])
            await db.add_media({
                "id": f"man_{slug}", "title": data["title"], "slug": slug,
                "type": data["type"], "year": data["year"], "image": message.text, "seasons_links": {}
            })
            await message.reply(f"🚀 Published: {Config.BASE_URL}/watch/{slug}")
            user_state.pop(uid, None)
        elif action == "ask_poster":
            await db.media.update_one({"slug": slug}, {"$set": {"image": message.text.strip()}})
            await message.reply("✅ Poster updated.")
            user_state.pop(uid, None)
        elif action == "ask_title_edit":
            new_title = message.text.strip()
            new_slug = slugify(new_title)
            await db.media.update_one({"slug": slug}, {"$set": {"title": new_title, "slug": new_slug}})
            await message.reply(f"✅ Title updated.")
            user_state.pop(uid, None)
        elif action == "ask_syno":
            await db.media.update_one({"slug": slug}, {"$set": {"synopsis": message.text.strip()}})
            await message.reply("✅ Synopsis updated.")
            user_state.pop(uid, None)
        elif action == "ask_gname":
            user_state[uid].update({"gname": message.text.strip(), "action": "ask_glink"})
            await message.reply(f"🔗 Send Link for `{message.text}`:")
        elif action == "ask_glink":
            media = await db.get_media_by_slug(slug)
            links = media.get("seasons_links", {})
            links[state["gname"]] = {"Server 1": message.text.strip()}
            await db.media.update_one({"slug": slug}, {"$set": {"seasons_links": links}})
            await message.reply(f"✅ Group added.")
            user_state.pop(uid, None)

    logger.info("Bot handlers successfully initialized.")

async def set_commands(client: Client):
    try:
        await client.set_bot_commands([
            BotCommand("start", "Start Bot"),
            BotCommand("search", "Import from TMDB"),
            BotCommand("edit", "Edit Metadata"),
            BotCommand("edit_m", "Manage Servers"),
            BotCommand("save", "Backup/Restore"),
            BotCommand("ping", "Status Check"),
            BotCommand("cancel", "Cancel Process")
        ])
    except: pass
