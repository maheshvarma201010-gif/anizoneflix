from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from database.db import db, clean_doc
from config.config import Config
from api.media_api import media_api
import os
import logging
import traceback
import asyncio
import sys
from bot import bot, set_commands, register_handlers
from utils.auth import get_current_admin, verify_token
from utils.utils import slugify
from fastapi.responses import RedirectResponse, JSONResponse, Response
from contextlib import asynccontextmanager

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OTT_APP")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    logger.info("OTT Platform Engine starting...")
    try:
        await db.connect()
        loop = asyncio.get_running_loop()
        bot.loop = loop
        if hasattr(bot, "dispatcher"):
            bot.dispatcher.loop = loop

        register_handlers(bot)
        await bot.start()
        await set_commands(bot)
        me = await bot.get_me()
        logger.info(f"Production Suite LIVE -> @{me.username}")
    except Exception as e:
        logger.critical(f"STARTUP FAILURE: {e}")
        logger.error(traceback.format_exc())

    yield

    # SHUTDOWN
    logger.info("Production Engine shutting down...")
    try:
        if bot.is_connected:
            await bot.stop()
        await media_api.close()
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

# --- APP INITIALIZATION ---

app = FastAPI(title="MoviesZoneFlix", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/src", StaticFiles(directory="src"), name="src")
# Try to use new src/pages first, then fallback or handle specifically
templates = Jinja2Templates(directory="src/pages")
# For shared layouts
templates.env.loader.searchpath.append("src/layouts")

templates.env.filters["slugify"] = slugify

# --- CUSTOM RESPONSES ---

def safe_api_response(success=True, data=None, message=""):
    return JSONResponse(content={
        "success": success,
        "data": data or [],
        "message": message
    })

# --- WEB ROUTES ---

@app.api_route("/", methods=["GET", "HEAD"])
async def index(request: Request):
    if request.method == "HEAD":
        return Response(status_code=200)
    try:
        trending = await db.get_all_media(limit=10)
        popular_movies = await db.get_all_media(limit=10, filters={"type": "movie"})
        popular_series = await db.get_all_media(limit=10, filters={"type": "tv"})
        categories = await db.get_all_categories()

        return templates.TemplateResponse(request=request, name="index.html", context={
            "trending": trending or [],
            "popular_movies": popular_movies or [],
            "popular_series": popular_series or [],
            "categories": categories or [],
            "logo_url": Config.LOGO_URL,
            "site_name": "MoviesZoneFlix",
            "tmdb_key": Config.TMDB_API_KEY,
            "omdb_key": Config.OMDB_API_KEY
        })
    except Exception as e:
        logger.error(f"Index error: {e}")
        return templates.TemplateResponse(request=request, name="index.html", context={
            "trending": [], "popular_movies": [], "popular_series": [], "categories": [],
            "logo_url": Config.LOGO_URL, "site_name": "MoviesZoneFlix"
        })

@app.get("/watch/{slug}")
async def media_detail(request: Request, slug: str):
    try:
        media = await db.get_media_by_slug(slug)
        if not media:
            return templates.TemplateResponse(request=request, name="404.html", context={"error": "Title not found."}, status_code=404)

        categories = await db.get_all_categories()
        episodes = await db.get_episodes(media.get("id", "0"))

        return templates.TemplateResponse(request=request, name="details.html", context={
            "media": media,
            "episodes": episodes or [],
            "categories": categories or [],
            "logo_url": Config.LOGO_URL,
            "site_name": "MoviesZoneFlix"
        })
    except Exception as e:
        logger.error(f"Detail error for {slug}: {e}")
        return templates.TemplateResponse(request=request, name="404.html", context={"error": "Database error."}, status_code=500)

@app.get("/search")
async def search_web(request: Request, q: str = "", type: str = "", year: str = "", genre: str = ""):
    try:
        filters = {}
        if type: filters["type"] = type
        if year: filters["year"] = year
        if genre: filters["genres"] = {"$in": [genre]}

        results = []
        if q:
            results = await db.media.find({
                **filters,
                "$or": [
                    {"title": {"$regex": q, "$options": "i"}},
                    {"category": q}
                ]
            }).sort("_id", -1).to_list(length=50)
            results = clean_doc(results)
        else:
            results = await db.get_all_media(limit=50, filters=filters)

        categories = await db.get_all_categories()
        return templates.TemplateResponse(request=request, name="search.html", context={
            "results": results or [],
            "query": q,
            "categories": categories or [],
            "logo_url": Config.LOGO_URL,
            "site_name": "MoviesZoneFlix"
        })
    except Exception as e:
        logger.error(f"Search error: {e}")
        return templates.TemplateResponse(request=request, name="search.html", context={"results": [], "query": q, "categories": []})

@app.get("/categories")
async def categories_page(request: Request):
    categories = await db.get_all_categories()
    return templates.TemplateResponse(request=request, name="categories.html", context={"categories": categories})

# --- ADMIN ROUTES ---

@app.get("/admin/login")
async def admin_login(request: Request, token: str = None):
    if not token: return RedirectResponse(url="/")
    try:
        payload = verify_token(token)
        if payload and payload.get("is_admin"):
            response = RedirectResponse(url="/admin/dashboard")
            is_secure = "onrender.com" in str(request.base_url) or request.headers.get("x-forwarded-proto") == "https"
            response.set_cookie("admin_token", token, httponly=True, secure=is_secure, samesite="lax", max_age=86400)
            return response
    except: pass
    return RedirectResponse(url="/")

@app.get("/admin/dashboard")
async def admin_dashboard(request: Request, admin=Depends(get_current_admin)):
    posts = await db.get_all_media(limit=100)
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request, "posts": posts or [], "logo_url": Config.LOGO_URL, "site_name": "MoviesZoneFlix"
    })

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")
