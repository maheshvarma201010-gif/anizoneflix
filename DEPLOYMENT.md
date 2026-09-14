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
| `BASE_URL` | Your Production URL | `https://anizoneflix.vercel.app` |
| `LOGO_URL` | Website Logo URL | `https://.../logo.png` |

## 2. Vercel Deployment (100% Successful Vercel Support)

Vercel is fully supported out of the box via `vercel.json` and `@vercel/python` serverless functions.

### Configuration Settings for Vercel Project:

- **Framework Preset / Application Preset**: `Other`
- **Build Command**: `pip install -r requirements.txt`
- **Install Command**: `pip install -r requirements.txt`
- **Output Directory**: `.`

### Deployment Steps:
1. Import project into Vercel from Git repository.
2. Select **Framework Preset**: `Other`.
3. Configure Build & Install commands and Output Directory as shown above.
4. Set Environment Variables (`MONGO_URI`, `BOT_TOKEN`, `API_ID`, `API_HASH`, `BASE_URL`, `ADMIN_IDS`).
5. Deploy project.

## 3. Render Deployment (Full Suite)

Render is recommended for hosting both the Web Server and the continuous Telegram Bot process in a single environment.

1. **New Web Service**: Connect your GitHub repository.
2. **Runtime**: `Python 3`
3. **Build Command**: `pip install -r requirements.txt`
4. **Start Command**: `python app.py` (or `python main.py`)
5. **Environment**: Add all variables from Section 1.
6. **Health Check Path**: `/` (Render uses `HEAD` requests, which are supported).

## 4. Manual / Docker Deployment

```bash
# Build
docker build -t anizoneflix .

# Run
docker run -p 10000:10000 --env-file .env anizoneflix
```

## 5. Post-Deployment Verification

1. Access `https://your-app.vercel.app/ping`.
2. Ensure `status` returns `ok`.
3. Open your web portal and check anime listing and details routes.
