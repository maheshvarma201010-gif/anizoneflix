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
    logger.info("Starting Telegram Bot Sequence...")
    try:
        # Ensure Pyrogram uses the same event loop as FastAPI
        import asyncio
        loop = asyncio.get_running_loop()

        # Critical: Sync bot and dispatcher with current running loop
        bot.loop = loop
        if hasattr(bot, "dispatcher"):
            bot.dispatcher.loop = loop

        # Register handlers BEFORE starting to ensure they are bound to the correct loop
        logger.info("Registering Bot Handlers...")
        register_handlers(bot)

        # Start the client
        logger.info("Connecting to Telegram...")
        await bot.start()
        logger.info("Bot Started Successfully - Session connected")

        # Set commands
        await set_commands(bot)

        # Bot diagnostics
        me = await bot.get_me()
        logger.info(f"BOT ONLINE -> @{me.username} ({me.id})")

        # Diagnostics: verify handlers are active
        handler_count = sum(len(group) for group in bot.dispatcher.groups.values())
        logger.info(f"Diagnostics: {handler_count} handlers loaded. LONG POLLING ACTIVE.")

    except Exception as e:
        logger.error(f"CRITICAL: Bot startup failed: {e}")
        logger.error(traceback.format_exc())
        # On Render, if the bot fails, we might want the whole app to fail
        # so it restarts, but for now we'll just log it.

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Stopping Bot...")
    try:
        if bot.is_connected:
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
        # Render healthcheck expects a 200 OK for HEAD /
        # We also verify bot connection health
        status_code = 200 if bot.is_connected else 503
        from fastapi.responses import Response
        return Response(status_code=status_code)

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

@app.get("/schedule")
async def schedule_page(request: Request):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    schedules = {}
    for day in days:
        schedules[day] = await db.get_schedule(day)

    categories = await db.get_all_categories()
    return templates.TemplateResponse("schedule.html", {
        "request": request,
        "schedules": schedules,
        "categories": categories,
        "logo_url": Config.LOGO_URL,
        "site_name": "ANIZONEFLIX"
    })

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
async def admin_login_page(request: Request, token: str = None):
    if not token:
        return templates.TemplateResponse("404.html", {
            "request": request,
            "error": "Missing token",
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        }, status_code=400)
    try:
        from utils.auth import verify_token
        payload = verify_token(token)
        if payload and payload.get("is_admin"):
            response = RedirectResponse(url="/admin/dashboard", status_code=303)
            # Use secure cookies if on Render (HTTPS)
            # We also check X-Forwarded-Proto for Render/Proxies
            is_secure = "onrender.com" in str(request.base_url) or request.headers.get("x-forwarded-proto") == "https"

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
        # Return a more descriptive error instead of a generic 500
        return templates.TemplateResponse("404.html", {
            "request": request,
            "error": f"Login failed: {str(e)}",
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        }, status_code=500)

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
