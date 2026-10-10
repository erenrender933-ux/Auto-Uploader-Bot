import asyncio
import time


def humanbytes(size: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    n = 0
    size = float(size or 0)
    while size >= 1024 and n < len(units) - 1:
        size /= 1024
        n += 1
    return f"{size:.2f} {units[n]}"


def human_time(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def make_bar(percent: float, length: int = 14) -> str:
    percent = max(0.0, min(percent, 100.0))
    filled = int(length * percent / 100)
    return "▰" * filled + "▱" * (length - filled)


class Progress:
    """
    info  : dict with title, season, episode, language, quality
    sinks : objects with an async edit(text) method (PostSink)
    """

    def __init__(self, info: dict, sinks: list, interval: int = 7):
        self.info = info
        self.sinks = sinks
        self.interval = interval
        self.stage = "Downloading"
        self.start = time.time()
        self.last_edit = 0.0
        self._busy = False

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

    async def _push(self, text: str, force: bool = False):
        # skip if the previous edit is still running (keeps downloads fast)
        if self._busy and not force:
            return
        self._busy = True
        try:
            await asyncio.gather(
                *(sink.edit(text) for sink in self.sinks),
                return_exceptions=True,
            )
        finally:
            self._busy = False

    async def status(self, text: str):
        self.set_stage(text)
        await self._push(self._header() + f"<b>{text}</b>", force=True)

    async def update(self, current: int, total: int):
        """Download / upload callback (bytes)."""
        now = time.time()
        if now - self.last_edit < self.interval and current != total:
            return
        self.last_edit = now

        percent = (current * 100 / total) if total else 0
        elapsed = max(now - self.start, 1)
        speed = current / elapsed
        eta = (total - current) / speed if speed else 0

        await self._push(
            self._header()
            + f"<blockquote><b>{self.stage}...</blockquote></b>\n"
            + f"<b><blockquote>{make_bar(percent)} {percent:.1f}%</b></blockquote>\n\n"
            + f"<b>✅ Done:</b> {humanbytes(current)} / {humanbytes(total)}\n"
            + f"<b>⚡ Speed:</b> {humanbytes(speed)}/s\n"
            + f"<b>⏱️ ETA:</b> {human_time(eta)}"
        )

    async def update_encode(self, done_sec: float, total_sec: float):
        """ffmpeg callback (seconds of video processed)."""
        now = time.time()
        if now - self.last_edit < self.interval and done_sec < total_sec:
            return
        self.last_edit = now

        percent = (done_sec * 100 / total_sec) if total_sec else 0
        elapsed = max(now - self.start, 1)
        rate = done_sec / elapsed
        eta = (total_sec - done_sec) / rate if rate else 0

        await self._push(
            self._header()
            + "<b><blockquote>⚙️ Encoding Files...</blockquote></b>\n"
            + f"<blockquote><b>{make_bar(percent)} {percent:.1f}%</b></blockquote>\n\n"
            + f"⏱️<b>ETA:</b> {human_time(eta)}"
        )
