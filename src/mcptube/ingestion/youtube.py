"""YouTube video ingestion via yt-dlp."""

import json
import logging
import re
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import yt_dlp

from mcptube.models import Chapter, TranscriptSegment, Video

logger = logging.getLogger(__name__)

# Canonical YouTube video id: exactly 11 base64url chars. Single source of truth,
# reused by the URL patterns and the ?v= fallback so the two can't drift apart.
VIDEO_ID_PATTERN = r"[A-Za-z0-9_-]{11}"
VIDEO_ID_RE = re.compile(VIDEO_ID_PATTERN)

# A video id can arrive straight from a tool call (get_frame, get_frame_by_query),
# where it becomes a filesystem path and a stream URL. Validate it as a safe token
# (no path separators, no traversal) at those sinks. Deliberately platform-agnostic
# — not the strict 11-char YouTube form — so non-YouTube ids stay supportable.
SAFE_VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


class ExtractionError(Exception):
    """Raised when video extraction fails."""


class YouTubeExtractor:
    """Extracts metadata and transcripts from YouTube videos via yt-dlp.

    Single responsibility: given a YouTube URL, return a populated Video model.
    All yt-dlp interaction is encapsulated here.
    """

    _URL_PATTERNS = [
        re.compile(rf"(?:youtube\.com/watch\?.*v=)({VIDEO_ID_PATTERN})"),
        re.compile(rf"(?:youtu\.be/)({VIDEO_ID_PATTERN})"),
        re.compile(rf"(?:youtube\.com/embed/)({VIDEO_ID_PATTERN})"),
        re.compile(rf"(?:youtube\.com/v/)({VIDEO_ID_PATTERN})"),
    ]

    _LANG_PREFERENCE = ("en", "en-orig", "en-US", "en-GB")

    def extract(self, url: str) -> Video:
        """Extract metadata and transcript from a YouTube video URL.

        Args:
            url: YouTube video URL in any standard format.

        Returns:
            Populated Video model.

        Raises:
            ExtractionError: If extraction fails.
        """
        video_id = self.parse_video_id(url)
        # SSRF guard: never hand the caller's raw URL to yt-dlp — its GenericIE would
        # follow an attacker-controlled/internal host (e.g. 169.254.169.254). Rebuild
        # the canonical URL from the validated id so only youtube.com is ever fetched.
        canonical_url = f"https://www.youtube.com/watch?v={video_id}"
        info = self._fetch_info(canonical_url)
        transcript = self._extract_transcript(info)
        chapters = self._extract_chapters(info)

        return Video(
            video_id=video_id,
            title=info.get("title", ""),
            description=info.get("description", ""),
            channel=info.get("channel", "") or info.get("uploader", ""),
            duration=float(info.get("duration", 0) or 0),
            thumbnail_url=info.get("thumbnail", ""),
            chapters=chapters,
            transcript=transcript,
        )

    @classmethod
    def parse_video_id(cls, url: str) -> str:
        """Extract the 11-character video ID from a YouTube URL.

        Supports youtube.com/watch, youtu.be, /embed/, and /v/ formats.

        Raises:
            ExtractionError: If the URL cannot be parsed.
        """
        for pattern in cls._URL_PATTERNS:
            match = pattern.search(url)
            if match:
                return match.group(1)

        # Fallback: query parameter parsing. Validate the id charset (not just the
        # length) so a traversal payload like ?v=../../../ab can't pass as an id.
        parsed = urlparse(url)
        video_id = parse_qs(parsed.query).get("v", [None])[0]
        if video_id and VIDEO_ID_RE.fullmatch(video_id):
            return video_id

        raise ExtractionError(f"Could not extract video ID from URL: {url}")

    def _fetch_info(self, url: str) -> dict:
        """Fetch video info dict from yt-dlp without downloading media."""
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": list(self._LANG_PREFERENCE),
            "subtitlesformat": "json3",
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    raise ExtractionError(f"yt-dlp returned no info for: {url}")
                return info
        except yt_dlp.utils.DownloadError as e:
            raise ExtractionError(f"Failed to extract video info: {e}") from e

    def _extract_transcript(self, info: dict) -> list[TranscriptSegment]:
        """Extract transcript segments, preferring manual over auto-generated."""
        subtitles = info.get("subtitles") or {}
        auto_captions = info.get("automatic_captions") or {}

        sub_data = self._find_json3(subtitles) or self._find_json3(auto_captions)
        if not sub_data:
            logger.warning("No English transcript available for: %s", info.get("id"))
            return []

        return self._parse_json3(sub_data)

    def _find_json3(self, subs: dict) -> dict | None:
        """Find and download json3 subtitle data for the best English variant."""
        # Try preferred language codes first
        for lang in self._LANG_PREFERENCE:
            data = self._get_json3_for_lang(subs, lang)
            if data:
                return data

        # Fallback: any en-* variant
        for lang in subs:
            if lang.startswith("en"):
                data = self._get_json3_for_lang(subs, lang)
                if data:
                    return data

        return None

    def _get_json3_for_lang(self, subs: dict, lang: str) -> dict | None:
        """Download json3 data for a specific language code if available."""
        formats = subs.get(lang)
        if not formats:
            return None
        for fmt in formats:
            if fmt.get("ext") == "json3":
                return self._download_json(fmt["url"])
        return None

    def _download_json(self, url: str) -> dict | None:
        """Download and parse JSON from a URL."""
        try:
            with urlopen(url, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning("Failed to download subtitle data: %s", e)
            return None

    def _parse_json3(self, data: dict) -> list[TranscriptSegment]:
        """Parse YouTube json3 subtitle format into TranscriptSegment list.

        YouTube json3 structure:
            {"events": [{"tStartMs": int, "dDurationMs": int, "segs": [{"utf8": str}]}]}
        """
        segments = []
        for event in data.get("events", []):
            segs = event.get("segs")
            if not segs:
                continue

            text = "".join(s.get("utf8", "") for s in segs).strip()
            if not text or text == "\n":
                continue

            start_ms = event.get("tStartMs", 0)
            duration_ms = event.get("dDurationMs", 0)

            segments.append(TranscriptSegment(
                start=start_ms / 1000.0,
                duration=duration_ms / 1000.0,
                text=text,
            ))

        return segments

    def _extract_chapters(self, info: dict) -> list[Chapter]:
        """Extract chapter markers when provided by the uploader."""
        return [
            Chapter(title=ch["title"], start=float(ch.get("start_time", 0)))
            for ch in (info.get("chapters") or [])
            if ch.get("title")
        ]


def extract_transcript_from_info(info: dict) -> list[TranscriptSegment]:
    """Extrai o transcript (json3) de um info-dict do yt-dlp, se houver.

    Esta função de módulo reutiliza a lógica de parsing json3 já existente
    na classe YouTubeExtractor, permitindo que o transcript seja extraído
    sem instanciar a classe.

    Args:
        info: Dicionário de informações retornado pelo yt-dlp.

    Returns:
        Lista de segmentos de transcript, ou lista vazia se nenhum for encontrado.
    """
    return YouTubeExtractor()._extract_transcript(info)
