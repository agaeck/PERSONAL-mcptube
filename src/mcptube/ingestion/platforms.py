"""Allowlist de plataformas + resolver — o gate anti-SSRF da ingestão."""

from urllib.parse import urlparse

from mcptube.ingestion.youtube import ExtractionError


class UnsupportedPlatformError(ExtractionError):
    """URL cujo host não está na allowlist de plataformas suportadas."""


# sufixo de host -> nome da plataforma. Casa se o host é igual ao sufixo
# ou termina em ".<sufixo>" (subdomínio). É o gate anti-SSRF: só estes
# hosts chegam ao yt-dlp.
_ALLOWLIST = {
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "instagram.com": "instagram",
    "tiktok.com": "tiktok",
    "vm.tiktok.com": "tiktok",
    "facebook.com": "facebook",
    "fb.watch": "facebook",
}


def resolve_platform(url: str) -> str:
    """Retorna a plataforma para uma URL allowlistada, senão levanta.

    Raises:
        UnsupportedPlatformError: host fora da allowlist.
    """
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for suffix, platform in _ALLOWLIST.items():
        if host == suffix or host.endswith("." + suffix):
            return platform
    raise UnsupportedPlatformError(f"Unsupported platform for URL: {url}")


def namespaced_id(platform: str, native_id: str) -> str:
    """Id de vídeo único e path-safe: '{platform}_{native_id}'."""
    return f"{platform}_{native_id}"
