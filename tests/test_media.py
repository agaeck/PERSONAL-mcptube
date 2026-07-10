from unittest.mock import MagicMock, patch

import pytest

from mcptube.config import settings
from mcptube.ingestion import media
from mcptube.ingestion.media import MediaExtractor
from mcptube.ingestion.platforms import UnsupportedPlatformError


def _mock_ydl(mock_cls, info):
    ydl = MagicMock()
    ydl.extract_info.return_value = info
    mock_cls.return_value.__enter__ = lambda s: ydl
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)


@patch("mcptube.ingestion.ytdlp_session.yt_dlp.YoutubeDL")
def test_extract_tiktok_namespaced_no_transcript(mock_cls):
    _mock_ydl(mock_cls, {"id": "7263", "extractor": "TikTok",
                          "title": "t", "webpage_url": "https://www.tiktok.com/@u/video/7263"})
    v = MediaExtractor().extract("https://www.tiktok.com/@u/video/7263")
    assert v.platform == "tiktok"
    assert v.video_id == "tiktok_7263"
    assert v.source_url == "https://www.tiktok.com/@u/video/7263"
    assert v.transcript == []


@patch("mcptube.ingestion.ytdlp_session.yt_dlp.YoutubeDL")
def test_extract_rejects_generic_extractor(mock_cls):
    _mock_ydl(mock_cls, {"id": "x", "extractor": "generic", "webpage_url": "https://www.facebook.com/x"})
    with pytest.raises(Exception):
        MediaExtractor().extract("https://www.facebook.com/watch/?v=1")


def test_extract_rejects_unsupported_host():
    with pytest.raises(UnsupportedPlatformError):
        MediaExtractor().extract("https://example.com/x")


def test_build_ydl_opts_injects_pot_provider(monkeypatch):
    monkeypatch.setattr(settings, "pot_base_url", "http://mcptube-pot:4416")
    opts = media._build_ydl_opts()
    assert opts["extractor_args"] == {
        "youtubepot-bgutilhttp": {"base_url": ["http://mcptube-pot:4416"]}
    }


def test_build_ydl_opts_without_pot_provider(monkeypatch):
    monkeypatch.setattr(settings, "pot_base_url", None)
    opts = media._build_ydl_opts()
    assert "extractor_args" not in opts
