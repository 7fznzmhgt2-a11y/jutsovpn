"""SoundCloud search and download via yt-dlp."""

import asyncio
import json
import logging
import os
import tempfile

logger = logging.getLogger(__name__)


async def search_soundcloud(query: str, limit: int = 5) -> list[dict]:
    """Search SoundCloud for tracks. Returns list of {title, url, duration}."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp", "--flat-playlist", "--dump-json",
            f"scsearch{limit}:{query}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        results = []
        for line in stdout.decode().strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                results.append({
                    "title": data.get("title", "Unknown"),
                    "url": data.get("webpage_url") or data.get("url", ""),
                    "duration": data.get("duration", 0),
                    "uploader": data.get("uploader", ""),
                })
            except json.JSONDecodeError:
                continue
        return results
    except Exception:
        logger.exception("SoundCloud search failed")
        return []


async def download_soundcloud(url: str) -> str | None:
    """Download audio from SoundCloud URL. Returns file path or None."""
    tmp_dir = tempfile.mkdtemp(prefix="sc_")
    output_path = os.path.join(tmp_dir, "%(title)s.%(ext)s")

    try:
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--no-playlist",
            "-o", output_path,
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            logger.error("yt-dlp failed: %s", stderr.decode()[:500])
            return None

        # Find the downloaded file
        for f in os.listdir(tmp_dir):
            if f.endswith(".mp3") or f.endswith(".m4a") or f.endswith(".ogg"):
                return os.path.join(tmp_dir, f)

        # Check for any file
        files = os.listdir(tmp_dir)
        if files:
            return os.path.join(tmp_dir, files[0])

        return None
    except asyncio.TimeoutError:
        logger.error("yt-dlp download timed out")
        return None
    except Exception:
        logger.exception("SoundCloud download failed")
        return None
