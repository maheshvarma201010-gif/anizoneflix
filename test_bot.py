import asyncio
from bot import bot, register_handlers
from pyrogram import filters

async def test():
    print("Testing handler registration...")
    register_handlers(bot)
    print(f"Groups: {list(bot.dispatcher.groups.keys())}")
    for group, handlers in bot.dispatcher.groups.items():
        print(f"Group {group}: {len(handlers)} handlers")
        for h in handlers:
            print(f"  - {type(h)}")

if __name__ == "__main__":
    asyncio.run(test())
