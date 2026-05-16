import asyncio
import os
import random
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import yt_dlp
from config.settings import settings

logger = logging.getLogger(__name__)


def _get_proxy() -> Optional[str]:
    if settings.PROXY_LIST:
        return random.choice(settings.PROXY_LIST)
    return None


def _base_opts(proxy: Optional[str] = None) -> Dict[str, Any]:
    opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "noplaylist": True,
        "cookiesfrombrowser": None,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    }
    if proxy:
        opts["proxy"] = proxy
    return opts


class DownloadService:

    @staticmethod
    async def get_info(url: str) -> Dict[str, Any]:
        """Extract metadata without downloading."""
        proxy = _get_proxy()
        opts = {**_base_opts(proxy), "skip_download": True}

        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(
                None, lambda: _extract_info(url, opts)
            )
            return info
        except Exception as e:
            # Retry without proxy on failure
            if proxy:
                logger.warning(f"Info extraction failed with proxy, retrying: {e}")
                opts.pop("proxy", None)
                info = await loop.run_in_executor(
                    None, lambda: _extract_info(url, opts)
                )
                return info
            raise

    @staticmethod
    async def download_video(
        url: str,
        quality: str = "best",
        format_id: Optional[str] = None,
        output_dir: Optional[str] = None,
        cookies_str: Optional[str] = None,
        audio_only: bool = False,
        trim_start: Optional[int] = None,
        trim_end: Optional[int] = None,
    ) -> Path:
        """Download a video and return the local file path."""
        out_dir = output_dir or settings.DOWNLOAD_DIR
        proxy = _get_proxy()
        opts = _base_opts(proxy)
        opts["outtmpl"] = os.path.join(out_dir, "%(id)s.%(ext)s")

        # Cookie support
        if cookies_str:
            cookie_file = os.path.join(out_dir, "cookies.txt")
            with open(cookie_file, "w") as f:
                f.write(cookies_str)
            opts["cookiefile"] = cookie_file

        # Format selection
        if audio_only:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        elif format_id:
            opts["format"] = format_id
        else:
            quality_map = {
                "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "4k": "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best",
                "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
                "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
                "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
                "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]",
                "audio": "bestaudio/best",
            }
            opts["format"] = quality_map.get(quality, quality_map["best"])
            opts["merge_output_format"] = "mp4"

        # Download in executor thread
        loop = asyncio.get_event_loop()
        result_path = await loop.run_in_executor(
            None, lambda: _do_download(url, opts)
        )
        return Path(result_path)

    @staticmethod
    async def download_playlist(
        url: str,
        quality: str = "720p",
        max_items: int = 50,
    ) -> List[Path]:
        """Download an entire playlist (up to max_items)."""
        out_dir = settings.DOWNLOAD_DIR
        proxy = _get_proxy()
        opts = _base_opts(proxy)
        opts.update({
            "outtmpl": os.path.join(out_dir, "%(playlist_index)s-%(id)s.%(ext)s"),
            "noplaylist": False,
            "playlistend": max_items,
            "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
            "merge_output_format": "mp4",
        })
        loop = asyncio.get_event_loop()
        paths = await loop.run_in_executor(
            None, lambda: _do_download_playlist(url, opts)
        )
        return [Path(p) for p in paths]

    @staticmethod
    async def get_thumbnail(url: str) -> Optional[Path]:
        """Download only the video thumbnail."""
        out_dir = settings.DOWNLOAD_DIR
        proxy = _get_proxy()
        opts = {
            **_base_opts(proxy),
            "skip_download": True,
            "writethumbnail": True,
            "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        }
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: _extract_info(url, opts))
        # Find the downloaded thumbnail
        for ext in ["jpg", "jpeg", "png", "webp"]:
            p = Path(out_dir) / f"{info['id']}.{ext}"
            if p.exists():
                return p
        return None

    @staticmethod
    def get_available_formats(info: Dict[str, Any]) -> List[Dict]:
        """Parse formats from info dict into a clean list."""
        formats = []
        for f in info.get("formats", []):
            if f.get("vcodec") == "none":
                continue  # skip audio-only formats in video list
            formats.append({
                "format_id": f["format_id"],
                "ext": f.get("ext", "?"),
                "height": f.get("height"),
                "fps": f.get("fps"),
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "vcodec": f.get("vcodec"),
                "acodec": f.get("acodec"),
                "tbr": f.get("tbr"),
            })
        return sorted(formats, key=lambda x: x.get("height") or 0, reverse=True)


# ─── Pure sync helpers (run in executor) ──────────────────────────────────────

def _extract_info(url: str, opts: Dict) -> Dict:
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _do_download(url: str, opts: Dict) -> str:
    downloaded_path = None

    class PathCollector(yt_dlp.YoutubeDL):
        def process_info(self, info):
            nonlocal downloaded_path
            super().process_info(info)
            downloaded_path = self.prepare_filename(info)

    with PathCollector(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if downloaded_path is None:
            downloaded_path = ydl.prepare_filename(info)

    # Handle merged output
    mp4_path = downloaded_path.rsplit(".", 1)[0] + ".mp4"
    if os.path.exists(mp4_path):
        return mp4_path
    if downloaded_path and os.path.exists(downloaded_path):
        return downloaded_path
    raise FileNotFoundError(f"Downloaded file not found for {url}")


def _do_download_playlist(url: str, opts: Dict) -> List[str]:
    paths = []

    original_process_info = yt_dlp.YoutubeDL.process_info

    def patched_process_info(self, info):
        original_process_info(self, info)
        path = self.prepare_filename(info)
        if os.path.exists(path):
            paths.append(path)

    yt_dlp.YoutubeDL.process_info = patched_process_info
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    finally:
        yt_dlp.YoutubeDL.process_info = original_process_info

    return paths
