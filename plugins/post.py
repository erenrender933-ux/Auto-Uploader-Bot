import asyncio
import copy
import html
import json
import os

import httpx
from pyrogram import Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from helpers.buttons import raw_quality_markup

QUALITY_ORDER = ["480p", "720p", "1080p", "2160p", "HDRIP"]
AUDIO_LANGUAGES = {"Tamil", "Telugu", "Hindi", "Malayalam", "Kannada"}
LINE = "━━━━━━━━━━━━━━━━━━"


def language_label(language: str) -> str:
    if language in AUDIO_LANGUAGES:
        return f"{language} Audio"
    if language == "English":
        return "English Sub"
    return language


def build_caption(title: str, season: int, episode: int, language: str) -> str:
    return (
        f"<b><blockquote>{html.escape(title, quote=False)}</blockquote>\n"
        f"{LINE}\n"
        f"➥ Season: {season:02d}\n"
        f"➤ Episode: {episode:02d}\n"
        f"➥ Quality: Multi Quality [{language_label(language)}]\n"
        f"{LINE}\n\n"
        f"<blockquote>ɴᴇᴡ ᴇᴘɪsᴏᴅᴇ {episode:02d} ᴀᴅᴅᴇᴅ 👇</b></blockquote>"
    )


def build_primary_caption(
    title: str, season: int, episode: int, language: str,
    qualities: list, synopsis: str = "",
) -> str:
    ordered = sorted(
        qualities, key=lambda q: QUALITY_ORDER.index(q) if q in QUALITY_ORDER else 9
    )
    info = []
    if season != 1:
        info.append(f"<b>❃ Season: {season:02d}")
    info += [
        f"❃ Audio: {language}",
        f"❃ Quality: {', '.join(ordered)}",
        f"❃ Episode: {episode:02d}",
    ]

    head = (
        f"<blockquote>{html.escape(title, quote=False)}</blockquote>\n"
        f"{LINE}\n" + "\n".join(info) + f"\n{LINE}</b>"
    )

    # photo captions are limited to 1024 visible characters
    visible = len(title) + len(LINE) * 2 + sum(len(x) for x in info) + len(info) + 8
    room = 1024 - visible - 30
    text = " ".join(synopsis.split())
    if text and room > 150:
        if len(text) > room:
            text = text[: room - 1].rsplit(" ", 1)[0] + "…"
        return (
            head
            + f"\n<blockquote expandable>➥ {html.escape(text, quote=False)}</blockquote>"
        )
    return head


def strip_style(markup: dict) -> dict:
    plain = copy.deepcopy(markup)
    for row in plain["inline_keyboard"]:
        for button in row:
            button.pop("style", None)
    return plain


async def _call(method: str, data: dict, files: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{Config.BOT_TOKEN}/{method}"
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, data=data, files=files)
    return resp.json()


class PostSink:
    """One main channel post. Quality buttons are added as files finish."""

    def __init__(self, chat_id: int, message_id: int, link: str | None):
        self.chat_id = chat_id
        self.message_id = message_id
        self.link = link
        self.links: dict = {}
        self.styled = True

    def add_link(self, quality: str, link: str):
        self.links[quality] = link

    def _markup(self) -> dict:
        markup = raw_quality_markup(self.links)
        return markup if self.styled else strip_style(markup)

    async def push_buttons(self) -> bool:
        for _ in range(3):
            result = await _call(
                "editMessageReplyMarkup",
                {
                    "chat_id": self.chat_id,
                    "message_id": self.message_id,
                    "reply_markup": json.dumps(self._markup()),
                },
            )
            if result.get("ok"):
                return True

            desc = result.get("description", "")
            if "not modified" in desc:
                return True

            retry = result.get("parameters", {}).get("retry_after")
            if retry:
                await asyncio.sleep(retry)
                continue

            if self.styled:
                self.styled = False  # fall back to plain buttons
                continue
            return False
        return False


async def send_primary_post(
    client: Client,
    cfg: dict,
    title: str,
    season: int,
    episode: int,
    language: str,
    qualities: list,
    photo: str | None,
    watch_link: str,
    synopsis: str = "",
) -> str:
    """Post in the primary channel. Returns an error text, or '' on success."""
    chat_id = cfg.get("primary_channel")
    if not chat_id:
        return ""

    caption = build_primary_caption(title, season, episode, language, qualities, synopsis)
    label = "• ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ᴡᴀᴛᴄʜ •"
    plain = InlineKeyboardMarkup([[InlineKeyboardButton(label, url=watch_link)]])

    msg, error = None, ""
    # second try without the expandable quote, in case it is not supported
    for text in (caption, caption.replace("<blockquote expandable>", "<blockquote>")):
        try:
            if photo and os.path.exists(photo):
                msg = await client.send_photo(
                    chat_id, photo, caption=text, reply_markup=plain
                )
            else:
                msg = await client.send_message(chat_id, text, reply_markup=plain)
            break
        except Exception as e:
            error = str(e)
    if msg is None:
        return error

    # Pyrogram cannot colour buttons, so make it red through the Bot API.
    # If this fails, the plain button stays and the post is still fine.
    red = {
        "inline_keyboard": [[{"text": label, "url": watch_link, "style": "danger"}]]
    }
    try:
        await _call(
            "editMessageReplyMarkup",
            {
                "chat_id": chat_id,
                "message_id": msg.id,
                "reply_markup": json.dumps(red),
            },
        )
    except Exception:
        pass
    return ""


async def send_stickers(client: Client, cfg: dict, chat_ids: list):
    """Send the saved sticker (see /setsticker) to each chat."""
    file_id = cfg.get("sticker_file_id")
    if not file_id:
        return
    for chat_id in chat_ids:
        try:
            await client.send_sticker(chat_id, file_id)
        except Exception:
            pass
