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
    episodes
    season
    seasonYear
    studios(isMain: true) { nodes { name } }
    coverImage { extraLarge large }
  }
}
"""


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

    description = re.sub(r"<.*?>", "", media.get("description") or "")
    studios = media["studios"]["nodes"]

    return {
        "title": media["title"]["english"] or media["title"]["romaji"],
        "synopsis": description.strip()[:450],
        "rating": (media.get("averageScore") or 0) / 10,
        "genres": media.get("genres", [])[:4],
        "status": media.get("status", "UNKNOWN"),
        "episodes": media.get("episodes"),
        "studio": studios[0]["name"] if studios else "Unknown",
        "poster_url": media["coverImage"]["extraLarge"],
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
