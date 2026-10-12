import asyncio
import html
from collections import defaultdict

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from helpers.parser import parse_filename

OWNER = filters.user(Config.OWNER_ID)
QUALITY_ORDER = {"480p": 0, "720p": 1, "1080p": 2, "2160p": 3, "HDRIP": 4}

# user_id -> list of queued files
QUEUE: dict[int, list] = {}
# user_id -> files received in the last few seconds (for one summary message)
PENDING: dict[int, dict] = {}


def summary_text(added: list, failed: list, total: int) -> str:
    lines = []
    if added:
        lines.append(f"<b>Added {len(added)} file(s) to queue</b>\n")

    groups = defaultdict(list)
    for item in added:
        groups[(item["title"], item["season"])].append(item)

    for (title, season), files in groups.items():
        eps = sorted({f["episode"] for f in files})
        quals = sorted(
            {f["quality"] for f in files}, key=lambda q: QUALITY_ORDER.get(q, 9)
        )
        langs = sorted({f["language"] for f in files})

        if len(eps) == 1:
            ep_line = f"Episode: {eps[0]:02d}"
        else:
            ep_line = f"Episodes: {eps[0]:02d} - {eps[-1]:02d} ({len(eps)})"

        text = (
            f"<b>{html.escape(title)}</b> S{season:02d}\n{ep_line}\n"
            f"Quality: {', '.join(quals)}\nLanguage: {', '.join(langs)}"
        )

        missing = [e for e in range(eps[0], eps[-1] + 1) if e not in eps]
        if missing:
            text += "\n<b>Missing:</b> " + ", ".join(f"{e:02d}" for e in missing)

        incomplete = [
            e for e in eps
            if len({f["quality"] for f in files if f["episode"] == e}) != len(quals)
        ]
        if incomplete:
            text += "\n<b>Incomplete qualities:</b> " + ", ".join(
                f"{e:02d}" for e in incomplete
            )
        lines.append(text + "\n")

    if failed:
        lines.append(
            "<b>Could not detect:</b>\n"
            + "\n".join(f"<code>{html.escape(n)}</code>" for n in failed[:10])
            + "\n"
        )

    lines.append(f"Total in queue: {total}\nSend more or /start_process")
    return "\n".join(lines)


async def _send_summary(client: Client, chat_id: int, user_id: int):
    await asyncio.sleep(4)  # wait until no new file arrives
    pending = PENDING.pop(user_id, None)
    if not pending:
        return
    total = len(QUEUE.get(user_id, []))
    await client.send_message(
        chat_id, summary_text(pending["added"], pending["failed"], total)
    )


@Client.on_message(filters.private & OWNER & (filters.document | filters.video))
async def collect_file(client: Client, message: Message):
    media = message.document or message.video
    name = media.file_name or message.caption or ""
    user_id = message.from_user.id

    pending = PENDING.setdefault(
        user_id, {"added": [], "failed": [], "task": None}
    )

    parsed = parse_filename(name)
    if not parsed:
        pending["failed"].append(name or "(no name)")
    else:
        item = {
            "chat_id": message.chat.id,
            "msg_id": message.id,
            "size": media.file_size,
            "name": name,
            "title": parsed.title,
            "season": parsed.season,
            "episode": parsed.episode,
            "quality": parsed.quality,
            "language": parsed.language,
        }
        QUEUE.setdefault(user_id, []).append(item)
        pending["added"].append(item)

    if pending["task"]:
        pending["task"].cancel()
    pending["task"] = asyncio.create_task(
        _send_summary(client, message.chat.id, user_id)
    )


@Client.on_message(filters.command("queue") & filters.private & OWNER)
async def show_queue(client: Client, message: Message):
    items = QUEUE.get(message.from_user.id, [])
    if not items:
        return await message.reply_text("Queue is empty.")
    await message.reply_text(summary_text(items, [], len(items)))


@Client.on_message(filters.command("clear") & filters.private & OWNER)
async def clear_queue(client: Client, message: Message):
    QUEUE[message.from_user.id] = []
    await message.reply_text("Queue cleared.")
