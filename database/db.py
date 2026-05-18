from motor.motor_asyncio import AsyncIOMotorClient
from config.config import Config
import os
import logging
import asyncio

logger = logging.getLogger("ANIZONEFLIX_DB")

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.anime = None
        self.episodes = None
        self.users = None
        self.settings = None
        self.categories = None
        self.schedules = None

    async def connect(self):
        """Initialize connection within the running event loop"""
        if self.client:
            return

        logger.info("Initializing Database Connection...")
        try:
            if os.getenv("TESTING") == "1":
                from mongomock_motor import AsyncMongoMockClient as MockClient
                self.client = MockClient()
            else:
                uri = Config.MONGO_URI or "mongodb://localhost:27017"
                if not Config.MONGO_URI and "onrender.com" in Config.BASE_URL:
                    logger.warning("CRITICAL: MONGO_URI is not set!")

                self.client = AsyncIOMotorClient(
                    uri,
                    serverSelectionTimeoutMS=5000,
                    retryWrites=True,
                    retryReads=True
                )
                # Verify connection
                await self.client.admin.command('ping')

            self.db = self.client[Config.DB_NAME]
            self.anime = self.db.anime
            self.episodes = self.db.episodes
            self.users = self.db.users
            self.settings = self.db.settings
            self.categories = self.db.categories
            self.schedules = self.db.schedules
            logger.info("Database Connected Successfully.")
        except Exception as e:
            logger.error(f"Database Connection Failed: {e}")
            raise e

    async def ping(self):
        if not self.client: return False
        try:
            await self.client.admin.command('ping')
            return True
        except:
            return False

    async def add_anime(self, data):
        return await self.anime.update_one({"mal_id": data["mal_id"]}, {"$set": data}, upsert=True)

    async def get_anime_by_mal_id(self, mal_id):
        return await self.anime.find_one({"mal_id": mal_id})

    async def get_anime_by_slug(self, slug):
        return await self.anime.find_one({"slug": slug})

    async def get_all_anime(self, limit=20, skip=0):
        return await self.anime.find().sort("_id", -1).skip(skip).limit(limit).to_list(length=limit)

    async def search_anime_db(self, query):
        return await self.anime.find({"title": {"$regex": query, "$options": "i"}}).to_list(length=20)

    async def delete_anime(self, mal_id):
        await self.episodes.delete_many({"mal_id": mal_id})
        return await self.anime.delete_one({"mal_id": mal_id})

    async def delete_anime_by_slug(self, slug):
        anime = await self.get_anime_by_slug(slug)
        if anime:
            await self.episodes.delete_many({"mal_id": anime["mal_id"]})
        return await self.anime.delete_one({"slug": slug})

    async def add_episode(self, data):
        query = {
            "mal_id": data["mal_id"],
            "season": data.get("season"),
            "episode": data.get("episode"),
            "quality": data.get("quality"),
            "audio": data.get("audio")
        }
        return await self.episodes.update_one(query, {"$set": data}, upsert=True)

    async def get_episodes(self, mal_id):
        return await self.episodes.find({"mal_id": mal_id}).sort([("season", 1), ("episode", 1)]).to_list(length=1000)

    async def update_episode_count(self, mal_id, season, episode, quality, field="views"):
        return await self.episodes.update_one(
            {"mal_id": mal_id, "season": season, "episode": episode, "quality": quality},
            {"$inc": {field: 1}}
        )

    async def update_settings(self, key, value):
        await self.settings.update_one({"key": key}, {"$set": {"value": value}}, upsert=True)

    async def get_settings(self, key):
        res = await self.settings.find_one({"key": key})
        return res["value"] if res else None

    async def add_category(self, name):
        return await self.categories.update_one({"name": name}, {"$set": {"name": name}}, upsert=True)

    async def delete_category(self, name):
        return await self.categories.delete_one({"name": name})

    async def get_all_categories(self):
        if not self.categories: return []
        return await self.categories.find().to_list(length=100)

    async def update_schedule(self, day, content):
        return await self.schedules.update_one({"day": day}, {"$set": {"content": content}}, upsert=True)

    async def get_schedule(self, day):
        if not self.schedules: return "No schedule set for this day."
        res = await self.schedules.find_one({"day": day})
        return res["content"] if res else "No schedule set for this day."

    async def get_all_schedules(self):
        if not self.schedules: return []
        return await self.schedules.find().to_list(length=7)

    async def add_admin(self, user_id):
        return await self.users.update_one({"user_id": user_id}, {"$set": {"user_id": user_id, "is_admin": True}}, upsert=True)

    async def is_admin(self, user_id):
        if not self.users: return False
        try:
            user = await self.users.find_one({"user_id": user_id, "is_admin": True})
            return user is not None
        except:
            return False

db = Database()
