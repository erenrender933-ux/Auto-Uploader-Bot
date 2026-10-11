import asyncio
import html
import time

from pyrogram.errors import FloodWait, MessageNotModified


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
        return f"{h}h, {m}m, {s}s"
    if m:
        return f"{m}m, {s}s"
    return f"{s}s"


def make_bar(percent: float, length: int = 12) -> str:
    percent = max(0.0, min(percent, 100.0))
    filled = int(length * percent / 100)
    return "■" * filled + "□" * (length - filled)


class Progress:
    """
    name  : output file name shown as "Anime Name"
    sinks : objects with an async edit(text) method
    stats : {"done": int, "total": int} shared by the whole task
    """

    def __init__(self, name: str, sinks: list, stats: dict | None = None,
                 task_id: int = 0, interval: int = 7):
        self.name = name
        self.sinks = sinks
        self.stats = stats or {"done": 0, "total": 0}
        self.task_id = task_id
        self.interval = interval
        self.stage = "Downloading"
        self.start = time.time()
        self.last_edit = 0.0
        self._busy = False

    def set_stage(self, stage: str):
        self.stage = stage
        self.start = time.time()
        self.last_edit = 0.0

    def _text(self, status: str, percent=None, size_line="", speed=0.0, left=0.0):
        parts = [
            f"<blockquote>▶ <b>Anime Name :</b> <i>{html.escape(self.name)}</i></blockquote>"
        ]
        if percent is None:
            parts.append(
                f"<blockquote>▶ <b>Status :</b> <i>{html.escape(status)}</i></blockquote>"
            )
        else:
            took = time.time() - self.start
            parts.append(
                f"<blockquote>▶ <b>Status :</b> <i>{html.escape(status)}</i>\n"
                f"   [{make_bar(percent)}] {percent:.2f}%</blockquote>"
            )
            parts.append(
                f"<blockquote>   ▶ <b>Size :</b> {size_line}\n"
                f"   ▶ <b>Speed :</b> {humanbytes(speed)}/s\n"
                f"   ▶ <b>Time Took :</b> {human_time(took)}\n"
                f"   ▶ <b>Time Left :</b> {human_time(left)}</blockquote>"
            )
        parts.append(
            f"<blockquote>▶ <b>File(s) Encoded:</b> "
            f"{self.stats['done']} / {self.stats['total']}\n"
            f"▶ <b>Task ID :</b> {self.task_id}</blockquote>"
        )
        return "\n".join(parts)

    async def _push(self, text: str, force: bool = False):
        # skip if the previous edit is still running (keeps transfers fast)
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
        await self._push(self._text(text), force=True)

    async def update(self, current: int, total: int):
        """Download / upload callback (bytes)."""
        now = time.time()
        if now - self.last_edit < self.interval and current != total:
            return
        self.last_edit = now

        percent = (current * 100 / total) if total else 0
        elapsed = max(now - self.start, 1)
        speed = current / elapsed
        left = (total - current) / speed if speed else 0

        await self._push(
            self._text(
                self.stage, percent,
                f"{humanbytes(current)} out of ~ {humanbytes(total)}",
                speed, left,
            )
        )

    async def update_encode(self, done_sec: float, total_sec: float, out_size: int = 0):
        """ffmpeg callback (seconds of video done, bytes written so far)."""
        now = time.time()
        if now - self.last_edit < self.interval and done_sec < total_sec:
            return
        self.last_edit = now

        percent = (done_sec * 100 / total_sec) if total_sec else 0
        elapsed = max(now - self.start, 1)
        rate = done_sec / elapsed
        left = (total_sec - done_sec) / rate if rate else 0
        estimate = out_size * total_sec / done_sec if done_sec else 0
        speed = out_size / elapsed

        await self._push(
            self._text(
                self.stage, percent,
                f"{humanbytes(out_size)} out of ~ {humanbytes(estimate)}",
                speed, left,
            )
        )


class ProgressSink:
    """A separate progress message under the main channel post."""

    def __init__(self, message, markup=None):
        self.message = message
        self.markup = markup
        self._last = None

    async def edit(self, text: str):
        if text == self._last:
            return
        try:
            await self.message.edit_text(text, reply_markup=self.markup)
            self._last = text
        except MessageNotModified:
            self._last = text
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            pass

    async def delete(self):
        try:
            await self.message.delete()
        except Exception:
            pass
