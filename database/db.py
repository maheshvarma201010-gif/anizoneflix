from motor.motor_asyncio import AsyncIOMotorClient
from config.config import Config
import os
import logging
import asyncio
import re
from bson import ObjectId

logger = logging.getLogger("MZ_DB")

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
        self._anime = None
        self._episodes = None
        self._users = None
        self._categories = None
        self._schedules = None

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
                self._anime = self._db.anime
                self._episodes = self._db.episodes
                self._users = self._db.users
                self._categories = self._db.categories
                self._schedules = self._db.schedules

                logger.info(f"Database Persistence Verified: {Config.DB_NAME} is active.")
                return
            except Exception as e:
                logger.error(f"Database connection blocked on attempt {attempt}: {e}")
                if attempt == 5:
                    logger.critical("FINAL PERSISTENCE FAILURE: System cannot guarantee data safety.")
                    raise e
                await asyncio.sleep(attempt * 2)

    @property
    def anime(self):
        return self._anime if self._anime is not None else self.MockCollection("anime")

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
    def schedules(self):
        return self._schedules if self._schedules is not None else self.MockCollection("schedules")

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

    async def add_anime(self, data):
        try:
            if self._anime is None: return None
            return await self._anime.update_one({"mal_id": data["mal_id"]}, {"$set": data}, upsert=True)
        except Exception as e:
            logger.error(f"Persistence Error (add_anime): {e}")
            return None

    async def get_anime_by_slug(self, slug):
        try:
            if self._anime is None: return None
            doc = await self._anime.find_one({"slug": slug})
            return clean_doc(doc)
        except Exception as e:
            logger.error(f"Read Error (get_anime_by_slug): {e}")
            return None

    async def get_anime_by_mal_id(self, mal_id):
        try:
            if self._anime is None: return None
            doc = await self._anime.find_one({"mal_id": mal_id})
            return clean_doc(doc)
        except Exception as e:
            logger.error(f"Read Error (get_anime_by_mal_id): {e}")
            return None

    async def get_all_anime(self, limit=20, skip=0):
        try:
            if self._anime is None: return []
            cursor = self._anime.find().sort("_id", -1).skip(skip).limit(limit)
            docs = await cursor.to_list(length=limit)
            return clean_doc(docs) or []
        except Exception as e:
            logger.error(f"Read Error (get_all_anime): {e}")
            return []

    async def search_anime_db(self, query):
        try:
            if self._anime is None: return []
            safe_query = re.escape(query)
            cursor = self._anime.find({"title": {"$regex": safe_query, "$options": "i"}})
            docs = await cursor.to_list(length=20)
            return clean_doc(docs) or []
        except Exception as e:
            logger.error(f"Read Error (search_anime_db): {e}")
            return []

    async def get_anime(self, identifier):
        """Robust lookup by ID string or Slug"""
        if not identifier: return None
        try:
            if self._anime is None: return None

            # Try ObjectId lookup first if it looks like one
            if isinstance(identifier, str) and len(identifier) == 24:
                try:
                    doc = await self._anime.find_one({"_id": ObjectId(identifier)})
                    if doc: return clean_doc(doc)
                except: pass

            # Fallback to slug
            doc = await self._anime.find_one({"slug": identifier})
            return clean_doc(doc)
        except Exception as e:
            logger.error(f"Read Error (get_anime): {e}")
            return None

    async def delete_anime_by_slug(self, slug):
        try:
            if self._anime is None: return None
            anime = await self.get_anime_by_slug(slug)
            if anime:
                if self._episodes is not None:
                    await self._episodes.delete_many({"mal_id": anime["mal_id"]})
            return await self._anime.delete_one({"slug": slug})
        except Exception as e:
            logger.error(f"Sanitization Error (delete_anime_by_slug): {e}")
            return None

    async def add_episode(self, data):
        try:
            if self._episodes is None: return None
            # Standardize defaults
            data.setdefault("status", "published")
            data.setdefault("views", 0)
            data.setdefault("downloads", 0)

            # Complex query for multi-quality / language / episode uniqueness
            query = {
                "mal_id": data["mal_id"],
                "season": data.get("season"),
                "episode": data.get("episode"),
                "quality": data.get("quality"),
                "audio": data.get("audio")
            }
            return await self._episodes.update_one(query, {"$set": data}, upsert=True)
        except Exception as e:
            logger.error(f"Persistence Error (add_episode): {e}")
            return None

    async def get_episodes(self, mal_id, status=None):
        try:
            if self._episodes is None: return []
            query = {"mal_id": mal_id}
            if status:
                query["status"] = status

            cursor = self._episodes.find(query).sort([("season", 1), ("episode", 1), ("sort_order", 1)])
            docs = await cursor.to_list(length=1000)
            return clean_doc(docs) or []
        except Exception as e:
            logger.error(f"Read Error (get_episodes): {e}")
            return []

    async def publish_episodes(self, mal_id, user_id):
        """Transition all user drafts to live status"""
        try:
            if self._episodes is None: return None
            return await self._episodes.update_many(
                {"mal_id": mal_id, "uploaded_by": user_id, "status": "draft"},
                {"$set": {"status": "published"}}
            )
        except Exception as e:
            logger.error(f"Publish Error: {e}")
            return None

    async def delete_drafts(self, mal_id, user_id):
        try:
            if self._episodes is None: return None
            return await self._episodes.delete_many({"mal_id": mal_id, "uploaded_by": user_id, "status": "draft"})
        except Exception as e:
            logger.error(f"Delete Drafts Error: {e}")
            return None

    async def get_episode_by_hash(self, hash_token):
        try:
            if self._episodes is None: return None
            doc = await self._episodes.find_one({"hash": hash_token})
            return clean_doc(doc)
        except Exception as e:
            logger.error(f"Hash Lookup Error: {e}")
            return None

    async def update_episode(self, ep_id, data):
        try:
            if self._episodes is None: return None
            oid = ObjectId(ep_id) if isinstance(ep_id, str) and len(ep_id) == 24 else ep_id
            return await self._episodes.update_one({"_id": oid}, {"$set": data})
        except Exception as e:
            logger.error(f"Episode Update Error: {e}")
            return None

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

    async def update_schedule(self, day, content):
        try:
            if self._schedules is None: return None
            return await self._schedules.update_one({"day": day}, {"$set": {"content": content}}, upsert=True)
        except Exception as e:
            logger.error(f"Persistence Error (update_schedule): {e}")
            return None

    async def get_schedule(self, day):
        try:
            if self._schedules is None: return "No data synchronized."
            res = await self._schedules.find_one({"day": day})
            return res.get("content", "No data synchronized.") if res else "No data synchronized."
        except Exception as e:
            logger.error(f"Read Error (get_schedule): {e}")
            return "Intelligence network offline."

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
                "anime": self._anime,
                "episodes": self._episodes,
                "users": self._users,
                "categories": self._categories,
                "schedules": self._schedules
            }
            total_found = 0
            for name, coll in collections.items():
                if coll is not None:
                    docs = await coll.find().to_list(length=100000)
                    data[name] = clean_doc(docs)
                    total_found += len(docs)

            if total_found == 0:
                return {} # Return empty dict to indicate connected but empty
            return data
        except Exception as e:
            logger.error(f"Export Error: {e}")
            return None

    async def import_data(self, data):
        try:
            if self._db is None: return False
            collections = {
                "anime": self._anime,
                "episodes": self._episodes,
                "users": self._users,
                "categories": self._categories,
                "schedules": self._schedules
            }

            # Prepare data and validate before deleting
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

            # Now perform deletions and insertions
            for name, processed_docs in to_import.items():
                coll = collections.get(name)
                await coll.delete_many({})
                await coll.insert_many(processed_docs)

            return True
        except Exception as e:
            logger.error(f"Import Error: {e}")
            return False

db = Database()
