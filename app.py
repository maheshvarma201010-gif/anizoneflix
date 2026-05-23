from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from database.db import db, clean_doc
from config.config import Config
from api.anime_api import anime_api
import os
import logging
import traceback
import asyncio
import sys
import mimetypes
import re
from bot import bot, set_commands, register_handlers
from utils.auth import get_current_admin, verify_token
from utils.utils import slugify
from fastapi.responses import RedirectResponse, JSONResponse, Response, StreamingResponse
from contextlib import asynccontextmanager

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ANIZONEFLIX_APP")

# --- GLOBAL ERROR HANDLING ---

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    logger.info("AniZoneFlix Production Engine starting...")
    try:
        await db.connect()
        if not Config.MONGO_URI:
            # Seed data for testing
            await db.add_anime({
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
            })
            await db.episodes.insert_one({
                "hash": "abc123test",
                "mal_id": "12345",
                "season": 1,
                "episode": 1,
                "episode_title": "Homecoming",
                "quality": "1080p",
                "file_id": "mock_file_id",
                "file_name": "Naruto_S1E1_1080p.mkv",
                "file_size": 1000000,
                "views": 0
            })
        loop = asyncio.get_running_loop()
        bot.loop = loop
        if hasattr(bot, "dispatcher"):
            bot.dispatcher.loop = loop

        def loop_exception_handler(loop, context):
            msg = context.get("exception", context["message"])
            logger.error(f"Async Task Error: {msg}")
        loop.set_exception_handler(loop_exception_handler)

        register_handlers(bot)
        if Config.API_ID and Config.API_HASH and Config.BOT_TOKEN:
            await bot.start()
            await set_commands(bot)
            me = await bot.get_me()
            logger.info(f"Production Suite LIVE -> @{me.username}")
        else:
            logger.warning("Bot credentials missing, skipping bot startup.")
    except Exception as e:
        logger.critical(f"STARTUP FAILURE: {e}")
        logger.error(traceback.format_exc())

    yield

    # SHUTDOWN
    logger.info("Production Engine shutting down...")
    try:
        if bot.is_connected:
            await bot.stop()
        await anime_api.close()
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

# --- APP INITIALIZATION ---

app = FastAPI(title="ANIZONEFLIX", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.filters["slugify"] = slugify
templates.env.globals["Config"] = Config

# --- CUSTOM RESPONSES ---

def safe_api_response(success=True, data=None, message=""):
    return JSONResponse(content={
        "success": success,
        "data": data or [],
        "message": message
    })

# --- ERROR HANDLERS ---

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"ROUTE ERROR: {request.url.path} -> {exc}")
    if "api" in request.url.path:
        return safe_api_response(False, None, "Internal Server Error")
    # CRITICAL: Always use keyword arguments for TemplateResponse
    return templates.TemplateResponse(request=request, name="404.html", context={"error": "Internal Server Error"}, status_code=500)

# --- WEB ROUTES ---

@app.api_route("/", methods=["GET", "HEAD"])
async def index(request: Request):
    if request.method == "HEAD":
        is_healthy = await db.ping() and bot.is_connected
        return Response(status_code=200 if is_healthy else 503)

    try:
        trending = await db.get_all_anime(limit=10)
        recent = await db.get_all_anime(limit=20)
        categories = await db.get_all_categories()

        return templates.TemplateResponse(request=request, name="index.html", context={
            "trending": trending or [],
            "recent": recent or [],
            "categories": categories or [],
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        })
    except Exception as e:
        logger.error(f"Index error: {e}")
        return templates.TemplateResponse(request=request, name="index.html", context={
            "trending": [], "recent": [], "categories": [],
            "logo_url": Config.LOGO_URL, "site_name": "ANIZONEFLIX"
        })

@app.get("/ping")
async def health_ping():
    return safe_api_response(True, {"status": "ok", "db": await db.ping(), "bot": bot.is_connected})

@app.get("/watch")
@app.get("/watch/{path}")
@app.get("/watch/{mal_id}/{slug}")
async def watch_episode(request: Request, path: str = None, mal_id: str = None, slug: str = None):
    ep_hash = request.query_params.get("hash") or path or request.query_params.get("path")
    # Redirect if using old-style links to the new SEO format
    if ep_hash and not slug:
         episode = await db.get_episode_by_hash(ep_hash)
         if episode:
              anime = await db.get_anime_by_mal_id(episode["mal_id"])
              if anime:
                   new_slug = slugify(f"{anime['title']}-episode-{episode['episode']}")
                   return RedirectResponse(url=f"/watch/{episode['mal_id']}/{new_slug}?hash={ep_hash}")

    if not ep_hash: raise HTTPException(status_code=400)

    settings = await db.get_settings()
    if not settings.get("stream_enabled", True):
        return templates.TemplateResponse(request=request, name="404.html", context={"error": "Streaming is currently disabled by administrator."}, status_code=403)

    episode = await db.get_episode_by_hash(ep_hash)
    if not episode: raise HTTPException(status_code=404)

    anime = await db.get_anime_by_mal_id(episode["mal_id"])

    return templates.TemplateResponse(request=request, name="player.html", context={
        "anime": anime,
        "episode": episode,
        "logo_url": Config.LOGO_URL,
        "site_name": "ANIZONEFLIX"
    })

@app.get("/stream/{ep_hash}")
@app.get("/stream/{ep_hash}/{filename}")
async def stream_file(request: Request, ep_hash: str, filename: str = None):
    settings = await db.get_settings()
    if not settings.get("stream_enabled", True):
        raise HTTPException(status_code=403)
    return await stream_media_handler(request, ep_hash, "inline")

async def stream_media_handler(request: Request, ep_id: str, disposition: str):
    try:
        # Explicitly lookup by hash as ep_id is always a token_hex(12)
        episode = await db.get_episode_by_hash(ep_id)
        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")

        file_id = episode.get("file_id")
        if not file_id:
            raise HTTPException(status_code=404, detail="File ID not found")

        # Get file properties from Telegram
        media = None
        if Config.BIN_CHANNEL and episode.get("msg_id"):
            try:
                file_info = await bot.get_messages(Config.BIN_CHANNEL, episode.get("msg_id"))
                if file_info and (file_info.document or file_info.video):
                    media = file_info.document or file_info.video
            except Exception as e:
                logger.error(f"Error fetching message from BIN_CHANNEL: {e}")

        # Fallback to file_id if msg_id failed or BIN_CHANNEL not set
        if not media:
            media = file_id

        # Robust metadata extraction
        if hasattr(media, "file_size"):
            file_size = media.file_size
            file_name = media.file_name or episode.get("file_name") or "video.mp4"
        else:
            file_size = episode.get("file_size")
            file_name = episode.get("file_name") or "video.mp4"

        if not file_size or file_size == "N/A":
             raise HTTPException(status_code=400, detail="File size unknown, cannot stream.")

        file_size = int(file_size)
        mime_type = media.mime_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream"

        # Explicit MKV support
        if file_name.lower().endswith(".mkv"):
            mime_type = "video/x-matroska"

        range_header = request.headers.get("Range")
        start = 0
        end = file_size - 1

        if range_header:
            range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if range_match:
                start = int(range_match.group(1))
                if range_match.group(2):
                    end = int(range_match.group(2))

        content_length = end - start + 1

        # Adaptive chunk sizing based on content length
        if content_length < 100 * 1024 * 1024: # < 100MB
            chunk_size = 512 * 1024
        elif content_length < 500 * 1024 * 1024: # < 500MB
            chunk_size = 1024 * 1024
        else:
            chunk_size = 2 * 1024 * 1024

        async def file_generator():
            try:
                # Optimized chunk size for "Ultra Speed" streaming
                async for chunk in bot.stream_media(media, offset=start, limit=content_length, chunk_size=chunk_size):
                    if chunk:
                        yield chunk
            except Exception as e:
                logger.error(f"Generator Error during stream: {e}")

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Type": mime_type,
            "Content-Disposition": f"{disposition}; filename=\"{file_name}\"",
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Expose-Headers": "Content-Range, Content-Length, Accept-Ranges",
            "Access-Control-Allow-Origin": "*",
        }

        return StreamingResponse(
            file_generator(),
            status_code=206 if range_header else 200,
            headers=headers
        )
    except Exception as e:
        logger.error(f"Streaming Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/schedule")
async def schedule_page(request: Request):
    try:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        schedules = {}
        for day in days:
            schedules[day] = await db.get_schedule(day)

        categories = await db.get_all_categories()
        return templates.TemplateResponse(request=request, name="schedule.html", context={
            "schedules": schedules,
            "categories": categories or [],
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        })
    except Exception as e:
        logger.error(f"Schedule page error: {e}")
        return templates.TemplateResponse(request=request, name="schedule.html", context={
            "schedules": {}, "categories": [],
            "logo_url": Config.LOGO_URL, "site_name": "ANIZONEFLIX"
        })

@app.get("/anime/{slug}")
async def anime_detail(request: Request, slug: str):
    try:
        anime = await db.get_anime_by_slug(slug)
        if not anime:
            return templates.TemplateResponse(request=request, name="404.html", context={"error": "Title not found."}, status_code=404)

        categories = await db.get_all_categories()
        episodes = await db.get_episodes(anime.get("mal_id", "0"))
        settings = await db.get_settings()

        # Sort and clean episodes for display
        clean_episodes = []
        for ep in episodes:
            clean_episodes.append(clean_doc(ep))

        return templates.TemplateResponse(request=request, name="details.html", context={
            "anime": anime,
            "episodes": clean_episodes,
            "categories": categories or [],
            "settings": settings,
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        })
    except Exception as e:
        logger.error(f"Detail error for {slug}: {e}")
        return templates.TemplateResponse(request=request, name="404.html", context={"error": "Database error."}, status_code=500)

@app.get("/api/anime")
async def get_anime_api(skip: int = 0, limit: int = 20):
    try:
        data = await db.get_all_anime(limit=limit, skip=skip)
        return safe_api_response(True, data)
    except Exception as e:
        return safe_api_response(False, None, str(e))

@app.get("/search")
async def search_web(request: Request, q: str = ""):
    try:
        results = []
        if q:
            if await db.ping():
                results = await db.anime.find({"$or": [
                    {"title": {"$regex": q, "$options": "i"}},
                    {"category": q}
                ]}).sort("_id", -1).to_list(length=50)
                results = clean_doc(results)
            else:
                results = []
        else:
            results = await db.get_all_anime(limit=50)

        categories = await db.get_all_categories()
        return templates.TemplateResponse(request=request, name="search.html", context={
            "results": results or [],
            "query": q,
            "categories": categories or [],
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        })
    except Exception as e:
        logger.error(f"Search error: {e}")
        return templates.TemplateResponse(request=request, name="search.html", context={"results": [], "query": q, "categories": []})

@app.get("/az-index")
async def az_index(request: Request):
    try:
        if await db.ping():
            # Fetch all to build index (for production consider aggregation or separate collection if size is massive)
            all_anime = await db.anime.find({}, {"title": 1, "slug": 1}).sort("title", 1).to_list(length=5000)
        else:
            all_anime = []

        indexed_data = {}
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        for char in chars: indexed_data[char] = []
        indexed_data["#"] = []

        for item in all_anime:
            title = item.get("title", "").strip().upper()
            if not title: continue
            first_char = title[0]
            if first_char in chars:
                indexed_data[first_char].append(item)
            elif first_char.isdigit() or not first_char.isalpha():
                indexed_data["#"].append(item)

        categories = await db.get_all_categories()
        return templates.TemplateResponse(request=request, name="az_index.html", context={
            "indexed_data": indexed_data,
            "chars": chars + "#",
            "categories": categories or [],
            "logo_url": Config.LOGO_URL,
            "site_name": "ANIZONEFLIX"
        })
    except Exception as e:
        logger.error(f"AZ Index error: {e}")
        return templates.TemplateResponse(request=request, name="404.html", context={"error": "Index Generation Failed"}, status_code=500)

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
    posts = await db.get_all_anime(limit=100)
    return templates.TemplateResponse(request=request, name="admin_dashboard.html", context={
        "posts": posts or [], "logo_url": Config.LOGO_URL, "site_name": "ANIZONEFLIX"
    })

@app.get("/admin/edit/{mal_id}")
async def edit_post_page(request: Request, mal_id: str, admin=Depends(get_current_admin)):
    try: query_id = int(mal_id)
    except: query_id = mal_id
    anime = await db.get_anime_by_mal_id(query_id)
    if not anime: return RedirectResponse(url="/admin/dashboard")
    return templates.TemplateResponse(request=request, name="edit.html", context={
        "anime": anime, "logo_url": Config.LOGO_URL, "site_name": "ANIZONEFLIX"
    })

@app.post("/api/admin/save/{mal_id}")
async def save_post(request: Request, mal_id: str, admin=Depends(get_current_admin)):
    try:
        data = await request.json()
        try: query_id = int(mal_id)
        except: query_id = mal_id
        if await db.ping():
            await db.anime.update_one({"mal_id": query_id}, {"$set": data})
            return safe_api_response(True)
        return safe_api_response(False, message="Database Offline")
    except Exception as e: return safe_api_response(False, message=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")
