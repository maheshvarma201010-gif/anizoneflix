from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from database.db import db
from config.config import Config
from api.anime_api import anime_api
import os
import logging
import traceback
from bot import bot, set_commands, register_handlers
from utils.auth import get_current_admin, create_access_token
from fastapi.responses import RedirectResponse
import json

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ANIZONEFLIX_APP")

app = FastAPI(title="ANIZONEFLIX")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Bot lifecycle management
@app.on_event("startup")
async def startup_event():
    logger.info("Starting Telegram Bot...")
    try:
        # Sync loops before starting
        import asyncio
        loop = asyncio.get_running_loop()
        bot.loop = loop
        bot.dispatcher.loop = loop

        await bot.start()
        logger.info("Bot Started Successfully")
        logger.info("Session connected")

        # Bot diagnostics
        me = await bot.get_me()
        logger.info(f"BOT ONLINE -> @{me.username}")
        logger.info(f"BOT ID -> {me.id}")
        logger.info("LONG POLLING ACTIVE")

        register_handlers(bot)

        # Give some time for handlers to register if they are in the task queue
        await asyncio.sleep(1)

        # Diagnostics: count handlers
        handler_count = 0
        for group in bot.dispatcher.groups.values():
            handler_count += len(group)
        logger.info(f"Diagnostics: {handler_count} handlers loaded in {len(bot.dispatcher.groups)} groups.")
        logger.info(f"Dispatcher state: {'running' if bot.is_connected else 'stopped'}")

        await set_commands(bot)
        logger.info("Handlers and Commands Loaded Successfully")
    except Exception as e:
        logger.error(f"Critical error during bot startup: {e}")
        logger.error(traceback.format_exc())
        # We don't want to block the web server if the bot fails,
        # but in some cases, you might want to raise e.

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Stopping Bot...")
    try:
        await bot.stop()
        logger.info("Bot Stopped Successfully")
    except Exception as e:
        logger.error(f"Error during bot shutdown: {e}")

# Context processor for global variables
@app.middleware("http")
async def add_global_vars(request: Request, call_next):
    request.state.logo_url = Config.LOGO_URL
    request.state.site_name = "ANIZONEFLIX"
    response = await call_next(request)
    return response

@app.api_route("/", methods=["GET", "HEAD"])
async def index(request: Request):
    if request.method == "HEAD":
        return {"status": "running"}

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
        # Fetch and sort episodes by number
        episodes = await db.get_episodes(anime["mal_id"])
        if episodes:
            episodes.sort(key=lambda x: x.get("episode", 0))

    return templates.TemplateResponse(request=request, name="details.html", context={
        "anime": anime,
        "episodes": episodes if not os.getenv("TESTING") else [],
        "categories": categories,
        "logo_url": Config.LOGO_URL,
        "site_name": "ANIZONEFLIX",
        "version": "Alpha v1.0"
    })

@app.get("/api/anime")
async def get_anime_api(skip: int = 0, limit: int = 20):
    return await db.get_all_anime(limit=limit, skip=skip)

@app.get("/search")
async def search_web(request: Request, q: str = ""):
    if os.getenv("TESTING"):
        results = []
        categories = [{"name": "Action"}, {"name": "Adventure"}, {"name": "Comedy"}]
    else:
        if q:
            # Check if q is a category
            results = await db.anime.find({"$or": [
                {"title": {"$regex": q, "$options": "i"}},
                {"category": q}
            ]}).sort("_id", -1).to_list(length=50)
        else:
            results = await db.get_all_anime(limit=50)
        categories = await db.get_all_categories()

    return templates.TemplateResponse(request=request, name="search.html", context={
        "results": results,
        "query": q,
        "categories": categories,
        "logo_url": Config.LOGO_URL,
        "site_name": "ANIZONEFLIX",
        "version": "v2.0 Ultra"
    })

# Admin Web Routes
@app.get("/admin/login")
async def admin_login_page(request: Request, token: str):
    try:
        from utils.auth import verify_token
        payload = verify_token(token)
        if payload and payload.get("is_admin"):
            response = RedirectResponse(url="/admin/dashboard", status_code=303)
            # Use secure cookies if on Render (HTTPS)
            is_secure = "onrender.com" in str(request.base_url)
            response.set_cookie(
                "admin_token",
                token,
                httponly=True,
                secure=is_secure,
                samesite="lax",
                max_age=86400
            )
            logger.info(f"Admin logged in: {payload.get('user_id')}")
            return response
        logger.warning(f"Failed login attempt with token: {token[:10]}...")
        return templates.TemplateResponse("404.html", {
            "request": request,
            "error": "Invalid or expired admin token",
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        }, status_code=403)
    except Exception as e:
        logger.error(f"Login error: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal Server Error during login")

@app.get("/admin/dashboard")
async def admin_dashboard(request: Request, admin=Depends(get_current_admin)):
    posts = await db.get_all_anime(limit=100)
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "posts": posts,
        "logo_url": Config.LOGO_URL,
        "site_name": "ANIZONEFLIX"
    })

@app.get("/admin/edit/{mal_id}")
async def edit_post_page(request: Request, mal_id: str, admin=Depends(get_current_admin)):
    # Try both string and int (some IDs are strings from auto-post)
    try:
        query_id = int(mal_id)
    except:
        query_id = mal_id

    anime = await db.get_anime_by_mal_id(query_id)
    if not anime:
        return {"error": "Post not found"}
    return templates.TemplateResponse("edit.html", {
        "request": request,
        "anime": anime,
        "logo_url": Config.LOGO_URL,
        "site_name": "ANIZONEFLIX"
    })

@app.post("/api/admin/save/{mal_id}")
async def save_post(request: Request, mal_id: str, admin=Depends(get_current_admin)):
    data = await request.json()
    try:
        query_id = int(mal_id)
    except:
        query_id = mal_id

    # Update DB
    await db.anime.update_one({"mal_id": query_id}, {"$set": data})
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
