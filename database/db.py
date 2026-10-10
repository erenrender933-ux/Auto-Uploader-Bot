from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

DEFAULTS = {
    "_id": "global",
    "target_channel": Config.TARGET_CHANNEL,
    "main_channels": Config.MAIN_CHANNELS,
    "join_link": Config.JOIN_LINK,
    "watermark_enabled": True,
    "watermark_text": Config.WATERMARK_TEXT,
    "rename_enabled": True,
    "rename_format": "[AnimesTamilHub] {title} S{season}E{episode} [{quality}] [{language}]",
    "metadata_enabled": True,
    "metadata_title": "Animes Tamil Hub",
    "metadata_author": "@Anime_Hub_Tamil",
    "db_channel": Config.DB_CHANNEL,
    "filestore_bot": Config.FILESTORE_BOT,
}


class Database:
    def __init__(self):
        self.client = AsyncIOMotorClient(Config.MONGO_URI)
        self.db = self.client[Config.DB_NAME]
        self.settings = self.db["settings"]

    async def get(self) -> dict:
        doc = await self.settings.find_one({"_id": "global"})
        if not doc:
            await self.settings.insert_one(DEFAULTS.copy())
            doc = DEFAULTS.copy()
        # fill missing keys after updates
        for key, value in DEFAULTS.items():
            doc.setdefault(key, value)
        return doc

    async def set(self, key: str, value):
        await self.settings.update_one(
            {"_id": "global"}, {"$set": {key: value}}, upsert=True
        )

    async def add_main_channel(self, chat_id: int):
        await self.settings.update_one(
            {"_id": "global"},
            {"$addToSet": {"main_channels": chat_id}},
            upsert=True,
        )

    async def remove_main_channel(self, chat_id: int):
        await self.settings.update_one(
            {"_id": "global"}, {"$pull": {"main_channels": chat_id}}
        )


db = Database()
