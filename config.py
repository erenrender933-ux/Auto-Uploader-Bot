import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    API_ID = int(os.getenv("API_ID", 0))
    WATCH_LINK = os.getenv("WATCH_LINK", "https://t.me/Anime_Hub_Tamil")
    PRIMARY_CHANNEL = int(os.getenv("PRIMARY_CHANNEL", 0))
    API_HASH = os.getenv("API_HASH", "")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    OWNER_ID = int(os.getenv("OWNER_ID", 0))
    DB_CHANNEL = int(os.getenv("DB_CHANNEL", 0))
    FILESTORE_BOT = os.getenv("FILESTORE_BOT", "")

    MONGO_URI = os.getenv("MONGO_URI", "")
    DB_NAME = os.getenv("DB_NAME", "AutoUploader")

    # Defaults (can be changed from the bot later)
    MAIN_CHANNELS = [
        int(x) for x in (
            os.getenv("MAIN_CHANNEL_1"),
            os.getenv("MAIN_CHANNEL_2"),
        ) if x
    ]
    TARGET_CHANNEL = int(os.getenv("TARGET_CHANNEL", 0))
    JOIN_LINK = os.getenv("JOIN_LINK", "https://t.me/Anime_Hub_Tamil")

    DOWNLOAD_DIR = "downloads"
    WATERMARK_TEXT = "Animes Tamil Hub"
