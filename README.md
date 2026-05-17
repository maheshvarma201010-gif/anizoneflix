# 🎬 ANIZONEFLIX ULTRA - Power-Pack Anime CMS

An industrial-grade Anime Management System powered by **FastAPI**, **Pyrogram 2.x**, and a massive **Multi-API Aggregator**. This project provides elite performance, speed, and 100% reliability by connecting to 10+ high-speed anime metadata sources.

## 🚀 Ultra-Performance Features

- **10+ API Aggregator:** Connects to Jikan (MAL), AniList, Kitsu, Shikimori, TMDb, Simkl, MangaDex, and more simultaneously.
- **Fail-Proof Search:** If one API is down, the system instantly falls back to others. No more "Not Found" errors.
- **Parallel Processing:** Search queries are run in parallel for maximum speed.
- **Smart Grouping:** Automatically detects series, seasons, and episodes from filenames.
- **Web Admin Dashboard:** Full control over your posts, custom buttons, and metadata via a secure web interface.
- **High-End UI:** Glassmorphism design, mobile-optimized, and SEO ready.

---

## 🛠️ Bot Commands

### 🛡️ Admin Suite
- `/search <name>` - **ULTRA SEARCH:** Aggregates all APIs and lets you pick the best match.
- `/add_post <name>` - **SPEED MODE:** Instantly publishes the top result to your website.
- `/edit` - Generates a secure, one-click access link to the **Web Admin Panel**.
- `/del <id>` - Instantly remove content from the database and website.
- `/categories` - Manage website genres and navigation.

---

## 🔑 Configuration & APIs

This system is pre-configured with high-speed endpoints. You can further customize them in your `.env`:

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `API_ID` | Telegram API ID | `12345` |
| `API_HASH` | Telegram API Hash | `abcdef...` |
| `BOT_TOKEN` | Bot Token | `12345:token` |
| `TMDB_API_KEY` | High-speed TMDb Key | `3fd2be3efead2b9a05f39645152865e2` |
| `JIKAN_API` | Jikan Base | `https://api.jikan.moe/v4` |

### Integrated APIs:
1. **Jikan (MAL):** Primary source for MAL metadata.
2. **AniList (GraphQL):** High-precision search and covers.
3. **Kitsu.io:** Rapid metadata fallback.
4. **Shikimori:** Russian/Global database powerhouse.
5. **TMDb:** Industry-standard reliability for TV/Anime.
6. **Simkl:** Fast search and posters.
7. **MangaDex:** Title and image fallback.
8. **Notify.moe:** Real-time update source.
9. **Enime:** Metadata API provider.
10. **Consumet:** Content aggregator API.

---

## 🌐 Elite Deployment

1. **GitHub:** Fork and connect your repository to Render.
2. **Runtime:** Select `Python 3.10+`.
3. **Build:** `pip install -r requirements.txt`
4. **Start:** `python main.py`
5. **Healthcheck:** Pre-configured for Render (HEAD /).

---

## 🛡️ Security
- **JWT Authentication:** Secure web admin access.
- **CSRF Protection:** Integrated into the dashboard.
- **Rate Limiting:** Protects your APIs and server.

**Engineered for Speed. Built for Reliability.**
