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
from bot import bot, set_commands, register_handlers
from utils.auth import get_current_admin
from fastapi.responses import RedirectResponse, JSONResponse, Response

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ANIZONEFLIX_APP")

app = FastAPI(title="ANIZONEFLIX")

# Stability: Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def startup_event():
    logger.info("Executive Suite Startup sequence initiated...")
    try:
        # 1. Initialize Database
        await db.connect()

        # 2. Sync Bot with running loop
        import asyncio
        loop = asyncio.get_running_loop()
        bot.loop = loop
        if hasattr(bot, "dispatcher"):
            bot.dispatcher.loop = loop

        register_handlers(bot)
        await bot.start()
        await set_commands(bot)

        me = await bot.get_me()
        logger.info(f"System Online: {me.username} (Ready for Render)")
    except Exception as e:
        logger.critical(f"Startup Critical Failure: {e}")
        logger.error(traceback.format_exc())

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Graceful shutdown initiated...")
    try:
        await bot.stop()
        await anime_api.close()
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

@app.middleware("http")
async def add_global_vars(request: Request, call_next):
    request.state.logo_url = Config.LOGO_URL
    request.state.site_name = "ANIZONEFLIX"
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"Middleware Error: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})

@app.api_route("/", methods=["GET", "HEAD"])
async def index(request: Request):
    if request.method == "HEAD":
        return Response(status_code=200 if await db.ping() else 503)

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
        logger.error(f"Home page crash: {e}")
        return templates.TemplateResponse("404.html", {"request": request, "error": "System temporarily unavailable."})

@app.get("/schedule")
async def schedule_page(request: Request):
    """RENDER STABILITY: Robust Schedule Route"""
    try:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        schedules = {}
        for day in days:
            schedules[day] = await db.get_schedule(day)

        categories = await db.get_all_categories()
        return templates.TemplateResponse("schedule.html", {
            "request": request,
            "schedules": schedules or {},
            "categories": categories or [],
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        })
    except Exception as e:
        logger.error(f"Schedule page crash: {e}")
        return templates.TemplateResponse("schedule.html", {
            "request": request,
            "schedules": {d: "System error: Data unreachable." for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]},
            "categories": [],
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        })

@app.get("/ping")
async def health_ping():
    """Render health check endpoint"""
    db_status = await db.ping()
    bot_status = bot.is_connected
    return JSONResponse({
        "status": "healthy" if db_status and bot_status else "degraded",
        "database": db_status,
        "bot": bot_status
    })

@app.get("/anime/{slug}")
async def anime_detail(request: Request, slug: str):
    try:
        anime = await db.get_anime_by_slug(slug)
        if not anime:
            return templates.TemplateResponse("404.html", {"request": request, "error": "Title not found."}, status_code=404)

        categories = await db.get_all_categories()
        episodes = await db.get_episodes(anime["mal_id"])

        return templates.TemplateResponse("details.html", {
            "request": request,
            "anime": anime,
            "episodes": episodes or [],
            "categories": categories or [],
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        })
    except Exception as e:
        logger.error(f"Details page crash: {e}")
        return JSONResponse(status_code=500, content={"error": "Error loading series details."})

@app.get("/api/anime")
async def get_anime_api(skip: int = 0, limit: int = 20):
    try:
        data = await db.get_all_anime(limit=limit, skip=skip)
        return data or []
    except:
        return []

if __name__ == "__main__":
    import uvicorn
    # Use environment PORT for Render
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")
