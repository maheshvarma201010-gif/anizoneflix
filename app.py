from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from database.db import db
from config.config import Config
from api.anime_api import anime_api
import os
import logging
import traceback
import asyncio
from bot import bot, set_commands, register_handlers
from utils.auth import get_current_admin
from fastapi.responses import RedirectResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ANIZONEFLIX_APP")

app = FastAPI(title="ANIZONEFLIX")

# Stability: CORS for Render / Remote access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- GLOBAL ERROR HANDLERS ---

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    if "api" in request.url.path:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "data": None, "message": str(exc.detail)}
        )
    return templates.TemplateResponse("404.html", {"request": request, "error": exc.detail}, status_code=exc.status_code)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"GLOBAL CRASH: {exc}")
    logger.error(traceback.format_exc())
    if "api" in request.url.path:
        return JSONResponse(
            status_code=500,
            content={"success": False, "data": None, "message": "Internal Server Error"}
        )
    return templates.TemplateResponse("404.html", {"request": request, "error": "System temporarily unavailable."}, status_code=500)

# --- LIFECYCLE ---

@app.on_event("startup")
async def startup_event():
    logger.info("AniZoneFlix Production Engine starting...")
    try:
        # 1. Initialize Database with Retries
        await db.connect()

        # 2. Synchronize Pyrogram with running event loop
        loop = asyncio.get_running_loop()
        bot.loop = loop
        if hasattr(bot, "dispatcher"):
            bot.dispatcher.loop = loop

        # 3. Register Handlers BEFORE startup
        register_handlers(bot)

        # 4. Start Telegram Client
        await bot.start()
        await set_commands(bot)

        me = await bot.get_me()
        logger.info(f"Production Suite LIVE -> @{me.username}")
    except Exception as e:
        logger.critical(f"STARTUP FAILURE: {e}")
        # We allow the app to start so Render doesn't loop forever,
        # but the /ping will show degraded status.

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Production Engine shutting down...")
    try:
        if bot.is_connected:
            await bot.stop()
        await anime_api.close()
        logger.info("Shutdown complete.")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

# --- MIDDLEWARE ---

@app.middleware("http")
async def safety_middleware(request: Request, call_next):
    request.state.logo_url = Config.LOGO_URL
    request.state.site_name = "ANIZONEFLIX"
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"Middleware Exception: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": "Critical Error"})

# --- ROUTES ---

@app.api_route("/", methods=["GET", "HEAD"])
async def index(request: Request):
    if request.method == "HEAD":
        # Health check logic
        is_healthy = await db.ping() and bot.is_connected
        return Response(status_code=200 if is_healthy else 503)

    try:
        trending = await db.get_all_anime(limit=10)
        recent = await db.get_all_anime(limit=20)
        categories = await db.get_all_categories()

        return templates.TemplateResponse("index.html", {
            "request": request,
            "trending": trending or [],
            "recent": recent or [],
            "categories": categories or [],
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        })
    except Exception as e:
        logger.error(f"Index route error: {e}")
        return templates.TemplateResponse("index.html", {
            "request": request, "trending": [], "recent": [], "categories": [],
            "logo_url": Config.LOGO_URL, "site_name": "ANIZONEFLIX"
        })

@app.get("/ping")
async def render_health_ping():
    db_ok = await db.ping()
    bot_ok = bot.is_connected
    return {
        "success": db_ok and bot_ok,
        "status": "healthy" if db_ok and bot_ok else "degraded",
        "database": db_ok,
        "bot": bot_ok
    }

@app.get("/schedule")
async def schedule_page(request: Request):
    """RENDER PRODUCTION: Safe Schedule Route"""
    try:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        schedules = {}
        for day in days:
            schedules[day] = await db.get_schedule(day)

        categories = await db.get_all_categories()
        return templates.TemplateResponse("schedule.html", {
            "request": request,
            "schedules": schedules,
            "categories": categories or [],
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        })
    except Exception as e:
        logger.error(f"Schedule page error: {e}")
        return templates.TemplateResponse("schedule.html", {
            "request": request, "schedules": {}, "categories": [],
            "logo_url": Config.LOGO_URL, "site_name": "ANIZONEFLIX"
        })

@app.get("/anime/{slug}")
async def anime_detail(request: Request, slug: str):
    try:
        anime = await db.get_anime_by_slug(slug)
        if not anime:
            return templates.TemplateResponse("404.html", {"request": request, "error": "Title not found."}, status_code=404)

        categories = await db.get_all_categories()
        episodes = await db.get_episodes(anime.get("mal_id", "0"))

        return templates.TemplateResponse("details.html", {
            "request": request,
            "anime": anime,
            "episodes": episodes or [],
            "categories": categories or [],
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        })
    except Exception as e:
        logger.error(f"Detail page error: {e}")
        return templates.TemplateResponse("404.html", {"request": request, "error": "Series data unreachable."})

@app.get("/api/anime")
async def get_anime_api(skip: int = 0, limit: int = 20):
    try:
        data = await db.get_all_anime(limit=limit, skip=skip)
        return {"success": True, "data": data or [], "message": "Success"}
    except Exception as e:
        return {"success": False, "data": [], "message": str(e)}

@app.get("/search")
async def search_web(request: Request, q: str = ""):
    try:
        if q:
            results = await db.anime.find({"$or": [
                {"title": {"$regex": q, "$options": "i"}},
                {"category": q}
            ]}).sort("_id", -1).to_list(length=50)
        else:
            results = await db.get_all_anime(limit=50)

        categories = await db.get_all_categories()
        return templates.TemplateResponse("search.html", {
            "request": request,
            "results": results or [],
            "query": q,
            "categories": categories or [],
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        })
    except Exception as e:
        logger.error(f"Search route error: {e}")
        return templates.TemplateResponse("search.html", {
            "request": request, "results": [], "query": q, "categories": [],
            "logo_url": Config.LOGO_URL, "site_name": "ANIZONEFLIX"
        })

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")
