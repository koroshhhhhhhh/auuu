"""Download, FFmpeg conversion and upload. No Telegram-library code here."""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Callable

import httpx

import config
import texts

log = logging.getLogger("mp3bot.converter")

API_URL = "https://api.telegram.org"
SEM = asyncio.Semaphore(config.MAX_CONCURRENT_JOBS)

ProgressCb = Callable[[float], None]  # receives a fraction between 0 and 1

_client: httpx.AsyncClient | None = None


class ConvertError(Exception):
    """Error whose text is safe to show to the user."""

    def __init__(self, user_text: str):
        super().__init__(user_text)
        self.user_text = user_text


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10, read=120, write=300, pool=30),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            transport=httpx.AsyncHTTPTransport(retries=2),
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def download(url: str, dest: Path, size_hint: int | None, on_progress: ProgressCb) -> None:
    async with get_client().stream("GET", url) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or size_hint or 0)
        done = 0
        with open(dest, "wb") as f:
            async for chunk in r.aiter_bytes(256 * 1024):
                f.write(chunk)
                done += len(chunk)
                if total:
                    on_progress(min(done / total, 1.0))
    on_progress(1.0)


async def probe(path: Path) -> tuple[float, str | None]:
    """Return (duration in seconds, first audio codec or None)."""
    proc = await asyncio.create_subprocess_exec(
        config.FFPROBE_PATH, "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,codec_name",
        "-of", "json", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        log.error("ffprobe failed: %s", err.decode(errors="replace")[-500:])
        raise ConvertError(texts.ERR_GENERIC)
    data = json.loads(out or b"{}")
    audio = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    try:
        duration = float(data.get("format", {}).get("duration") or 0)
    except ValueError:
        duration = 0.0
    return duration, (audio[0].get("codec_name") if audio else None)


async def to_mp3(src: Path, dst: Path, duration: float, codec: str | None, on_progress: ProgressCb) -> None:
    # Already MP3 audio: copy the stream (instant). Otherwise encode.
    audio_args = ["-c:a", "copy"] if codec == "mp3" else ["-c:a", "libmp3lame", "-b:a", config.AUDIO_BITRATE]
    args = [
        config.FFMPEG_PATH, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src), "-map", "0:a:0", "-vn", "-sn", "-dn", *audio_args,
        "-f", "mp3", "-progress", "pipe:1", "-nostats", str(dst),
    ]
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    async def _read_progress() -> None:
        assert proc.stdout is not None
        async for line in proc.stdout:
            if line.startswith((b"out_time_us=", b"out_time_ms=")) and duration > 0:
                try:
                    seconds = int(line.split(b"=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                on_progress(max(0.0, min(seconds / duration, 1.0)))

    async def _run() -> bytes:
        assert proc.stderr is not None
        err_task = asyncio.create_task(proc.stderr.read())
        await _read_progress()
        await proc.wait()
        return await err_task

    try:
        err = await asyncio.wait_for(_run(), timeout=config.FFMPEG_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        log.error("ffmpeg timed out")
        raise ConvertError(texts.ERR_GENERIC)
    except asyncio.CancelledError:
        proc.kill()
        raise

    if proc.returncode != 0 or not dst.exists():
        log.error("ffmpeg failed: %s", err.decode(errors="replace")[-500:])
        raise ConvertError(texts.ERR_GENERIC)
    on_progress(1.0)


class _Reader:
    """File wrapper that reports how much has been handed to the network."""

    def __init__(self, path: Path, on_progress: ProgressCb):
        self._f = open(path, "rb")
        self._size = max(os.path.getsize(path), 1)
        self._cb = on_progress

    def read(self, n: int = -1) -> bytes:
        data = self._f.read(n)
        self._cb(min(self._f.tell() / self._size, 1.0))
        return data

    def seek(self, *args):
        return self._f.seek(*args)

    def tell(self) -> int:
        return self._f.tell()

    def close(self) -> None:
        self._f.close()


async def send_audio(
    chat_id: int, path: Path, caption: str, duration: float,
    reply_to: int, thread_id: int | None, on_progress: ProgressCb,
) -> None:
    url = f"{API_URL}/bot{config.BOT_TOKEN}/sendAudio"
    data = {
        "chat_id": str(chat_id),
        "caption": caption,
        "duration": str(int(duration)),
        "reply_parameters": json.dumps({"message_id": reply_to, "allow_sending_without_reply": True}),
    }
    if thread_id:
        data["message_thread_id"] = str(thread_id)

    for attempt in range(3):
        reader = _Reader(path, on_progress)
        try:
            r = await get_client().post(url, data=data, files={"audio": ("audio.mp3", reader, "audio/mpeg")})
        finally:
            reader.close()
        try:
            body = r.json()
        except ValueError:
            body = {}
        if body.get("ok"):
            return
        retry = (body.get("parameters") or {}).get("retry_after")
        if retry and attempt < 2:
            await asyncio.sleep(retry + 0.5)
            continue
        log.error("sendAudio failed: %s %s", r.status_code, str(body)[:300])
        raise ConvertError(texts.ERR_GENERIC)
