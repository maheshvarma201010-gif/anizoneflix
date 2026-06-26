from pyrogram import Client, filters
from bot import is_authorized
from core.forward_engine import active_tasks

@Client.on_message(filters.command("forwardstop") & filters.private)
async def forwardstop_cmd(client, message):
    if not await is_authorized(message.from_user.id):
        return await message.reply("🚫 **Unauthorized.**")

    uid = message.from_user.id
    if uid in active_tasks:
        active_tasks[uid].stop()
        await message.reply("🛑 **Forwarding task requested to stop.** final stats will be sent shortly.")
    else:
        await message.reply("ℹ️ **No active forwarding task found for your session.**")
