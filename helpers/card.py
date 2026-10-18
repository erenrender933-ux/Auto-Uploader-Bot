import asyncio
import io
import math

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
W, H = 1280, 640


def _font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int, max_lines: int = 2) -> list:
    lines, line = [], ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=font) <= max_w:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,") + "..."
    return lines


def _star(draw, cx: int, cy: int, r: int, color):
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = r if i % 2 == 0 else r * 0.45
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    draw.polygon(points, fill=color)


def _compose(cover_bytes: bytes, data: dict, out_path: str) -> str:
    cover = Image.open(io.BytesIO(cover_bytes)).convert("RGB")

    # blurred, darkened background made from the cover
    scale = max(W / cover.width, H / cover.height)
    bg = cover.resize((int(cover.width * scale), int(cover.height * scale)))
    left, top = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(28))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (10, 10, 18)), 0.62)

    # cover art on the right with a soft left edge
    cw = int(cover.width * H / cover.height)
    art = cover.resize((cw, H))
    mask = Image.new("L", (cw, H), 255)
    md = ImageDraw.Draw(mask)
    fade = 120
    for x in range(min(fade, cw)):
        md.line([(x, 0), (x, H)], fill=int(255 * x / fade))
    bg.paste(art, (W - cw, 0), mask)

    draw = ImageDraw.Draw(bg)
    x = 70
    max_w = W - cw - x - 30

    # small info line
    parts = [data.get("season_label"), data.get("format")]
    if data.get("episodes"):
        parts.append(f"{data['episodes']} Episodes")
    info = "  •  ".join(p for p in parts if p)
    draw.text((x, 80), info, font=_font(REGULAR, 26), fill=(205, 205, 215))

    # title
    title = data.get("title", "")
    size = 70 if len(title) <= 22 else 56 if len(title) <= 40 else 44
    tfont = _font(BOLD, size)
    y = 140
    for line in _wrap(draw, title, tfont, max_w):
        draw.text((x, y), line, font=tfont, fill=(255, 255, 255))
        y += size + 10

    # studio
    if data.get("studio"):
        draw.text((x, y + 6), data["studio"], font=_font(REGULAR, 32), fill=(255, 107, 129))

    # rating
    if data.get("score"):
        ry = H - 240
        _star(draw, x + 26, ry + 34, 28, (255, 79, 129))
        draw.text((x + 70, ry), f"{data['score']}%", font=_font(BOLD, 58), fill=(255, 255, 255))

    # genre chips
    cx, cy = x, H - 130
    cfont = _font(REGULAR, 26)
    for genre in data.get("genres", []):
        tw = draw.textlength(genre, font=cfont)
        draw.rounded_rectangle(
            (cx, cy, cx + tw + 44, cy + 54), radius=27,
            fill=(52, 52, 64), outline=(150, 150, 165), width=2,
        )
        draw.text((cx + 22, cy + 12), genre, font=cfont, fill=(235, 235, 240))
        cx += int(tw) + 64

    bg.save(out_path, "JPEG", quality=90)
    return out_path


async def make_card(data: dict, out_path: str):
    """Create the anime info card. Returns the file path, or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(data["poster_url"])
            resp.raise_for_status()
        return await asyncio.to_thread(_compose, resp.content, data, out_path)
    except Exception:
        return None
