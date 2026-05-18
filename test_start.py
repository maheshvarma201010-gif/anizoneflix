import asyncio
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler

async def test():
    bot = Client("test", api_id=123, api_hash="abc", bot_token="token", in_memory=True)

    async def h(c, m):
        pass

    bot.add_handler(MessageHandler(h, filters.command("test")))
    print(f"Before start: {bot.dispatcher.groups}")

    # Try to start without valid credentials just to trigger dispatcher init
    try:
        await bot.start()
    except:
        pass

    print(f"After start: {bot.dispatcher.groups}")

if __name__ == "__main__":
    asyncio.run(test())
