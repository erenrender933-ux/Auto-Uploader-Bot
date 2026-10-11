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


def language_label(language: str) -> str:
    if language in AUDIO_LANGUAGES:
        return f"{language} Audio"
    if language == "English":
        return "English Sub"
    return language


def build_caption(title: str, season: int, episode: int, language: str) -> str:
    return (
        f"<b><blockquote>{html.escape(title)}</b></blockquote>\n"
        "<b>━━━━━━━━━━━━━━━━━━\n"
        f"☆ Season: {season:02d}\n"
        f"☆ Episode: {episode:02d}\n"
        f"☆ Quality: Multi Quality [{language_label(language)}]\n"
        "━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"<b><blockquote>ɴᴇᴡ ᴇᴘɪsᴏᴅᴇ {episode:02d} ᴀᴅᴅᴇᴅ 👇</b></blockquote>"
    )


def build_primary_caption(
    title: str, season: int, episode: int, language: str, qualities: list
) -> str:
    ordered = sorted(
        qualities, key=lambda q: QUALITY_ORDER.index(q) if q in QUALITY_ORDER else 9
    )
    quality_text = ",".join(q.upper() for q in ordered)
    return (
        f"<blockquote>╰┈➤ {html.escape(title.upper(), quote=False)}</blockquote>\n"
        "<b>━━━━━━━━━━━━━━━━━━\n"
        f"✧ sᴇᴀsᴏɴ  ✦ {season:02d}\n"
        f"✧ ᴀᴜᴅɪᴏ   ✦ {language.upper()}\n"
        f"✧ ǫᴜᴀʟɪᴛʏ ✦ {quality_text}.\n"
        f"✧ ᴇᴘɪsᴏᴅᴇ ✦ {episode:02d}\n"
        "━━━━━━━━━━━━━━━━━━</b>\n\n"
        "<blockquote>➤ ᴜsᴇ ᴠʟᴄ ᴘʟᴀʏᴇʀ ᴏʀ ᴍx ᴘʟᴀʏᴇʀ ᴛᴏ ᴡᴀᴛᴄʜ ᴛʜᴇ ᴇᴘɪsᴏᴅᴇs "
        "ᴡɪᴛʜ ɢᴏᴏᴅ ᴇxᴘᴇʀɪᴇɴᴄᴇ !.</blockquote>\n"
        "<blockquote>≡ ɴᴏᴛᴇ :- ɴᴇxᴛ ɴᴇᴡ ᴇᴘɪsᴏᴅᴇ ɴᴇxᴛ ᴡᴇᴇᴋ sᴏ sᴛᴀʏ ᴛᴜɴᴇᴅ "
        "ɢᴜʏs.!</blockquote>"
    )


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
    poster: str | None,
    watch_link: str,
) -> str:
    """Post in the primary channel. Returns an error text, or '' on success."""
    chat_id = cfg.get("primary_channel")
    if not chat_id:
        return ""

    caption = build_primary_caption(title, season, episode, language, qualities)
    label = "• ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ᴡᴀᴛᴄʜ •"
    plain = InlineKeyboardMarkup([[InlineKeyboardButton(label, url=watch_link)]])

    try:
        if poster and os.path.exists(poster):
            msg = await client.send_photo(
                chat_id, poster, caption=caption, reply_markup=plain
            )
        else:
            msg = await client.send_message(chat_id, caption, reply_markup=plain)
    except Exception as e:
        return str(e)

    # Pyrogram cannot colour buttons, so change the markup to blue via Bot API.
    # If this fails, the plain button stays and the post is still fine.
    blue = {
        "inline_keyboard": [[{"text": label, "url": watch_link, "style": "primary"}]]
    }
    try:
        await _call(
            "editMessageReplyMarkup",
            {
                "chat_id": chat_id,
                "message_id": msg.id,
                "reply_markup": json.dumps(blue),
            },
        )
    except Exception:
        pass
    return ""
