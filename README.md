# 👑 AniZoneFlix Executive Suite v2.0

AniZoneFlix is an industrial-grade Anime Management Portal and Telegram Bot Suite. Designed for high performance, absolute stability, and an executive user experience, it seamlessly integrates a FastAPI web application with a powerful Pyrogram/Kurigram-based bot supporting native `ButtonStyle` colored inline keyboards.

---

## 🌟 Key Features & Capabilities

### 🎨 Color-Coded Interactive Telegram UI
- **Native Pyrogram/Kurigram `ButtonStyle`:** Full support for colored inline keyboard buttons across all bot menus.
  - 🔵 **PRIMARY (BLUE):** Navigation, search results, menu selection, mode selection, page counters.
  - 🟢 **SUCCESS (GREEN):** Adding groups/boxes/buttons, positive confirmations, and status refreshes.
  - 🔴 **DANGER (RED):** Permanent erasures, deletions, cancellations, closes, and process aborts.

### 📡 Multi-API Intelligence Feed Aggregator
- **Multi-Source Metadata Extraction:** Aggregates metadata automatically from Jikan (MyAnimeList), AniList, Kitsu, TMDB, Shikimori, and Simkl.
- **Auto-Enrichment Engine:** Automatically fills missing synopsis, scores, studio details, genres, and poster artwork on incomplete entries.

### 🤖 Link Batching & Range Link Automation
- **Sequential Genlink Mode:** Sends `/genlink <link>` sequentially for every message ID in a specified range.
- **Serial Batch Automation:** Triggers `/serielbatch` in configured generator bots, responds to range link and filter prompts, and monitors stream output for bulk generated blocks.
- **Multi-Bot Support:** Manage multiple target link generator bot usernames (`/setbot`) and Pyrogram session strings (`/ss`).

### ⚡ 24/7 Bot Uptime Monitoring Suite
- **Continuous Monitoring:** Background service pings registered bot/service URLs continuously every 1 second.
- **Live Status Feed:** Displays real-time HTTP status codes, latency in milliseconds, and online/offline indicators (`/uptime`).

### 🎵 Embedded Web Audio API Engine
- **Background Music Player:** Serves background music uploaded via Telegram (`/songs`) with a Web Audio API gain booster (+300% volume boost).
- **Dedicated Song Channel:** Automatically backs up and syncs audio files to a dedicated Telegram channel.

### 💾 Zero-Data-Loss Database Management
- **Instant Backup:** Export all MongoDB collections into a structured `backup.zip` file (`/save`).
- **One-Click Restore:** Upload a `backup.zip` archive to restore or migrate database records safely.

---

## 🛠 Complete Command Reference

| Command | Usage Syntax | Description |
|---|---|---|
| `/start` | `/start` | Welcome banner, Quick Start guide, Access Portal URL, and Admin Guide button. |
| `/help` | `/help` | Interactive 14-page A to Z Admin Guide with styled navigation buttons (`⬅️ Prev`, `Next ➡️`). |
| `/search` | `/search <title>` | Scans multi-source intelligence feeds and launches interactive page setup wizard. |
| `/post` | `/post <CHANNEL_ID_OR_LINK>` | Configures post channel or publishes formatted announcements with attached page buttons (`📥 Title`). |
| `/add_post` | `/add_post <title>` | One-shot rapid deployment tool to create and publish a series page instantly. |
| `/add_page` | `/add_page [title]` | Guided step-by-step manual page wizard for creating custom entries. |
| `/manual` | `/manual` | Advanced manual creator for title, synopsis, rating, poster URL, and custom button links. |
| `/edit` | `/edit <url/slug>` | Executive Suite for managing seasons, custom boxes, buttons, category, title, artwork, and purge. |
| `/edit_m` | `/edit_m <url/slug>` | Custom Button Management suite for top-level external redirect buttons, custom boxes, and languages. |
| `/change_poster` | `/change_poster <url/slug>` | Swaps poster artwork URL for any series page. |
| `/categories` | `/categories` | Category Console to view, add, or delete genres and tags. |
| `/schedule` | `/schedule [TIME NAME URL]` | Airing Schedule Console for assigning entries to days of the week (Monday - Sunday). |
| `/songs` | `/songs` | Background Music Console to upload, replace, or delete background music tracks. |
| `/uptime` | `/uptime` | 24/7 Bot Uptime Monitoring Suite for checking status and response times of registered services. |
| `/setbot` | `/setbot [@username]` | Configures target link generator bot usernames for range link batching. |
| `/ss` | `/ss [session_string]` | Configures Pyrogram session string for user client automation. |
| `/save` | `/save` | Database Backup (ZIP export) and Restore (ZIP import) interface. |
| `/category_page` | `/category_page <url/slug>` | Migrates an anime page from its current category to any destination category. |
| `/del` | `/del <url/slug>` | Permanently erases an anime entry and its associated data from the database. |
| `/ping` | `/ping` | System latency and MongoDB connectivity diagnostic check. |
| `/cancel` | `/cancel` | Aborts any active wizard flow or input state. |

---

## ⚙️ Environment Variables

| Variable | Required | Description | Example |
|---|---|---|---|
| `API_ID` | **Yes** | Telegram API ID from my.telegram.org | `123456` |
| `API_HASH` | **Yes** | Telegram API Hash from my.telegram.org | `0123456789abcdef0123456789abcdef` |
| `BOT_TOKEN` | **Yes** | Telegram Bot Token from @BotFather | `123456789:ABCdefGHIjklMNOpqrsTUVwxyZ` |
| `MONGO_URI` | **Yes** | MongoDB Atlas connection string | `mongodb+sandbox...` |
| `DB_NAME` | No | Database name (Default: `anizoneflix`) | `anizoneflix` |
| `BASE_URL` | **Yes** | Public HTTP URL of your deployment | `https://my-anizoneflix.onrender.com` |
| `ADMIN_IDS` | **Yes** | Comma-separated list of Telegram Admin User IDs | `123456789,987654321` |
| `LOGO_URL` | No | Default poster image fallback URL | `https://example.com/logo.jpg` |

---

## ☁️ Deployment Guide

### 🚀 Deploying on Render

1. Create a **New Web Service** on Render connected to your repository.
2. Configure **Build & Start Commands:**
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
3. Add the required **Environment Variables** in the Render Dashboard.

---

## 🐳 Docker Deployment

```bash
# Build Docker image
docker build -t anizoneflix .

# Run Docker container
docker run -d -p 10000:10000 --env-file .env --name anizoneflix anizoneflix
```

---

## 📄 License & Disclaimer

This software is developed for administrative management and educational purposes only.

**AniZoneFlix Executive Suite** — *Engineered for Perfection.*
