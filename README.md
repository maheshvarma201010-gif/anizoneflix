# 🎥 ANIZONEFLIX - Full Stack Anime Platform (V1.0)

ANIZONEFLIX is a high-performance, professional anime website and Telegram bot system. It allows admins to search for anime metadata via the Jikan API and publish content instantly to a beautiful glassmorphism-themed website.

---

## 🚀 Key Features

- **High-End UI:** Modern dark theme with glassmorphism, trending carousels, and smooth animations.
- **Automated Bot Flow:** Search -> Select -> Details -> Season -> Links -> Publish.
- **Dynamic Branding:** LOGO_URL and Name globally controlled via Environment Variables.
- **SEO Optimized:** Fast loading with clean meta tags for better search visibility.
- **Mobile Responsive:** Fully functional sidebar and navigation on all mobile devices.
- **Production Ready:** Pre-configured for Render, Docker, and Railway.

---

## 🛠 Step-by-Step Deployment Guide (Render)

### Phase 1: Obtain Your Credentials

1.  **Telegram API Credentials:**
    - Go to [my.telegram.org](https://my.telegram.org).
    - Login and click on **API Development tools**.
    - Create an app (if not already done).
    - Copy your `API_ID` and `API_HASH`.

2.  **Telegram Bot Token:**
    - Open Telegram and message [@BotFather](https://t.me/BotFather).
    - Send `/newbot`, choose a name and username.
    - Copy the `BOT_TOKEN` provided.

3.  **MongoDB URI:**
    - Sign up at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas).
    - Create a **Free Cluster**.
    - Go to **Network Access** -> **Add IP Address** -> Select **Allow Access From Anywhere (0.0.0.0/0)**.
    - Go to **Database Access** -> Create a User with a password.
    - Go to **Clusters** -> **Connect** -> **Connect your application**.
    - Copy the connection string. Replace `<password>` with your actual password. This is your `MONGO_URI`.

4.  **Admin ID:**
    - Message [@userinfobot](https://t.me/userinfobot) on Telegram.
    - Copy your numeric ID. This is your `ADMIN_IDS`.

### Phase 2: Deploy to Render

1.  **Fork/Upload:** Ensure this repository is in your GitHub account.
2.  **Create Web Service:**
    - Log in to [Render](https://render.com).
    - Click **New +** -> **Web Service**.
    - Connect your GitHub repository.
3.  **Configuration:**
    - **Name:** `anizoneflix`
    - **Runtime:** `Docker`
    - **Instance Type:** `Free` (or higher)
4.  **Environment Variables:** Click **Advanced** -> **Add Environment Variable** for each:
    - `API_ID`: (Your Telegram API ID)
    - `API_HASH`: (Your Telegram API Hash)
    - `BOT_TOKEN`: (Your Telegram Bot Token)
    - `MONGO_URI`: (Your MongoDB Connection String)
    - `ADMIN_IDS`: (Your numeric Telegram ID)
    - `LOGO_URL`: (Direct link to your logo image, e.g., `https://i.imgur.com/example.png`)
    - `BASE_URL`: (Your website URL, e.g., `https://anizoneflix.onrender.com`)
    - `JIKAN_API`: `https://api.jikan.moe/v4`
    - `SECRET_KEY`: (Any random text)
    - `ADMIN_API_KEY`: (Any random text)
5.  **Click Deploy!** Render will build the Docker image and start the bot and website together.

---

## 🤖 Telegram Bot Usage

Only authorized **Admins** can use the bot.

### Core Commands
- `/start` - Check if bot is alive.
- `/search <name>` - Search for anime and start the adding flow.
- `/categories` - Add or remove website genres.
- `/del <id/url>` - Remove an entry (Paste MAL ID or the Website Link).
- `/help` - View all admin commands.

### The "Adding" Flow (Sequential)
1. Send `/search One Piece`.
2. Pick the correct result by replying with its **number** (e.g., `1`).
3. The bot fetches full details automatically.
4. Enter **Season Number** (e.g., `1`).
5. Enter **480p Link** (or click **Skip**).
6. Enter **720p Link** (or click **Skip**).
7. Enter **1080p Link** (or click **Skip**).
8. Enter **Batch Link** (or click **Skip**).
9. Enter **YouTube Trailer** link (or click **Skip**).
10. **Done!** The bot provides the live link to your website.

---

## 📁 Repository Structure

```text
anizoneflix-repo/
├── bot/                # Telegram Bot package
│   └── __init__.py     # Core Bot logic, Commands, Handlers
├── api/                # Jikan API wrapper
├── database/           # MongoDB Motor integration
├── static/             # Frontend Assets (CSS/JS/Images)
├── templates/          # HTML Templates (Jinja2)
├── config/             # Environment configuration
├── main.py             # Entry Point (Unified Bot + Web)
├── bot.py              # Bot proxy entry
├── app.py              # FastAPI app definition
├── Dockerfile          # Container build config
└── render.yaml         # Render blueprint
```

---

## 🔧 Troubleshooting

- **Bot not responding?**
    1. Send `/ping` to the bot. If it replies "Pong!", the bot is active.
    2. Check Render logs. If you see "Bot started", but no response, ensure `ADMIN_IDS` includes your ID.
    3. Verify your `API_ID` and `API_HASH` are correct from `my.telegram.org`.
- **MongoDB error?**
    1. Ensure your IP Whitelist in Atlas is set to `0.0.0.0/0`.
    2. Check that your `MONGO_URI` includes the correct password and database name.
- **UI not loading?**
    1. Check `BASE_URL` is set correctly in environment variables.
    2. Ensure the port is automatically handled by Render (Docker exposed on 8000).

---

**Developed for ANIZONEFLIX.** Built with ❤️ for Anime Fans.
