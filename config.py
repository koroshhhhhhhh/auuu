"""Settings. Everything here can be overridden from the .env file."""
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Seconds a user must wait after a finished request before the next one.
COOLDOWN_SECONDS = _int("COOLDOWN_SECONDS", 12)

# How many FFmpeg processes may run at the same time.
MAX_CONCURRENT_JOBS = _int("MAX_CONCURRENT_JOBS", 4)

# FFmpeg / FFprobe executables. Leave as is when they are in PATH.
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "ffprobe")

AUDIO_BITRATE = os.getenv("AUDIO_BITRATE", "192k")
FFMPEG_TIMEOUT = _int("FFMPEG_TIMEOUT", 300)

# Telegram Bot API limits (cloud Bot API).
MAX_VIDEO_BYTES = 20 * 1024 * 1024
MAX_AUDIO_BYTES = 50 * 1024 * 1024

# Seconds before an unanswered confirmation expires.
PENDING_TTL = 600

# Minimum seconds between two progress edits (Telegram flood protection).
EDIT_INTERVAL = 1.2

TEMP_DIR = Path(os.getenv("TEMP_DIR") or tempfile.gettempdir()) / "mp3bot"
