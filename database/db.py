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
        self.anime = self.db.anime
        self.users = self.db.users
        self.settings = self.db.settings
        self.categories = self.db.categories

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
        return await self.anime.delete_one({"mal_id": mal_id})

    async def delete_anime_by_slug(self, slug):
        return await self.anime.delete_one({"slug": slug})

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
