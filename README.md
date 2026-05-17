# 🎬 ANIZONEFLIX - FastAPI + Pyrogram Anime CMS

A powerful, high-performance Anime CMS and Management Bot built with **FastAPI**, **Pyrogram**, and **MongoDB**. This project allows you to manage an anime streaming website entirely through a Telegram bot.

## 🚀 Key Features

- **FastAPI Web Server:** Glassmorphism UI, SEO optimized, and fast.
- **Pyrogram Bot:** Integrated management for searching, adding, and deleting anime.
- **Automated Posting:** Use `/add_post <name>` to instantly publish anime from Jikan API.
- **Jikan API Integration:** Fetches metadata, images, and trailers automatically.
- **MongoDB Database:** Scalable and robust data storage.
- **Render Ready:** Optimized for seamless deployment on Render.

---

## 🛠️ Commands

### 👤 User Commands
- `/start` - Start the bot and see welcome message.
- `/ping` - Check if the bot is alive.

### 🛡️ Admin Commands
- `/add_post <name>` - **One-shot Auto-Publish:** Fetches first result from Jikan and posts to website.
- `/add_post <name> <image_url>` - Same as above, but uses a custom image URL.
- `/search <name>` - **Interactive Search:** Pick from top 8 results and add links step-by-step.
- `/categories` - Manage website genres/categories.
- `/del <mal_id or url>` - Remove anime from database.
- `/add_admin <user_id>` - Authorize a new admin.
- `/help` - Show full admin guide.

---

## 🔑 Environment Variables

| Variable | Description |
| :--- | :--- |
| `API_ID` | Telegram API ID from [my.telegram.org](https://my.telegram.org) |
| `API_HASH` | Telegram API Hash |
| `BOT_TOKEN` | Bot Token from [@BotFather](https://t.me/BotFather) |
| `MONGO_URI` | MongoDB Connection String |
| `ADMIN_IDS` | Comma-separated list of Admin User IDs |
| `BASE_URL` | Your website URL (e.g. `https://your-site.onrender.com`) |
| `JIKAN_API` | Jikan API Base URL (Default: `https://api.jikan.moe/v4`) |
| `LOGO_URL` | Global site logo URL |

---

## 📚 Jikan API Guide: Step-by-Step

This project uses the **Jikan API**, a free and open-source PHP & REST API for MyAnimeList.net.

### How to set up Jikan API:
1. **No API Key Required:** Jikan v4 is public and does not require a private API key for standard usage.
2. **Endpoint:** By default, the bot uses `https://api.jikan.moe/v4`.
3. **Configuration:**
   - Ensure `JIKAN_API` in your `.env` is set to `https://api.jikan.moe/v4`.
   - If you want to host your own instance (to avoid rate limits), you can follow the [official Jikan installation guide](https://github.com/jikan-me/jikan-rest).
4. **Rate Limits:** The public API has a limit of 3 requests per second and 60 requests per minute. The bot is designed to handle this, but for heavy usage, consider a private instance.

---

## 🌐 Deployment on Render

1. **Create Web Service:** Connect your GitHub repo.
2. **Environment:** Choose `Python`.
3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `python main.py`
5. **Environment Variables:** Fill in all required variables from the table above.
6. **Healthcheck:** Render will automatically ping `/` (HEAD request). Our app is pre-configured to handle this.

---

## 🤝 Contribution

Feel free to fork this repo and submit PRs for any improvements or new features!

**Built with ❤️ for Anime Fans.**
