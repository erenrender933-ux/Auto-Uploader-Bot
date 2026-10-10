from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Telegram button colours: success = green, primary = blue, danger = red
STYLES = {
    "480p": "success",
    "720p": "primary",
    "1080p": "danger",
    "HDRIP": "primary",
}
ROW_ONE = ["480p", "720p", "1080p"]


def raw_quality_markup(links: dict) -> dict:
    """Coloured buttons for a direct Bot API call (used in post.py)."""
    rows = []
    first = [
        {"text": q, "url": links[q], "style": STYLES[q]}
        for q in ROW_ONE if q in links
    ]
    if first:
        rows.append(first)
    if "HDRIP" in links:
        rows.append([{"text": "HDRIP", "url": links["HDRIP"], "style": STYLES["HDRIP"]}])
    return {"inline_keyboard": rows}


def plain_quality_markup(links: dict) -> InlineKeyboardMarkup:
    """Fallback without colours, if the colour request fails."""
    rows = []
    first = [InlineKeyboardButton(q, url=links[q]) for q in ROW_ONE if q in links]
    if first:
        rows.append(first)
    if "HDRIP" in links:
        rows.append([InlineKeyboardButton("HDRIP", url=links["HDRIP"])])
    return InlineKeyboardMarkup(rows)


def join_markup(join_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Join Now", url=join_link)]])
