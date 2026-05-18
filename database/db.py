from motor.motor_asyncio import AsyncIOMotorClient
from config.config import Config
import os
import logging
import asyncio

logger = logging.getLogger("ANIZONEFLIX_DB")

class Database:
    def __init__(self):
        self.client = None
        self._db = None
        self._anime = None
        self._episodes = None
        self._users = None
        self._settings = None
        self._categories = None
        self._schedules = None

    async def connect(self):
        """Initialize connection with high reliability and retries"""
        if self.client:
            return

        uri = Config.MONGO_URI or "mongodb://localhost:27017"
        for attempt in range(1, 4):
            try:
                logger.info(f"Connecting to Database (Attempt {attempt}/3)...")
                self.client = AsyncIOMotorClient(
                    uri,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=10000,
                    retryWrites=True,
                    retryReads=True
                )
                # Test connectivity
                await self.client.admin.command('ping')

                self._db = self.client[Config.DB_NAME]
                self._anime = self._db.anime
                self._episodes = self._db.episodes
                self._users = self._db.users
                self._settings = self._db.settings
                self._categories = self._db.categories
                self._schedules = self._db.schedules

                logger.info("Database Synchronization Complete.")
                return
            except Exception as e:
                logger.error(f"Database sync failed on attempt {attempt}: {e}")
                if attempt == 3:
                    logger.critical("Final database connection attempt failed.")
                else:
                    await asyncio.sleep(2)

    @property
    def anime(self):
        return self._anime if self._anime is not None else self.MockCollection()

    @property
    def episodes(self):
        return self._episodes if self._episodes is not None else self.MockCollection()

    @property
    def users(self):
        return self._users if self._users is not None else self.MockCollection()

    @property
    def categories(self):
        return self._categories if self._categories is not None else self.MockCollection()

    @property
    def schedules(self):
        return self._schedules if self._schedules is not None else self.MockCollection()

    class MockCollection:
        """Safety layer to prevent AttributeErrors if DB is down"""
        def __getattr__(self, name):
            async def mock_func(*args, **kwargs): return None
            return mock_func

        async def find_one(self, *args, **kwargs): return None
        def find(self, *args, **kwargs):
            class MockCursor:
                async def to_list(self, *args, **kwargs): return []
                def sort(self, *args, **kwargs): return self
                def skip(self, *args, **kwargs): return self
                def limit(self, *args, **kwargs): return self
            return MockCursor()
        async def update_one(self, *args, **kwargs): return None
        async def delete_one(self, *args, **kwargs): return None
        async def delete_many(self, *args, **kwargs): return None

    async def ping(self):
        try:
            if not self.client: return False
            await self.client.admin.command('ping')
            return True
        except: return False

    # --- Robust CRUD Methods ---

    async def add_anime(self, data):
        return await self.anime.update_one({"mal_id": data["mal_id"]}, {"$set": data}, upsert=True)

    async def get_anime_by_slug(self, slug):
        return await self.anime.find_one({"slug": slug})

    async def get_all_anime(self, limit=20, skip=0):
        try:
            # CORRECT Motor find usage
            return await self.anime.find().sort("_id", -1).skip(skip).limit(limit).to_list(length=limit)
        except: return []

    async def search_anime_db(self, query):
        try:
            return await self.anime.find({"title": {"$regex": query, "$options": "i"}}).to_list(length=20)
        except: return []

    async def delete_anime_by_slug(self, slug):
        anime = await self.get_anime_by_slug(slug)
        if anime:
            await self.episodes.delete_many({"mal_id": anime["mal_id"]})
        return await self.anime.delete_one({"slug": slug})

    async def add_episode(self, data):
        query = {"mal_id": data["mal_id"], "season": data.get("season"), "episode": data.get("episode"), "quality": data.get("quality")}
        return await self.episodes.update_one(query, {"$set": data}, upsert=True)

    async def get_episodes(self, mal_id):
        try:
            return await self.episodes.find({"mal_id": mal_id}).sort([("season", 1), ("episode", 1)]).to_list(length=1000)
        except: return []

    async def get_all_categories(self):
        try:
            return await self.categories.find().to_list(length=100)
        except: return []

    async def update_schedule(self, day, content):
        return await self.schedules.update_one({"day": day}, {"$set": {"content": content}}, upsert=True)

    async def get_schedule(self, day):
        try:
            res = await self.schedules.find_one({"day": day})
            return res["content"] if res else "No data synchronized."
        except: return "Database connection unavailable."

    async def is_admin(self, user_id):
        try:
            user = await self.users.find_one({"user_id": user_id, "is_admin": True})
            return user is not None
        except: return False

db = Database()
