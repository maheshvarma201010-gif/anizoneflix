from pyrogram import Client, filters
from database.db import db

@Client.on_message(filters.command("ping"))
async def ping_handler(client, message):
    db_status = "✅ Online" if await db.ping() else "❌ Offline"
    await message.reply_text(f"🏓 **Pong!**\n\n🗄 **Database:** {db_status}\n⚡ **Status:** Operational")
