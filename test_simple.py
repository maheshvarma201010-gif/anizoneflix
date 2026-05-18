from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler

bot = Client("test", api_id=123, api_hash="abc", bot_token="token")

def register(b):
    @b.on_message(filters.command("test"))
    async def h(c, m):
        pass

register(bot)
print(f"Handlers: {bot.dispatcher.groups}")
