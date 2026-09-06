import aiohttp
import asyncio
import logging
import os
from config.config import Config

logger = logging.getLogger("ANIZONEFLIX_API")

class AnimeAPI:
    def __init__(self):
        self.apis = {
            "jikan": "https://api.jikan.moe/v4",
            "anilist": "https://graphql.anilist.co",
            "kitsu": "https://kitsu.io/api/edge",
            "shikimori": "https://shikimori.one/api",
            "simkl": "https://api.simkl.com",
            "tmdb": "https://api.themoviedb.org/3"
        }
        self.tmdb_key = Config.TMDB_API_KEY
        self.simkl_id = Config.SIMKL_ID or "834160a0f9b6c0e86b971a17c247f078e34898144"
        self._session = None

    async def get_session(self):
        if self._session is None or self._session.closed:
            # Create session in the current loop
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5),
                headers={"User-Agent": "AniZoneFlix/2.0 (Executive Suite)"}
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("API Session Closed.")

    async def _get(self, url, params=None, headers=None):
        session = await self.get_session()
        try:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status == 200:
                    try:
                        return await resp.json()
                    except Exception as je:
                        logger.error(f"JSON Parse Error from {url}: {je}")
                else:
                    logger.debug(f"API Non-200 Status {resp.status} for {url}")
        except Exception as e:
            logger.debug(f"API Request Error {url}: {e}")
        return None

    async def search_jikan(self, query):
        data = await self._get(f"{self.apis['jikan']}/anime", params={"q": query, "limit": 5})
        if data and "data" in data:
            return [{"source": "jikan", "id": x["mal_id"], "title": x["title"], "image": x["images"]["jpg"]["large_image_url"], "year": x.get("year")} for x in data["data"]]
        return []

    async def search_anilist(self, query):
        query_gql = """
        query ($search: String) {
          Page (perPage: 5) {
            media (search: $search, type: ANIME) {
              id
              title { romaji }
              coverImage { large }
              seasonYear
            }
          }
        }
        """
        session = await self.get_session()
        try:
            async with session.post(self.apis["anilist"], json={'query': query_gql, 'variables': {'search': query}}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get('data', {}).get('Page', {}).get('media', [])
                    return [{"source": "anilist", "id": x["id"], "title": x["title"]["romaji"], "image": x["coverImage"]["large"], "year": x.get("seasonYear")} for x in results]
        except Exception as e:
            logger.debug(f"AniList Error: {e}")
        return []

    async def search_kitsu(self, query):
        data = await self._get(f"{self.apis['kitsu']}/anime", params={"filter[text]": query, "page[limit]": 5})
        if data and "data" in data:
            return [{"source": "kitsu", "id": x["id"], "title": x["attributes"]["canonicalTitle"], "image": x["attributes"]["posterImage"]["large"], "year": x["attributes"].get("startDate", "")[:4]} for x in data["data"]]
        return []

    async def search_tmdb(self, query):
        if not self.tmdb_key: return []
        data = await self._get(f"{self.apis['tmdb']}/search/multi", params={"api_key": self.tmdb_key, "query": query})
        if data and "results" in data:
            return [{"source": "tmdb", "id": x["id"], "title": x.get("name") or x.get("title"), "image": f"https://image.tmdb.org/t/p/w500{x.get('poster_path')}", "year": (x.get("first_air_date") or x.get("release_date", ""))[:4]} for x in data["results"] if x.get("poster_path")]
        return []

    async def search_all(self, query):
        """High-Performance Aggregator"""
        tasks = [
            self.search_jikan(query),
            self.search_anilist(query),
            self.search_kitsu(query),
            self.search_tmdb(query)
        ]
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Gather Error: {e}")
            return []

        flat = []
        seen = set()
        for res_list in results:
            if isinstance(res_list, list):
                for item in res_list:
                    uid = f"{item['title'].lower()}"
                    if uid not in seen:
                        flat.append(item)
                        seen.add(uid)
        return flat[:15]

    async def get_details(self, source, id):
        details = None
        if source == "jikan":
            data = await self._get(f"{self.apis['jikan']}/anime/{id}/full")
            if data and "data" in data:
                x = data["data"]
                details = {
                    "title": x.get("title"), "synopsis": x.get("synopsis"), "score": x.get("score", 0),
                    "image": x.get("images", {}).get("jpg", {}).get("large_image_url"),
                    "genres": [g["name"] for g in x.get("genres", [])],
                    "status": x.get("status"), "year": x.get("year"), "episodes": x.get("episodes"),
                    "trailer": x.get("trailer", {}).get("url"), "studios": [s["name"] for s in x.get("studios", [])]
                }
        elif source == "anilist":
            query_gql = """
            query ($id: Int) {
              Media (id: $id, type: ANIME) {
                title { romaji english }
                description
                averageScore
                coverImage { extraLarge }
                genres
                status
                seasonYear
                episodes
                trailer { id site }
                studios { nodes { name } }
              }
            }
            """
            session = await self.get_session()
            try:
                async with session.post(self.apis["anilist"], json={'query': query_gql, 'variables': {'id': int(id)}}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        x = data.get('data', {}).get('Media', {})
                        if x:
                            studios_list = [st["name"] for st in x.get("studios", {}).get("nodes", [])] if x.get("studios") else []
                            details = {
                                "title": x.get("title", {}).get("romaji") or x.get("title", {}).get("english"),
                                "synopsis": x.get("description"),
                                "score": round(x.get("averageScore", 0) / 10.0, 1) if x.get("averageScore") else 0,
                                "image": x.get("coverImage", {}).get("extraLarge"),
                                "genres": x.get("genres", []),
                                "status": x.get("status"),
                                "year": x.get("seasonYear"),
                                "episodes": x.get("episodes"),
                                "trailer": f"https://www.youtube.com/watch?v={x['trailer']['id']}" if x.get("trailer") and x["trailer"].get("site") == "youtube" else None,
                                "studios": studios_list
                            }
            except Exception as e:
                logger.error(f"AniList Details Error: {e}")
        elif source == "kitsu":
            data = await self._get(f"{self.apis['kitsu']}/anime/{id}")
            if data and "data" in data:
                attr = data["data"].get("attributes", {})
                details = {
                    "title": attr.get("canonicalTitle") or attr.get("titles", {}).get("en_jp"),
                    "synopsis": attr.get("synopsis"),
                    "score": round(float(attr.get("averageRating", 0)) / 10.0, 1) if attr.get("averageRating") else 0,
                    "image": attr.get("posterImage", {}).get("large"),
                    "genres": [],
                    "status": attr.get("status"),
                    "year": attr.get("startDate", "")[:4] if attr.get("startDate") else None,
                    "episodes": attr.get("episodeCount"),
                    "trailer": f"https://www.youtube.com/watch?v={attr['youtubeVideoId']}" if attr.get("youtubeVideoId") else None,
                    "studios": []
                }
        elif source == "tmdb":
            if self.tmdb_key:
                data = await self._get(f"{self.apis['tmdb']}/tv/{id}", params={"api_key": self.tmdb_key})
                if not data:
                    data = await self._get(f"{self.apis['tmdb']}/movie/{id}", params={"api_key": self.tmdb_key})
                if data:
                    details = {
                        "title": data.get("name") or data.get("title"),
                        "synopsis": data.get("overview"),
                        "score": round(data.get("vote_average", 0), 1),
                        "image": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get("poster_path") else None,
                        "genres": [g["name"] for g in data.get("genres", [])],
                        "status": data.get("status"),
                        "year": (data.get("first_air_date") or data.get("release_date", ""))[:4] if (data.get("first_air_date") or data.get("release_date")) else None,
                        "episodes": data.get("number_of_episodes"),
                        "trailer": None,
                        "studios": [c["name"] for c in data.get("production_companies", [])]
                    }

        if details:
            # Auto-enrich missing fields if title is present
            title = details.get("title")
            if title:
                details = await self.enrich_details(details, title=title)

        return details

    async def enrich_details(self, base_details, title):
        """Automatically retries fetching from all sources to fill any missing metadata"""
        if not base_details:
            base_details = {}

        # Search for alternative matches across APIs
        candidates = await self.search_all(title)
        for cand in candidates[:3]:
            # Skip same source if base_details already came from it
            cand_source = cand.get("source")
            cand_id = cand.get("id")
            if not cand_id:
                continue

            # Fetch secondary details
            sec_details = None
            if cand_source == "jikan":
                data = await self._get(f"{self.apis['jikan']}/anime/{cand_id}/full")
                if data and "data" in data:
                    x = data["data"]
                    sec_details = {
                        "synopsis": x.get("synopsis"), "score": x.get("score", 0),
                        "image": x.get("images", {}).get("jpg", {}).get("large_image_url"),
                        "genres": [g["name"] for g in x.get("genres", [])],
                        "year": x.get("year"), "trailer": x.get("trailer", {}).get("url"),
                        "studios": [s["name"] for s in x.get("studios", [])]
                    }
            elif cand_source == "anilist":
                query_gql = """
                query ($id: Int) {
                  Media (id: $id, type: ANIME) {
                    description
                    averageScore
                    coverImage { extraLarge }
                    genres
                    seasonYear
                    trailer { id site }
                    studios { nodes { name } }
                  }
                }
                """
                session = await self.get_session()
                try:
                    async with session.post(self.apis["anilist"], json={'query': query_gql, 'variables': {'id': int(cand_id)}}) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            x = data.get('data', {}).get('Media', {})
                            if x:
                                sec_details = {
                                    "synopsis": x.get("description"),
                                    "score": round(x.get("averageScore", 0) / 10.0, 1) if x.get("averageScore") else 0,
                                    "image": x.get("coverImage", {}).get("extraLarge"),
                                    "genres": x.get("genres", []),
                                    "year": x.get("seasonYear"),
                                    "trailer": f"https://www.youtube.com/watch?v={x['trailer']['id']}" if x.get("trailer") and x["trailer"].get("site") == "youtube" else None,
                                    "studios": [st["name"] for st in x.get("studios", {}).get("nodes", [])] if x.get("studios") else []
                                }
                except Exception:
                    pass

            if sec_details:
                # Merge missing/empty fields
                if (not base_details.get("synopsis") or base_details.get("synopsis") == "N/A") and sec_details.get("synopsis"):
                    base_details["synopsis"] = sec_details["synopsis"]
                if (not base_details.get("score") or base_details.get("score") == 0) and sec_details.get("score"):
                    base_details["score"] = sec_details["score"]
                if (not base_details.get("image") or "logo" in str(base_details.get("image")).lower()) and sec_details.get("image"):
                    base_details["image"] = sec_details["image"]
                if not base_details.get("genres") and sec_details.get("genres"):
                    base_details["genres"] = sec_details["genres"]
                if (not base_details.get("year") or base_details.get("year") == "N/A") and sec_details.get("year"):
                    base_details["year"] = sec_details["year"]
                if not base_details.get("trailer") and sec_details.get("trailer"):
                    base_details["trailer"] = sec_details["trailer"]
                if not base_details.get("studios") and sec_details.get("studios"):
                    base_details["studios"] = sec_details["studios"]

        return base_details

anime_api = AnimeAPI()
