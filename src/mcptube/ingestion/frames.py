"""Frame extraction from YouTube videos via yt-dlp + ffmpeg."""

import logging
import subprocess
import time
from pathlib import Path

import yt_dlp

from mcptube.config import settings
from mcptube.ingestion.ffmpeg_errors import ffmpeg_error_tail
from mcptube.ingestion.platforms import UnsupportedPlatformError, resolve_platform
from mcptube.ingestion.ytdlp_session import (
    extract_info_with_retry,
    network_opts,
    video_stream_opts,
)
from mcptube.ingestion.youtube import SAFE_VIDEO_ID_RE

logger = logging.getLogger(__name__)


class FrameExtractionError(Exception):
    """Raised when frame extraction fails."""


class StreamForbiddenError(FrameExtractionError):
    """Raised when the stream URL answers ffmpeg with HTTP 403."""


class FrameExtractor:
    """Extracts individual frames from YouTube videos.

    Uses yt-dlp to resolve direct stream URLs (ffmpeg cannot read
    YouTube page URLs directly), then ffmpeg to seek and extract
    a single frame. Frames are cached on disk to avoid re-extraction.
    """

    _MAX_RES = 360
    _ATTEMPTS = 3
    _RETRY_DELAY_S = 2.0

    def extract_frame(self, video_id: str, timestamp: float, source_url: str) -> Path:
        """Extract a single frame at the given timestamp.

        Args:
            video_id: Namespaced video ID (used only for the cache path).
            timestamp: Time in seconds to extract frame at.
            source_url: URL of the originating platform (YouTube, Instagram, etc.).

        Returns:
            Path to the extracted JPEG frame.

        Raises:
            FrameExtractionError: If extraction fails.
        """
        # Check cache first
        cache_path = self._cache_path(video_id, timestamp)
        if cache_path.exists():
            logger.info("Frame cache hit: %s", cache_path)
            return cache_path

        # YouTube intermittently issues stream URLs that only serve the first
        # minute of the file and answer 403 past it. The restriction belongs to
        # the issued URL, so resolving again yields a usable one.
        for attempt in range(1, self._ATTEMPTS + 1):
            stream_url = self._resolve_stream_url(source_url)
            try:
                self._extract_with_ffmpeg(stream_url, timestamp, cache_path)
                break
            except StreamForbiddenError:
                if attempt == self._ATTEMPTS:
                    raise
                logger.warning(
                    "Stream URL rejected with 403 (attempt %d/%d), resolving again",
                    attempt, self._ATTEMPTS,
                )
                time.sleep(self._RETRY_DELAY_S * attempt)

        return cache_path

    def _resolve_stream_url(self, source_url: str) -> str:
        """Resolve a direct stream URL from the platform's source URL."""
        try:
            resolve_platform(source_url)
        except UnsupportedPlatformError as e:
            raise FrameExtractionError(str(e)) from e

        ydl_opts = network_opts({
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            **video_stream_opts(self._MAX_RES),
        })
        try:
            info = extract_info_with_retry(source_url, ydl_opts)
        except yt_dlp.utils.DownloadError as e:
            raise FrameExtractionError(f"Failed to resolve stream URL: {e}") from e
        if info is None:
            raise FrameExtractionError(f"yt-dlp returned no info for: {source_url}")
        stream_url = info.get("url")
        if not stream_url:
            raise FrameExtractionError(f"No stream URL resolved for: {source_url}")
        return stream_url

    def _extract_with_ffmpeg(self, stream_url: str, timestamp: float, output: Path) -> None:
        """Use ffmpeg to seek and extract a single JPEG frame."""
        output.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ffmpeg",
            "-ss", str(timestamp),
            "-i", stream_url,
            "-frames:v", "1",
            "-q:v", "2",
            "-y",
            str(output),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0 or not output.exists():
                error = StreamForbiddenError if "403 Forbidden" in result.stderr else FrameExtractionError
                raise error(
                    f"ffmpeg failed (code {result.returncode}): {ffmpeg_error_tail(result.stderr)}"
                )
            logger.info("Frame extracted: %s", output)
        except subprocess.TimeoutExpired:
            raise FrameExtractionError(f"ffmpeg timed out extracting frame at {timestamp}s")
        except FileNotFoundError:
            raise FrameExtractionError(
                "ffmpeg not found. Install it: https://ffmpeg.org/download.html"
            )

    @staticmethod
    def _cache_path(video_id: str, timestamp: float) -> Path:
        """Generate a deterministic cache path for a frame."""
        if not SAFE_VIDEO_ID_RE.fullmatch(video_id):
            raise FrameExtractionError(f"Invalid video id: {video_id!r}")
        settings.frames_dir.mkdir(parents=True, exist_ok=True)
        return settings.frames_dir / f"{video_id}_{timestamp:.2f}.jpg"
