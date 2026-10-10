from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from helpers.parser import parse_filename

OWNER = filters.user(Config.OWNER_ID)

# user_id -> list of queued files
QUEUE: dict[int, list] = {}


@Client.on_message(filters.private & OWNER & (filters.document | filters.video))
async def collect_file(client: Client, message: Message):
    media = message.document or message.video
    name = media.file_name or message.caption or ""
    parsed = parse_filename(name)

    if not parsed:
        return await message.reply_text(
            f"Could not detect anime / episode from:\n<code>{name}</code>\n"
            "Rename the file and send it again.",
            quote=True,
        )

    items = QUEUE.setdefault(message.from_user.id, [])
    items.append(
        {
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
    )

    await message.reply_text(
        f"<b>Added to queue</b> ({len(items)})\n\n"
        f"<b>Anime:</b> {parsed.title}\n"
        f"<b>Season:</b> {parsed.season:02d}\n"
        f"<b>Episode:</b> {parsed.episode:02d}\n"
        f"<b>Quality:</b> {parsed.quality}\n"
        f"<b>Language:</b> {parsed.language}\n\n"
        "Send more files or /start_process",
        quote=True,
    )


@Client.on_message(filters.command("queue") & filters.private & OWNER)
async def show_queue(client: Client, message: Message):
    items = QUEUE.get(message.from_user.id, [])
    if not items:
        return await message.reply_text("Queue is empty.")

    lines = [
        f"{i}. {it['title']} S{it['season']:02d}E{it['episode']:02d} "
        f"[{it['quality']}] [{it['language']}]"
        for i, it in enumerate(items, 1)
    ]
    await message.reply_text("<b>Queue</b>\n\n" + "\n".join(lines))


@Client.on_message(filters.command("clear") & filters.private & OWNER)
async def clear_queue(client: Client, message: Message):
    QUEUE[message.from_user.id] = []
    await message.reply_text("Queue cleared.")
