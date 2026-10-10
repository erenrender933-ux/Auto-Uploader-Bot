import re
from dataclasses import dataclass
from typing import Optional

from guessit import guessit

LANGUAGE_MAP = {
    "tamil": "Tamil", "tam": "Tamil",
    "telugu": "Telugu", "tel": "Telugu",
    "hindi": "Hindi", "hin": "Hindi",
    "malayalam": "Malayalam", "mal": "Malayalam",
    "kannada": "Kannada",
    "english": "English", "eng": "English",
    "japanese": "Japanese", "jap": "Japanese", "jpn": "Japanese",
    "multi": "Multi Audio", "dual": "Dual Audio",
}


@dataclass
class ParsedFile:
    title: str
    season: int
    episode: int
    quality: str
    language: str
    extension: str


def _clean_title(raw: str) -> str:
    raw = re.sub(r"[\[\(].*?[\]\)]", " ", raw)   # remove [tags] and (tags)
    raw = re.sub(r"[._]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" -")
    return raw.title()


def detect_language(name: str) -> str:
    lowered = name.lower()
    for key, value in LANGUAGE_MAP.items():
        if re.search(rf"(?<![a-z]){key}(?![a-z])", lowered):
            return value
    return "Japanese"


def detect_quality(name: str, guess: dict) -> str:
    lowered = name.lower()
    if "hdrip" in lowered:
        return "HDRIP"
    size = str(guess.get("screen_size", "")).lower()
    if size in ("480p", "720p", "1080p", "2160p"):
        return size
    match = re.search(r"(480|720|1080|2160)p?", lowered)
    return f"{match.group(1)}p" if match else "720p"


def parse_filename(filename: str) -> Optional[ParsedFile]:
    guess = guessit(filename, {"type": "episode"})

    title = guess.get("title")
    if not title:
        return None

    season = guess.get("season", 1)
    episode = guess.get("episode")

    # fallback: "Title - 05" style names
    if episode is None:
        match = re.search(r"[\s_\-\[]E?(\d{1,3})[\s_\-\]]", filename)
        if not match:
            return None
        episode = int(match.group(1))

    if isinstance(season, list):
        season = season[0]
    if isinstance(episode, list):
        episode = episode[0]

    return ParsedFile(
        title=_clean_title(str(title)),
        season=int(season),
        episode=int(episode),
        quality=detect_quality(filename, guess),
        language=detect_language(filename),
        extension=guess.get("container", "mkv"),
)
