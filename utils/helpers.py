import os
import re
import uuid
from pathlib import Path
from typing import Optional
from aiogram import Bot
from aiogram.types import Message, FSInputFile


# ── URL Detection ──────────────────────────────────────────────────────────────

URL_RE = re.compile(
    r'https?://[^\s<>"{}|\\^`\[\]]+'
)

SUPPORTED_DOMAINS = [
    "youtube.com", "youtu.be",
    "tiktok.com", "vm.tiktok.com",
    "instagram.com",
    "twitter.com", "x.com",
    "facebook.com", "fb.watch",
    "twitch.tv",
    "reddit.com", "v.redd.it",
    "dailymotion.com",
    "vimeo.com",
    "threads.net",
    "linkedin.com",
    "pinterest.com",
    "bilibili.com",
    "rumble.com",
    "odysee.com",
    "soundcloud.com",
    "mixcloud.com",
    "bandcamp.com",
    "streamable.com",
    "gfycat.com",
    "imgur.com",
]


def extract_url(text: str) -> Optional[str]:
    match = URL_RE.search(text or "")
    return match.group(0) if match else None


def is_supported_url(url: str) -> bool:
    return any(domain in url for domain in SUPPORTED_DOMAINS)


# ── Formatting ─────────────────────────────────────────────────────────────────

def format_size(size_bytes: int) -> str:
    if size_bytes is None:
        return "غير محدد"
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def format_duration(seconds: int) -> str:
    if not seconds:
        return "غير محدد"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_views(n: Optional[int]) -> str:
    if not n:
        return "غير محدد"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def make_job_id() -> str:
    return str(uuid.uuid4())[:8]


# ── Telegram File Sender ───────────────────────────────────────────────────────

TELEGRAM_MAX_BYTES = 2_000 * 1024 * 1024  # 2 GB (Bot API local server)
TELEGRAM_DEFAULT_MAX = 50 * 1024 * 1024   # 50 MB (standard Bot API)


async def send_file_smart(
    bot: Bot,
    chat_id: int,
    file_path: Path,
    caption: str = "",
    reply_to: Optional[int] = None,
) -> bool:
    """
    Send a file as video or document based on size and extension.
    Returns True on success.
    """
    size = file_path.stat().st_size
    ext = file_path.suffix.lower()
    fsi = FSInputFile(str(file_path))

    kwargs = dict(chat_id=chat_id, caption=caption[:1024], reply_to_message_id=reply_to)

    try:
        if ext in (".mp4", ".mkv", ".webm", ".mov") and size <= TELEGRAM_DEFAULT_MAX:
            await bot.send_video(video=fsi, **kwargs)
        elif ext in (".mp3", ".flac", ".aac", ".wav", ".ogg") and size <= TELEGRAM_DEFAULT_MAX:
            await bot.send_audio(audio=fsi, **kwargs)
        elif ext in (".gif",) and size <= TELEGRAM_DEFAULT_MAX:
            await bot.send_animation(animation=fsi, **kwargs)
        else:
            await bot.send_document(document=fsi, **kwargs)
        return True
    except Exception:
        # File too large: send a notice
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ الملف كبير جداً للإرسال عبر تيليغرام ({format_size(size)}).\n"
                "استخدم زر الرفع السحابي لرفعه إلى Google Drive أو Dropbox."
            ),
            reply_to_message_id=reply_to,
        )
        return False


def cleanup(*paths: Path):
    for p in paths:
        if p and p.exists():
            try:
                p.unlink()
            except Exception:
                pass
