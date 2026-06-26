from pyrogram import Client, filters
from bot import is_authorized
from core.session import session_manager

@Client.on_message(filters.command("logout") & filters.private)
async def logout_cmd(client, message):
    if not await is_authorized(message.from_user.id):
        return await message.reply("🚫 **Unauthorized.**")

    await message.reply("⏳ **Cleaning session data...**")
    await session_manager.logout()
    await message.reply("🚪 **Logged out successfully.** All local and cloud session records cleared.")
