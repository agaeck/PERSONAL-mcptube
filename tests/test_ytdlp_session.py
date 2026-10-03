# tests/test_ytdlp_session.py
"""Tests for the shared yt-dlp session helpers (network opts + retry)."""

from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from mcptube.config import settings
from mcptube.ingestion import ytdlp_session


class TestNetworkOpts:
    def test_injects_pot_base_url(self, monkeypatch):
        monkeypatch.setattr(settings, "pot_base_url", "http://127.0.0.1:4416")
        monkeypatch.setattr(settings, "cookies_file", None)
        opts = ytdlp_session.network_opts({"quiet": True})
        assert opts["extractor_args"] == {
            "youtubepot-bgutilhttp": {"base_url": ["http://127.0.0.1:4416"]}
        }
        assert opts["quiet"] is True

    def test_injects_cookiefile(self, monkeypatch, tmp_path):
        ck = tmp_path / "c.txt"
        monkeypatch.setattr(settings, "pot_base_url", None)
        monkeypatch.setattr(settings, "cookies_file", ck)
        opts = ytdlp_session.network_opts({})
        assert opts["cookiefile"] == str(ck)

    def test_no_settings_no_injection(self, monkeypatch):
        monkeypatch.setattr(settings, "pot_base_url", None)
        monkeypatch.setattr(settings, "cookies_file", None)
        opts = ytdlp_session.network_opts({"a": 1})
        assert opts == {"a": 1}

    def test_does_not_mutate_input(self, monkeypatch):
        monkeypatch.setattr(settings, "pot_base_url", "http://x:1")
        base = {"quiet": True}
        ytdlp_session.network_opts(base)
        assert "extractor_args" not in base


class TestVideoStreamOpts:
    """Feeds canned format lists to yt-dlp's real selector (no network)."""

    def test_youtube_without_muxed_formats_picks_https_h264_at_cap(self, select_format, youtube_formats):
        picked = select_format(youtube_formats, ytdlp_session.video_stream_opts(720))
        assert picked["format_id"] == "136"

    def test_lower_cap_picks_lower_resolution(self, select_format, youtube_formats):
        picked = select_format(youtube_formats, ytdlp_session.video_stream_opts(360))
        assert picked["format_id"] == "134"

    def test_cap_applies_to_smallest_dimension_of_vertical_video(self, select_format, instagram_formats):
        # 720x1280 must count as 720p; a height filter would wrongly exclude it.
        picked = select_format(instagram_formats, ytdlp_session.video_stream_opts(720))
        assert picked["format_id"] == "dash-720"

    def test_low_cap_prefers_file_of_unknown_size_over_ones_above_the_cap(self, select_format, instagram_formats):
        # Instagram's progressive files carry no dimensions; the old "best" selector
        # picked them too, and they are what the scene path downloads.
        picked = select_format(instagram_formats, ytdlp_session.video_stream_opts(360))
        assert not picked["format_id"].startswith("dash-")

    def test_falls_back_to_hls_when_no_https_format(self, select_format, youtube_formats):
        hls_only = [f for f in youtube_formats if f["protocol"] == "m3u8_native"]
        picked = select_format(hls_only, ytdlp_session.video_stream_opts(720))
        assert picked["format_id"] == "232"

    def test_muxed_only_platform_still_resolves(self, select_format):
        muxed = [{"format_id": "0", "url": "https://cdn.example/0", "ext": "mp4"}]
        picked = select_format(muxed, ytdlp_session.video_stream_opts(720))
        assert picked["url"] == "https://cdn.example/0"


class TestExtractInfoWithRetry:
    def _ydl_que_falha_n_vezes(self, mock_cls, n_falhas, info):
        ydl = MagicMock()
        efeitos = [yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot")] * n_falhas
        efeitos.append(info)
        ydl.extract_info.side_effect = efeitos
        mock_cls.return_value.__enter__ = lambda s: ydl
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        return ydl

    @patch("mcptube.ingestion.ytdlp_session.time.sleep")
    @patch("mcptube.ingestion.ytdlp_session.yt_dlp.YoutubeDL")
    def test_retries_transient_failure_then_succeeds(self, mock_cls, _sleep):
        ydl = self._ydl_que_falha_n_vezes(mock_cls, 2, {"id": "x"})
        info = ytdlp_session.extract_info_with_retry("https://u", {}, attempts=3)
        assert info == {"id": "x"}
        assert ydl.extract_info.call_count == 3

    @patch("mcptube.ingestion.ytdlp_session.time.sleep")
    @patch("mcptube.ingestion.ytdlp_session.yt_dlp.YoutubeDL")
    def test_raises_after_exhausting_attempts(self, mock_cls, _sleep):
        self._ydl_que_falha_n_vezes(mock_cls, 5, {"id": "x"})
        with pytest.raises(yt_dlp.utils.DownloadError):
            ytdlp_session.extract_info_with_retry("https://u", {}, attempts=3)

    @patch("mcptube.ingestion.ytdlp_session.yt_dlp.YoutubeDL")
    def test_success_first_try_no_retry(self, mock_cls):
        ydl = self._ydl_que_falha_n_vezes(mock_cls, 0, {"id": "ok"})
        info = ytdlp_session.extract_info_with_retry("https://u", {})
        assert info == {"id": "ok"}
        assert ydl.extract_info.call_count == 1

    @patch("mcptube.ingestion.ytdlp_session.yt_dlp.YoutubeDL")
    def test_does_not_download_by_default(self, mock_cls):
        ydl = self._ydl_que_falha_n_vezes(mock_cls, 0, {"id": "ok"})
        ytdlp_session.extract_info_with_retry("https://u", {})
        assert ydl.extract_info.call_args.kwargs["download"] is False

    @patch("mcptube.ingestion.ytdlp_session.yt_dlp.YoutubeDL")
    def test_download_flag_is_forwarded(self, mock_cls):
        ydl = self._ydl_que_falha_n_vezes(mock_cls, 0, {"id": "ok"})
        ytdlp_session.extract_info_with_retry("https://u", {}, download=True)
        assert ydl.extract_info.call_args.kwargs["download"] is True
