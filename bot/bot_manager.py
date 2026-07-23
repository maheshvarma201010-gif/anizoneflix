import asyncio
import logging
import re
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import db
from config.config import Config

logger = logging.getLogger("MZ_MULTI_BOT")
logger.setLevel(logging.INFO)

class MultiBotManager:
    def __init__(self):
        self.active_bots = {}

    async def start_all(self):
        """Load and start all multi-bots configured in the database"""
        logger.info("Initializing Multi-Bot Manager...")
        try:
            bot_docs = await db.bots.find().to_list(length=100)
            for doc in bot_docs:
                token = doc.get("token")
                group_id = doc.get("group_id")
                if token and group_id:
                    asyncio.create_task(self.start_bot(token, group_id))
        except Exception as e:
            logger.error(f"Error loading multi-bots: {e}")

    async def start_bot(self, token: str, group_id):
        """Initialize, register handlers, and start a single dynamic bot client"""
        bot_id = token.split(":")[0]
        if bot_id in self.active_bots:
            logger.info(f"Bot {bot_id} is already running.")
            return True

        logger.info(f"Starting Multi-Bot {bot_id} for group {group_id}...")
        try:
            # Parse group_id securely
            try:
                target_group_id = int(group_id)
            except ValueError:
                target_group_id = group_id

            # Create Pyrogram Client
            client = Client(
                name=f"dynamic_bot_{bot_id}",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                bot_token=token,
                in_memory=True
            )

            # Register Message Handler
            @client.on_message(filters.text & ~filters.command(["start", "help", "addbot"]))
            async def handle_user_query(c: Client, message: Message):
                # Ensure the message is sent within the configured group
                if message.chat.id != target_group_id:
                    return

                query = message.text.strip()
                if not query:
                    return

                # Search database for a matching movie/series title
                try:
                    # Look for exact or case-insensitive substring match
                    match = await db.media.find_one({"title": {"$regex": f"^{re.escape(query)}$", "$options": "i"}})
                    if not match:
                        # Try fallback substring match if not exactly matched
                        match = await db.media.find_one({"title": {"$regex": f".*{re.escape(query)}.*", "$options": "i"}})

                    if match:
                        link = f"{Config.BASE_URL}/watch/{match['slug']}"
                        await c.send_message(
                            chat_id=message.chat.id,
                            text=f"🎬 **{match['title']}**\n\n🔗 **Link:** {link}",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🍿 Watch Now", url=link)]]),
                            reply_to_message_id=message.id
                        )
                    else:
                        # Silent if no match is found
                        pass
                except Exception as ex:
                    logger.error(f"Error during dynamic bot query: {ex}")

            await client.start()
            self.active_bots[bot_id] = client
            logger.info(f"Multi-Bot {bot_id} is successfully LIVE and listening in {target_group_id}.")
            return True
        except Exception as e:
            logger.error(f"Failed to start dynamic bot {bot_id}: {e}")
            return False

    async def stop_all(self):
        for bot_id, client in list(self.active_bots.items()):
            try:
                await client.stop()
                logger.info(f"Stopped dynamic bot {bot_id}.")
            except Exception as e:
                logger.error(f"Error stopping dynamic bot {bot_id}: {e}")
        self.active_bots.clear()

# Global instance
multibot_manager = MultiBotManager()
