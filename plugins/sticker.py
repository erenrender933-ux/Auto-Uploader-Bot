from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from database.db import db

OWNER = filters.user(Config.OWNER_ID)
STICKER_WAIT: set[int] = set()


@Client.on_message(filters.command("setsticker") & filters.private & OWNER)
async def set_sticker(client: Client, message: Message):
    reply = message.reply_to_message
    if reply and reply.sticker:
        await db.set("sticker_file_id", reply.sticker.file_id)
        return await message.reply_text("Sticker saved.")
    STICKER_WAIT.add(message.from_user.id)
    await message.reply_text("Send the sticker now.")


@Client.on_message(filters.private & OWNER & filters.sticker)
async def save_sticker(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in STICKER_WAIT:
        return
    STICKER_WAIT.discard(user_id)
    await db.set("sticker_file_id", message.sticker.file_id)
    await message.reply_text(
        "Sticker saved. It will be sent after every episode post "
        "in the main channels and the primary channel."
    )


@Client.on_message(filters.command("delsticker") & filters.private & OWNER)
async def del_sticker(client: Client, message: Message):
    await db.set("sticker_file_id", None)
    await message.reply_text("Sticker removed.")
