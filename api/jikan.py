import aiohttp
from config.config import Config

class JikanAPI:
    def __init__(self):
        self.base_url = Config.JIKAN_API

    async def search_anime(self, query):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/anime", params={"q": query}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", [])
                return []

    async def get_anime_details(self, mal_id):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/anime/{mal_id}/full") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", {})
                return {}

jikan = JikanAPI()
