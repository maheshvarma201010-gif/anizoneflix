from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from database.db import db
from config.config import Config
from api.jikan import jikan
import os

app = FastAPI(title="ANIZONEFLIX")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Context processor for global variables
@app.middleware("http")
async def add_global_vars(request: Request, call_next):
    request.state.logo_url = Config.LOGO_URL
    request.state.site_name = "ANIZONEFLIX"
    response = await call_next(request)
    return response

@app.get("/")
async def index(request: Request):
    if os.getenv("TESTING"):
        mock_anime = {
            "title": "Test Anime",
            "slug": "test-anime",
            "image": "https://cdn.myanimelist.net/images/anime/13/17405.jpg",
            "season": "1",
            "status": "Finished Airing",
            "synopsis": "This is a test synopsis for the home page layout verification."
        }
        trending = [mock_anime] * 4
        recent = [mock_anime] * 8
        categories = [{"name": "Action"}, {"name": "Adventure"}, {"name": "Comedy"}]
    else:
        trending = await db.get_all_anime(limit=10)
        recent = await db.get_all_anime(limit=20)
        categories = await db.get_all_categories()

    return templates.TemplateResponse(request=request, name="index.html", context={
        "trending": trending,
        "recent": recent,
        "categories": categories,
        "logo_url": Config.LOGO_URL,
        "site_name": "ANIZONEFLIX",
        "version": "Alpha v1.0"
    })

@app.get("/anime/{slug}")
async def anime_detail(request: Request, slug: str):
    if (slug == "test-anime" or slug == "test-anime-hd") and (Config.DEBUG or os.getenv("TESTING")):
        anime = {
            "title": "Test Anime HD",
            "season": "1",
            "status": "Currently Airing",
            "score": "8.5",
            "episodes": "24",
            "year": "2023",
            "image": "https://cdn.myanimelist.net/images/anime/13/17405.jpg",
            "genres": ["Action", "Adventure", "Fantasy"],
            "synopsis": "This is a test synopsis for the high-end glassmorphism UI verification.",
            "links": {
                "480p": "#",
                "720p": "#",
                "1080p": "#",
                "batch": "#"
            },
            "trailer": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        }
        categories = [{"name": "Action"}, {"name": "Adventure"}, {"name": "Comedy"}]
    else:
        anime = await db.get_anime_by_slug(slug)

        if not anime:
            categories = await db.get_all_categories()
            return templates.TemplateResponse(request=request, name="404.html", context={
                "categories": categories,
                "logo_url": Config.LOGO_URL,
                "site_name": "ANIZONEFLIX",
                "version": "Alpha v1.0"
            }, status_code=404)

        categories = await db.get_all_categories()
    return templates.TemplateResponse(request=request, name="details.html", context={
        "anime": anime,
        "categories": categories,
        "logo_url": Config.LOGO_URL,
        "site_name": "ANIZONEFLIX",
        "version": "Alpha v1.0"
    })

@app.get("/search")
async def search_web(request: Request, q: str = ""):
    if os.getenv("TESTING"):
        results = []
        categories = [{"name": "Action"}, {"name": "Adventure"}, {"name": "Comedy"}]
    else:
        results = await db.search_anime_db(q)
        categories = await db.get_all_categories()

    return templates.TemplateResponse(request=request, name="search.html", context={
        "results": results,
        "query": q,
        "categories": categories,
        "logo_url": Config.LOGO_URL,
        "site_name": "ANIZONEFLIX",
        "version": "Alpha v1.0"
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
