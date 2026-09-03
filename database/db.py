from motor.motor_asyncio import AsyncIOMotorClient
from config.config import Config
import os
import logging
import asyncio
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
        self._media = None
        self._episodes = None
        self._users = None
        self._categories = None
        self._settings = None
        self._bots = None

    async def connect(self):
        """Initialize connection with absolute persistence focus and retries"""
        if self.client:
            return

        uri = Config.MONGO_URI
        if not uri:
            logger.critical("MONGO_URI IS NOT SET. DATA PERSISTENCE IS DISABLED. FALLING BACK TO MONGOMOCK MOTOR.")
            await self._connect_mock()
            return

        for attempt in range(1, 6):
            try:
                logger.info(f"Connecting to MongoDB Atlas (Attempt {attempt}/5)...")
                self.client = AsyncIOMotorClient(
                    uri,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=10000,
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
                self._bots = self._db.bots

                logger.info(f"Database Persistence Verified: {Config.DB_NAME} is active.")
                await self._seed_mock_data_if_empty()
                return
            except Exception as e:
                logger.error(f"Database connection blocked on attempt {attempt}: {e}")
                if attempt == 5:
                    logger.critical("FINAL PERSISTENCE FAILURE: Falling back to MONGOMOCK MOTOR.")
                    await self._connect_mock()
                    return
                await asyncio.sleep(1)

    async def _connect_mock(self):
        try:
            from mongomock_motor import AsyncMongoMockClient
            self.client = AsyncMongoMockClient()
            self._db = self.client[Config.DB_NAME]
            self._media = self._db.media
            self._episodes = self._db.episodes
            self._users = self._db.users
            self._categories = self._db.categories
            self._settings = self._db.settings
            self._bots = self._db.bots
            logger.info("Mock Database connected successfully.")
            await self._seed_mock_data_if_empty()
        except Exception as e:
            logger.error(f"Failed to initialize mock database: {e}")

    async def _seed_mock_data_if_empty(self):
        try:
            count = await self._media.count_documents({})
            if count == 0:
                logger.info("Seeding beautiful mock data...")
                mock_data = [
                    {
                        "id": "1",
                        "tmdb_id": 27205,
                        "title": "Inception",
                        "slug": "inception",
                        "type": "movie",
                        "image": "https://static.tvmaze.com/uploads/images/medium_portrait/81/202627.jpg",
                        "backdrop": "https://static.tvmaze.com/uploads/images/medium_portrait/81/202627.jpg",
                        "synopsis": "Cobb, a skilled thief who commits corporate espionage by infiltrating the subconscious of his targets, is offered a chance to regain his old life as payment for a task considered to be impossible: \"inception\", the implantation of another person's idea into a target's subconscious.",
                        "score": 8.8,
                        "year": "2010",
                        "genres": ["Action", "Sci-Fi", "Adventure"],
                        "seasons_links": {
                            "1080p BluRay": {
                                "Download Mirror 1": "https://example.com/dl-inception-1080",
                                "Telegram File": "https://telegram.me/inception_file"
                            },
                            "4K UHD": {
                                "Google Drive Premium": "https://example.com/dl-inception-4k"
                            }
                        },
                        "director": "Christopher Nolan",
                        "cast": ["Leonardo DiCaprio", "Joseph Gordon-Levitt", "Elliot Page"],
                        "runtime": "148 min",
                        "trailer": "https://www.youtube.com/watch?v=YoHD9XEInc0",
                        "status": "Available"
                    },
                    {
                        "id": "2",
                        "tmdb_id": 1399,
                        "title": "Game of Thrones",
                        "slug": "game-of-thrones",
                        "type": "tv",
                        "image": "https://static.tvmaze.com/uploads/images/medium_portrait/498/1245274.jpg",
                        "backdrop": "https://static.tvmaze.com/uploads/images/medium_portrait/498/1245274.jpg",
                        "synopsis": "Seven noble families fight for control of the mythical land of Westeros. Friction between the houses leads to full-scale war. All while a very ancient evil awakens in the farthest north.",
                        "score": 9.2,
                        "year": "2011",
                        "genres": ["Action", "Adventure", "Drama", "Fantasy"],
                        "seasons_links": {
                            "Season 1 [720p Dual]": {
                                "Direct GDrive": "https://example.com/got-s1-720p",
                                "Fast Server": "https://example.com/got-s1-fast"
                            },
                            "Season 8 [1080p Multi]": {
                                "High Speed Link": "https://example.com/got-s8-1080p"
                            }
                        },
                        "director": "David Benioff, D.B. Weiss",
                        "cast": ["Emilia Clarke", "Kit Harington", "Peter Dinklage"],
                        "runtime": "60 min",
                        "trailer": "https://www.youtube.com/watch?v=KPLYYOfL1No",
                        "status": "Completed"
                    },
                    {
                        "id": "3",
                        "tmdb_id": 157336,
                        "title": "Interstellar",
                        "slug": "interstellar",
                        "type": "movie",
                        "image": "https://static.tvmaze.com/uploads/images/medium_portrait/502/1255112.jpg",
                        "backdrop": "https://static.tvmaze.com/uploads/images/medium_portrait/502/1255112.jpg",
                        "synopsis": "The adventures of a group of explorers who make use of a newly discovered wormhole to surpass the limitations on human space travel and conquer the vast distances involved in an interstellar voyage.",
                        "score": 8.6,
                        "year": "2014",
                        "genres": ["Adventure", "Drama", "Sci-Fi"],
                        "seasons_links": {
                            "1080p Web-DL": {
                                "GDrive Hub": "https://example.com/dl-interstellar"
                            }
                        },
                        "director": "Christopher Nolan",
                        "cast": ["Matthew McConaughey", "Anne Hathaway", "Jessica Chastain"],
                        "runtime": "169 min",
                        "trailer": "https://www.youtube.com/watch?v=zSWdZAZE3Tc",
                        "status": "Available"
                    },
                    {
                        "id": "4",
                        "tmdb_id": 4321,
                        "title": "Landscape Image Movie Test",
                        "slug": "landscape-image-movie-test",
                        "type": "movie",
                        "image": "https://static.tvmaze.com/uploads/images/background/1/2.jpg",
                        "backdrop": "https://static.tvmaze.com/uploads/images/background/1/2.jpg",
                        "synopsis": "This is a specialized media item with a landscape poster image. It is used to test the website's dynamic aspect-ratio fitting to ensure that landscape posters are displayed beautifully without any cropping, clipping, or stretching.",
                        "score": 7.9,
                        "year": "2024",
                        "genres": ["Action", "Drama"],
                        "seasons_links": {
                            "1080p HDR": {
                                "Direct Stream": "https://example.com/dl-landscape-test"
                            }
                        },
                        "director": "Test Director",
                        "cast": ["Actor A", "Actor B"],
                        "runtime": "115 min",
                        "trailer": "https://www.youtube.com/watch?v=tgbNymZ7vqY",
                        "status": "Available"
                    }
                ]

                for item in mock_data:
                    await self._media.insert_one(item)

                for cat in ["Action", "Sci-Fi", "Adventure", "Drama", "Fantasy"]:
                    await self._categories.update_one({"name": cat}, {"$set": {"name": cat}}, upsert=True)

                logger.info("Mock database seeding complete!")
        except Exception as e:
            logger.error(f"Error seeding mock database: {e}")

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

    @property
    def bots(self):
        return self._bots if self._bots is not None else self.MockCollection("bots")

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

    async def resolve_unique_title_and_slug(self, base_title, media_id=None):
        import re
        from utils.utils import slugify

        if not base_title:
            return base_title, slugify(base_title or "")

        base_title = base_title.strip()
        base_slug = slugify(base_title)

        if self._media is None:
            return base_title, base_slug

        query = {
            "$or": [
                {"title": {"$regex": f"^{re.escape(base_title)}$", "$options": "i"}},
                {"slug": base_slug}
            ]
        }
        if media_id:
            query["id"] = {"$ne": str(media_id)}

        existing = await self._media.find_one(query)
        if not existing:
            return base_title, base_slug

        count = 1
        while True:
            candidate_title = f"{base_title}{count}"
            candidate_slug = slugify(candidate_title)

            cand_query = {
                "$or": [
                    {"title": {"$regex": f"^{re.escape(candidate_title)}$", "$options": "i"}},
                    {"slug": candidate_slug}
                ]
            }
            if media_id:
                cand_query["id"] = {"$ne": str(media_id)}

            cand_existing = await self._media.find_one(cand_query)
            if not cand_existing:
                return candidate_title, candidate_slug
            count += 1

    async def add_media(self, data):
        import time
        try:
            if self._media is None: return None

            # Ensure data has an id
            if "id" not in data or not data["id"]:
                from utils.utils import slugify
                slug_val = data.get("slug") or slugify(data.get("title", "media"))
                data["id"] = f"man_{slug_val}"

            uid = str(data["id"])

            # Ensure created_at timestamp exists
            if "created_at" not in data or not data["created_at"]:
                data["created_at"] = time.time()

            # Check duplicate title / slug if title is present
            if "title" in data:
                title, slug = await self.resolve_unique_title_and_slug(data["title"], media_id=uid)
                data["title"] = title
                data["slug"] = slug

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
            doc = await self._media.find_one({"id": str(media_id)})
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
