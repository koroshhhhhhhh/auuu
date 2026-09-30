"""Telegram handlers: confirmation flow, progress message, cooldown, help."""
import asyncio
import contextlib
import logging
import math
import re
import shutil
import time
import uuid
from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, RetryAfter, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

import config
import converter
import texts
from converter import ConvertError

log = logging.getLogger("mp3bot.handlers")


# ---------- cooldown ----------

class Limiter:
    def __init__(self) -> None:
        self._until: dict[int, float] = {}
        self._active: set[int] = set()

    def check(self, uid: int) -> str | None:
        """Return a message to show if the user must wait, else None."""
        if uid in self._active:
            return texts.BUSY
        remaining = self._until.get(uid, 0) - time.monotonic()
        if remaining > 0:
            return texts.COOLDOWN.format(seconds=math.ceil(remaining))
        return None

    def start(self, uid: int) -> None:
        self._active.add(uid)

    def finish(self, uid: int) -> None:
        self._active.discard(uid)
        now = time.monotonic()
        self._until[uid] = now + config.COOLDOWN_SECONDS
        if len(self._until) > 1000:
            self._until = {u: t for u, t in self._until.items() if t > now}


limiter = Limiter()


# ---------- pending confirmations ----------

@dataclass
class Pending:
    user_id: int
    file_id: str
    file_size: int | None
    video_msg_id: int
    thread_id: int | None
    created: float


PENDING: dict[tuple[int, int], Pending] = {}


def _prune_pending() -> None:
    limit = time.monotonic() - config.PENDING_TTL
    for key in [k for k, p in PENDING.items() if p.created < limit]:
        PENDING.pop(key, None)


def _keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(texts.BTN_YES, callback_data="yes", style="primary"),
        InlineKeyboardButton(texts.BTN_NO, callback_data="no", style="danger"),
    ]])


def _media(msg: Message | None) -> tuple[str, int | None] | None:
    """(file_id, file_size) if the message holds a video, else None."""
    if msg is None:
        return None
    if msg.video:
        return msg.video.file_id, msg.video.file_size
    if msg.video_note:
        return msg.video_note.file_id, msg.video_note.file_size
    doc = msg.document
    if doc and (doc.mime_type or "").startswith("video/"):
        return doc.file_id, doc.file_size
    return None


# ---------- progress message ----------

class Progress:
    """Edits one message. Values are set synchronously, edits are throttled."""

    def __init__(self, bot, chat_id: int, message_id: int, first_text: str):
        self.bot, self.chat_id, self.message_id = bot, chat_id, message_id
        self.percent = 0
        self.stage = texts.STAGE_DOWNLOAD
        self._last = first_text
        self._task = asyncio.create_task(self._loop())

    def set(self, percent: float, stage: str | None = None) -> None:
        self.percent = max(self.percent, min(100, int(percent)))
        if stage:
            self.stage = stage

    async def _edit(self, text: str) -> None:
        if text == self._last:
            return
        try:
            await self.bot.edit_message_text(text, chat_id=self.chat_id, message_id=self.message_id)
            self._last = text
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.5)
        except BadRequest as e:
            if "not modified" in str(e).lower():
                self._last = text
            else:
                log.debug("edit failed: %s", e)
        except TelegramError as e:
            log.debug("edit failed: %s", e)

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(config.EDIT_INTERVAL)
            await self._edit(texts.progress_text(self.stage, self.percent))

    async def _stop(self) -> None:
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def finish(self) -> None:
        await self._stop()
        await self._edit(texts.progress_text(texts.STAGE_DONE, 100))

    async def fail(self, text: str) -> None:
        await self._stop()
        await self._edit(text)


# ---------- the job ----------

async def run_job(app: Application, chat_id: int, prompt_id: int, p: Pending) -> None:
    progress = Progress(app.bot, chat_id, prompt_id, texts.progress_text(texts.STAGE_DOWNLOAD, 0))
    job_dir = config.TEMP_DIR / uuid.uuid4().hex
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
        src, dst = job_dir / "video", job_dir / "audio.mp3"

        tg_file = await app.bot.get_file(p.file_id)
        await converter.download(tg_file.file_path, src, p.file_size, lambda f: progress.set(f * 40))

        duration, codec = await converter.probe(src)
        if codec is None:
            raise ConvertError(texts.ERR_NO_AUDIO)

        progress.set(40, texts.STAGE_CONVERT)
        async with converter.SEM:
            await converter.to_mp3(src, dst, duration, codec, lambda f: progress.set(40 + f * 40))
        src.unlink(missing_ok=True)

        if dst.stat().st_size > config.MAX_AUDIO_BYTES:
            raise ConvertError(texts.ERR_OUTPUT_BIG)

        progress.set(80, texts.STAGE_UPLOAD)
        await converter.send_audio(
            chat_id, dst, f"@{app.bot.username}", duration, p.video_msg_id, p.thread_id,
            lambda f: progress.set(80 + f * 20),
        )
        await progress.finish()
    except ConvertError as e:
        await progress.fail(e.user_text)
    except Exception:
        log.exception("job failed")
        await progress.fail(texts.ERR_GENERIC)
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)
        limiter.finish(p.user_id)


# ---------- handlers ----------

async def _ask(update: Update, video_msg: Message | None) -> None:
    msg, user = update.effective_message, update.effective_user
    media = _media(video_msg)
    if not (msg and user and video_msg and media):
        return
    file_id, size = media
    if size and size > config.MAX_VIDEO_BYTES:
        await msg.reply_text(texts.ERR_TOO_BIG)
        return
    blocked = limiter.check(user.id)
    if blocked:
        await msg.reply_text(blocked)
        return
    sent = await msg.reply_text(texts.CONFIRM, reply_markup=_keyboard())
    _prune_pending()
    PENDING[(sent.chat_id, sent.message_id)] = Pending(
        user_id=user.id, file_id=file_id, file_size=size, video_msg_id=video_msg.message_id,
        thread_id=video_msg.message_thread_id if video_msg.is_topic_message else None,
        created=time.monotonic(),
    )


async def on_private_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask(update, update.effective_message)


async def on_mp3_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    await _ask(update, msg.reply_to_message if msg else None)


async def _answer(query, text: str | None = None, alert: bool = False) -> None:
    with contextlib.suppress(TelegramError):
        await query.answer(text, show_alert=alert)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.message:
        return
    chat_id, prompt_id = q.message.chat.id, q.message.message_id
    p = PENDING.get((chat_id, prompt_id))
    if p is None:
        await _answer(q, texts.EXPIRED, True)
        return
    if q.from_user.id != p.user_id:
        await _answer(q, texts.NOT_YOURS, True)
        return

    if q.data == "no":
        PENDING.pop((chat_id, prompt_id), None)
        await _answer(q)
        with contextlib.suppress(TelegramError):
            await q.edit_message_text(texts.CANCELLED)
        return

    if q.data != "yes":
        await _answer(q)
        return
    blocked = limiter.check(p.user_id)
    if blocked:
        await _answer(q, blocked, True)
        return

    # From here on everything is synchronous until the job is registered,
    # so a double click can never start two jobs.
    PENDING.pop((chat_id, prompt_id), None)
    limiter.start(p.user_id)
    await _answer(q)
    first = texts.progress_text(texts.STAGE_DOWNLOAD, 0)
    with contextlib.suppress(TelegramError):
        await q.edit_message_text(first)
    context.application.create_task(run_job(context.application, chat_id, prompt_id, p))


async def on_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(texts.HELP, parse_mode=ParseMode.HTML)


def register(app: Application) -> None:
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(CommandHandler(["start", "help"], on_help))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/راهنما(@\w+)?\s*$"), on_help))
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & ~filters.ANIMATION
        & (filters.VIDEO | filters.VIDEO_NOTE | filters.Document.VIDEO),
        on_private_video,
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & filters.REPLY & filters.Regex(re.compile(r"^\s*mp3\s*$", re.IGNORECASE)),
        on_mp3_reply,
    ))
