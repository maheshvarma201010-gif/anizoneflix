# 💎 MoviesZoneFlix — Premium Entertainment & Media Management Hub 🎥

Welcome to **MoviesZoneFlix**, the ultimate high-performance streaming info portal, metadata aggregator, and Telegram bot suite. Built for speed, elegance, and extreme visual fidelity across all devices.

---

## ✨ Key Features & Enhancements

### 🎨 Cinematic Premium UI/UX
- **Elite Dark Mode Theme:** Deep fluid backgrounds (`#050505`) highlighted with neon red and gold gradient accents.
- **Perfect Aspect Ratio Controls:** Complete scaling protection for landscape and portrait posters, backdrops, and video thumbnails. No clipping, stretching, or unexpected shifting.
- **Glassmorphic Interactive Components:** Sophisticated hover cards, modern slide structures, unified pagination, and sleek tab switching (Downloads, Metadata, Reviews, Similar titles).
- **Infinite Layout Smoothness:** 100% horizontal scroll protection with custom overflow management, fluid lazy image transitions, and premium pulsing countdown timers.

### 🌐 Advanced Multi-API Integrations
Fully integrated and synced metadata services with resilient, persistent database fallback modes:
- **TMDb (The Movie Database):** Deep search capabilities, dynamic synopsis, backdrops, poster art, and media categorizations.
- **TVmaze:** Robust television series indexing, episode trackers, and fallback artwork support.
- **OMDb:** High-performance IMDB rating overlays and extended media specifications.
- **Trakt.tv:** Unified social insights, reviews, and community comments.

### 👑 Premium Telegram Management Bot Core
A highly polished management tool loaded with rich emojis and optimized conversational pipelines:
- **🔍 `/search <query>`** — Search and import rich metadata directly from TMDb with zero manual hassle.
- **✏️ `/edit <url/slug>`** — Modify posters, descriptions, runtime, scores, trailers, and release year.
- **📂 Category Move Option** — Fully integrated in both `/edit` and `/edit_m` panels to seamlessly re-classify media across genres.
- **🔗 `/edit_m <url/slug>`** — Complete file-mirror and server manager.
- **🎬 `/add_movie` & 📺 `/add_series`** — Manual override options for customized entries.
- **🗑️ `/del <url/slug>`** — Secure purging from MongoDB.
- **📢 `/posttochannel <id> <link>`** — Instantly publish structured, beautiful cards to your Telegram channels.
- **💾 `/save`** — Export full database backups or restore JSON structures.
- **📡 `/ping`** — Dynamic latency check.
- **❌ `/cancel`** — Instantly reset active chat flows.

### 💾 Safe Persistence & MongoDB Sync
- Removed startup data deletion: your database syncs smoothly with `MONGO_URI` while maintaining total data integrity.
- Resilient offline fallback seeding: launches in mock-mode with TVmaze samples when Atlas is unreachable.

---

## 🚀 Vercel Deployment Guide (100% Successful Deployment Support)

MoviesZoneFlix fully supports seamless, 100% successful zero-error deployment on **Vercel** serverless infrastructure using the `@vercel/python` builder and serverless entry point (`api/index.py`).

### ⚙️ Vercel Project Settings

When importing or configuring your project on Vercel, set the following exact build & deployment settings:

| Setting | Exact Value |
| :--- | :--- |
| **Application Preset** | `Other` |
| **Build Command** | `pip install -r requirements.txt` |
| **Install Command** | `pip install -r requirements.txt` |
| **Output Directory** | `.` |

---

### 🔑 Environment Variables

Configure the following environment variables in your Vercel Project Settings:

```env
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/dbname
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyZ
API_ID=123456
API_HASH=abcdef1234567890abcdef1234567890
ADMIN_USER=admin
ADMIN_PASS=supersecretpassword
JWT_SECRET=your_jwt_secret_here
TMDB_API_KEY=your_tmdb_api_key
OMDB_API_KEY=your_omdb_api_key
TRAKT_CLIENT_ID=your_trakt_client_id
```

---

## 🛠️ Local Installation & Technical Specifications

### Tech Stack
- **Backend Core:** FastAPI, Uvicorn, Python 3.10+
- **Database Layer:** Motor (Async MongoDB), MongoDB Atlas
- **Telegram Bot Suite:** Pyrogram / Kurigram (with Pyromod interactive prompting)
- **Design & Interface:** Jinja2, TailwindCSS, JavaScript (ES6+), SwiperJS

### Local Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/MoviesZoneFlix.git
   cd MoviesZoneFlix
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run tests:
   ```bash
   pytest
   ```
4. Start the launcher:
   ```bash
   python main.py
   ```

---
*An elite production-ready design crafted with perfection by Jules.*
