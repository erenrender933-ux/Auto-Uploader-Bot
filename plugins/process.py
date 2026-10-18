import asyncio
import html
import os
import re
from helpers.card import make_card
from plugins.post import PostSink, build_caption, send_primary_post, send_stickers
from collections import defaultdict

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from database.db import db
from helpers.anilist import download_poster, fetch_anime
from helpers.buttons import join_markup
from helpers.ffmpeg_tools import (
    make_thumbnail, mean_volume, pick_audio, probe, process_video,
)
from helpers.link import make_link
from helpers.progress import Progress, ProgressSink
from helpers.thumb import prepare_thumb
from plugins.collector import QUEUE
from plugins.post import PostSink, build_caption, send_primary_post

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


def _key(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


def unify_titles(items: list):
    """Make slightly different titles of the same anime identical."""
    seasons = defaultdict(list)
    for item in items:
        seasons[item["season"]].append(item)

    for group in seasons.values():
        canon = {}
        for item in sorted(group, key=lambda i: len(_key(i["title"]))):
            key = _key(item["title"])
            match = next((k for k in canon if key.startswith(k)), None)
            if match:
                item["title"] = canon[match]
            else:
                canon[key] = item["title"]


def build_order(items: list) -> list:
    """Exact processing order: anime, then episode 01, 02, ... then quality."""
    groups = defaultdict(list)
    for item in items:
        groups[(item["title"], item["season"])].append(item)

    order = []
    for group in groups.values():
        episodes = defaultdict(list)
        for item in group:
            episodes[(item["episode"], item["language"])].append(item)
        for _, files in sorted(episodes.items()):
            files.sort(key=lambda f: QUALITY_ORDER.get(f["quality"], 9))
            order.extend(files)
    return order


def describe_tracks(meta: dict) -> str:
    parts = []
    for i, (codec, s) in enumerate(zip(meta["audio"], meta["audio_streams"]), 1):
        title = f" '{s['title']}'" if s["title"] else ""
        parts.append(f"#{i} {s['lang'] or 'und'} {codec}{title}")
    return ", ".join(parts) or "none"


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
        f"Send the <b>poster</b> for <b>{html.escape(title)}</b> "
        f"(Season {season:02d}), or /skip to use the AniList poster.\n"
        "(Auto skip in 2 minutes)",
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
        f"Send the <b>thumbnail</b> for <b>{html.escape(title)}</b>, "
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


# ---------- main channel: post on top, progress message below ----------

async def open_posts(client: Client, cfg: dict, info: dict, poster):
    caption = build_caption(
        info["title"], info["season"], info["episode"], info["language"]
    )
    join = join_markup(cfg["join_link"])
    posts, sinks = [], []

    for chat_id in cfg["main_channels"]:
        try:
            if poster and os.path.exists(poster):
                msg = await client.send_photo(chat_id, poster, caption=caption)
            else:
                msg = await client.send_message(chat_id, caption)
            posts.append(PostSink(chat_id, msg.id, getattr(msg, "link", None)))

            prog = await client.send_message(
                chat_id,
                f"<b>{html.escape(info['title'])}</b>\n\n<b>Preparing...</b>",
                reply_markup=join,
            )
            sinks.append(ProgressSink(prog, join))
        except Exception:
            pass
    return posts, sinks


# ---------- download (also used to prefetch the next file) ----------

async def download_source(client, item, progress=None):
    if item.get("local_path"):
        return item["local_path"]  # already downloaded by /leech
    msg = await client.get_messages(item["chat_id"], item["msg_id"])
    return await client.download_media(
        msg,
        file_name=os.path.join(WORK_DIR, f"src_{item['msg_id']}.mkv"),
        progress=progress.update if progress else None,
    )


# ---------- one file ----------

async def process_file(
    client, chat_id, item, cfg, posts, sinks, saved_thumb,
    stats, task_id, pre, nxt,
):
    """Returns (link or None, download task of the next file or None)."""
    target = cfg["target_channel"]
    label = html.escape(
        f"{item['title']} S{item['season']:02d}E{item['episode']:02d} "
        f"[{item['quality']}]"
    )

    if cfg["rename_enabled"]:
        new_name = build_name(cfg["rename_format"], item)
    else:
        new_name = os.path.splitext(item["name"])[0] or build_name(
            "{title} S{season}E{episode} [{quality}]", item
        )
    out_name = f"{safe_name(new_name)}.mkv"
    progress = Progress(out_name, sinks, stats, task_id)

    src_path = out_path = auto_thumb = None
    next_task = None
    try:
        if pre is not None:
            if not pre.done():
                await progress.status("Downloading")
            src_path = await pre
        else:
            progress.set_stage("Downloading")
            src_path = await download_source(client, item, progress)

        # start downloading the next file while this one is encoding
        if nxt is not None:
            next_task = asyncio.create_task(download_source(client, nxt))

        meta = await probe(src_path)

        # stream filter: keep only one audio track, drop everything else
        audio_indexes = None
        wanted = cfg.get("keep_language")
        track = int(cfg.get("audio_track") or 0)
        if track:
            if track > len(meta["audio_streams"]):
                raise RuntimeError(
                    f"Audio track {track} not found. This file has "
                    f"{len(meta['audio_streams'])} audio track(s): "
                    f"{describe_tracks(meta)}"
                )
            audio_indexes = [track - 1]
        elif wanted:
            audio_indexes = pick_audio(meta["audio_streams"], wanted)
            if not audio_indexes:
                raise RuntimeError(
                    f"No {wanted} audio found. Tracks: {describe_tracks(meta)}. "
                    "Use /settrack N to pick one by number."
                )

        out_path = os.path.join(WORK_DIR, out_name)

        progress.set_stage("Encoding")
        ok, error = await process_video(
            src_path,
            out_path,
            title=cfg["metadata_title"],
            author=cfg["metadata_author"],
            watermark_text=cfg["watermark_text"],
            watermark_enabled=cfg["watermark_enabled"],
            metadata_enabled=cfg["metadata_enabled"],
            quality=item["quality"],
            duration=meta["duration"],
            audio_indexes=audio_indexes,
            has_audio=bool(meta["audio"]),
            language=wanted or "",
            on_progress=progress.update_encode,
        )
        if not ok:
            raise RuntimeError(f"ffmpeg failed: {error}")

        out_meta = await probe(out_path)

        # the filter must leave exactly the chosen audio and no subtitles
        if audio_indexes is not None and (
            len(out_meta["audio"]) != len(audio_indexes) or out_meta["subs"]
        ):
            raise RuntimeError(
                "Stream filter failed: output has "
                f"{len(out_meta['audio'])} audio and {out_meta['subs']} "
                "subtitle streams"
            )

        # make sure the output really has sound
        out_vol = None
        if meta["audio"]:
            if not out_meta["audio"]:
                raise RuntimeError("Output file has no audio. Upload stopped.")
            mid = meta["duration"] * 0.4 if meta["duration"] else 0
            out_vol = await mean_volume(out_path, mid)
            if out_vol is None or out_vol < -80:
                src_vol = await mean_volume(src_path, mid)
                raise RuntimeError(
                    f"Output audio is silent ({out_vol} dB). "
                    f"Source audio: {src_vol} dB. Tracks: {describe_tracks(meta)}"
                )

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
            caption=f"<b>{html.escape(os.path.basename(out_path))}</b>",
            force_document=True,
            progress=progress.update,
        )

        link = make_link(cfg["filestore_bot"], target, sent.id)

        # add this quality's button to every main channel post right away
        for post in posts:
            post.add_link(item["quality"], link)
        await asyncio.gather(
            *(post.push_buttons() for post in posts), return_exceptions=True
        )
        await progress.status(f"{item['quality']} Uploaded")

        await client.send_message(
            chat_id,
            f"<b>Upload completed:</b> {label}\n"
            f"<code>Streams: {out_meta['videos']} video, "
            f"{len(out_meta['audio'])} audio, {out_meta['subs']} sub | "
            f"audio {', '.join(out_meta['audio']) or 'none'} | "
            f"volume {out_vol} dB</code>",
        )
        return link, next_task

    except Exception as e:
        await client.send_message(
            chat_id, f"<b>Failed:</b> {label}\n<code>{html.escape(str(e))}</code>"
        )
        return None, next_task

    finally:
        remove(src_path)
        remove(out_path)
        remove(auto_thumb)


# ---------- whole queue ----------

async def run_queue(client, chat_id, user_id, items, cfg, stats, task_id):
    anime_groups = defaultdict(list)
    for item in items:
        anime_groups[(item["title"], item["season"])].append(item)

    # next file in the exact processing order (used to prefetch downloads)
    order = build_order(items)
    following = {id(a): b for a, b in zip(order, order[1:])}

    uploaded = failed = 0
    pre = None

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
            posts, sinks = await open_posts(client, cfg, info, poster)
            links = {}

            for item in files:
                if STATE["cancel"]:
                    break
                link, pre = await process_file(
                    client, chat_id, item, cfg, posts, sinks, thumb,
                    stats, task_id, pre, following.get(id(item)),
                )
                stats["done"] += 1
                if link:
                    links[item["quality"]] = link
                    uploaded += 1
                else:
                    failed += 1

            # progress messages are removed when the episode is done
            for sink in sinks:
                await sink.delete()

            if links:
                if STATE["cancel"]:
                    pass
                elif not cfg.get("primary_channel"):
                    await client.send_message(
                        chat_id,
                        "Primary channel is not set. Use /setprimary -100xxxx",
                    )
                else:
                    watch_link = cfg.get("watch_link") or cfg["join_link"]
                    try:
                        error = await send_primary_post(
                            client, cfg, title, season, episode, language,
                            list(links.keys()), poster, watch_link,
                        )
                    except Exception as e:
                        error = str(e)
                    if error:
                        await client.send_message(
                            chat_id,
                            "Primary channel post failed:\n"
                            f"<code>{html.escape(str(error))}</code>",
                        )
                    else:
                        await client.send_message(
                            chat_id, "Primary channel post sent."
                        )
            else:
                for post in posts:
                    try:
                        await client.delete_messages(post.chat_id, post.message_id)
                    except Exception:
                        pass

        remove(poster)
        remove(thumb)

    if pre is not None:
        pre.cancel()

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

    # one language for the whole batch, and one title per anime
    keep = cfg.get("keep_language")
    if keep:
        for item in items:
            item["language"] = keep
    unify_titles(items)

    task_id = await db.next_task_id()
    stats = {"done": 0, "total": len(items)}

    STATE.update(running=True, cancel=False)
    QUEUE[user_id] = []
    await message.reply_text(
        f"Upload process started for {len(items)} file(s). Task ID: {task_id}"
    )

    try:
        await run_queue(client, message.chat.id, user_id, items, cfg, stats, task_id)
    finally:
        STATE["running"] = False


@Client.on_message(filters.command("cancel") & filters.private & OWNER)
async def cancel_process(client: Client, message: Message):
    if not STATE["running"]:
        return await message.reply_text("Nothing is running.")
    STATE["cancel"] = True
    await message.reply_text("Cancelling after the current file...")
