import asyncio
from core.logger import logger
from database.db import db
from config.config import Config

class StartupChecker:
    @staticmethod
    async def check_all(bot):
        """
        Performs a series of health checks on startup.
        """
        logger.info("--- 🚀 Initializing System Health Checks ---")

        # 1. Database Availability
        if not await db.ping():
            logger.warning("⚠️ Database connection not verified via ping. Attempting to connect...")
            try:
                await db.connect()
                if await db.ping():
                    logger.info("✅ Database Connection Restored.")
                else:
                    logger.critical("❌ Database remains offline after reconnection attempt.")
            except Exception as e:
                logger.error(f"❌ Database connection error: {e}")
        else:
            logger.info("✅ Database Online.")

        # 2. Bot Permissions in Bin Channel
        # Assuming there's a bin channel or similar requirement
        try:
            me = await bot.get_me()
            logger.info(f"✅ Bot Token Valid: @{me.username}")
        except Exception as e:
            logger.critical(f"❌ Bot Token Invalid or Telegram API Unreachable: {e}")

        # 3. Userbot Sessions
        # This will be handled in the refactored app.py/lifespan

        logger.info("--- ✅ System Health Checks Completed ---")
        return True

    @staticmethod
    async def test_target_channel(bot, channel_id):
        """
        Sends a hidden test message to verify permissions and deletes it.
        """
        try:
            msg = await bot.send_message(channel_id, "🔍 **System Health Check: Testing Permissions...**")
            await asyncio.sleep(1)
            await msg.delete()
            return True, "Permissions Verified."
        except Exception as e:
            return False, f"Permission Check Failed: {e}"
