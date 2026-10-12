from pyrogram import Client, filters
from pyrogram.types import Message
from helpers.ffmpeg_tools import LANG_CODES

from config import Config
from database.db import db

OWNER = filters.user(Config.OWNER_ID)


def arg(message: Message) -> str:
    parts = message.text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def onoff(value: bool) -> str:
    return "ON" if value else "OFF"


@Client.on_message(filters.command("settings") & filters.private & OWNER)
async def show_settings(client: Client, message: Message):
    cfg = await db.get()
    mains = "\n".join(f"  <code>{c}</code>" for c in cfg["main_channels"]) or "  None"
    await message.reply_text(
        "<b>Settings</b>\n\n"
        f"<b>Target channel:</b> <code>{cfg['target_channel']}</code>\n"
        f"<b>Main channels:</b>\n{mains}\n"
        f"<b>Primary channel:</b> <code>{cfg.get('primary_channel')}</code>\n"
        f"<b>Watch link:</b> {cfg.get('watch_link')}\n"
        f"<b>Keep language:</b> {cfg.get('keep_language') or 'OFF (keep all)'}\n"
        f"<b>Audio track:</b> {cfg.get('audio_track') or 'OFF'}\n"
        f"<b>File store bot:</b> @{cfg['filestore_bot']}\n"
        f"<b>Join link:</b> {cfg['join_link']}\n\n"
        f"<b>Watermark:</b> {onoff(cfg['watermark_enabled'])} "
        f"({cfg['watermark_text']})\n"
        f"<b>Rename:</b> {onoff(cfg['rename_enabled'])}\n"
        f"<code>{cfg['rename_format']}</code>\n"
        f"<b>Metadata:</b> {onoff(cfg['metadata_enabled'])}\n"
        f"Title: {cfg['metadata_title']}\n"
        f"Author: {cfg['metadata_author']}",
        disable_web_page_preview=True,
    )


# ---------- channels ----------

@Client.on_message(filters.command("settarget") & filters.private & OWNER)
async def set_target(client: Client, message: Message):
    value = arg(message)
    try:
        chat_id = int(value)
        chat = await client.get_chat(chat_id)
    except Exception:
        return await message.reply_text(
            "Usage: /settarget -100xxxxxxxxxx\n"
            "Make sure the bot is an admin in that channel."
        )
    await db.set("target_channel", chat_id)
    await message.reply_text(f"Target channel changed to <b>{chat.title}</b>")


@Client.on_message(filters.command("addmain") & filters.private & OWNER)
async def add_main(client: Client, message: Message):
    try:
        chat_id = int(arg(message))
        chat = await client.get_chat(chat_id)
    except Exception:
        return await message.reply_text(
            "Usage: /addmain -100xxxxxxxxxx\n"
            "Make sure the bot is an admin in that channel."
        )
    await db.add_main_channel(chat_id)
    await message.reply_text(f"Main channel added: <b>{chat.title}</b>")


@Client.on_message(filters.command("delmain") & filters.private & OWNER)
async def del_main(client: Client, message: Message):
    try:
        chat_id = int(arg(message))
    except ValueError:
        return await message.reply_text("Usage: /delmain -100xxxxxxxxxx")
    await db.remove_main_channel(chat_id)
    await message.reply_text("Main channel removed.")


@Client.on_message(filters.command("setfilestore") & filters.private & OWNER)
async def set_filestore(client: Client, message: Message):
    value = arg(message).lstrip("@")
    if not value:
        return await message.reply_text("Usage: /setfilestore YourFileStoreBot")
    await db.set("filestore_bot", value)
    await message.reply_text(f"File store bot set to @{value}")


@Client.on_message(filters.command("setjoin") & filters.private & OWNER)
async def set_join(client: Client, message: Message):
    value = arg(message)
    if not value.startswith("https://t.me/"):
        return await message.reply_text("Usage: /setjoin https://t.me/Anime_Hub_Tamil")
    await db.set("join_link", value)
    await message.reply_text("Join link updated.")


# ---------- watermark ----------

@Client.on_message(filters.command("setwatermark") & filters.private & OWNER)
async def set_watermark(client: Client, message: Message):
    value = arg(message)
    if not value:
        return await message.reply_text("Usage: /setwatermark Animes Tamil Hub")
    await db.set("watermark_text", value)
    await message.reply_text(f"Watermark text set to: {value}")


@Client.on_message(filters.command("watermark") & filters.private & OWNER)
async def toggle_watermark(client: Client, message: Message):
    value = arg(message).lower()
    if value not in ("on", "off"):
        return await message.reply_text("Usage: /watermark on or /watermark off")
    await db.set("watermark_enabled", value == "on")
    await message.reply_text(f"Watermark {value.upper()}")


# ---------- rename ----------

@Client.on_message(filters.command("setformat") & filters.private & OWNER)
async def set_format(client: Client, message: Message):
    value = arg(message)
    if not value:
        return await message.reply_text(
            "Usage: /setformat [AnimesTamilHub] {title} S{season}E{episode} "
            "[{quality}] [{language}]"
        )
    try:
        value.format(title="a", season="01", episode="01", quality="720p", language="Tamil")
    except (KeyError, IndexError, ValueError):
        return await message.reply_text(
            "Invalid format. Allowed: {title} {season} {episode} {quality} {language}"
        )
    await db.set("rename_format", value)
    await message.reply_text("Rename format updated.")


@Client.on_message(filters.command("rename") & filters.private & OWNER)
async def toggle_rename(client: Client, message: Message):
    value = arg(message).lower()
    if value not in ("on", "off"):
        return await message.reply_text("Usage: /rename on or /rename off")
    await db.set("rename_enabled", value == "on")
    await message.reply_text(f"Rename {value.upper()}")


# ---------- metadata ----------

@Client.on_message(filters.command("setmeta") & filters.private & OWNER)
async def set_meta(client: Client, message: Message):
    value = arg(message)
    if "|" not in value:
        return await message.reply_text("Usage: /setmeta Animes Tamil Hub | @Anime_Hub_Tamil")
    title, author = (x.strip() for x in value.split("|", 1))
    await db.set("metadata_title", title)
    await db.set("metadata_author", author)
    await message.reply_text("Metadata updated.")


@Client.on_message(filters.command("metadata") & filters.private & OWNER)
async def toggle_metadata(client: Client, message: Message):
    value = arg(message).lower()
    if value not in ("on", "off"):
        return await message.reply_text("Usage: /metadata on or /metadata off")
    await db.set("metadata_enabled", value == "on")
    await message.reply_text(f"Metadata {value.upper()}")


@Client.on_message(filters.command("setprimary") & filters.private & OWNER)
async def set_primary(client: Client, message: Message):
    try:
        chat_id = int(arg(message))
        chat = await client.get_chat(chat_id)
    except Exception:
        return await message.reply_text(
            "Usage: /setprimary -100xxxxxxxxxx\n"
            "Make sure the bot is an admin in that channel."
        )
    await db.set("primary_channel", chat_id)
    await message.reply_text(f"Primary channel set to <b>{chat.title}</b>")


@Client.on_message(filters.command("setwatch") & filters.private & OWNER)
async def set_watch(client: Client, message: Message):
    value = arg(message)
    if not value.startswith("https://t.me/"):
        return await message.reply_text("Usage: /setwatch https://t.me/Anime_Hub_Tamil")
    await db.set("watch_link", value)
    await message.reply_text("Watch link updated.")


@Client.on_message(filters.command("setlang") & filters.private & OWNER)
async def set_lang(client: Client, message: Message):
    value = arg(message).strip()
    if value.lower() in ("off", "none", "all"):
        await db.set("keep_language", "")
        return await message.reply_text(
            "Language filter OFF. All audio and subtitle streams are kept."
        )

    match = next((n for n in LANG_CODES if n.lower() == value.lower()), None)
    if not match:
        return await message.reply_text(
            "Usage: /setlang Tamil\nOptions: " + ", ".join(LANG_CODES)
            + "\n/setlang off to keep everything"
        )
    await db.set("keep_language", match)
    await message.reply_text(
        f"Language set to <b>{match}</b>.\n"
        f"Only {match} audio is kept. Other audio, subtitles and extra "
        "streams are removed."
    )
    
    
@Client.on_message(filters.command("settrack") & filters.private & OWNER)
async def set_track(client: Client, message: Message):
    value = arg(message).lower()
    if value in ("off", "0", "none"):
        await db.set("audio_track", 0)
        return await message.reply_text("Track number OFF. Language tags are used.")
    if not value.isdigit() or int(value) < 1:
        return await message.reply_text(
            "Usage: /settrack 2  (keep the 2nd audio track)\n/settrack off"
        )
    await db.set("audio_track", int(value))
    await message.reply_text(
        f"Audio track {value} will be kept in every file.\n"
        "Other audio, subtitles and extra streams are removed."
    )
    
