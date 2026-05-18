# 🚀 AniZoneFlix Production Deployment Guide

This guide ensures a stable, error-free deployment of the **AniZoneFlix Executive Suite** on Render and Vercel.

---

## 🛠 Prerequisites
- **MongoDB Atlas:** A cluster URI (e.g., `mongodb+srv://...`).
- **Telegram Bot:** `API_ID`, `API_HASH`, and `BOT_TOKEN` from [@BotFather](https://t.me/BotFather) and [my.telegram.org](https://my.telegram.org).
- **TMDb:** An API Key for advanced metadata.

---

## ☁️ Render Deployment (Recommended)

Render is the primary target for this system due to its native support for long-running Python services and persistent event loops.

### 1. Create a "Web Service"
- **Runtime:** `Python 3`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python main.py` or `uvicorn app:app --host 0.0.0.0 --port $PORT`

### 2. Environment Variables (CRITICAL)
Add these in the Render Dashboard:
| Key | Value |
|-----|-------|
| `API_ID` | Your Telegram API ID |
| `API_HASH` | Your Telegram API Hash |
| `BOT_TOKEN` | Your Bot Token |
| `MONGO_URI` | Your MongoDB Atlas URI |
| `TMDB_API_KEY` | Your TMDb Key |
| `BASE_URL` | `https://your-app.onrender.com` |
| `PORT` | `10000` |

### 3. Health Check
- **Endpoint:** `/` (Method: `HEAD`) or `/ping`
- Render will automatically monitor this to ensure the bot/DB are connected.

---

## 📐 Vercel Deployment

Vercel is suitable for the **Web Frontend** only. Because Pyrogram requires a permanent connection for long polling, the **Bot will NOT work on Vercel Serverless Functions**.

### 1. Configuration
- **Framework Preset:** `FastAPI`
- **Output Directory:** `.`

### 2. Requirements
Vercel requires a `vercel.json` and uses `api/index.py` naming by default. For this project, it is better to use Render for the full suite.

---

## 🐳 Docker Deployment (Universal)

For 100% environment parity, use the included Dockerfile.

### 1. Build
```bash
docker build -t anizoneflix .
```

### 2. Run
```bash
docker run -p 8080:8080 --env-file .env anizoneflix
```

---

## 🔍 Troubleshooting Fixes
- **500 Error on Schedule:** The system now returns "No data" instead of crashing. Ensure you have used `/schedule` in the bot at least once.
- **Bot Not Responding:** Check Render logs for `STARTUP FAILURE`. Ensure `API_ID` and `API_HASH` are correct.
- **Database Failure:** The system retries 5 times. If it fails, verify that your IP is whitelisted in MongoDB Atlas.

**AniZoneFlix Executive Suite v2.0**
*Engineered for Absolute Stability.*
