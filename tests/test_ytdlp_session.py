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
