from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from database.db import db
from plugins.process import PHOTO_WAIT

OWNER = filters.user(Config.OWNER_ID)
THUMB_WAIT: set[int] = set()


@Client.on_message(filters.command("setthumb") & filters.private & OWNER)
async def set_thumb(client: Client, message: Message):
    reply = message.reply_to_message
    if reply and reply.photo:
        await db.set("thumb_file_id", reply.photo.file_id)
        return await message.reply_text("Thumbnail saved.")
    THUMB_WAIT.add(message.from_user.id)
    await message.reply_text("Send the photo to save as the default thumbnail.")


@Client.on_message(filters.private & OWNER & filters.photo, group=2)
async def save_thumb(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in THUMB_WAIT or user_id in PHOTO_WAIT:
        return
    THUMB_WAIT.discard(user_id)
    await db.set("thumb_file_id", message.photo.file_id)
    await message.reply_text("Thumbnail saved. It will be used for all uploads.")


@Client.on_message(filters.command("viewthumb") & filters.private & OWNER)
async def view_thumb(client: Client, message: Message):
    cfg = await db.get()
    if not cfg.get("thumb_file_id"):
        return await message.reply_text("No thumbnail saved.")
    await message.reply_photo(cfg["thumb_file_id"], caption="Saved thumbnail")


@Client.on_message(filters.command("delthumb") & filters.private & OWNER)
async def del_thumb(client: Client, message: Message):
    await db.set("thumb_file_id", None)
    await message.reply_text("Thumbnail removed.")
