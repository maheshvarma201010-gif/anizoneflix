import aiohttp
import asyncio
import logging
import json
import os
from config.config import Config

logger = logging.getLogger("ANIZONEFLIX_API")

class AnimeAPI:
    def __init__(self):
        # Industrial-grade high-speed API endpoints
        self.apis = {
            "jikan": "https://api.jikan.moe/v4",
            "anilist": "https://graphql.anilist.co",
            "kitsu": "https://kitsu.io/api/edge",
            "shikimori": "https://shikimori.one/api",
            "simkl": "https://api.simkl.com",
            "tmdb": "https://api.themoviedb.org/3",
            "anidb": "http://api.anidb.net:9001/httpapi",
            "notifymoe": "https://notify.moe/api",
            "mangadex": "https://api.mangadex.org",
            "enime": "https://api.enime.moe",
            "consumet": "https://api.consumet.org/meta/anilist",
            "myanimelist": "https://api.myanimelist.net/v2"
        }
        self.tmdb_key = "3fd2be3efead2b9a05f39645152865e2"
        self.simkl_id = "834160a0f9b6c0e86b971a17c247f078e34898144"

    async def _get(self, url, params=None, headers=None, timeout=5):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, params=params, headers=headers, timeout=timeout) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except: pass
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
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.apis["anilist"], json={'query': query_gql, 'variables': {'search': query}}, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get('data', {}).get('Page', {}).get('media', [])
                        return [{"source": "anilist", "id": x["id"], "title": x["title"]["romaji"], "image": x["coverImage"]["large"], "year": x.get("seasonYear")} for x in results]
            except: pass
        return []

    async def search_kitsu(self, query):
        data = await self._get(f"{self.apis['kitsu']}/anime", params={"filter[text]": query, "page[limit]": 5})
        if data and "data" in data:
            return [{"source": "kitsu", "id": x["id"], "title": x["attributes"]["canonicalTitle"], "image": x["attributes"]["posterImage"]["large"], "year": x["attributes"].get("startDate", "")[:4]} for x in data["data"]]
        return []

    async def search_shikimori(self, query):
        data = await self._get(f"{self.apis['shikimori']}/animes", params={"search": query, "limit": 5})
        if data:
            return [{"source": "shikimori", "id": x["id"], "title": x["name"], "image": f"https://shikimori.one{x['image']['original']}", "year": x.get("aired_on", "")[:4]} for x in data]
        return []

    async def search_simkl(self, query):
        data = await self._get(f"{self.apis['simkl']}/search/anime", params={"q": query, "client_id": self.simkl_id})
        if data:
            return [{"source": "simkl", "id": x.get("ids", {}).get("simkl"), "title": x["title"], "image": f"https://simkl.in/posters/{x['poster']}_m.jpg", "year": x.get("year")} for x in data if x.get("ids")]
        return []

    async def search_tmdb(self, query):
        data = await self._get(f"{self.apis['tmdb']}/search/multi", params={"api_key": self.tmdb_key, "query": query})
        if data and "results" in data:
            return [{"source": "tmdb", "id": x["id"], "title": x.get("name") or x.get("title"), "image": f"https://image.tmdb.org/t/p/w500{x.get('poster_path')}", "year": (x.get("first_air_date") or x.get("release_date", ""))[:4]} for x in data["results"] if x.get("poster_path")]
        return []

    async def search_mangadex(self, query):
        data = await self._get(f"{self.apis['mangadex']}/manga", params={"title": query, "limit": 5})
        if data and "data" in data:
            return [{"source": "mangadex", "id": x["id"], "title": x["attributes"]["title"].get("en") or list(x["attributes"]["title"].values())[0], "image": "", "year": x["attributes"].get("year")} for x in data["data"]]
        return []

    async def search_notifymoe(self, query):
        data = await self._get(f"{self.apis['notifymoe']}/anime", params={"q": query})
        if data: # Notify.moe returns list
            return [{"source": "notifymoe", "id": x["id"], "title": x["title"]["canonical"], "image": x["image"]["large"], "year": x.get("year")} for x in data[:5] if "title" in x]
        return []

    async def search_enime(self, query):
        data = await self._get(f"{self.apis['enime']}/search/{query}")
        if data and "data" in data:
            return [{"source": "enime", "id": x["id"], "title": x["title"]["english"] or x["title"]["romaji"], "image": x["coverImage"], "year": x.get("year")} for x in data["data"][:5]]
        return []

    async def search_consumet(self, query):
        data = await self._get(f"{self.apis['consumet']}/{query}")
        if data and "results" in data:
            return [{"source": "consumet", "id": x["id"], "title": x["title"], "image": x["image"], "year": x.get("releaseDate")} for x in data["results"][:5]]
        return []

    async def search_all(self, query):
        """Ultra-Performance Aggregator: Runs 11 APIs in Parallel"""
        tasks = [
            self.search_jikan(query),
            self.search_anilist(query),
            self.search_kitsu(query),
            self.search_shikimori(query),
            self.search_simkl(query),
            self.search_tmdb(query),
            self.search_mangadex(query),
            self.search_notifymoe(query),
            self.search_enime(query),
            self.search_consumet(query)
        ]
        results = await asyncio.gather(*tasks)

        flat = []
        seen = set()
        for res_list in results:
            for item in res_list:
                uid = f"{item['source']}_{item['id']}"
                if uid not in seen:
                    flat.append(item)
                    seen.add(uid)
        return flat[:30]

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
            async with aiohttp.ClientSession() as session:
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
                except: pass
        return None

anime_api = AnimeAPI()
