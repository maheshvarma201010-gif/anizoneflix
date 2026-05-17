import aiohttp
import logging
from config.config import Config

logger = logging.getLogger("ANIZONEFLIX_API")

class AnimeAPI:
    def __init__(self):
        self.jikan_base = Config.JIKAN_API.rstrip("/")
        self.anilist_url = "https://graphql.anilist.co"

    async def search_jikan(self, query):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.jikan_base}/anime", params={"q": query}, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("data", [])
                        return [{"source": "jikan", **res} for res in results]
                    else:
                        logger.warning(f"Jikan search failed: {resp.status}")
            except Exception as e:
                logger.error(f"Jikan search error: {e}")
        return []

    async def search_anilist(self, query):
        query_gql = """
        query ($search: String) {
          Page (perPage: 10) {
            media (search: $search, type: ANIME) {
              id
              title { romaji english }
              coverImage { large }
              description
              averageScore
              status
              episodes
              seasonYear
              genres
            }
          }
        }
        """
        variables = {'search': query}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.anilist_url, json={'query': query_gql, 'variables': variables}, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get('data', {}).get('Page', {}).get('media', [])
                        return [{"source": "anilist", **res} for res in results]
                    else:
                        logger.warning(f"AniList search failed: {resp.status}")
            except Exception as e:
                logger.error(f"AniList search error: {e}")
        return []

    async def search_all(self, query):
        # Fallback system: try Jikan, if fails or no results, try AniList
        results = await self.search_jikan(query)
        if not results:
            logger.info(f"Jikan found nothing for '{query}', trying AniList...")
            results = await self.search_anilist(query)
        return results

    async def get_details(self, mal_id):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.jikan_base}/anime/{mal_id}/full", timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("data", {})
                    else:
                        logger.warning(f"Jikan details failed: {resp.status}")
            except Exception as e:
                logger.error(f"Jikan details error: {e}")
        return {}

anime_api = AnimeAPI()
