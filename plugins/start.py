from pyrogram import Client, filters
from bot import is_authorized
from config.config import Config

@Client.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if await is_authorized(message.from_user.id):
        await message.reply(
            "👑 **Admin Executive Suite**\n\n"
            "Welcome back, Commander. Use the menu or commands to manage your content forwarding system.\n\n"
            "🛠 **Core Controls:**\n"
            "• /forward - Start new copy task\n"
            "• /forwardstop - Abort current task\n"
            "• /login - Authorize userbot\n"
            "• /logout - Clear session"
        )
    else:
        await message.reply(
            "✨ **AniZoneFlix Forwarder**\n\n"
            "Welcome to the premium content transfer system. This bot is currently in private mode for authorized administrators."
        )

@Client.on_message(filters.command("help") & filters.private)
async def help_cmd(client, message):
    if not await is_authorized(message.from_user.id):
        return await message.reply("🚫 **Access Restricted.**")

    await message.reply(
        "📖 **Command Documentation**\n\n"
        "**/login**\nAuthorize your user account to allow message copying from private/restricted channels.\n\n"
        "**/logout**\nRemove all session data and disconnect the userbot.\n\n"
        "**/forward**\nEnter the forwarding wizard to copy a range of messages. This method preserves original media quality and captions without forward tags.\n\n"
        "**/forwardstop**\nGracefully stop the current active task."
    )
