"""Local media → small audio file, for `amperstand capture-file`.

The server does the transcription; this side only uses ffmpeg to pull a mono
32 kbps audio track out of the recording, so a two-hour video uploads as
about 35 MB instead of gigabytes.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

AUDIO_ARGS = ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "aac", "-b:a", "32k"]
AUDIO_SUFFIX = ".m4a"


class MediaError(Exception):
    """The file can't be read or converted locally."""


@dataclass(frozen=True)
class MediaInfo:
    duration: float  # seconds
    has_video: bool


def find_tools() -> tuple[str, str]:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise MediaError(
            "ffmpeg is not installed (capture-file needs ffmpeg and ffprobe on PATH). "
            "Install it with `brew install ffmpeg` on macOS or `sudo apt install ffmpeg` on Debian/Ubuntu."
        )
    return ffmpeg, ffprobe


def probe(path: Path, ffprobe: str) -> MediaInfo:
    """Duration and stream kinds. Raises MediaError when there is no audio to transcribe."""
    r = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type",
         "-of", "default=nw=1", str(path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise MediaError(f"ffprobe can't read {path.name}: {r.stderr.strip()[:300]}")
    kinds = re.findall(r"^codec_type=(\w+)$", r.stdout, re.M)
    if "audio" not in kinds:
        raise MediaError(f"{path.name} has no audio track")
    m = re.search(r"^duration=([\d.]+)$", r.stdout, re.M)
    if not m or float(m.group(1)) <= 0:
        raise MediaError(f"ffprobe reports no duration for {path.name}")
    return MediaInfo(duration=float(m.group(1)), has_video="video" in kinds)


def extract_audio(path: Path, dest_dir: Path, ffmpeg: str) -> Path:
    """Write the recording's audio as a small mono AAC file; returns its path."""
    out = dest_dir / f"audio{AUDIO_SUFFIX}"
    r = subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(path), *AUDIO_ARGS, str(out)],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise MediaError(f"ffmpeg couldn't extract the audio: {r.stderr.strip()[:300]}")
    return out


def hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def title_from_filename(path: Path) -> str:
    """'riverside_ai_seo (1).mp4' → 'riverside ai seo'."""
    stem = re.sub(r"\s*\(\d+\)$", "", path.stem)
    return re.sub(r"[_\s]+", " ", stem).strip() or path.name
