# 👑 ANIZONEFLIX ULTRA: Industrial-Grade Anime Suite

ANIZONEFLIX ULTRA is a professional-grade anime management portal and Telegram bot suite. Engineered for absolute performance, it transforms Telegram media into secure, high-speed streaming and download links with a premium "Anime-Style" web interface.

---

## ⚡ Core Features

### 🚀 Ultra-Speed File-to-Link
- **Zero-Link Admin Flow:** Simply send media to the bot. It automatically requests files after title selection.
- **Strict Caption Parser:** Mandatory metadata extraction (**Season**, **Episode**, **Title**, **Quality**) strictly from captions.
- **Persistent Storage:** Integrated `BIN_CHANNEL` ensures permanent link stability.

### 🎬 Advanced Streaming System
- **Secure Hash-Based URLs:** All media accessed via `/watch?path=UNIQUE_HASH`. No File IDs exposed.
- **Modern Anime UI:** Responsive web player with loading animations and screenshot protection.
- **External Player Support:** Instant deep-linking to **VLC**, **MX Player**, and **PlayIt** using direct streaming protocols.
- **Global Toggles:** Admins can enable/disable Streaming and Downloading globally via bot commands.

### 🛡️ Admin Management
- `/manage`: Interactive dashboard to toggle global stream/download visibility.
- Permanent MongoDB settings persistence.

---

## 🛠 Deployment Guide

### 1. Environment Variables
| Key | Description |
|-----|-------------|
| `API_ID` | Telegram API ID |
| `API_HASH` | Telegram API Hash |
| `BOT_TOKEN` | Bot Token |
| `MONGO_URI` | MongoDB Connection String |
| `BIN_CHANNEL` | Telegram ID for file storage |
| `BASE_URL` | Your App URL (e.g., `https://anizone.onrender.com`) |

### 2. Quick Start
```bash
# Clone and install
git clone https://github.com/anizone/suite.git && cd suite
pip install -r requirements.txt

# Run
python main.py
```

---

## 💎 Command Suite
- `/manage`: Global system controls (Stream/Download toggles).
- `/search <name>`: Rapid automated metadata calibration.
- `/add_post <name>`: One-shot series publication.
- `/manual`: Custom button management.

**ANIZONEFLIX** — *Engineered for Perfection.*
