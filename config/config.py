import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID", 22266643))
    API_HASH = os.getenv("API_HASH", "7d0b85b4146034511b8776ed7ff99de4")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "7718434227:AAE8eUh3AxmlmvoSRliSk4k3rzoFnuHubT4")

    # Database Configuration
    MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://hemanthbreaker2027:9550399779htr@cluster0.haybbxg.mongodb.net/?appName=Cluster0")
    DB_NAME = os.getenv("DB_NAME", "movieszoneflix")

    # Core Identity
    BASE_URL = os.getenv("BASE_URL", "https://movieszoneflix.vercel.app")
    PORT = int(os.getenv("PORT", 10000))
    LOGO_URL = os.getenv("LOGO_URL", "https://i.postimg.cc/fy0r3pZN/IMG-20260514-215929-933.jpg")

    # Security & Intelligence
    SECRET_KEY = os.getenv("SECRET_KEY", "ALONEX")
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "ALONEX")
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "8663988850,5778136067,6138776364,7083779209").split(",") if x]
    TMDB_API_KEY = os.getenv("TMDB_API_KEY", "b1048f453055b9944a23e8fd411bb469")
    OMDB_API_KEY = os.getenv("OMDB_API_KEY", "http://www.omdbapi.com/?i=tt3896198&apikey=8c907f89")
    TRAKT_CLIENT_ID = os.getenv("TRAKT_CLIENT_ID", "")
    SIMKL_ID = os.getenv("SIMKL_ID", "f4b817b188dd51674f71293d68c070b61ab05e80220a54e9d4fd6a6368f892a2")

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
