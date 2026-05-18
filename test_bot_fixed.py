import asyncio
from bot import bot, register_handlers
from config.config import Config

async def test():
    print("Testing handler registration with start sequence simulation...")
    register_handlers(bot)

    # Simulate app.py logic
    loop = asyncio.get_running_loop()
    bot.loop = loop
    if hasattr(bot, "dispatcher"):
        bot.dispatcher.loop = loop

    # We won't actually call start() as it requires valid network/token
    # But we can check if they are queued in bot._handlers
    print(f"Dispatcher groups: {bot.dispatcher.groups}")

    # Accessing private handlers list to see if they were added via add_handler
    if hasattr(bot, "_handlers"):
        print(f"Pending handlers: {len(bot._handlers)}")

    # Pyrogram 2.x stores added handlers in bot.dispatcher.groups AFTER start or if dispatcher is initialized.
    # If groups is empty, and we called add_handler, they are likely in a pending state or
    # the dispatcher needs to be explicitly created/connected.

if __name__ == "__main__":
    asyncio.run(test())
