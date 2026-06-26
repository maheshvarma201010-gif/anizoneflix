import asyncio
from core.logger import bot_logger
from core.session import session_manager
from database.db import db

async def run_health_check(bot):
    bot_logger.info("🚀 Initiating System Health Check...")

    # 1. Database
    if await db.ping():
        bot_logger.info("✔ Database: Connected")
    else:
        bot_logger.error("✘ Database: Offline")
        return False

    # 2. Userbot Session
    client = await session_manager.get_client()
    if client:
        bot_logger.info("✔ Userbot: Authorized")
    else:
        bot_logger.warning("ℹ Userbot: Not logged in")

    # 3. Bot Permissions (Optional test if channel configured)
    try:
        me = await bot.get_me()
        bot_logger.info(f"✔ Bot: @{me.username} is active")
    except Exception as e:
        bot_logger.error(f"✘ Bot: Initialization failed: {e}")
        return False

    bot_logger.info("✨ Health check completed successfully.")
    return True
