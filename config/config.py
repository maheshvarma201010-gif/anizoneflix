import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH", "")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")

    # Database Configuration
    MONGO_URI = os.getenv("MONGO_URI", "")
    DB_NAME = os.getenv("DB_NAME", "movieszoneflix")

    # Core Identity
    BASE_URL = os.getenv("BASE_URL", "https://movieszoneflix.onrender.com")
    PORT = int(os.getenv("PORT", 10000))
    LOGO_URL = os.getenv("LOGO_URL", "https://telegra.ph/file/0c1737e466395b3531b78.jpg")

    # Security & Intelligence
    SECRET_KEY = os.getenv("SECRET_KEY", "executive-suite-secret-key-v2")
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "admin-api-key")
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
    OMDB_API_KEY = os.getenv("OMDB_API_KEY", "")
    TRAKT_CLIENT_ID = os.getenv("TRAKT_CLIENT_ID", "")
    SIMKL_ID = os.getenv("SIMKL_ID", "")

    DEBUG = os.getenv("DEBUG", "False").lower() == "true"

    @classmethod
    def validate(cls):
        """Validate critical production variables"""
        is_prod = "onrender.com" in cls.BASE_URL
        if is_prod and not cls.MONGO_URI:
            return False, "MONGO_URI is missing in production environment!"
        if not cls.BOT_TOKEN:
            return False, "BOT_TOKEN is missing!"
        return True, "Configuration Validated."
