# 👑 AniZoneFlix Executive Suite v2.0

The world's most advanced Anime Management Portal & Telegram Bot Suite. Engineered for absolute stability, industrial-grade automation, and a premium streaming experience.

---

## 🚀 Deployment Guide

### ☁️ Render Deployment (Full Suite: Web + Bot)
Render is the recommended platform for hosting the combined FastAPI server and Pyrogram long-polling bot.

1.  **Create a New Web Service:**
    *   **Runtime:** `Python 3`
    *   **Build Command:** `pip install -r requirements.txt`
    *   **Start Command:** `python main.py` or `uvicorn app:app --host 0.0.0.0 --port $PORT`

2.  **Environment Variables:**
    | Key | Description |
    |-----|-------------|
    | `API_ID` | Telegram API ID from my.telegram.org |
    | `API_HASH` | Telegram API Hash from my.telegram.org |
    | `BOT_TOKEN` | Bot Token from @BotFather |
    | `MONGO_URI` | MongoDB Atlas Connection String |
    | `TMDB_API_KEY` | TMDb API Key for advanced metadata |
    | `PORT` | Set to `10000` (Render default) |
    | `BASE_URL` | `https://your-app.onrender.com` |

3.  **Health Check:** Set to `/` (HEAD) or `/ping`.

---

### 📐 Vercel Deployment (Frontend Only)
Vercel is optimized for frontend delivery. **Note:** Pyrogram bots will NOT function on Vercel as they require persistent connections.

1.  **Framework:** `FastAPI` (Vercel will detect `app.py`).
2.  **Environment Variables:**
    *   `VITE_BACKEND_URL`: `https://your-render-app.onrender.com` (If using a separate JS frontend).
    *   For this Python-native suite, simply add all variables from the Render list above.

---

### 🐳 Docker Deployment (Parity Environment)
```bash
# Build
docker build -t anizoneflix .

# Run
docker run -p 8080:8080 --env-file .env anizoneflix
```

---

## 🛠 Features & Architecture

### 🛡 Production Hardening
*   **Synchronized Lifespan:** Database, Bot, and API sessions share the same event loop, preventing "Session stopped" errors.
*   **Safe-Fail DB:** Robust retries and `MockCollection` safety prevents 500 errors during cold starts or DB maintenance.
*   **Response Integrity:** All API endpoints return a standardized `{ success, data, message }` JSON schema.
*   **Error-Proof UI:** Jinja2 templates are hardened with existence checks to prevent crashes on missing metadata.

### 🎯 Intelligence Aggregator
High-speed metadata extraction from:
✅ Jikan (MAL) ✅ AniList ✅ Kitsu ✅ TMDb ✅ Simkl

### 💎 Executive Bot Suite
*   `/search <title>`: Interactive intelligence setup with custom metadata calibration.
*   `/manual`: Custom detailed creation with unlimited direct access buttons.
*   `/edit_m <url>`: Manage and append custom buttons to existing posts.
*   `/add_page`: Manual content creation for series metadata.
*   `/edit <url>`: Real-time content group and archive management.
*   `/schedule`: Centralized airtime synchronization across the network.
*   `/categories`: Full CRUD genre management.

---

## 🔍 Industrial-Grade Diagnostics
Monitor system health via `/ping` or the HEAD request on `/`.
*   **Status 200:** System fully operational.
*   **Status 503:** Degraded status (Bot or Database disconnected).

**AniZoneFlix** — *Engineered for Perfection.*
