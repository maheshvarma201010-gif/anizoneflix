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
import re
from bot import bot, set_commands, register_handlers
from utils.auth import get_current_admin, verify_token
from utils.utils import slugify
from fastapi.responses import RedirectResponse, JSONResponse, Response, StreamingResponse
from contextlib import asynccontextmanager
from urllib.parse import quote

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MZ_APP")

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
    logger.info("MoviesZoneFlix Production Engine starting...")
    try:
        await db.connect()
        loop = asyncio.get_running_loop()
        bot.loop = loop
        if hasattr(bot, "dispatcher"):
            bot.dispatcher.loop = loop

        def loop_exception_handler(loop, context):
            msg = context.get("exception", context["message"])
            logger.error(f"Async Task Error: {msg}")
        loop.set_exception_handler(loop_exception_handler)

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
        await anime_api.close()
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

# --- APP INITIALIZATION ---

app = FastAPI(title="MOVIESZONEFLIX", lifespan=lifespan)

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
            "site_name": "MoviesZoneFlix"
        })
    except Exception as e:
        logger.error(f"Index error: {e}")
        return templates.TemplateResponse(request=request, name="index.html", context={
            "trending": [], "recent": [], "categories": [],
            "logo_url": Config.LOGO_URL, "site_name": "MoviesZoneFlix"
        })

@app.get("/ping")
async def health_ping():
    return safe_api_response(True, {"status": "ok", "db": await db.ping(), "bot": bot.is_connected})

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
            "site_name": "MoviesZoneFlix"
        })
    except Exception as e:
        logger.error(f"Schedule page error: {e}")
        return templates.TemplateResponse(request=request, name="schedule.html", context={
            "schedules": {}, "categories": [],
            "logo_url": Config.LOGO_URL, "site_name": "MoviesZoneFlix"
        })

@app.get("/anime/{slug}")
async def anime_detail(request: Request, slug: str):
    try:
        anime = await db.get_anime_by_slug(slug)
        if not anime:
            return templates.TemplateResponse(request=request, name="404.html", context={"error": "Title not found."}, status_code=404)

        categories = await db.get_all_categories()

        # Check admin for drafts
        token = request.cookies.get("admin_token")
        is_admin = False
        if token:
            try:
                payload = verify_token(token)
                is_admin = payload and payload.get("is_admin")
            except: pass

        episodes = await db.get_episodes(anime.get("mal_id", "0"), status=None if is_admin else "published")

        return templates.TemplateResponse(request=request, name="details.html", context={
            "anime": anime,
            "episodes": episodes or [],
            "categories": categories or [],
            "logo_url": Config.LOGO_URL,
            "site_name": "MoviesZoneFlix"
        })
    except Exception as e:
        logger.error(f"Detail error for {slug}: {e}")
        return templates.TemplateResponse(request=request, name="404.html", context={"error": "Database error."}, status_code=500)

@app.get("/watch/{aid}/{slug}")
async def watch_page(request: Request, aid: str, slug: str, hash: str = None):
    try:
        anime = await db.get_anime(aid)
        if not anime: return RedirectResponse("/")

        episode = None
        if hash:
            episode = await db.get_episode_by_hash(hash)

        if not episode:
            eps = await db.get_episodes(anime["mal_id"], status="published")
            if not eps: return RedirectResponse(f"/anime/{anime['slug']}")
            episode = eps[0]

        stream_url = f"{Config.BASE_URL}/stream/{episode['hash']}"
        return templates.TemplateResponse(request=request, name="watch.html", context={
            "anime": anime,
            "episode": episode,
            "stream_url": stream_url,
            "logo_url": Config.LOGO_URL,
            "site_name": "MoviesZoneFlix"
        })
    except Exception as e:
        logger.error(f"Watch Error: {e}")
        return RedirectResponse("/")

@app.get("/stream/{hash}")
@app.get("/stream/{hash}/{filename}")
async def stream_media_handler(request: Request, hash: str, filename: str = None):
    try:
        if not bot.is_connected:
            try: await bot.start()
            except: pass

        episode = await db.get_episode_by_hash(hash)
        if not episode: raise HTTPException(status_code=404)

        file_id = episode.get("file_id")
        if not file_id: raise HTTPException(status_code=404)

        # Proxy from Telegram
        file_info = await bot.get_messages(Config.BIN_CHANNEL, episode.get("msg_id", 0))
        media = file_info.document or file_info.video
        if not media: raise HTTPException(status_code=404)

        file_size = media.file_size
        range_header = request.headers.get("Range")

        start, end = 0, file_size - 1
        if range_header:
            match = re.search(r"bytes=(\d+)-(\d*)", range_header)
            if match:
                start = int(match.group(1))
                if match.group(2):
                    end = int(match.group(2))

        chunk_size = 1024 * 1024 # 1MB default
        if file_size < 100 * 1024 * 1024: chunk_size = 512 * 1024
        elif file_size > 500 * 1024 * 1024: chunk_size = 2 * 1024 * 1024

        async def stream_generator():
            try:
                # Pyrogram stream_media uses 1MB chunks. offset/limit are in chunks.
                chunk_size = 1024 * 1024
                offset_chunks = start // chunk_size
                skip_bytes = start % chunk_size
                bytes_to_read = end - start + 1
                bytes_read = 0

                async for chunk in bot.stream_media(media, offset=offset_chunks):
                    if skip_bytes > 0:
                        chunk = chunk[skip_bytes:]
                        skip_bytes = 0

                    if bytes_read + len(chunk) > bytes_to_read:
                        chunk = chunk[:bytes_to_read - bytes_read]

                    yield chunk
                    bytes_read += len(chunk)

                    if bytes_read >= bytes_to_read:
                        break
            except Exception as e:
                logger.error(f"Stream generation error: {e}")

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Content-Type": media.mime_type or "video/mp4",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Range, Content-Length, Accept-Ranges",
            "Content-Disposition": f'inline; filename="{quote(episode.get("file_name", "video.mp4"))}"'
        }

        return StreamingResponse(stream_generator(), status_code=206 if range_header else 200, headers=headers)
    except Exception as e:
        logger.error(f"Streaming route failure: {e}")
        raise HTTPException(status_code=500)

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
            "site_name": "MoviesZoneFlix"
        })
    except Exception as e:
        logger.error(f"Search error: {e}")
        return templates.TemplateResponse(request=request, name="search.html", context={"results": [], "query": q, "categories": []})

@app.get("/dl")
async def download_redirect(url: str):
    if not url: return RedirectResponse(url="/")
    return RedirectResponse(url=url)

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
            "site_name": "MoviesZoneFlix"
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
        "posts": posts or [], "logo_url": Config.LOGO_URL, "site_name": "MoviesZoneFlix"
    })

@app.get("/admin/edit/{mal_id}")
async def edit_post_page(request: Request, mal_id: str, admin=Depends(get_current_admin)):
    try: query_id = int(mal_id)
    except: query_id = mal_id
    anime = await db.get_anime_by_mal_id(query_id)
    if not anime: return RedirectResponse(url="/admin/dashboard")
    return templates.TemplateResponse(request=request, name="edit.html", context={
        "anime": anime, "logo_url": Config.LOGO_URL, "site_name": "MoviesZoneFlix"
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
