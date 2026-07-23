import aiohttp
import asyncio
import logging
from config.config import Config

logger = logging.getLogger("MEDIA_API")

class MediaAPI:
    def __init__(self):
        self.tmdb_url = "https://api.themoviedb.org/3"
        self.tvmaze_url = "https://api.tvmaze.com"
        self.omdb_url = "https://www.omdbapi.com"
        self.trakt_url = "https://api.trakt.tv"
        self.tmdb_key = Config.TMDB_API_KEY
        self.omdb_key = Config.OMDB_API_KEY
        self.trakt_id = Config.TRAKT_CLIENT_ID
        self._session = None

    async def get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "MoviesZoneFlix/1.0"}
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get(self, url, params=None, headers=None):
        session = await self.get_session()
        try:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"API Error {resp.status} for {url}")
        except Exception as e:
            logger.error(f"Request Error {url}: {e}")
        return None

    async def search_tmdb(self, query):
        if not self.tmdb_key: return []
        params = {"api_key": self.tmdb_key, "query": query}
        data = await self._get(f"{self.tmdb_url}/search/multi", params=params)
        if data and "results" in data:
            results = []
            for x in data["results"]:
                if x.get("media_type") not in ["movie", "tv"]: continue
                results.append({
                    "id": x["id"],
                    "title": x.get("title") or x.get("name"),
                    "type": x["media_type"],
                    "poster": f"https://image.tmdb.org/t/p/w500{x.get('poster_path')}" if x.get('poster_path') else None,
                    "backdrop": f"https://image.tmdb.org/t/p/original{x.get('backdrop_path')}" if x.get('backdrop_path') else None,
                    "year": (x.get("release_date") or x.get("first_air_date") or "0000")[:4],
                    "rating": x.get("vote_average", 0),
                    "overview": x.get("overview")
                })
            return results
        return []

    async def get_tmdb_details(self, media_type, tmdb_id):
        if not self.tmdb_key: return None
        params = {"api_key": self.tmdb_key, "append_to_response": "videos,credits,similar"}
        return await self._get(f"{self.tmdb_url}/{media_type}/{tmdb_id}", params=params)

    async def search_tvmaze(self, query):
        data = await self._get(f"{self.tvmaze_url}/search/shows", params={"q": query})
        if data:
            return [{
                "id": x["show"]["id"],
                "title": x["show"]["name"],
                "type": "tv",
                "poster": x["show"]["image"]["medium"] if x["show"].get("image") else None,
                "year": x["show"].get("premiered", "0000")[:4],
                "rating": x["show"]["rating"].get("average", 0) if x["show"].get("rating") else 0,
                "overview": x["show"].get("summary")
            } for x in data]
        return []

    async def get_omdb_metadata(self, title, year=None, imdb_id=None):
        """Fetch extensive meta rating/cast from OMDb"""
        if not self.omdb_key: return None
        params = {"apikey": self.omdb_key, "plot": "full"}
        if imdb_id:
            params["i"] = imdb_id
        else:
            params["t"] = title
            if year: params["y"] = year
        return await self._get(self.omdb_url, params=params)

    async def get_trakt_metadata(self, media_type, query):
        """Fetch global social stats/reviews from Trakt"""
        if not self.trakt_id: return None
        headers = {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": self.trakt_id
        }
        # Trakt uses "show" instead of "tv"
        t_type = "show" if media_type == "tv" else "movie"
        params = {"query": query}
        results = await self._get(f"{self.trakt_url}/search/{t_type}", params=params, headers=headers)
        if results and isinstance(results, list) and len(results) > 0:
            # Get the first match
            first = results[0]
            trakt_id = first.get(t_type, {}).get("ids", {}).get("trakt")
            if trakt_id:
                # Fetch statistics
                stats = await self._get(f"{self.trakt_url}/{t_type}s/{trakt_id}/stats", headers=headers)
                comments = await self._get(f"{self.trakt_url}/{t_type}s/{trakt_id}/comments/trending", headers=headers)
                return {
                    "trakt_id": trakt_id,
                    "stats": stats or {},
                    "comments": comments or []
                }
        return None

media_api = MediaAPI()
