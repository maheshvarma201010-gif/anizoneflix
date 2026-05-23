# 👑 ANIZONEFLIX ULTRA: The Executive Anime Suite

ANIZONEFLIX ULTRA is an industrial-grade, automated anime management portal and Telegram bot suite. Engineered for extreme performance, it transforms Telegram media files into high-speed streaming and download links with a premium web interface.

---

## ⚡ Core Features

### 🚀 Ultra-Speed File-to-Link
- **Zero-Link Admin Flow:** Admins simply send files/videos to the bot. No manual links required.
- **Smart Metadata Extraction:** Automated extraction of **Season**, **Episode**, **Quality** (480p to 4K), **Audio** (Multi/Hindi/Tamil/Telugu), and **Codec** (HEVC/AVC).
- **Persistent Storage:** Integrated `BIN_CHANNEL` support ensuring files remain accessible and links never expire.

### 🎬 Premium Streaming Experience
- **High-Speed Delivery:** Optimized chunked streaming for ultra-fast buffering and zero-stock downloads.
- **Advanced Seeking:** Full support for `Range` requests, enabling instant seeking in web players.
- **Tiered Selection UI:** A modern, multi-step web interface: **Select Season** ➔ **Select Quality** ➔ **Select Episode** ➔ **Watch/Download**.

### 🛰 Intelligence Aggregator
- Instant metadata fetching from **MAL**, **AniList**, **Kitsu**, and **TMDb**.
- Automated series grouping and synchronization.

---

## 🛠 Deployment Guide

### 1. Environment Variables
| Key | Description |
|-----|-------------|
| `API_ID` | Telegram API ID |
| `API_HASH` | Telegram API Hash |
| `BOT_TOKEN` | Bot Token from @BotFather |
| `MONGO_URI` | MongoDB Connection String |
| `BIN_CHANNEL` | ID of the Telegram channel for persistent storage |
| `BASE_URL` | Your application URL (e.g., `https://your-app.onrender.com`) |

### 2. Manual Installation
```bash
# Clone the repository
git clone https://github.com/anizoneflix/suite.git && cd suite

# Install dependencies
pip install -r requirements.txt

# Start the application
python main.py
```

---

## 💎 Bot Command Suite
- `/search <name>`: Rapid series setup with automated metadata calibration.
- `/add_post <name>`: One-shot publication with instant file request.
- `/manual`: Custom creation with unlimited direct access buttons.
- `/categories`: Full CRUD genre management.
- `/schedule`: Centralized airtime synchronization.

**ANIZONEFLIX** — *Powering the next generation of anime streaming.*
