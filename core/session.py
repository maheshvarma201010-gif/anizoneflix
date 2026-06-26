import asyncio
from pyrogram import Client
from core.logger import logger
from database.session_storage import session_storage
from config.config import Config

class UserbotManager:
    def __init__(self):
        self.clients = {} # user_id -> Client

    async def start_session(self, user_id: int, session_string: str = None):
        """
        Initializes and starts a Userbot client for the given user_id.
        If session_string is not provided, it attempts to load from DB.
        """
        if user_id in self.clients and self.clients[user_id].is_connected:
            return self.clients[user_id]

        if not session_string:
            session_string = await session_storage.get_session(user_id)

        if not session_string:
            logger.warning(f"No session found for user {user_id}")
            return None

        try:
            client = Client(
                name=f"userbot_{user_id}",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                session_string=session_string,
                in_memory=True
            )
            await client.start()
            self.clients[user_id] = client
            logger.info(f"Userbot session started for user {user_id}")
            return client
        except Exception as e:
            logger.error(f"Failed to start Userbot for {user_id}: {e}")
            return None

    async def stop_session(self, user_id: int):
        """
        Stops and removes a Userbot client.
        """
        client = self.clients.pop(user_id, None)
        if client:
            try:
                if client.is_connected:
                    await client.stop()
                logger.info(f"Userbot session stopped for user {user_id}")
            except Exception as e:
                logger.error(f"Error stopping userbot for {user_id}: {e}")
        return True

    async def get_client(self, user_id: int):
        """
        Returns the active Client for a user, starting it if necessary.
        """
        if user_id in self.clients:
            client = self.clients[user_id]
            if client.is_connected:
                return client
            else:
                try:
                    await client.start()
                    return client
                except:
                    pass

        return await self.start_session(user_id)

    async def restore_all_sessions(self):
        """
        Restores all saved sessions from the database on startup.
        """
        sessions = await session_storage.get_all_sessions()
        for sess in sessions:
            user_id = sess.get("user_id")
            session_string = sess.get("value")
            if user_id and session_string:
                asyncio.create_task(self.start_session(user_id, session_string))
        logger.info(f"Initiated restoration for {len(sessions)} Userbot sessions.")

userbot_manager = UserbotManager()
