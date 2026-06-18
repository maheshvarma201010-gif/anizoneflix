import asyncio
from pyrogram import Client
from config.config import Config

async def test():
    app = Client("test", Config.API_ID, Config.API_HASH, bot_token=Config.BOT_TOKEN, in_memory=True)
    await app.start()
    try:
        gen = app.stream_media("BQACAgQAAxkBAAEC...")
        print(f"Type: {type(gen)}")
        import inspect
        print(f"Is async generator: {inspect.isasyncgen(gen)}")
    finally:
        await app.stop()

if __name__ == "__main__":
    asyncio.run(test())
