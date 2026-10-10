import asyncio
import copy
import html
import json
import os

import httpx

from config import Config
from helpers.buttons import raw_quality_markup

AUDIO_LANGUAGES = {"Tamil", "Telugu", "Hindi", "Malayalam", "Kannada"}


def language_label(language: str) -> str:
    if language in AUDIO_LANGUAGES:
        return f"{language} Audio"
    if language == "English":
        return "English Sub"
    return language


def build_caption(title: str, season: int, episode: int, language: str) -> str:
    return (
        f"<blockquote><b>{html.escape(title)}</blockquote></b>\n"
        "<b>━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>➤ Season: {season:02d}\n"
        f"➤ Episode: {episode:02d}\n"
        f"➤ Quality: Multi Quality [{language_label(language)}]</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"<b><blockquote>ɴᴇᴡ ᴇᴘɪsᴏᴅᴇ {episode:02d} ᴀᴅᴅᴇᴅ 👇</b></blockquote>"
    )


def strip_style(markup: dict) -> dict:
    plain = copy.deepcopy(markup)
    for row in plain["inline_keyboard"]:
        for button in row:
            button.pop("style", None)
    return plain


async def _call(method: str, data: dict, files: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{Config.BOT_TOKEN}/{method}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, data=data, files=files)
    return resp.json()


async def send_post(chat_id: int, caption: str, markup: dict, poster: str | None):
    error = ""
    # first try with coloured buttons, then without colours
    for attempt in (markup, strip_style(markup)):
        data = {
            "chat_id": chat_id,
            "parse_mode": "HTML",
            "reply_markup": json.dumps(attempt),
        }
        if poster and os.path.exists(poster):
            data["caption"] = caption
            with open(poster, "rb") as photo:
                result = await _call("sendPhoto", data, {"photo": photo})
        else:
            data["text"] = caption
            result = await _call("sendMessage", data)

        if result.get("ok"):
            return True, ""
        error = result.get("description", "unknown error")
    return False, error


async def post_to_main_channels(
    cfg: dict,
    title: str,
    season: int,
    episode: int,
    language: str,
    links: dict,
    poster: str | None,
) -> list[str]:
    caption = build_caption(title, season, episode, language)
    markup = raw_quality_markup(links)
    errors = []
    for chat_id in cfg["main_channels"]:
        ok, error = await send_post(chat_id, caption, markup, poster)
        if not ok:
            errors.append(f"{chat_id}: {error}")
    return errors
    

class PostSink:
    """One main-channel post that shows progress and collects quality buttons."""

    def __init__(self, chat_id: int, message_id: int, is_photo: bool, join_link: str):
        self.chat_id = chat_id
        self.message_id = message_id
        self.is_photo = is_photo
        self.join_link = join_link
        self.links: dict = {}
        self.final = False
        self.styled = True
        self._last = None

    def add_link(self, quality: str, link: str):
        self.links[quality] = link

    def _markup(self) -> dict:
        rows = raw_quality_markup(self.links)["inline_keyboard"] if self.links else []
        if not self.final:
            rows = rows + [[{"text": "Join Now", "url": self.join_link}]]
        markup = {"inline_keyboard": rows}
        return markup if self.styled else strip_style(markup)

    async def edit(self, text: str):
        method = "editMessageCaption" if self.is_photo else "editMessageText"
        text_key = "caption" if self.is_photo else "text"

        for _ in range(3):
            markup = self._markup()
            key = (text, json.dumps(markup, sort_keys=True))
            if key == self._last:
                return

            result = await _call(
                method,
                {
                    "chat_id": self.chat_id,
                    "message_id": self.message_id,
                    text_key: text,
                    "parse_mode": "HTML",
                    "reply_markup": json.dumps(markup),
                },
            )
            if result.get("ok"):
                self._last = key
                return

            desc = result.get("description", "")
            if "not modified" in desc:
                self._last = key
                return

            retry = result.get("parameters", {}).get("retry_after")
            if retry:
                await asyncio.sleep(retry)
                continue

            if self.styled:
                self.styled = False  # fall back to plain buttons
                continue
            return

    async def finalize(self, caption: str):
        self.final = True
        await self.edit(caption)
