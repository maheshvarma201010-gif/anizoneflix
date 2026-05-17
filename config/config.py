import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH", "")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    MONGO_URI = os.getenv("MONGO_URI", "")
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    JIKAN_API = os.getenv("JIKAN_API", "https://api.jikan.moe/v4")
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "admin-api-key")
    LOGO_URL = os.getenv("LOGO_URL", "https://telegra.ph/file/0c1737e466395b3531b78.jpg")
    BASE_URL = os.getenv("BASE_URL", "https://anizoneflix.onrender.com")
    DB_NAME = "anizoneflix"
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
