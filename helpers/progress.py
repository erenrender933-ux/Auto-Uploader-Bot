import time

from pyrogram.errors import FloodWait, MessageNotModified
import asyncio


def humanbytes(size: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    n = 0
    size = float(size or 0)
    while size >= 1024 and n < len(units) - 1:
        size /= 1024
        n += 1
    return f"{size:.2f} {units[n]}"


def human_time(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def make_bar(percent: float, length: int = 14) -> str:
    filled = int(length * percent / 100)
    return "▰" * filled + "▱" * (length - filled)


class Progress:
    """
    info    : dict with title, season, episode, language, quality
    targets : list of (message, reply_markup) that get edited live
    """

    def __init__(self, info: dict, targets: list, interval: int = 5):
        self.info = info
        self.targets = targets
        self.interval = interval
        self.stage = "Downloading"
        self.start = time.time()
        self.last_edit = 0.0

    def set_stage(self, stage: str):
        self.stage = stage
        self.start = time.time()
        self.last_edit = 0.0

    def _header(self) -> str:
        i = self.info
        return (
            f"<b>{i['title']}</b>\n\n"
            f"<b>Season:</b> {int(i['season']):02d}\n"
            f"<b>Episode:</b> {int(i['episode']):02d}\n"
            f"<b>Language:</b> {i['language']}\n"
            f"<b>Quality:</b> {i['quality']}\n\n"
        )

    async def _edit_all(self, text: str):
        for message, markup in self.targets:
            try:
                await message.edit_text(text, reply_markup=markup)
            except MessageNotModified:
                pass
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception:
                pass

    async def status(self, text: str):
        """Message without a bar, e.g. 'Setup File Processing...!'"""
        self.set_stage(text)
        await self._edit_all(self._header() + f"<b>{text}</b>")

    async def update(self, current: int, total: int):
        """Pass this as the progress= callback in Pyrogram."""
        now = time.time()
        if now - self.last_edit < self.interval and current != total:
            return
        self.last_edit = now

        percent = (current * 100 / total) if total else 0
        elapsed = max(now - self.start, 1)
        speed = current / elapsed
        eta = (total - current) / speed if speed else 0

        text = (
            self._header()
            + f"<b>{self.stage}...</b>\n"
            + f"{make_bar(percent)} {percent:.1f}%\n\n"
            + f"<b>Done:</b> {humanbytes(current)} / {humanbytes(total)}\n"
            + f"<b>Speed:</b> {humanbytes(speed)}/s\n"
            + f"<b>ETA:</b> {human_time(eta)}"
        )
        await self._edit_all(text)
