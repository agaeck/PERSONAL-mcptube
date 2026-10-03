# tests/test_frames.py
"""Tests for frame extraction."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from mcptube.ingestion.frames import FrameExtractionError, FrameExtractor


class TestFrameExtractor:
    @patch("mcptube.ingestion.frames.subprocess.run")
    @patch.object(FrameExtractor, "_resolve_stream_url", return_value="https://stream.example.com/video.mp4")
    def test_extract_frame_calls_ffmpeg(self, mock_resolve, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)

        extractor = FrameExtractor()
        cache_path = extractor._cache_path("abc123", 10.0)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(b"\xff\xd8fake-jpeg")

        with patch.object(FrameExtractor, "_cache_path", return_value=tmp_path / "test.jpg"):
            # File doesn't exist at tmp_path, so ffmpeg should be called
            result_path = tmp_path / "test.jpg"
            mock_run.return_value = MagicMock(returncode=0)

            with patch.object(extractor, "_extract_with_ffmpeg") as mock_ffmpeg:
                mock_ffmpeg.side_effect = lambda url, ts, out: out.write_bytes(b"\xff\xd8fake")
                path = extractor.extract_frame(
                    "abc123", 10.0, "https://www.youtube.com/watch?v=abc123"
                )

            mock_resolve.assert_called_once_with("https://www.youtube.com/watch?v=abc123")

    @patch.object(FrameExtractor, "_cache_path")
    def test_extract_frame_cached(self, mock_cache_path, tmp_path):
        cached = tmp_path / "cached_frame.jpg"
        cached.write_bytes(b"\xff\xd8fake-jpeg")
        mock_cache_path.return_value = cached

        extractor = FrameExtractor()
        path = extractor.extract_frame(
            "abc123", 10.0, "https://www.youtube.com/watch?v=abc123"
        )
        assert path == cached

    def test_extract_with_ffmpeg_not_found(self, tmp_path):
        extractor = FrameExtractor()
        output = tmp_path / "out.jpg"

        with patch("mcptube.ingestion.frames.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(FrameExtractionError, match="ffmpeg not found"):
                extractor._extract_with_ffmpeg("https://stream.url", 10.0, output)

    def test_extract_with_ffmpeg_fails(self, tmp_path):
        extractor = FrameExtractor()
        output = tmp_path / "out.jpg"

        mock_result = MagicMock(returncode=1, stderr="Some error")
        with patch("mcptube.ingestion.frames.subprocess.run", return_value=mock_result):
            with pytest.raises(FrameExtractionError, match="ffmpeg failed"):
                extractor._extract_with_ffmpeg("https://stream.url", 10.0, output)

    def test_ffmpeg_failure_reports_end_of_stderr(self, tmp_path):
        stderr = (
            "ffmpeg version 7.1.5 Copyright (c) the FFmpeg developers\n"
            + "  configuration: --enable-x\n" * 20
            + "Error opening input files: Server returned 403 Forbidden (access denied)\n"
        )
        mock_result = MagicMock(returncode=8, stderr=stderr)
        with patch("mcptube.ingestion.frames.subprocess.run", return_value=mock_result):
            with pytest.raises(FrameExtractionError, match="403 Forbidden"):
                FrameExtractor()._extract_with_ffmpeg("https://stream.url", 10.0, tmp_path / "out.jpg")

    def _ffmpeg_that_rejects(self, forbidden_urls):
        """Fake subprocess.run: 403 for the given stream URLs, a written frame otherwise."""
        def fake_run(cmd, **kwargs):
            if cmd[cmd.index("-i") + 1] in forbidden_urls:
                return MagicMock(
                    returncode=8,
                    stderr="Error opening input files: Server returned 403 Forbidden (access denied)\n",
                )
            Path(cmd[-1]).write_bytes(b"\xff\xd8fake")
            return MagicMock(returncode=0, stderr="")
        return fake_run

    @patch("time.sleep")
    def test_resolves_again_when_stream_is_forbidden(self, _sleep, tmp_path):
        # YouTube intermittently issues URLs that only serve the start of the file.
        out = tmp_path / "frame.jpg"
        with patch.object(FrameExtractor, "_cache_path", return_value=out), \
             patch.object(FrameExtractor, "_resolve_stream_url", side_effect=["https://s/bad", "https://s/good"]) as resolve, \
             patch("mcptube.ingestion.frames.subprocess.run", side_effect=self._ffmpeg_that_rejects({"https://s/bad"})):
            path = FrameExtractor().extract_frame("abc123", 500.0, "https://www.youtube.com/watch?v=abc123")

        assert path == out and out.exists()
        assert resolve.call_count == 2

    @patch("time.sleep")
    def test_gives_up_when_every_resolved_stream_is_forbidden(self, _sleep, tmp_path):
        urls = [f"https://s/bad{i}" for i in range(10)]
        with patch.object(FrameExtractor, "_cache_path", return_value=tmp_path / "frame.jpg"), \
             patch.object(FrameExtractor, "_resolve_stream_url", side_effect=urls) as resolve, \
             patch("mcptube.ingestion.frames.subprocess.run", side_effect=self._ffmpeg_that_rejects(set(urls))):
            with pytest.raises(FrameExtractionError, match="403 Forbidden"):
                FrameExtractor().extract_frame("abc123", 500.0, "https://www.youtube.com/watch?v=abc123")

        assert resolve.call_count == 3

    def test_other_ffmpeg_failures_are_not_retried(self, tmp_path):
        # A new URL cannot fix e.g. a timestamp past the end of the video.
        failing = MagicMock(returncode=1, stderr="Output file is empty, nothing was encoded\n")
        with patch.object(FrameExtractor, "_cache_path", return_value=tmp_path / "frame.jpg"), \
             patch.object(FrameExtractor, "_resolve_stream_url", return_value="https://s/ok") as resolve, \
             patch("mcptube.ingestion.frames.subprocess.run", return_value=failing):
            with pytest.raises(FrameExtractionError, match="nothing was encoded"):
                FrameExtractor().extract_frame("abc123", 9999.0, "https://www.youtube.com/watch?v=abc123")

        assert resolve.call_count == 1

    def test_extract_with_ffmpeg_timeout(self, tmp_path):
        extractor = FrameExtractor()
        output = tmp_path / "out.jpg"

        with patch("mcptube.ingestion.frames.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=30)):
            with pytest.raises(FrameExtractionError, match="timed out"):
                extractor._extract_with_ffmpeg("https://stream.url", 10.0, output)

    def test_cache_path_deterministic(self):
        p1 = FrameExtractor._cache_path("abc123", 10.0)
        p2 = FrameExtractor._cache_path("abc123", 10.0)
        assert p1 == p2

    def test_cache_path_different_for_different_input(self):
        p1 = FrameExtractor._cache_path("abc123", 10.0)
        p2 = FrameExtractor._cache_path("abc123", 20.0)
        assert p1 != p2

    def test_cache_path_rejects_traversal_id(self):
        # video_id reaches this sink directly via the get_frame tool, so it must be
        # validated locally instead of trusting an upstream repo.exists() check.
        with pytest.raises(FrameExtractionError):
            FrameExtractor._cache_path("../../../etc/passwd", 0.0)

    @patch("mcptube.ingestion.ytdlp_session.yt_dlp.YoutubeDL")
    def test_resolve_stream_url(self, mock_ydl_class):
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {"url": "https://stream.example.com/video.mp4"}
        mock_ydl_class.return_value.__enter__ = lambda s: mock_ydl
        mock_ydl_class.return_value.__exit__ = MagicMock(return_value=False)

        extractor = FrameExtractor()
        url = extractor._resolve_stream_url("https://www.youtube.com/watch?v=abc123")
        assert url == "https://stream.example.com/video.mp4"

    @patch("mcptube.ingestion.ytdlp_session.yt_dlp.YoutubeDL")
    def test_resolve_stream_url_uses_source_url(self, mock_ydl_class):
        ydl = MagicMock()
        ydl.extract_info.return_value = {"url": "https://stream/v.mp4"}
        mock_ydl_class.return_value.__enter__ = lambda s: ydl
        mock_ydl_class.return_value.__exit__ = MagicMock(return_value=False)
        FrameExtractor()._resolve_stream_url("https://www.tiktok.com/@u/video/7263")
        assert ydl.extract_info.call_args.args[0] == "https://www.tiktok.com/@u/video/7263"

    def test_resolve_stream_url_without_any_muxed_format(self, monkeypatch, youtube_formats):
        # yt-dlp >= 2026.08 offers YouTube only as separate video and audio streams.
        def fake_extract_info(ydl, url, download=False):
            info = {
                "id": "abc123", "title": "t", "extractor": "test", "extractor_key": "Test",
                "webpage_url": url, "formats": youtube_formats,
            }
            return ydl.process_video_result(info, download=False)

        monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", fake_extract_info)
        url = FrameExtractor()._resolve_stream_url("https://www.youtube.com/watch?v=abc123")
        assert url == "https://cdn.example/134"  # 360p h264 over plain https

    def test_resolve_stream_url_rejects_unsupported_host(self):
        # Defense-in-depth: source_url is read back from storage, not the original
        # request, so it must be re-validated against the platform allowlist here too.
        with pytest.raises(FrameExtractionError):
            FrameExtractor()._resolve_stream_url("https://evil.com/x")
