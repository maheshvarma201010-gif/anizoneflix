from pyrogram import Client, filters
from database.session_storage import session_storage
from core.session import userbot_manager
from config.config import Config

@Client.on_message(filters.command("logout") & filters.user(Config.ADMIN_IDS))
async def logout_handler(client, message):
    user_id = message.from_user.id

    # 1. Stop Userbot session if active
    await userbot_manager.stop_session(user_id)

    # 2. Delete from storage
    deleted = await session_storage.delete_session(user_id)

    if deleted:
        await message.reply_text("✅ **Logged out successfully.**\n\nYour session has been removed from the database.")
    else:
        await message.reply_text("❌ **Error:** No active session found.")
