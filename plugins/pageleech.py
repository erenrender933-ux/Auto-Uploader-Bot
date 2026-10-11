import asyncio
import html
import os
import shutil

import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from helpers.parser import parse_filename
from plugins.collector import QUEUE

OWNER = filters.user(Config.OWNER_ID)
WORK_DIR = os.path.abspath(Config.DOWNLOAD_DIR)

USAGE = (
    "Usage:\n<code>/pageleech https://site/episode-page</code>\n"
    "To set the name yourself:\n"
    "<code>/pageleech https://page | Anime Name S01E02 720p Tamil</code>"
)


def _download(url: str, folder: str) -> str:
    options = {
        "outtmpl": os.path.join(folder, "%(title)s.%(ext)s"),
        "format": "bv*+ba/b",
        "merge_output_format": "mkv",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.extract_info(url, download=True)

    files = [f for f in os.listdir(folder) if not f.endswith((".part", ".ytdl"))]
    if not files:
        raise RuntimeError("No video found on that page")
    files.sort(key=lambda f: os.path.getsize(os.path.join(folder, f)), reverse=True)
    return os.path.join(folder, files[0])


@Client.on_message(filters.command("pageleech") & filters.private & OWNER)
async def pageleech(client: Client, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text(USAGE)

    url, _, custom = parts[1].partition("|")
    url, custom = url.strip(), custom.strip()
    if not url.startswith(("http://", "https://")):
        return await message.reply_text(USAGE)

    folder = os.path.join(WORK_DIR, f"page_{message.id}")
    os.makedirs(folder, exist_ok=True)
    status = await message.reply_text("Finding the video and downloading... (no live progress)")

    try:
        path = await asyncio.to_thread(_download, url, folder)
    except Exception as e:
        shutil.rmtree(folder, ignore_errors=True)
        return await status.edit_text(
            f"Failed:\n<code>{html.escape(str(e)[:500])}</code>"
        )

    ext = os.path.splitext(path)[1] or ".mkv"
    name = (custom + ext) if custom else os.path.basename(path)
    parsed = parse_filename(name)
    if not parsed:
        shutil.rmtree(folder, ignore_errors=True)
        return await status.edit_text(
            f"Could not detect anime / episode from:\n<code>{html.escape(name)}</code>\n\n"
            + USAGE
        )

    QUEUE.setdefault(message.from_user.id, []).append(
        {
            "chat_id": message.chat.id,
            "msg_id": message.id,
            "size": os.path.getsize(path),
            "name": name,
            "title": parsed.title,
            "season": parsed.season,
            "episode": parsed.episode,
            "quality": parsed.quality,
            "language": parsed.language,
            "local_path": path,
        }
    )
    await status.edit_text(
        f"<b>Added to queue</b>\n\n"
        f"<b>Anime:</b> {html.escape(parsed.title)}\n"
        f"<b>Season:</b> {parsed.season:02d}\n"
        f"<b>Episode:</b> {parsed.episode:02d}\n"
        f"<b>Quality:</b> {parsed.quality}\n"
        f"<b>Language:</b> {parsed.language}\n\n"
        "Send more or /start_process"
      )
