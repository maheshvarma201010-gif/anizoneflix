from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified
from database.db import db
from core.logger import logger
from bson import ObjectId

@Client.on_callback_query(filters.regex("^help_guide$"))
async def help_cb(client, callback_query):
    from plugins.help import help_handler
    await help_handler(client, callback_query.message)
    await callback_query.answer()

@Client.on_callback_query(filters.regex("^schedule_refresh$"))
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

@Client.on_callback_query(filters.regex("^add_cat_prompt$"))
async def add_cat_prompt_cb(client, callback_query):
    from plugins.interactions import user_state
    user_state[callback_query.from_user.id] = {"action": "ask_cat_name"}
    await callback_query.message.edit_text("🏷 **Enter Category Name:**", reply_markup=None)
    await callback_query.answer()

@Client.on_callback_query(filters.regex("^del_cat_"))
async def del_cat_cb(client, callback_query):
    try:
        name = callback_query.data.split("del_cat_")[-1]
        await db.delete_category(name)
        await callback_query.answer(f"🗑 Removed: {name}", show_alert=True)
        # Refresh categories view
        from plugins.categories import categories_handler
        await categories_handler(client, callback_query.message)
    except Exception as e: logger.error(f"Del Cat CB Error: {e}")

# ... [Migrate all other 50+ callback handlers] ...
