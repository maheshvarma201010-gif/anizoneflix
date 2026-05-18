# AniZoneFlix Production Deployment Guide

This guide provides instructions for deploying the AniZoneFlix executive suite to production environments.

## 1. Environment Variables

Ensure the following variables are set in your deployment environment:

| Variable | Description | Example |
| :--- | :--- | :--- |
| `API_ID` | Telegram API ID | `1234567` |
| `API_HASH` | Telegram API Hash | `abcdef123456...` |
| `BOT_TOKEN` | Telegram Bot Token | `1234:ABC-DEF...` |
| `MONGO_URI` | MongoDB Atlas Connection String | `mongodb+srv://...` |
| `ADMIN_IDS` | Comma-separated Admin Telegram IDs | `12345678,87654321` |
| `BASE_URL` | Your Production URL | `https://anizoneflix.onrender.com` |
| `LOGO_URL` | Website Logo URL | `https://.../logo.png` |

## 2. Render Deployment (Full Suite)

Render is recommended for hosting both the Web Server and the Telegram Bot in a single environment.

1. **New Web Service**: Connect your GitHub repository.
2. **Runtime**: `Python 3`
3. **Build Command**: `pip install -r requirements.txt`
4. **Start Command**: `python app.py`
5. **Environment**: Add all variables from Section 1.
6. **Health Check Path**: `/` (Render uses `HEAD` requests, which are supported).

## 3. Vercel Deployment (Frontend Only)

If you wish to host the frontend separately:

1. **Build Command**: None (Static files are served directly by the backend).
2. **Note**: Since this is a FastAPI application, Vercel requires a `vercel.json` configuration for Serverless Functions if you are not using the Render approach.

## 4. Manual / Docker Deployment

```bash
# Build
docker build -t anizoneflix .

# Run
docker run -p 10000:10000 --env-file .env anizoneflix
```

## 5. Post-Deployment Verification

1. Access `https://your-app.onrender.com/ping`.
2. Ensure `db` and `bot` status are both `true`.
3. Open your Telegram Bot and send `/start`.
4. Verify that `/search` returns results from the multi-API aggregator.
