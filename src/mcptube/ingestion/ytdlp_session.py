"""Helpers compartilhados de sessão yt-dlp: opts de rede + retry.

Centraliza o que era triplicado em media.py, frames.py e scene_frames.py:
(1) injeção condicional de cookies/PO-token provider nos ydl_opts;
(2) retry com backoff para falhas transitórias — atrás do WARP, o egresso
    pode sair por IPs diferentes do pool da Cloudflare, e alguns estão
    bot-checked pelo YouTube; a tentativa seguinte costuma passar.
"""

import logging
import time

import yt_dlp

from mcptube.config import settings

logger = logging.getLogger(__name__)

_BACKOFF_S = 2.0


def network_opts(base_opts: dict) -> dict:
    """Retorna uma cópia de base_opts com cookies/PO-token conforme settings.

    Lê settings na chamada (não no import) para permanecer testável e
    sensível a mudanças de ambiente.
    """
    opts = dict(base_opts)
    if settings.cookies_file:
        opts["cookiefile"] = str(settings.cookies_file)
    if settings.pot_base_url:
        opts["extractor_args"] = {
            "youtubepot-bgutilhttp": {"base_url": [settings.pot_base_url]}
        }
    return opts


def video_stream_opts(max_res: int) -> dict:
    """Format selection for frame extraction: one stream that carries video.

    "bv*" accepts video-only formats. Frames need no audio, and YouTube stopped
    offering pre-muxed https formats on the clients yt-dlp can still use
    (yt-dlp >= 2026.08), so a "best"-style selector fails there with
    "Requested format is not available".
    """
    return {
        "format": "bv*",
        "format_sort": [
            f"res:{max_res}",  # caps the smallest dimension, so vertical videos count too
            "proto",  # plain https before HLS: a single seekable file
            "vcodec:h264",  # decoded natively by every ffmpeg build
        ],
    }


def extract_info_with_retry(
    url: str, opts: dict, attempts: int = 3, download: bool = False
) -> dict | None:
    """extract_info with retry/backoff for transient errors."""
    last_error: yt_dlp.utils.DownloadError | None = None
    for attempt in range(1, attempts + 1):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=download)
        except yt_dlp.utils.DownloadError as e:
            last_error = e
            if attempt < attempts:
                logger.warning(
                    "yt-dlp falhou (tentativa %d/%d) para %s: %s",
                    attempt, attempts, url, str(e)[:120],
                )
                time.sleep(_BACKOFF_S * attempt)
    assert last_error is not None
    raise last_error
