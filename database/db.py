from motor.motor_asyncio import AsyncIOMotorClient
from config.config import Config
import os
import logging
import asyncio
import re
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
                    appname="AniZoneFlix-Executive"
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

    @property
    def added_bots(self):
        return self._db.added_bots if self._db is not None else self.MockCollection("added_bots")

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
            return await self._anime.update_one(
                {"mal_id": data["mal_id"]},
                {"$set": data, "$currentDate": {"updated_at": True}},
                upsert=True
            )
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
            cursor = self._anime.find().sort([("updated_at", -1), ("_id", -1)]).skip(skip).limit(limit)
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
            docs = await cursor.to_list(length=10000)
            return clean_doc(docs) or []
        except Exception as e:
            logger.error(f"Read Error (search_anime_db): {e}")
            return []

    async def search_anime_intelligent(self, raw_query: str, limit: int = 50):
        try:
            if self._anime is None: return []
            q = raw_query.lower().strip()
            # Remove punctuation except spaces
            q = re.sub(r'[^\w\s]', '', q, flags=re.UNICODE)
            q = re.sub(r'\s+', ' ', q).strip()

            if not q:
                return []

            words = q.split()
            if not words:
                return []

            # Multi-word queries: build progressive query list for fallbacks
            # "naruto Telugu season 1" -> ["naruto", "naruto telugu", "naruto telugu season", "naruto telugu season 1"]
            query_variations = []
            for i in range(1, len(words) + 1):
                query_variations.append(" ".join(words[:i]))

            # We try search matching from shortest word to longest or longest to shortest depending on relevance.
            # Usually we check the longest first, but user requested:
            # "If user sends like naruto Telugu season 1 bot search for first word if not found with first and second words if not found first,second and third word at once"
            # Thus, we execute progressive fallbacks in this order:
            # 1. First word only: "naruto"
            # 2. First + Second: "naruto telugu"
            # 3. First + Second + Third: "naruto telugu season"
            # 4. Full query: "naruto telugu season 1"

            for variation in query_variations:
                word_regex = ".*".join([re.escape(w) for w in variation.split()])
                or_conditions = [
                    {"title": {"$regex": f"^{re.escape(variation)}$", "$options": "i"}},
                    {"title": {"$regex": f"^{re.escape(variation)}", "$options": "i"}},
                    {"title": {"$regex": re.escape(variation), "$options": "i"}}
                ]
                if word_regex:
                    or_conditions.append({"title": {"$regex": word_regex, "$options": "i"}})

                cursor = self._anime.find({"$or": or_conditions})
                docs = await cursor.to_list(length=100)
                docs = clean_doc(docs) or []

                if docs:
                    # Found matches with this variation! Apply in-memory ranking
                    scored_docs = []
                    for doc in docs:
                        title = doc.get("title", "").lower().strip()
                        score = 0
                        if title == variation:
                            score = 100
                        elif title.startswith(variation):
                            score = 80
                        elif f" {variation} " in f" {title} ":
                            score = 60
                        elif variation in title:
                            score = 40
                        else:
                            score = 20
                        scored_docs.append((score, doc))

                    scored_docs.sort(key=lambda x: x[0], reverse=True)
                    return [doc for _, doc in scored_docs][:limit]

            return []
        except Exception as e:
            logger.error(f"Read Error (search_anime_intelligent): {e}")
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
            query = {"mal_id": data["mal_id"], "season": data.get("season"), "episode": data.get("episode"), "quality": data.get("quality")}
            return await self._episodes.update_one(query, {"$set": data}, upsert=True)
        except Exception as e:
            logger.error(f"Persistence Error (add_episode): {e}")
            return None

    async def get_episodes(self, mal_id):
        try:
            if self._episodes is None: return []
            cursor = self._episodes.find({"mal_id": mal_id}).sort([("season", 1), ("episode", 1)])
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

    async def update_schedule(self, day, content):
        try:
            if self._schedules is None: return None
            return await self._schedules.update_one({"day": day}, {"$set": {"content": content}}, upsert=True)
        except Exception as e:
            logger.error(f"Persistence Error (update_schedule): {e}")
            return None

    async def get_schedule(self, day):
        try:
            if self._schedules is None: return []
            res = await self._schedules.find_one({"day": day})
            if not res: return []

            content = res.get("content", [])
            # Convert string to structured list and extract URLs
            if isinstance(content, str):
                structured = []
                for line in content.split("\n"):
                    line = line.strip()
                    if not line: continue

                    image_url = None
                    time_val = "TBA"

                    # Extract URL (more robustly, looking for common image extensions too)
                    url_match = re.search(r'(https?://[^\s]+\.(?:jpg|jpeg|png|webp|gif|bmp)(?:\?[^\s]*)?)', line, re.I)
                    if not url_match:
                        # Fallback to any URL
                        url_match = re.search(r'(https?://[^\s]+)', line)

                    if url_match:
                        image_url = url_match.group(0).strip('.,()[]{}')
                        line = line.replace(url_match.group(0), "").strip()

                    # Extract Time (e.g. "12:00 PM", "(12:00)", "12.00")
                    time_match = re.search(r'\(?(\d{1,2}[:.]\d{2}\s*(?:AM|PM|am|pm)?)\)?', line)
                    if time_match:
                        time_val = time_match.group(1).replace('.', ':')
                        line = line.replace(time_match.group(0), "").strip()

                    # Clean up remaining name (remove leading dots/numbers if any)
                    name = re.sub(r'^[\d\.\-\s]+', '', line).strip()
                    if not name and image_url: name = "Untitled Entry"

                    if name or image_url:
                        structured.append({"name": name, "time": time_val, "image": image_url})
                return structured
            return content
        except Exception as e:
            logger.error(f"Read Error (get_schedule): {e}")
            return []

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
                if coll is not None and isinstance(docs, list):
                    processed_docs = []
                    for doc in docs:
                        if isinstance(doc, dict):
                            # Handle MongoDB ObjectId if present in string format
                            if "_id" in doc and isinstance(doc["_id"], str) and len(doc["_id"]) == 24:
                                try: doc["_id"] = ObjectId(doc["_id"])
                                except: pass
                            processed_docs.append(doc)
                    to_import[name] = processed_docs

            # Now perform deletions and insertions in a transaction-like manner
            for name, coll in collections.items():
                if name in to_import:
                    await coll.delete_many({})
                    if to_import[name]:
                        await coll.insert_many(to_import[name])

            return True
        except Exception as e:
            logger.error(f"Import Error: {e}")
            return False

db = Database()
