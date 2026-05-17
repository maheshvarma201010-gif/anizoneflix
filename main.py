import asyncio
import os
import logging
from bot import bot
from app import app
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ANIZONEFLIX_MAIN")

async def start_bot():
    logger.info("Starting Telegram Bot...")
    try:
        await bot.start()
        from bot import set_commands
        await set_commands(bot)
        logger.info("Bot started and commands set successfully!")

        # Keep bot task alive and log heartbeat
        while True:
            await asyncio.sleep(300)
            logger.info("Bot Heartbeat: Still Alive")
    except Exception as e:
        logger.error(f"Critical error starting bot: {e}")

async def start_web():
    logger.info("Starting Web Server...")
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    # Start bot in the background
    asyncio.create_task(start_bot())

    # Run web server (blocks until exit)
    await start_web()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("System shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
