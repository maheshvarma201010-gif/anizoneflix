from pyrogram import Client, filters
from config.config import Config

@Client.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply_text(
        "👋 **Welcome to ANIZONEFLIX Pro Forwarder!**\n\n"
        "I am an enterprise-quality Telegram Auto Forward System. "
        "Use me to clone messages across channels with professional precision.\n\n"
        "💡 **Commands:**\n"
        "• `/login` - Authenticate your user account\n"
        "• `/logout` - Clear your session\n"
        "• `/forward` - Start a new forwarding task\n"
        "• `/forwardstop` - Stop the current task\n"
        "• `/help` - View detailed instructions"
    )
