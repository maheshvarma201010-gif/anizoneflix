# 🎬 ANIZONEFLIX ULTRA v2.0 - High-End Anime CMS

The ultimate, industrial-grade Anime Management System powered by **FastAPI**, **Pyrogram 2.x**, and a massive **Multi-API Aggregator**. This project provides elite performance, speed, and a high-end Telegram-themed UI.

## 🚀 v2.0 Ultra Features

- **Multi-API Aggregator:** Connects to 11+ high-speed sources (Jikan, AniList, Kitsu, Shikimori, TMDb, etc.).
- **Interactive Multi-Season Flow:** Effortlessly add multiple seasons (e.g., '1,2,3') in one go.
- **Separate Quality Links:** Dedicated slots for 480p, 720p, and 1080p links per season.
- **Custom Poster Choice:** Choose between automated API posters or provide your own manual URL.
- **Telegram-Themed Glassmorphism UI:** A beautiful, dark, and modern streaming interface.
- **Infinite Scroll Pagination:** Automated loading for unlimited anime listings.
- **Secure Web Admin:** JWT-authenticated dashboard for full control over metadata and buttons.

## 🛠️ Updated Bot Commands

### 🛡️ Admin Suite
- `/search <name>` - **ULTRA SEARCH:** Interactive setup with season and quality link collection.
- `/add_post <name>` - **SPEED MODE:** Instant one-shot publication to a selected category.
- `/edit` - Secure one-click login link for the **Web Admin Panel**.
- `/series <slug>` - View and verify all loaded episodes for a specific series.
- `/help` - Open the detailed v2.0 Admin Guide.

## 🔑 Environment Setup

Ensure the following are set in your Render environment:

| Variable | Description |
| :--- | :--- |
| `API_ID` | Telegram API ID |
| `API_HASH` | Telegram API Hash |
| `BOT_TOKEN` | Telegram Bot Token |
| `MONGO_URI` | MongoDB Connection String |
| `SECRET_KEY` | For JWT & Encryption (Min 32 chars recommended) |
| `BASE_URL` | Your website URL |

## 🌐 Elite Deployment

1. **GitHub:** Connect your repo to Render.
2. **Build:** `pip install -r requirements.txt`
3. **Start:** `python main.py`
4. **Auto-Optimization:** System automatically adjusts to Render's infrastructure.

**Engineered for Speed. Designed for Excellence.**
