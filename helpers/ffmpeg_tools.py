import asyncio
import json
import os

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Size control per quality. Raise maxrate for bigger files, lower for smaller.
PROFILES = {
    "480p": {"height": 480, "crf": 30, "maxrate": "350k", "audio": "64k"},
    "720p": {"height": 720, "crf": 29, "maxrate": "650k", "audio": "96k"},
    "1080p": {"height": 1080, "crf": 28, "maxrate": "1200k", "audio": "128k"},
}
DEFAULT_PROFILE = {"height": 720, "crf": 28, "maxrate": "800k", "audio": "96k"}


async def _run(cmd: list):
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode(errors="ignore"), err.decode(errors="ignore")


async def probe(path: str) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    code, out, _ = await _run(cmd)
    info = {
        "duration": 0, "width": 0, "height": 0,
        "audio": [], "audio_streams": [],
    }
    if code != 0:
        return info
    data = json.loads(out)
    info["duration"] = int(float(data.get("format", {}).get("duration", 0)))
    for stream in data.get("streams", []):
        kind = stream.get("codec_type")
        if kind == "video" and not info["width"]:
            info["width"] = stream.get("width", 0)
            info["height"] = stream.get("height", 0)
        elif kind == "audio":
            tags = {k.lower(): v for k, v in stream.get("tags", {}).items()}
            info["audio"].append(stream.get("codec_name", "unknown"))
            info["audio_streams"].append(
                {
                    "lang": tags.get("language", "").lower(),
                    "title": tags.get("title", "").lower(),
                }
            )
    return info


async def make_thumbnail(path: str, out_path: str, duration: int) -> str | None:
    at = max(duration // 10, 1)
    cmd = [
        "ffmpeg", "-y", "-ss", str(at), "-i", path,
        "-frames:v", "1", "-vf", "scale=320:-1", out_path,
    ]
    code, _, _ = await _run(cmd)
    return out_path if code == 0 and os.path.exists(out_path) else None


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


async def process_video(
    input_path: str,
    output_path: str,
    *,
    title: str,
    author: str,
    watermark_text: str,
    watermark_enabled: bool,
    metadata_enabled: bool,
    quality: str = "",
    duration: int = 0,
    on_progress=None,
) -> tuple[bool, str]:
    profile = PROFILES.get(quality, DEFAULT_PROFILE)

    # explicit mapping: first video, every audio, every subtitle, attachments
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-map", "0:v:0", "-map", "0:a?", "-map", "0:s?", "-map", "0:t?",
    ]

    if watermark_enabled and watermark_text:
        drawtext = (
            f"drawtext=text='{_escape(watermark_text)}':"
            f"fontfile={FONT}:fontcolor=white@0.5:"
            f"fontsize=h/28:x=w-tw-20:y=20"
        )
        vf = f"scale=-2:'min(ih,{profile['height']})',{drawtext}"
        bufsize = f"{int(profile['maxrate'][:-1]) * 2}k"
        cmd += [
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast",
            "-profile:v", "high", "-level", "4.1",
            "-crf", str(profile["crf"]),
            "-maxrate", profile["maxrate"], "-bufsize", bufsize,
            "-pix_fmt", "yuv420p",
            # AAC stereo 48 kHz plays everywhere (VLC, MX Player, phones)
            "-c:a", "aac", "-b:a", profile["audio"],
            "-ac", "2", "-ar", "48000",
            "-af", "aresample=async=1:first_pts=0",
        ]
    else:
        cmd += ["-c:v", "copy", "-c:a", "copy"]

    cmd += ["-c:s", "copy"]

    if metadata_enabled:
        cmd += [
            "-metadata", f"title={title}",
            "-metadata", f"author={author}",
            "-metadata:s:v:0", f"title={author}",
        ]

    cmd += [
        "-max_muxing_queue_size", "1024",
        "-progress", "pipe:1", "-nostats",
        output_path,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    err_task = asyncio.create_task(proc.stderr.read())

    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        key, _, value = line.decode(errors="ignore").strip().partition("=")
        if key in ("out_time_us", "out_time_ms") and value.isdigit():
            if on_progress and duration:
                seconds = min(int(value) / 1_000_000, duration)
                await on_progress(seconds, duration)

    await proc.wait()
    err = (await err_task).decode(errors="ignore")

    if proc.returncode != 0:
        return False, err[-500:]
    if on_progress and duration:
        await on_progress(duration, duration)
    return True, ""
