# 👑 AniZoneFlix Executive Suite v2.0

AniZoneFlix is an advanced, industrial-grade Anime Management Portal and Telegram Bot Suite. Designed for high performance, absolute stability, and a premium user experience, it seamlessly integrates a FastAPI web server with a powerful Pyrogram-based bot.

---

## 🚀 Deployment Guide

### 📦 Prerequisites
- **Python 3.9+**
- **MongoDB Atlas** account
- **Telegram API Credentials** (API ID and Hash from [my.telegram.org](https://my.telegram.org))
- **Bot Token** from [@BotFather](https://t.me/BotFather)

### ☁️ Recommended Deployment: Render
Render is ideal for hosting the entire suite, as it supports the persistent connections required by the Telegram bot.

1.  **Create a New Web Service** on Render.
2.  **Build Settings:**
    - **Runtime:** `Python 3`
    - **Build Command:** `pip install -r requirements.txt`
    - **Start Command:** `python main.py`
3.  **Required Environment Variables:**
    | Variable | Description |
    |----------|-------------|
    | `API_ID` | Your Telegram API ID |
    | `API_HASH` | Your Telegram API Hash |
    | `BOT_TOKEN` | Your Telegram Bot Token |
    | `MONGO_URI` | MongoDB Atlas Connection String |
    | `BASE_URL` | The public URL of your deployment |
    | `ADMIN_IDS` | Comma-separated list of Telegram User IDs for Admin access |
    | `BIN_CHANNEL` | Telegram Channel ID for media storage/forwarding |

---

## 🛠 Features & Architecture

### 🛡 Core Stability & Hardening
- **Unified Event Loop:** Database, Bot, and Web Server share a single async loop to prevent session conflicts.
- **Resilient Database Layer:** Implements intelligent retries and emergency mock collections to ensure the web portal remains online even during database maintenance.
- **Glassmorphism UI:** A modern, premium web interface built with Tailwind CSS, featuring loading skeletons, shimmering effects, and dynamic backdrop blurs.

### 💎 Executive Admin Suite (Telegram Bot)
The bot serves as the central command center for the entire platform:
- **`/search <title>`**: Interactive intelligence-driven setup for new series.
- **`/save`**: Data management interface for instant **Backup** (ZIP export) and **Restore** (ZIP import).
- **`/manual`**: Create custom pages with unlimited direct-access buttons.
- **`/edit <url>`**: Manage content groups, poster art, and series metadata in real-time.
- **`/schedule`**: Centralized management of airing schedules across the network.
- **`/categories`**: Full management of genres and tags.

### 🔍 System Diagnostics
Monitor the health of the system via standardized endpoints:
- **`GET /ping`**: Returns the connectivity status of the bot and database.
- **`HEAD /`**: Lightweight health check for deployment platforms.

---

## 🐳 Docker Deployment
For local development or specialized hosting:
```bash
# Build the image
docker build -t anizoneflix .

# Run the container
docker run -p 10000:10000 --env-file .env anizoneflix
```

---

## ⚖️ License & Disclaimer
This project is for educational and personal use only. The developers are not responsible for any misuse of this software.

**AniZoneFlix** — *Engineered for Perfection.*
