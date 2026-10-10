import asyncio
import os
import re
from collections import defaultdict

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from database.db import db
from helpers.anilist import download_poster, fetch_anime
from helpers.buttons import join_markup
from helpers.ffmpeg_tools import make_thumbnail, probe, process_video
from helpers.link import make_link
from helpers.progress import Progress
from helpers.thumb import prepare_thumb
from plugins.collector import QUEUE
from plugins.post import build_caption, finalize_post

OWNER = filters.user(Config.OWNER_ID)

STATE = {"running": False, "cancel": False}
PHOTO_WAIT: dict[int, asyncio.Future] = {}
QUALITY_ORDER = {"480p": 0, "720p": 1, "1080p": 2, "2160p": 3, "HDRIP": 4}
WORK_DIR = os.path.abspath(Config.DOWNLOAD_DIR)


def safe_name(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "", text).strip()


def build_name(fmt: str, item: dict) -> str:
    try:
        return fmt.format(
            title=item["title"],
            season=f"{item['season']:02d}",
            episode=f"{item['episode']:02d}",
            quality=item["quality"],
            language=item["language"],
        )
    except (KeyError, IndexError, ValueError):
        return (
            f"{item['title']} S{item['season']:02d}E{item['episode']:02d} "
            f"[{item['quality']}]"
        )


def remove(path):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


# ---------- asking for photos (poster / thumbnail) ----------

@Client.on_message(filters.private & OWNER & (filters.photo | filters.command("skip")))
async def photo_receiver(client: Client, message: Message):
    future = PHOTO_WAIT.get(message.from_user.id)
    if not future or future.done():
        return
    if message.photo:
        path = await message.download(
            file_name=os.path.join(WORK_DIR, f"photo_{message.id}.jpg")
        )
        future.set_result(path)
    else:
        future.set_result(None)


async def ask_photo(client: Client, chat_id: int, user_id: int, prompt: str):
    future = asyncio.get_running_loop().create_future()
    PHOTO_WAIT[user_id] = future
    await client.send_message(chat_id, prompt)
    try:
        return await asyncio.wait_for(future, timeout=120)
    except asyncio.TimeoutError:
        return None
    finally:
        PHOTO_WAIT.pop(user_id, None)


async def get_poster(client, chat_id, user_id, title, season):
    poster = await ask_photo(
        client, chat_id, user_id,
        f"Send the <b>poster</b> for <b>{title}</b> (Season {season:02d}), "
        "or /skip to use the AniList poster.\n(Auto skip in 2 minutes)",
    )
    if poster:
        return poster
    data = await fetch_anime(title)
    if data and data.get("poster_url"):
        return await download_poster(data["poster_url"], safe_name(title))
    return None


async def get_thumb(client, chat_id, user_id, title, cfg):
    path = await ask_photo(
        client, chat_id, user_id,
        f"Send the <b>thumbnail</b> for <b>{title}</b>, "
        "or /skip to use the saved thumbnail (/setthumb).\n"
        "(Auto skip in 2 minutes)",
    )
    if path:
        out = prepare_thumb(path, path + ".thumb.jpg")
        remove(path)
        return out

    if cfg.get("thumb_file_id"):
        try:
            saved = await client.download_media(
                cfg["thumb_file_id"],
                file_name=os.path.join(WORK_DIR, "saved_thumb.jpg"),
            )
            out = prepare_thumb(saved, saved + ".thumb.jpg")
            remove(saved)
            return out
        except Exception:
            return None
    return None


# ---------- main channel progress posts ----------

async def open_posts(client: Client, cfg: dict, info: dict, poster):
    join = join_markup(cfg["join_link"])
    text = (
        f"<b>{info['title']}</b>\n\n"
        f"<b>Season:</b> {int(info['season']):02d}\n"
        f"<b>Episode:</b> {int(info['episode']):02d}\n"
        f"<b>Language:</b> {info['language']}\n\n"
        "<b>Preparing...</b>"
    )
    posts = []
    for chat_id in cfg["main_channels"]:
        try:
            if poster and os.path.exists(poster):
                msg = await client.send_photo(
                    chat_id, poster, caption=text, reply_markup=join
                )
            else:
                msg = await client.send_message(chat_id, text, reply_markup=join)
            posts.append(msg)
        except Exception:
            pass
    return posts


# ---------- one file ----------

async def process_file(client, chat_id, item, cfg, posts, saved_thumb):
    info = {k: item[k] for k in ("title", "season", "episode", "language", "quality")}
    target = cfg["target_channel"]
    join = join_markup(cfg["join_link"])

    status = await client.send_message(chat_id, "Starting...")
    progress = Progress(info, [(status, None)] + [(m, join) for m in posts])

    src_path = out_path = auto_thumb = None
    try:
        msg = await client.get_messages(item["chat_id"], item["msg_id"])

        progress.set_stage("Downloading")
        src_path = await client.download_media(
            msg,
            file_name=os.path.join(WORK_DIR, f"src_{item['msg_id']}.mkv"),
            progress=progress.update,
        )

        meta = await probe(src_path)

        if cfg["rename_enabled"]:
            new_name = build_name(cfg["rename_format"], item)
        else:
            new_name = os.path.splitext(item["name"])[0] or build_name(
                "{title} S{season}E{episode} [{quality}]", item
            )
        out_path = os.path.join(WORK_DIR, f"{safe_name(new_name)}.mkv")

        progress.set_stage("Encoding Files")
        ok, error = await process_video(
            src_path,
            out_path,
            title=cfg["metadata_title"],
            author=cfg["metadata_author"],
            watermark_text=cfg["watermark_text"],
            watermark_enabled=cfg["watermark_enabled"],
            metadata_enabled=cfg["metadata_enabled"],
            duration=meta["duration"],
            on_progress=progress.update_encode,
        )
        if not ok:
            raise RuntimeError(f"ffmpeg failed: {error}")

        thumb = saved_thumb
        if not thumb:
            auto_thumb = await make_thumbnail(
                out_path, out_path + ".jpg", meta["duration"]
            )
            thumb = auto_thumb

        progress.set_stage("Uploading")
        sent = await client.send_document(
            target,
            out_path,
            thumb=thumb,
            caption=f"<b>{os.path.basename(out_path)}</b>",
            force_document=True,
            progress=progress.update,
        )

        link = make_link(cfg["filestore_bot"], target, sent.id)
        await status.edit_text(
            f"<b>Uploaded:</b> {item['title']} S{item['season']:02d}"
            f"E{item['episode']:02d} [{item['quality']}]"
        )
        return link

    except Exception as e:
        await status.edit_text(
            f"<b>Failed:</b> {item['title']} E{item['episode']:02d} "
            f"[{item['quality']}]\n<code>{e}</code>"
        )
        return None

    finally:
        remove(src_path)
        remove(out_path)
        remove(auto_thumb)


# ---------- whole queue ----------

async def run_queue(client, chat_id, user_id, items, cfg):
    anime_groups = defaultdict(list)
    for item in items:
        anime_groups[(item["title"], item["season"])].append(item)

    uploaded = failed = 0

    for (title, season), group in anime_groups.items():
        if STATE["cancel"]:
            break

        poster = await get_poster(client, chat_id, user_id, title, season)
        thumb = await get_thumb(client, chat_id, user_id, title, cfg)

        episodes = defaultdict(list)
        for item in group:
            episodes[(item["episode"], item["language"])].append(item)

        for (episode, language), files in sorted(episodes.items()):
            if STATE["cancel"]:
                break

            files.sort(key=lambda f: QUALITY_ORDER.get(f["quality"], 9))
            info = {
                "title": title, "season": season,
                "episode": episode, "language": language,
            }
            posts = await open_posts(client, cfg, info, poster)
            links = {}

            for item in files:
                if STATE["cancel"]:
                    break
                link = await process_file(client, chat_id, item, cfg, posts, thumb)
                if link:
                    links[item["quality"]] = link
                    uploaded += 1
                else:
                    failed += 1

            if links:
                errors = await finalize_post(
                    posts, build_caption(title, season, episode, language), links
                )
                if errors:
                    await client.send_message(
                        chat_id, "Post failed:\n<code>" + "\n".join(errors) + "</code>"
                    )
            else:
                for post in posts:
                    try:
                        await post.delete()
                    except Exception:
                        pass

        remove(poster)
        remove(thumb)

    note = "Cancelled" if STATE["cancel"] else "Process completed"
    await client.send_message(
        chat_id, f"<b>{note}</b>\n\nUploaded: {uploaded}\nFailed: {failed}"
    )


@Client.on_message(filters.command("start_process") & filters.private & OWNER)
async def start_process(client: Client, message: Message):
    user_id = message.from_user.id
    items = QUEUE.get(user_id, [])

    if not items:
        return await message.reply_text("Queue is empty. Send files first.")
    if STATE["running"]:
        return await message.reply_text("A process is already running.")

    cfg = await db.get()
    if not (cfg["target_channel"] and cfg["main_channels"] and cfg["filestore_bot"]):
        return await message.reply_text(
            "Target channel, main channels and file store bot must be set first."
        )

    STATE.update(running=True, cancel=False)
    QUEUE[user_id] = []
    await message.reply_text(f"Upload process started for {len(items)} file(s).")

    try:
        await run_queue(client, message.chat.id, user_id, items, cfg)
    finally:
        STATE["running"] = False


@Client.on_message(filters.command("cancel") & filters.private & OWNER)
async def cancel_process(client: Client, message: Message):
    if not STATE["running"]:
        return await message.reply_text("Nothing is running.")
    STATE["cancel"] = True
    await message.reply_text("Cancelling after the current file...")
