import asyncio
import json
import os
import re

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Size control per quality. Raise maxrate for bigger files, lower for smaller.
PROFILES = {
    "480p": {"height": 480, "crf": 30, "maxrate": "350k", "audio": "64k"},
    "720p": {"height": 720, "crf": 29, "maxrate": "650k", "audio": "96k"},
    "1080p": {"height": 1080, "crf": 28, "maxrate": "1200k", "audio": "128k"},
}
DEFAULT_PROFILE = {"height": 720, "crf": 28, "maxrate": "800k", "audio": "96k"}

# Language names and the codes / words used in audio stream tags
LANG_CODES = {
    "Tamil": {"tam", "ta", "tamil"},
    "Telugu": {"tel", "te", "telugu"},
    "Hindi": {"hin", "hi", "hindi"},
    "Malayalam": {"mal", "ml", "malayalam"},
    "Kannada": {"kan", "kn", "kannada"},
    "English": {"eng", "en", "english"},
    "Japanese": {"jpn", "ja", "jap", "japanese"},
}
ISO3 = {
    "Tamil": "tam", "Telugu": "tel", "Hindi": "hin", "Malayalam": "mal",
    "Kannada": "kan", "English": "eng", "Japanese": "jpn",
}


def pick_audio(streams: list, language: str) -> list:
    """Return the audio stream positions (0-based) matching the language."""
    codes = LANG_CODES.get(language, {language.lower()})
    names = {c for c in codes if len(c) > 3}
    picked = []
    for i, s in enumerate(streams):
        title = s.get("title", "")
        if s.get("lang", "") in codes or any(n in title for n in names):
            picked.append(i)
    if not picked and len(streams) == 1:
        picked = [0]  # single track without a language tag
    return picked


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


async def mean_volume(path: str, start: float, length: int = 30):
    """Mean volume (dB) of the first audio track. About -91 means silence."""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-ss", str(int(start)), "-t", str(length), "-i", path,
        "-map", "0:a:0", "-vn", "-af", "volumedetect", "-f", "null", "-",
    ]
    _, _, err = await _run(cmd)
    match = re.search(r"mean_volume:\s*(-inf|-?[\d.]+) dB", err)
    if not match:
        return None
    return -99.0 if match.group(1) == "-inf" else float(match.group(1))


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
    audio_indexes: list | None = None,
    has_audio: bool = True,
    language: str = "",
    on_progress=None,
) -> tuple[bool, str]:
    profile = PROFILES.get(quality, DEFAULT_PROFILE)

    if audio_indexes is not None:
        # language filter: video + chosen audio only, nothing else
        cmd = ["ffmpeg", "-y", "-i", input_path, "-map", "0:v:0"]
        for i in audio_indexes:
            cmd += ["-map", f"0:a:{i}"]
        cmd += ["-sn", "-dn"]
    else:
        # keep everything: first video, every audio, subtitles, attachments
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-map", "0:v:0", "-map", "0:a?", "-map", "0:s?", "-map", "0:t?",
            "-c:s", "copy",
        ]

    cmd += ["-map_chapters", "-1"]

    if watermark_enabled and watermark_text:
        drawtext = (
            f"drawtext=text='{_escape(watermark_text)}':"
            f"fontfile={FONT}:fontcolor=white@0.5:"
            f"fontsize=h/28:x=w-tw-20:y=20"
        )
        vf = (
            f"scale=-2:'min(ih,{profile['height']})':flags=fast_bilinear,"
            f"{drawtext}"
        )
        bufsize = f"{int(profile['maxrate'][:-1]) * 2}k"
        cmd += [
            "-vf", vf,
            "-c:v", "libx264", "-preset", "superfast",
            "-profile:v", "high", "-level", "4.1",
            "-crf", str(profile["crf"]),
            "-maxrate", profile["maxrate"], "-bufsize", bufsize,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", profile["audio"],
            "-ac", "2", "-ar", "48000",
        ]
    else:
        cmd += ["-c:v", "copy", "-c:a", "copy"]

    if audio_indexes:
        cmd += ["-disposition:a:0", "default"]
        if language in ISO3:
            for n in range(len(audio_indexes)):
                cmd += [f"-metadata:s:a:{n}", f"language={ISO3[language]}"]

    if metadata_enabled:
        cmd += [
            "-map_metadata", "-1",  # remove the old tags from the source
            "-metadata", f"title={title}",
            "-metadata", f"author={author}",
            "-metadata", f"artist={author}",
            "-metadata", f"comment={author}",
            "-metadata", f"encoded_by={author}",
            "-metadata:s:v", f"title={author}",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
        ]
        if has_audio:
            cmd += ["-metadata:s:a", f"title={author}"]

    cmd += [
        "-max_muxing_queue_size", "1024",
        "-progress", "pipe:1", "-nostats",
        output_path,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    err_task = asyncio.create_task(proc.stderr.read())

    seconds, size = 0.0, 0
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        key, _, value = line.decode(errors="ignore").strip().partition("=")
        if key == "total_size" and value.isdigit():
            size = int(value)
        elif key in ("out_time_us", "out_time_ms") and value.isdigit():
            seconds = int(value) / 1_000_000
        elif key == "progress" and on_progress and duration:
            await on_progress(min(seconds, duration), duration, size)

    await proc.wait()
    err = (await err_task).decode(errors="ignore")

    if proc.returncode != 0:
        return False, err[-500:]
    if on_progress and duration:
        final = os.path.getsize(output_path) if os.path.exists(output_path) else size
        await on_progress(duration, duration, final)
    return True, ""
