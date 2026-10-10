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
        f"<blockquote>{html.escape(title)}</blockquote>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"➥ Season: {season:02d}\n"
        f"➤ Episode: {episode:02d}\n"
        f"➥ Quality: Multi Quality [{language_label(language)}]\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"<blockquote>NEW EPISODE {episode:02d} ADDED 👇</blockquote>"
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
