from PIL import Image


def prepare_thumb(src: str, dst: str):
    """Telegram thumbs must be JPEG, max 320px, under 200 KB."""
    try:
        with Image.open(src) as img:
            img = img.convert("RGB")
            img.thumbnail((320, 320))
            img.save(dst, "JPEG", quality=85)
        return dst
    except Exception:
        return None
