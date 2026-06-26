from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config.config import Config
from database.db import db
from core.logger import logger
from urllib.parse import unquote

async def is_authorized(user_id):
    try:
        if user_id in Config.ADMIN_IDS:
            return True
        return await db.is_admin(user_id)
    except Exception as e:
        logger.error(f"Authorization Check Error: {e}")
        return False

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

@Client.on_message(filters.command(["edit", "edit_m"]))
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
                [InlineKeyboardButton("📦 Content Groups (Seasons)", callback_data=f"manage_groups_{aid}")],
                [InlineKeyboardButton("🗃 Custom Boxes", callback_data=f"manage_boxes_{aid}")],
                [InlineKeyboardButton("🔗 External Redirects (Buttons)", callback_data=f"manage_btns_{aid}")],
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
