from motor.motor_asyncio import AsyncIOMotorClient
from config.config import Config
import os
import logging
import asyncio
from bson import ObjectId

logger = logging.getLogger("OTT_DB")

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
        self._media = None
        self._episodes = None
        self._users = None
        self._categories = None
        self._settings = None

    async def connect(self):
        """Initialize connection with absolute persistence focus and retries"""
        if self.client:
            return

        uri = Config.MONGO_URI
        if not uri:
            logger.critical("MONGO_URI IS NOT SET. DATA PERSISTENCE IS DISABLED.")
            uri = "mongodb://localhost:27017"

        for attempt in range(1, 6):
            try:
                logger.info(f"Connecting to MongoDB Atlas (Attempt {attempt}/5)...")
                self.client = AsyncIOMotorClient(
                    uri,
                    serverSelectionTimeoutMS=15000,
                    connectTimeoutMS=30000,
                    retryWrites=True,
                    retryReads=True,
                    appname="MoviesZoneFlix-Executive"
                )
                await self.client.admin.command('ping')

                self._db = self.client[Config.DB_NAME]
                self._media = self._db.media
                self._episodes = self._db.episodes
                self._users = self._db.users
                self._categories = self._db.categories
                self._settings = self._db.settings

                logger.info(f"Database Persistence Verified: {Config.DB_NAME} is active.")
                return
            except Exception as e:
                logger.error(f"Database connection blocked on attempt {attempt}: {e}")
                if attempt == 5:
                    logger.critical("FINAL PERSISTENCE FAILURE: System cannot guarantee data safety.")
                    raise e
                await asyncio.sleep(attempt * 2)

    @property
    def media(self):
        return self._media if self._media is not None else self.MockCollection("media")

    @property
    def episodes(self):
        return self._episodes if self._episodes is not None else self.MockCollection("episodes")

    @property
    def users(self):
        return self._users if self._users is not None else self.MockCollection("users")

    @property
    def categories(self):
        return self._categories if self._categories is not None else self.MockCollection("categories")

    @property
    def settings(self):
        return self._settings if self._settings is not None else self.MockCollection("settings")

    class MockCollection:
        """Emergency layer to prevent system crashes if Atlas is unreachable"""
        def __init__(self, name):
            self.name = name

        def __getattr__(self, name):
            async def mock_func(*args, **kwargs):
                logger.error(f"SYSTEM DEGRADED: Call to {self.name}.{name} ignored (DB Offline).")
                return None
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
        def __bool__(self): return False

    async def ping(self):
        try:
            if self.client is None: return False
            await self.client.admin.command('ping')
            return True
        except: return False

    # --- Robust CRUD Methods (Persistence Focused) ---

    async def add_media(self, data):
        try:
            if self._media is None: return None
            # Using tmdb_id or similar unique identifier
            uid = data.get("tmdb_id") or data.get("mal_id") or data.get("id")
            return await self._media.update_one({"id": uid}, {"$set": data}, upsert=True)
        except Exception as e:
            logger.error(f"Persistence Error (add_media): {e}")
            return None

    async def get_media_by_slug(self, slug):
        try:
            if self._media is None: return None
            doc = await self._media.find_one({"slug": slug})
            return clean_doc(doc)
        except Exception as e:
            logger.error(f"Read Error (get_media_by_slug): {e}")
            return None

    async def get_media_by_id(self, media_id):
        try:
            if self._media is None: return None
            doc = await self._media.find_one({"id": media_id})
            return clean_doc(doc)
        except Exception as e:
            logger.error(f"Read Error (get_media_by_id): {e}")
            return None

    async def get_all_media(self, limit=20, skip=0, filters=None):
        try:
            if self._media is None: return []
            query = filters or {}
            cursor = self._media.find(query).sort("_id", -1).skip(skip).limit(limit)
            docs = await cursor.to_list(length=limit)
            return clean_doc(docs) or []
        except Exception as e:
            logger.error(f"Read Error (get_all_media): {e}")
            return []

    async def search_media_db(self, query):
        try:
            if self._media is None: return []
            cursor = self._media.find({"title": {"$regex": query, "$options": "i"}})
            docs = await cursor.to_list(length=20)
            return clean_doc(docs) or []
        except Exception as e:
            logger.error(f"Read Error (search_media_db): {e}")
            return []

    async def delete_media_by_slug(self, slug):
        try:
            if self._media is None: return None
            media = await self.get_media_by_slug(slug)
            if media:
                if self._episodes is not None:
                    await self._episodes.delete_many({"media_id": media["id"]})
            return await self._media.delete_one({"slug": slug})
        except Exception as e:
            logger.error(f"Sanitization Error (delete_media_by_slug): {e}")
            return None

    async def add_episode(self, data):
        try:
            if self._episodes is None: return None
            query = {"media_id": data["media_id"], "season": data.get("season"), "episode": data.get("episode"), "quality": data.get("quality")}
            return await self._episodes.update_one(query, {"$set": data}, upsert=True)
        except Exception as e:
            logger.error(f"Persistence Error (add_episode): {e}")
            return None

    async def get_episodes(self, media_id):
        try:
            if self._episodes is None: return []
            cursor = self._episodes.find({"media_id": media_id}).sort([("season", 1), ("episode", 1)])
            docs = await cursor.to_list(length=1000)
            return clean_doc(docs) or []
        except Exception as e:
            logger.error(f"Read Error (get_episodes): {e}")
            return []

    async def get_all_categories(self):
        try:
            if self._categories is None: return []
            cursor = self._categories.find()
            docs = await cursor.to_list(length=100)
            return clean_doc(docs) or []
        except Exception as e:
            logger.error(f"Read Error (get_all_categories): {e}")
            return []

    async def add_category(self, name):
        try:
            if self._categories is None: return None
            return await self._categories.update_one({"name": name}, {"$set": {"name": name}}, upsert=True)
        except Exception as e:
            logger.error(f"Persistence Error (add_category): {e}")
            return None

    async def delete_category(self, name):
        try:
            if self._categories is None: return None
            return await self._categories.delete_one({"name": name})
        except Exception as e:
            logger.error(f"Persistence Error (delete_category): {e}")
            return None

    async def is_admin(self, user_id):
        try:
            if self._users is None: return False
            user = await self._users.find_one({"user_id": user_id, "is_admin": True})
            return user is not None
        except: return False

    async def export_data(self):
        try:
            if self._db is None: return None
            data = {}
            collections = {
                "media": self._media,
                "episodes": self._episodes,
                "users": self._users,
                "categories": self._categories,
                "settings": self._settings
            }
            total_found = 0
            for name, coll in collections.items():
                if coll is not None:
                    docs = await coll.find().to_list(length=100000)
                    data[name] = clean_doc(docs)
                    total_found += len(docs)

            if total_found == 0:
                return {}
            return data
        except Exception as e:
            logger.error(f"Export Error: {e}")
            return None

    async def import_data(self, data):
        try:
            if self._db is None: return False
            collections = {
                "media": self._media,
                "episodes": self._episodes,
                "users": self._users,
                "categories": self._categories,
                "settings": self._settings
            }

            to_import = {}
            for name, docs in data.items():
                coll = collections.get(name)
                if coll and docs:
                    processed_docs = []
                    for doc in docs:
                        if "_id" in doc and isinstance(doc["_id"], str) and len(doc["_id"]) == 24:
                            try: doc["_id"] = ObjectId(doc["_id"])
                            except: pass
                        processed_docs.append(doc)
                    to_import[name] = processed_docs

            for name, processed_docs in to_import.items():
                coll = collections.get(name)
                await coll.delete_many({})
                await coll.insert_many(processed_docs)

            return True
        except Exception as e:
            logger.error(f"Import Error: {e}")
            return False

db = Database()
