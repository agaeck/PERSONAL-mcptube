"""Extração de mídia unificada multi-plataforma via yt-dlp."""

import logging

import yt_dlp

from mcptube.ingestion.platforms import namespaced_id, resolve_platform
from mcptube.ingestion.youtube import (
    ExtractionError,
    SAFE_VIDEO_ID_RE,
    extract_transcript_from_info,
)
from mcptube.models import Chapter, Video

logger = logging.getLogger(__name__)

_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "writesubtitles": True,
    "writeautomaticsub": True,
    "subtitleslangs": ["en", "en-orig", "en-US", "en-GB"],
    "subtitlesformat": "json3",
}


class MediaExtractor:
    """Extrai metadados + transcript (quando houver) de qualquer plataforma allowlistada."""

    def extract(self, url: str) -> Video:
        platform = resolve_platform(url)  # gate anti-SSRF (levanta se host não suportado)
        info = self._fetch_info(url)

        native_id = info.get("id")
        if not native_id:
            raise ExtractionError(f"yt-dlp returned no id for: {url}")
        video_id = namespaced_id(platform, str(native_id))
        if not SAFE_VIDEO_ID_RE.fullmatch(video_id):
            raise ExtractionError(f"Unsafe video id derived from: {url}")

        transcript = extract_transcript_from_info(info) if platform == "youtube" else []
        chapters = [
            Chapter(title=ch["title"], start=float(ch.get("start_time", 0)))
            for ch in (info.get("chapters") or [])
            if ch.get("title")
        ]
        return Video(
            video_id=video_id,
            platform=platform,
            source_url=info.get("webpage_url") or url,
            title=info.get("title", ""),
            description=info.get("description", ""),
            channel=info.get("channel", "") or info.get("uploader", ""),
            duration=float(info.get("duration", 0) or 0),
            thumbnail_url=info.get("thumbnail", ""),
            chapters=chapters,
            transcript=transcript,
        )

    def _fetch_info(self, url: str) -> dict:
        try:
            with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            raise ExtractionError(f"Failed to extract video info: {e}") from e
        if info is None:
            raise ExtractionError(f"yt-dlp returned no info for: {url}")
        # cinto-e-suspensório: nunca aceitar o extrator genérico (segue host arbitrário)
        if str(info.get("extractor", "")).lower().startswith("generic"):
            raise ExtractionError(f"Refusing generic extractor for: {url}")
        return info
