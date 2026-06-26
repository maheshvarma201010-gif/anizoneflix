from database.db import db
from core.logger import logger

class SessionStorage:
    def __init__(self):
        # We use the 'settings' collection to store session data
        self.collection = db._db.settings if db._db is not None else None

    async def _ensure_collection(self):
        if self.collection is None:
            if db._db is not None:
                self.collection = db._db.settings
            else:
                await db.connect()
                self.collection = db._db.settings

    async def save_session(self, user_id: int, session_string: str):
        """
        Saves a Pyrogram session string to MongoDB.
        """
        await self._ensure_collection()
        try:
            await self.collection.update_one(
                {"key": f"userbot_session_{user_id}"},
                {"$set": {"value": session_string, "user_id": user_id}},
                upsert=True
            )
            logger.info(f"Session saved for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving session: {e}")
            return False

    async def get_session(self, user_id: int):
        """
        Retrieves a Pyrogram session string from MongoDB.
        """
        await self._ensure_collection()
        try:
            doc = await self.collection.find_one({"key": f"userbot_session_{user_id}"})
            return doc.get("value") if doc else None
        except Exception as e:
            logger.error(f"Error retrieving session: {e}")
            return None

    async def delete_session(self, user_id: int):
        """
        Deletes a Pyrogram session string from MongoDB.
        """
        await self._ensure_collection()
        try:
            await self.collection.delete_one({"key": f"userbot_session_{user_id}"})
            logger.info(f"Session deleted for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False

    async def get_all_sessions(self):
        """
        Retrieves all stored userbot sessions.
        """
        await self._ensure_collection()
        try:
            cursor = self.collection.find({"key": {"$regex": "^userbot_session_"}})
            docs = await cursor.to_list(length=100)
            return docs
        except Exception as e:
            logger.error(f"Error retrieving all sessions: {e}")
            return []

session_storage = SessionStorage()
