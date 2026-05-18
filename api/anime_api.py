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
        if source == "jikan":
            data = await self._get(f"{self.apis['jikan']}/anime/{id}/full")
            if data and "data" in data:
                x = data["data"]
                return {
                    "title": x["title"], "synopsis": x["synopsis"], "score": x["score"],
                    "image": x["images"]["jpg"]["large_image_url"], "genres": [g["name"] for g in x["genres"]],
                    "status": x["status"], "year": x["year"], "episodes": x["episodes"],
                    "trailer": x["trailer"]["url"], "studios": [s["name"] for s in x["studios"]]
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
              }
            }
            """
            session = await self.get_session()
            try:
                async with session.post(self.apis["anilist"], json={'query': query_gql, 'variables': {'id': id}}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        x = data['data']['Media']
                        return {
                            "title": x["title"]["romaji"],
                            "synopsis": x["description"],
                            "score": x["averageScore"] / 10 if x["averageScore"] else 0,
                            "image": x["coverImage"]["extraLarge"],
                            "genres": x["genres"],
                            "status": x["status"],
                            "year": x["seasonYear"],
                            "episodes": x["episodes"],
                            "trailer": f"https://www.youtube.com/watch?v={x['trailer']['id']}" if x["trailer"] and x["trailer"]["site"] == "youtube" else None,
                            "studios": []
                        }
            except Exception as e:
                logger.error(f"AniList Details Error: {e}")
        return None

anime_api = AnimeAPI()
