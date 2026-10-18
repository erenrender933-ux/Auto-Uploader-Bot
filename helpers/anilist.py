import html
import os
import re
from typing import Optional

import httpx

from config import Config

API_URL = "https://graphql.anilist.co"

QUERY = """
query ($search: String) {
  Media(search: $search, type: ANIME) {
    title { romaji english }
    description(asHtml: false)
    averageScore
    genres
    status
    format
    episodes
    season
    seasonYear
    studios(isMain: true) { nodes { name } }
    coverImage { extraLarge large }
    bannerImage
  }
}
"""


def _clean(text: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\(Source:[^)]*\)", "", text, flags=re.I)
    text = re.sub(r"Note:.*", "", text, flags=re.I | re.S)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _format_label(value: Optional[str]) -> str:
    if not value:
        return ""
    if value == "TV":
        return "TV"
    return value.replace("_", " ").title()


async def fetch_anime(title: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                API_URL, json={"query": QUERY, "variables": {"search": title}}
            )
            resp.raise_for_status()
            media = resp.json()["data"]["Media"]
    except Exception:
        return None

    if not media:
        return None

    studios = media["studios"]["nodes"]
    season = (media.get("season") or "").title()
    year = media.get("seasonYear") or ""
    score = media.get("averageScore") or 0

    return {
        "title": media["title"]["english"] or media["title"]["romaji"],
        "synopsis": _clean(media.get("description") or ""),
        "score": score,
        "rating": score / 10,
        "genres": media.get("genres", [])[:3],
        "status": media.get("status", "UNKNOWN"),
        "format": _format_label(media.get("format")),
        "episodes": media.get("episodes"),
        "season_label": f"{season} {year}".strip(),
        "studio": studios[0]["name"] if studios else "",
        "poster_url": media["coverImage"]["extraLarge"],
        "banner_url": media.get("bannerImage"),
    }


async def download_poster(url: str, name: str) -> Optional[str]:
    path = os.path.join(Config.DOWNLOAD_DIR, f"{name}_poster.jpg")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)
        return path
    except Exception:
        return None
