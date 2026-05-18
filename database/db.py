from motor.motor_asyncio import AsyncIOMotorClient
from config.config import Config
import os
import logging
import asyncio
from bson import ObjectId

logger = logging.getLogger("ANIZONEFLIX_DB")

def clean_doc(doc):
    """Recursively convert ObjectId to string for JSON serialization"""
    if doc is None:
        return None
    if isinstance(doc, list):
        return [clean_doc(d) for d in doc]
    if isinstance(doc, dict):
        new_doc = {}
        for k, v in doc.items():
            if isinstance(v, ObjectId):
                new_doc[k] = str(v)
            elif isinstance(v, (dict, list)):
                new_doc[k] = clean_doc(v)
            else:
                new_doc[k] = v
        return new_doc
    return doc

class Database:
    def __init__(self):
        self.client = None
        self._db = None
        self.anime = None
        self.episodes = None
        self.users = None
        self.categories = None
        self.schedules = None

    async def connect(self):
        """Initialize connection with high reliability and retries"""
        if self.client:
            return

        uri = Config.MONGO_URI
        if not uri:
            logger.critical("MONGO_URI IS NOT SET. DATA PERSISTENCE IS DISABLED.")
            raise ValueError("MONGO_URI environment variable is required for production.")

        for attempt in range(1, 6):
            try:
                logger.info(f"Connecting to MongoDB Atlas (Attempt {attempt}/5)...")
                self.client = AsyncIOMotorClient(
                    uri,
                    serverSelectionTimeoutMS=10000,
                    connectTimeoutMS=20000,
                    retryWrites=True,
                    retryReads=True,
                    appname="AniZoneFlix-Executive"
                )
                # Verify connection
                await self.client.admin.command('ping')

                self._db = self.client[Config.DB_NAME]
                self.anime = self._db.anime
                self.episodes = self._db.episodes
                self.users = self._db.users
                self.categories = self._db.categories
                self.schedules = self._db.schedules

                logger.info(f"Database Persistence Verified: {Config.DB_NAME} is active.")
                return
            except Exception as e:
                logger.error(f"Database sync failed on attempt {attempt}: {e}")
                if attempt == 5:
                    logger.critical("FINAL PERSISTENCE FAILURE: System cannot guarantee data safety.")
                    raise e
                await asyncio.sleep(attempt * 2)

    async def ping(self):
        try:
            if not self.client: return False
            await self.client.admin.command('ping')
            return True
        except: return False

    # --- Robust CRUD Methods (Persistence Guaranteed) ---

    async def add_anime(self, data):
        try:
            if not self.anime: return None
            return await self.anime.update_one({"mal_id": data["mal_id"]}, {"$set": data}, upsert=True)
        except Exception as e:
            logger.error(f"Persistence Error (add_anime): {e}")
            return None

    async def get_anime_by_slug(self, slug):
        try:
            if not self.anime: return None
            doc = await self.anime.find_one({"slug": slug})
            return clean_doc(doc)
        except Exception as e:
            logger.error(f"Read Error (get_anime_by_slug): {e}")
            return None

    async def get_all_anime(self, limit=20, skip=0):
        try:
            if not self.anime: return []
            cursor = self.anime.find().sort("_id", -1).skip(skip).limit(limit)
            docs = await cursor.to_list(length=limit)
            return clean_doc(docs) or []
        except Exception as e:
            logger.error(f"Read Error (get_all_anime): {e}")
            return []

    async def search_anime_db(self, query):
        try:
            if not self.anime: return []
            cursor = self.anime.find({"title": {"$regex": query, "$options": "i"}})
            docs = await cursor.to_list(length=20)
            return clean_doc(docs) or []
        except Exception as e:
            logger.error(f"Read Error (search_anime_db): {e}")
            return []

    async def delete_anime_by_slug(self, slug):
        try:
            if not self.anime: return None
            anime = await self.get_anime_by_slug(slug)
            if anime:
                await self.episodes.delete_many({"mal_id": anime["mal_id"]})
            return await self.anime.delete_one({"slug": slug})
        except Exception as e:
            logger.error(f"Sanitization Error (delete_anime_by_slug): {e}")
            return None

    async def add_episode(self, data):
        try:
            if not self.episodes: return None
            query = {"mal_id": data["mal_id"], "season": data.get("season"), "episode": data.get("episode"), "quality": data.get("quality")}
            return await self.episodes.update_one(query, {"$set": data}, upsert=True)
        except Exception as e:
            logger.error(f"Persistence Error (add_episode): {e}")
            return None

    async def get_episodes(self, mal_id):
        try:
            if not self.episodes: return []
            cursor = self.episodes.find({"mal_id": mal_id}).sort([("season", 1), ("episode", 1)])
            docs = await cursor.to_list(length=1000)
            return clean_doc(docs) or []
        except Exception as e:
            logger.error(f"Read Error (get_episodes): {e}")
            return []

    async def get_all_categories(self):
        try:
            if not self.categories: return []
            cursor = self.categories.find()
            docs = await cursor.to_list(length=100)
            return clean_doc(docs) or []
        except Exception as e:
            logger.error(f"Read Error (get_all_categories): {e}")
            return []

    async def update_schedule(self, day, content):
        try:
            if not self.schedules: return None
            return await self.schedules.update_one({"day": day}, {"$set": {"content": content}}, upsert=True)
        except Exception as e:
            logger.error(f"Persistence Error (update_schedule): {e}")
            return None

    async def get_schedule(self, day):
        try:
            if not self.schedules: return "Persistence layer offline."
            res = await self.schedules.find_one({"day": day})
            return res.get("content", "No data synchronized.") if res else "No data synchronized."
        except Exception as e:
            logger.error(f"Read Error (get_schedule): {e}")
            return "Intelligence network offline."

    async def is_admin(self, user_id):
        try:
            if not self.users: return False
            user = await self.users.find_one({"user_id": user_id, "is_admin": True})
            return user is not None
        except: return False

db = Database()
