from pyrogram import Client, filters

@Client.on_message(filters.command("help"))
async def help_handler(client, message):
    help_text = (
        "🚀 **ANIZONEFLIX Professional Forwarder: Guide**\n\n"
        "**1. Authentication**\n"
        "Use `/login` to link your Telegram user account. This is required for accessing restricted channels or for higher forwarding limits. "
        "Your session is stored securely in our database and survives restarts.\n\n"
        "**2. Forwarding Messages**\n"
        "Use `/forward` to start. You will need:\n"
        "• **First Message Link:** The start of the range.\n"
        "• **Last Message Link:** The end of the range.\n"
        "• **Target Channel:** The username or ID of where to send.\n\n"
        "**3. Managing Tasks**\n"
        "• `/forwardstop`: Immediately halts the active process.\n"
        "• `/status`: (Coming soon) View system health.\n\n"
        "⚠️ **Note:** Ensure both the Bot and the Logged-in User Account are administrators in the target channel."
    )
    await message.reply_text(help_text)
