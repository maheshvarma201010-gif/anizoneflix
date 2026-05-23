import asyncio
from database.db import db
from config.config import Config
import secrets

async def seed():
    await db.connect()
    # Using mock db if Config.MONGO_URI is empty (which it is)

    anime_data = {
        "mal_id": "12345",
        "title": "Naruto Shippuden",
        "slug": "naruto-shippuden",
        "synopsis": "A young ninja who seeks recognition from his peers and dreams of becoming the Hokage.",
        "score": 8.5,
        "image": "https://m.media-amazon.com/images/M/MV5BZGFiMWFhNDAtMzUyZS00NmQ2LTljNDYtMmZjNTc5MDUxMzViXkEyXkFqcGdeQXVyNjAwNDUxODI@._V1_.jpg",
        "genres": ["Action", "Adventure"],
        "category": "Anime",
        "status": "Finished Airing",
        "year": "2007",
        "trailer": None,
        "studios": ["Studio Pierrot"]
    }
    await db.add_anime(anime_data)

    ep_hash = secrets.token_hex(12)
    episode_data = {
        "hash": ep_hash,
        "mal_id": "12345",
        "season": 1,
        "episode": 1,
        "episode_title": "Homecoming",
        "quality": "1080p",
        "file_id": "mock_file_id",
        "file_name": "Naruto_S1E1_1080p.mkv",
        "file_size": 1000000,
        "views": 0
    }
    await db.episodes.insert_one(episode_data)

    print(f"Seeded! Ep Hash: {ep_hash}")
    return ep_hash

if __name__ == "__main__":
    asyncio.run(seed())
