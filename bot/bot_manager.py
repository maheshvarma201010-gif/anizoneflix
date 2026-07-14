import asyncio
import logging
import re
import uuid
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config.config import Config
from database.db import db

logger = logging.getLogger("ANIZONEFLIX_BOT_MANAGER")

# Global caches with active size bounds to prevent memory leaks
search_cache = {}
MAX_CACHE_SIZE = 1000

def clean_search_query(q: str) -> str:
    """Standardized clean search query preserving Unicode, lowercasing, stripping, removing punctuation."""
    q = q.lower().strip()
    q = re.sub(r'[^\w\s]', '', q, flags=re.UNICODE)
    q = re.sub(r'\s+', ' ', q).strip()
    return q

async def send_search_results_page(client: Client, message, session_id: str, page: int = 0):
    cache = search_cache.get(session_id)
    if not cache:
        return

    results = cache["results"]
    user_id = cache["user_id"]

    per_page = 8
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_items = results[start_idx:end_idx]

    if not page_items:
        return

    buttons = []
    row = []
    for anime in page_items:
        # Compact callback data: s:user_id:hex_id (guaranteed under 64 bytes)
        aid = str(anime["_id"])
        callback_data = f"s:{user_id}:{aid}"
        button = InlineKeyboardButton(anime["title"][:25], callback_data=callback_data)
        row.append(button)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Navigation buttons
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"nav:{user_id}:{page-1}:{session_id}"))
    if end_idx < len(results):
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"nav:{user_id}:{page+1}:{session_id}"))

    if nav_row:
        buttons.append(nav_row)

    text = f"🎯 **Choose a matching title for '{cache['query']}'**:"

    try:
        if isinstance(message, CallbackQuery):
            await message.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Error sending search results page: {e}")

class AddedBotManager:
    def __init__(self):
        self.clients = {}  # token -> Client

    async def start_all(self):
        logger.info("Initializing and starting all added bots...")
        if not await db.ping():
            logger.error("DB Offline, cannot load added bots.")
            return

        try:
            cursor = db.added_bots.find()
            bots = await cursor.to_list(length=1000)
            for bot_doc in bots:
                token = bot_doc["token"]
                group_id = bot_doc["group_id"]
                bot_info = bot_doc.get("bot_info", {})
                await self.start_bot(token, group_id, bot_info)
        except Exception as e:
            logger.error(f"Error starting added bots: {e}")

    async def start_bot(self, token: str, group_id: int, bot_info: dict) -> bool:
        if token in self.clients:
            logger.info(f"Bot {bot_info.get('username')} already running.")
            return True

        logger.info(f"Starting added bot: @{bot_info.get('username') or 'Unknown'}")
        try:
            client = Client(
                name=f"added_bot_{bot_info.get('id', uuid.uuid4().hex[:8])}",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                bot_token=token,
                in_memory=True
            )

            # Register handlers
            self._register_handlers(client, group_id)

            await client.start()
            self.clients[token] = client
            logger.info(f"Added bot @{bot_info.get('username')} is now running.")
            return True
        except Exception as e:
            logger.error(f"Failed to start bot {bot_info.get('username')}: {e}")
            return False

    async def stop_bot(self, token: str):
        client = self.clients.pop(token, None)
        if client:
            try:
                await client.stop()
                logger.info("Bot client stopped.")
            except Exception as e:
                logger.error(f"Error stopping bot client: {e}")

    async def stop_all(self):
        logger.info("Stopping all added bots...")
        for token in list(self.clients.keys()):
            await self.stop_bot(token)

    def _register_handlers(self, client: Client, configured_group_id: int):

        @client.on_message(filters.text & filters.chat(configured_group_id))
        async def handle_group_text(c: Client, message: Message):
            if message.text.startswith("/"):
                return

            query = message.text.strip()
            if not query:
                return

            try:
                # Intelligent Relevance-Sorted matching
                results = await db.search_anime_intelligent(query, limit=50)
                if not results:
                    return

                if len(results) == 1:
                    anime = results[0]
                    await message.reply(f"{Config.BASE_URL}/anime/{anime['slug']}")
                    return

                # Multiple matches
                session_id = uuid.uuid4().hex[:8]

                # Active Cache Pruning to keep memory usage strictly bounded
                if len(search_cache) >= MAX_CACHE_SIZE:
                    # Remove first key (FIFO)
                    old_key = next(iter(search_cache))
                    search_cache.pop(old_key, None)

                search_cache[session_id] = {
                    "results": results,
                    "query": query,
                    "user_id": message.from_user.id if message.from_user else 0
                }

                await send_search_results_page(c, message, session_id, page=0)
            except Exception as e:
                logger.error(f"Error handling group text message: {e}")

        @client.on_callback_query()
        async def handle_bot_callback(c: Client, callback_query: CallbackQuery):
            data = callback_query.data
            if not (data.startswith("s:") or data.startswith("nav:")):
                return

            parts = data.split(":")
            if len(parts) < 3:
                await callback_query.answer("⚠️ Invalid callback data.", show_alert=True)
                return

            action = parts[0]
            expected_user_id = int(parts[1])
            clicker_id = callback_query.from_user.id if callback_query.from_user else 0

            # Button security
            if expected_user_id != clicker_id:
                await callback_query.answer("This menu belongs to another user.", show_alert=True)
                return

            if action == "s":
                aid = parts[2]
                await callback_query.answer()

                try:
                    # Direct lookup using _id / ID
                    anime = await db.get_anime(aid)
                    if anime:
                        await callback_query.message.edit_text(
                            f"{Config.BASE_URL}/anime/{anime['slug']}",
                            reply_markup=None
                        )
                    else:
                        await callback_query.answer("❌ Title not found in database.", show_alert=True)
                except Exception as e:
                    logger.error(f"Error serving selection callback: {e}")
                    await callback_query.answer("❌ Database Error.")

            elif action == "nav":
                if len(parts) < 4:
                    return
                page = int(parts[2])
                session_id = parts[3]
                await callback_query.answer()
                await send_search_results_page(c, callback_query, session_id, page=page)

added_bot_manager = AddedBotManager()
