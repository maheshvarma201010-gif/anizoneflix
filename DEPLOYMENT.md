# 🛠 Technical Deployment Specification

This document details the industrial-grade configurations required for a 100% success rate on Render and Vercel.

## 📦 Dependency Manifest
The system requires `Python 3.10+`. Core dependencies:
- `fastapi`, `uvicorn`, `jinja2`: Web Engine
- `pyrogram`, `tgcrypto`: Intelligence Suite
- `motor`, `dnspython`: Persistence Layer
- `PyJWT`, `cryptography`: Executive Authorization
- `aiohttp`: High-speed API aggregation

## ☁️ Render Optimization
Render's shared event loop can cause "PingTask stopped" errors if not handled correctly.
- **Fix Applied:** The system uses a single `lifespan` context to unify the event loop for Database, Bot, and Web.
- **Port Binding:** Automatically detects `$PORT` from environment.
- **Keep-Alive:** Health check endpoint `/ping` prevents free-tier idling during active hours.

## 📐 Vercel Frontend Configuration
If deploying a decoupled JS frontend (React/Vue/Vite) against this backend:
1.  Add `VITE_BACKEND_URL=https://your-render-app.onrender.com` to Vercel env.
2.  Enable CORS (already enabled in this backend via `CORSMiddleware`).

## 🔑 Administrative Environment
| Category | Variable | Required |
|----------|----------|----------|
| **Core** | `API_ID`, `API_HASH`, `BOT_TOKEN` | YES |
| **Database** | `MONGO_URI` | YES |
| **Identity** | `BASE_URL` | YES |
| **Security** | `SECRET_KEY`, `ADMIN_API_KEY` | YES |
| **Intelligence** | `TMDB_API_KEY` | YES |

## 🚀 Build Command
```bash
pip install --upgrade pip && pip install -r requirements.txt
```

## 🎬 Start Command
```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

---
*Engineered by AniZoneFlix for Executive Production Environments.*
