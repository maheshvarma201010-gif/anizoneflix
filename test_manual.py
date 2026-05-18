from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler

bot = Client("test", api_id=123, api_hash="abc", bot_token="token")

def register(b):
    async def h(c, m):
        pass
    b.add_handler(MessageHandler(h, filters.command("test")))

register(bot)
print(f"Handlers: {bot.dispatcher.groups}")
