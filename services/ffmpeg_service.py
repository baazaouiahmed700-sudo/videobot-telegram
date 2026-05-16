import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, List

from config.settings import settings

logger = logging.getLogger(__name__)


class FFmpegService:

    @staticmethod
    async def extract_audio(video_path: Path, output_format: str = "mp3") -> Path:
        """Extract audio track from video."""
        out = video_path.with_suffix(f".{output_format}")
        codec = {"mp3": "libmp3lame", "flac": "flac", "aac": "aac", "wav": "pcm_s16le"}.get(
            output_format, "libmp3lame"
        )
        await _run(["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", codec,
                    "-q:a", "2", str(out)])
        return out

    @staticmethod
    async def separate_audio_stem(video_path: Path, stem: str = "vocals") -> Path:
        """
        Use Demucs to separate stems (vocals / accompaniment).
        stem: 'vocals' | 'drums' | 'bass' | 'other'
        Returns path to stem wav file.
        """
        out_dir = video_path.parent / "demucs_out"
        out_dir.mkdir(exist_ok=True)
        await _run([
            "python", "-m", "demucs", "--two-stems", stem,
            "-o", str(out_dir), str(video_path)
        ])
        # Demucs output path pattern
        stem_path = out_dir / "htdemucs" / video_path.stem / f"{stem}.wav"
        if stem_path.exists():
            return stem_path
        # Fallback: find any wav matching stem name
        for f in out_dir.rglob(f"{stem}.wav"):
            return f
        raise FileNotFoundError(f"Demucs stem '{stem}' not found for {video_path}")

    @staticmethod
    async def trim(video_path: Path, start: int, end: int) -> Path:
        """Trim video to [start, end] seconds."""
        out = video_path.with_stem(f"{video_path.stem}_trim")
        duration = end - start
        await _run([
            "ffmpeg", "-y",
            "-ss", str(start), "-i", str(video_path),
            "-t", str(duration),
            "-c", "copy",
            str(out)
        ])
        return out

    @staticmethod
    async def convert(video_path: Path, target_format: str, resolution: Optional[str] = None) -> Path:
        """Convert video to another format / resolution."""
        out = video_path.with_suffix(f".{target_format}")
        cmd = ["ffmpeg", "-y", "-i", str(video_path)]
        if resolution:
            # e.g. "1280x720"
            cmd += ["-vf", f"scale={resolution}"]
        cmd += ["-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", str(out)]
        await _run(cmd)
        return out

    @staticmethod
    async def to_vertical(video_path: Path, add_captions: bool = False) -> Path:
        """Reframe video to 9:16 vertical (for Shorts/TikTok)."""
        out = video_path.with_stem(f"{video_path.stem}_vertical")
        # Crop center to 9:16
        vf = (
            "crop=ih*9/16:ih,"
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
        )
        cmd = ["ffmpeg", "-y", "-i", str(video_path), "-vf", vf,
               "-c:v", "libx264", "-c:a", "aac", str(out)]
        await _run(cmd)
        return out

    @staticmethod
    async def extract_clip(video_path: Path, start: int, end: int, vertical: bool = True) -> Path:
        """Extract a clip and optionally convert to vertical."""
        trimmed = await FFmpegService.trim(video_path, start, end)
        if vertical:
            result = await FFmpegService.to_vertical(trimmed)
            trimmed.unlink(missing_ok=True)
            return result
        return trimmed

    @staticmethod
    async def make_gif(video_path: Path, start: int, duration: int = 5, fps: int = 10) -> Path:
        """Create an animated GIF from a video segment."""
        out = video_path.with_suffix(".gif")
        palette = video_path.with_stem("palette").with_suffix(".png")
        # Two-pass GIF generation for quality
        await _run([
            "ffmpeg", "-y",
            "-ss", str(start), "-t", str(duration),
            "-i", str(video_path),
            "-vf", f"fps={fps},scale=480:-1:flags=lanczos,palettegen",
            str(palette)
        ])
        await _run([
            "ffmpeg", "-y",
            "-ss", str(start), "-t", str(duration),
            "-i", str(video_path),
            "-i", str(palette),
            "-filter_complex", f"fps={fps},scale=480:-1:flags=lanczos[x];[x][1:v]paletteuse",
            str(out)
        ])
        palette.unlink(missing_ok=True)
        return out

    @staticmethod
    async def extract_thumbnail(video_path: Path, timestamp: int = 5) -> Path:
        """Extract a frame as thumbnail JPEG."""
        out = video_path.with_suffix(".jpg")
        await _run([
            "ffmpeg", "-y",
            "-ss", str(timestamp),
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            str(out)
        ])
        return out

    @staticmethod
    async def burn_subtitles(video_path: Path, srt_path: Path) -> Path:
        """Burn SRT subtitles directly into the video."""
        out = video_path.with_stem(f"{video_path.stem}_subbed")
        await _run([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"subtitles='{srt_path}':force_style='Fontname=Arial,FontSize=20,PrimaryColour=&HFFFFFF,OutlineColour=&H000000'",
            "-c:a", "copy",
            str(out)
        ])
        return out

    @staticmethod
    async def extract_clips_batch(video_path: Path, moments: List[dict]) -> List[Path]:
        """Extract multiple viral clips in parallel."""
        tasks = [
            FFmpegService.extract_clip(video_path, m["start"], m["end"], vertical=True)
            for m in moments
        ]
        return await asyncio.gather(*tasks)


async def _run(cmd: List[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"FFmpeg error: {stderr.decode()[-500:]}")
        raise RuntimeError(f"FFmpeg command failed: {' '.join(cmd[:4])}")
