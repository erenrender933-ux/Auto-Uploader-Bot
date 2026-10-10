import os
import logging
from pyrogram import Client
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)


class AutoUploader(Client):
    def __init__(self):
        super().__init__(
            name="auto_uploader",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins=dict(root="plugins"),
            workers=50,
            sleep_threshold=30,
        )

    async def start(self):
        await super().start()
        me = await self.get_me()
        logging.info(f"Bot started as @{me.username}")

    async def stop(self, *args):
        await super().stop()
        logging.info("Bot stopped")


if __name__ == "__main__":
    AutoUploader().run()
