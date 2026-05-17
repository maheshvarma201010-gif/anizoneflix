from motor.motor_asyncio import AsyncIOMotorClient
from config.config import Config
import os

class Database:
    def __init__(self):
        if os.getenv("TESTING") == "1":
            from mongomock_motor import AsyncMongoMockClient as MockClient
            self.client = MockClient()
        else:
            uri = Config.MONGO_URI or "mongodb://localhost:27017"
            self.client = AsyncIOMotorClient(uri)
        self.db = self.client[Config.DB_NAME]
        self.anime = self.db.anime # This will now act as "posts"
        self.episodes = self.db.episodes
        self.users = self.db.users
        self.settings = self.db.settings
        self.categories = self.db.categories

    async def add_anime(self, data):
        # We ensure slug is unique for posts
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
        # Also delete episodes
        await self.episodes.delete_many({"mal_id": mal_id})
        return await self.anime.delete_one({"mal_id": mal_id})

    async def delete_anime_by_slug(self, slug):
        anime = await self.get_anime_by_slug(slug)
        if anime:
            await self.episodes.delete_many({"mal_id": anime["mal_id"]})
        return await self.anime.delete_one({"slug": slug})

    # Episode management
    async def add_episode(self, data):
        """
        data: { mal_id, season, episode, quality, audio, file_id, file_name, file_size, ... }
        """
        # Upsert based on mal_id, season, episode, quality, audio to avoid duplicates
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
        # field can be "views" or "downloads"
        return await self.episodes.update_one(
            {"mal_id": mal_id, "season": season, "episode": episode, "quality": quality},
            {"$inc": {field: 1}}
        )

    async def update_settings(self, key, value):
        await self.settings.update_one({"key": key}, {"$set": {"value": value}}, upsert=True)

    async def get_settings(self, key):
        res = await self.settings.find_one({"key": key})
        return res["value"] if res else None

    # Category methods
    async def add_category(self, name):
        return await self.categories.update_one({"name": name}, {"$set": {"name": name}}, upsert=True)

    async def delete_category(self, name):
        return await self.categories.delete_one({"name": name})

    async def get_all_categories(self):
        return await self.categories.find().to_list(length=100)

    # Admin methods
    async def add_admin(self, user_id):
        return await self.users.update_one({"user_id": user_id}, {"$set": {"user_id": user_id, "is_admin": True}}, upsert=True)

    async def is_admin(self, user_id):
        user = await self.users.find_one({"user_id": user_id, "is_admin": True})
        return user is not None

db = Database()
