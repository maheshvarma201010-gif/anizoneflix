import json
import zipfile
import tempfile
import os
import io
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config.config import Config
from database.db import db
from core.logger import logger
from urllib.parse import unquote

user_state = {}

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

@Client.on_message(filters.command("schedule"))
async def schedule_handler(client, message):
    if not message.from_user: return
    if not await is_authorized(message.from_user.id):
        return await message.reply("🚫 **Access Denied.**")

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    buttons = [[InlineKeyboardButton(days[i], callback_data=f"edit_sched_{days[i]}"), InlineKeyboardButton(days[i+1], callback_data=f"edit_sched_{days[i+1]}")] for i in range(0, 6, 2)]
    buttons.append([InlineKeyboardButton("Sunday", callback_data="edit_sched_Sunday")])
    buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="schedule_refresh")])
    await message.reply("📅 **Airing Schedule**", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_message(filters.command("change_poster"))
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

@Client.on_message(filters.command("del"))
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

@Client.on_message(filters.command("save"))
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

@Client.on_message(filters.command("cancel"))
async def cancel_handler(client, message):
    if message.from_user:
        user_state.pop(message.from_user.id, None)
    await message.reply("✨ **Action Cancelled.** standby.")
