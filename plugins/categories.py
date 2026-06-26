from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config.config import Config
from database.db import db
from core.logger import logger

async def is_authorized(user_id):
    try:
        if user_id in Config.ADMIN_IDS:
            return True
        return await db.is_admin(user_id)
    except Exception as e:
        logger.error(f"Authorization Check Error: {e}")
        return False

@Client.on_message(filters.command("categories"))
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
