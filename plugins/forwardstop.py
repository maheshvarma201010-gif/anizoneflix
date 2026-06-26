from pyrogram import Client, filters
from config.config import Config
from core.forward_engine import forward_engine

@Client.on_message(filters.command("forwardstop") & filters.user(Config.ADMIN_IDS))
async def forwardstop_handler(client, message):
    user_id = message.from_user.id

    stopped = await forward_engine.stop_forward(user_id)

    if stopped:
        await message.reply_text("🛑 **Forwarding task has been stopped safely.**")
    else:
        await message.reply_text("ℹ️ **No active forwarding task found for your account.**")
