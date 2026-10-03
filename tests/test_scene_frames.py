"""Tests for scene-change frame extraction via ffmpeg."""

import json
import subprocess
import pytest
import yt_dlp
from unittest.mock import MagicMock, patch
from pathlib import Path

from mcptube.ingestion.scene_frames import SceneFrameError, SceneFrameExtractor


@pytest.fixture
def extractor():
    return SceneFrameExtractor(threshold=0.4)


@pytest.fixture
def output_dir(tmp_path):
    d = tmp_path / "frames" / "abc123_scenes"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def fake_download(monkeypatch):
    """Stand in for yt-dlp: 'download' a file where the caller asked for it."""
    calls = []

    def fake(url, opts, download=False):
        calls.append({"url": url, "opts": opts, "download": download})
        path = Path(opts["paths"]["home"]) / "video.mp4"
        path.write_bytes(b"fake-video")
        return {"requested_downloads": [{"filepath": str(path)}]}

    monkeypatch.setattr("mcptube.ingestion.scene_frames.extract_info_with_retry", fake)
    return calls


def test_output_dir_rejects_traversal_id():
    # video_id reaches this path sink directly via the get_frame_by_query tool.
    with pytest.raises(SceneFrameError):
        SceneFrameExtractor._output_dir("../../../etc/passwd")


@pytest.fixture
def cached_frames(output_dir):
    """Create fake cached scene frames with metadata."""
    frames = []
    for i in range(3):
        path = output_dir / f"scene_{i+1:04d}.jpg"
        path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # fake JPEG header
        frames.append({
            "filename": path.name,
            "timestamp": float(i * 10),
            "index": i,
        })
    meta_path = output_dir / "metadata.json"
    meta_path.write_text(json.dumps(frames, indent=2))
    return frames


class TestInit:
    def test_default_threshold(self):
        ext = SceneFrameExtractor()
        assert ext._threshold == 0.4

    def test_custom_threshold(self):
        ext = SceneFrameExtractor(threshold=0.6)
        assert ext._threshold == 0.6


class TestParseShowinfoTimestamps:
    def test_parse_single_timestamp(self):
        stderr = "[Parsed_showinfo_2 @ 0x1234] n:   0 pts:  12345 pts_time:1.234 pos:5678\n"
        ts = SceneFrameExtractor._parse_showinfo_timestamps(stderr)
        assert len(ts) == 1
        assert abs(ts[0] - 1.234) < 0.001

    def test_parse_multiple_timestamps(self):
        stderr = (
            "[Parsed_showinfo_2 @ 0x1] n:0 pts:0 pts_time:0.000 pos:0\n"
            "[Parsed_showinfo_2 @ 0x1] n:1 pts:1000 pts_time:10.500 pos:100\n"
            "[Parsed_showinfo_2 @ 0x1] n:2 pts:2000 pts_time:25.750 pos:200\n"
        )
        ts = SceneFrameExtractor._parse_showinfo_timestamps(stderr)
        assert len(ts) == 3
        assert abs(ts[0] - 0.0) < 0.001
        assert abs(ts[1] - 10.5) < 0.001
        assert abs(ts[2] - 25.75) < 0.001

    def test_parse_no_showinfo_lines(self):
        stderr = "frame=100 fps=25 time=00:00:04.00 bitrate=1000kbps\n"
        ts = SceneFrameExtractor._parse_showinfo_timestamps(stderr)
        assert ts == []

    def test_parse_empty_stderr(self):
        ts = SceneFrameExtractor._parse_showinfo_timestamps("")
        assert ts == []

    def test_parse_mixed_output(self):
        stderr = (
            "Input #0, mov,mp4 from 'stream.mp4'\n"
            "[Parsed_showinfo_2 @ 0x1] n:0 pts:0 pts_time:5.000 pos:0\n"
            "frame=50 fps=25\n"
            "[Parsed_showinfo_2 @ 0x1] n:1 pts:1000 pts_time:15.000 pos:100\n"
            "Output #0, image2\n"
        )
        ts = SceneFrameExtractor._parse_showinfo_timestamps(stderr)
        assert len(ts) == 2
        assert abs(ts[0] - 5.0) < 0.001
        assert abs(ts[1] - 15.0) < 0.001


class TestCaching:
    def test_load_cached_frames(self, extractor, output_dir, cached_frames):
        loaded = extractor._load_cached(output_dir)
        assert loaded is not None
        assert len(loaded) == 3
        assert loaded[0]["timestamp"] == 0.0
        assert loaded[1]["timestamp"] == 10.0
        assert loaded[2]["timestamp"] == 20.0

    def test_load_cached_returns_none_when_no_metadata(self, extractor, output_dir):
        loaded = extractor._load_cached(output_dir)
        assert loaded is None

    def test_load_cached_returns_none_when_files_missing(self, extractor, output_dir):
        meta = [{"filename": "missing.jpg", "timestamp": 0.0, "index": 0}]
        (output_dir / "metadata.json").write_text(json.dumps(meta))
        loaded = extractor._load_cached(output_dir)
        assert loaded is None

    def test_save_metadata(self, extractor, output_dir):
        frames = [
            {"path": output_dir / "scene_0001.jpg", "timestamp": 5.0, "index": 0},
            {"path": output_dir / "scene_0002.jpg", "timestamp": 15.0, "index": 1},
        ]
        extractor._save_metadata(output_dir, frames)
        meta_path = output_dir / "metadata.json"
        assert meta_path.exists()
        data = json.loads(meta_path.read_text())
        assert len(data) == 2
        assert data[0]["filename"] == "scene_0001.jpg"
        assert data[1]["timestamp"] == 15.0


class TestOutputDir:
    @patch("mcptube.ingestion.scene_frames.settings")
    def test_output_dir_path(self, mock_settings, tmp_path):
        mock_settings.frames_dir = tmp_path / "frames"
        path = SceneFrameExtractor._output_dir("abc123")
        assert path == tmp_path / "frames" / "abc123_scenes"


class TestDownloadVideo:
    URL = "https://www.youtube.com/watch?v=abc123"

    def test_returns_the_downloaded_file(self, extractor, tmp_path, fake_download):
        path = extractor._download_video(self.URL, tmp_path)
        assert path.read_bytes() == b"fake-video"
        assert path.parent == tmp_path

    def test_downloads_the_source_url(self, extractor, tmp_path, fake_download):
        extractor._download_video("https://www.tiktok.com/@u/video/7263", tmp_path)
        assert fake_download[0]["url"] == "https://www.tiktok.com/@u/video/7263"
        assert fake_download[0]["download"] is True

    def test_requests_a_360p_stream(self, extractor, tmp_path, fake_download, select_format, youtube_formats):
        extractor._download_video(self.URL, tmp_path)
        opts = fake_download[0]["opts"]
        picked = select_format(
            youtube_formats, {"format": opts["format"], "format_sort": opts["format_sort"]}
        )
        # Decoding a whole video at 720p does not fit in the ffmpeg timeout.
        assert picked["format_id"] == "134"

    def test_refuses_live_streams(self, extractor, tmp_path, fake_download, select_format, youtube_formats):
        # A live stream keeps downloading until it ends; nothing else bounds the call.
        extractor._download_video(self.URL, tmp_path)
        opts = {k: fake_download[0]["opts"][k] for k in ("format", "format_sort", "match_filter")}
        assert "format_id" not in select_format(youtube_formats, opts, is_live=True)
        assert select_format(youtube_formats, opts, is_live=False)["format_id"] == "134"

    def test_downloads_only_the_video_from_a_playlist_url(self, extractor, tmp_path, fake_download):
        extractor._download_video(self.URL + "&list=PL123", tmp_path)
        assert fake_download[0]["opts"]["noplaylist"] is True

    def test_dest_dir_is_not_expanded_as_an_output_template(self, extractor, tmp_path, fake_download):
        dest = tmp_path / "50%(id)s"
        dest.mkdir()
        extractor._download_video(self.URL, dest)
        opts = fake_download[0]["opts"]
        with yt_dlp.YoutubeDL({"quiet": True, "paths": opts["paths"], "outtmpl": opts["outtmpl"]}) as ydl:
            filename = ydl.prepare_filename({"id": "abc", "title": "t", "ext": "mp4"})
        assert Path(filename) == dest / "video.mp4"

    def test_no_info(self, extractor, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "mcptube.ingestion.scene_frames.extract_info_with_retry", lambda *a, **k: None
        )
        with pytest.raises(SceneFrameError, match="no info"):
            extractor._download_video(self.URL, tmp_path)

    @pytest.mark.parametrize(
        "downloads", [[], [{"filepath": "/nonexistent/video.mp4"}]], ids=["none", "file-missing"]
    )
    def test_nothing_downloaded(self, downloads, extractor, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "mcptube.ingestion.scene_frames.extract_info_with_retry",
            lambda *a, **k: {"requested_downloads": downloads},
        )
        with pytest.raises(SceneFrameError, match="No video file"):
            extractor._download_video(self.URL, tmp_path)

    def test_download_error_is_wrapped(self, extractor, tmp_path, monkeypatch):
        def failing(*args, **kwargs):
            raise yt_dlp.utils.DownloadError("HTTP Error 403: Forbidden")

        monkeypatch.setattr("mcptube.ingestion.scene_frames.extract_info_with_retry", failing)
        with pytest.raises(SceneFrameError, match="Failed to download video.*403"):
            extractor._download_video(self.URL, tmp_path)

    def test_rejects_unsupported_host(self, extractor, tmp_path):
        # Defense-in-depth: source_url is read back from storage, not the original
        # request, so it must be re-validated against the platform allowlist here too.
        with pytest.raises(SceneFrameError):
            extractor._download_video("https://evil.com/x", tmp_path)


class TestExtractWithFfmpeg:
    @patch("mcptube.ingestion.scene_frames.subprocess.run")
    def test_successful_extraction(self, mock_run, extractor, output_dir):
        # Create fake frame files as if ffmpeg wrote them
        for i in range(2):
            (output_dir / f"scene_{i+1:04d}.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 50)

        mock_run.return_value = MagicMock(
            returncode=0,
            stderr=(
                "[Parsed_showinfo_2 @ 0x1] n:0 pts:0 pts_time:5.000 pos:0\n"
                "[Parsed_showinfo_2 @ 0x1] n:1 pts:1000 pts_time:20.000 pos:100\n"
            ),
        )

        frames = extractor._extract_with_ffmpeg("https://stream.example.com/v.mp4", output_dir, 50)
        assert len(frames) == 2
        assert frames[0]["timestamp"] == 5.0
        assert frames[1]["timestamp"] == 20.0

    @patch("mcptube.ingestion.scene_frames.subprocess.run")
    def test_ffmpeg_failure_no_frames(self, mock_run, extractor, output_dir):
        mock_run.return_value = MagicMock(returncode=1, stderr="Error: invalid input")
        with pytest.raises(SceneFrameError, match="ffmpeg failed"):
            extractor._extract_with_ffmpeg("https://stream.example.com/v.mp4", output_dir, 50)

    @patch("mcptube.ingestion.scene_frames.subprocess.run")
    def test_ffmpeg_failure_reports_end_of_stderr(self, mock_run, extractor, output_dir):
        stderr = (
            "ffmpeg version 7.1.5 Copyright (c) the FFmpeg developers\n"
            + "  configuration: --enable-x\n" * 20
            + "Error opening input files: Invalid data found when processing input\n"
        )
        mock_run.return_value = MagicMock(returncode=1, stderr=stderr)
        with pytest.raises(SceneFrameError, match="Invalid data found"):
            extractor._extract_with_ffmpeg(output_dir / "video.mp4", output_dir, 50)

    @patch("mcptube.ingestion.scene_frames.subprocess.run")
    def test_ffmpeg_timeout(self, mock_run, extractor, output_dir):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=120)
        with pytest.raises(SceneFrameError, match="timed out"):
            extractor._extract_with_ffmpeg("https://stream.example.com/v.mp4", output_dir, 50)

    @patch("mcptube.ingestion.scene_frames.subprocess.run")
    def test_ffmpeg_not_found(self, mock_run, extractor, output_dir):
        mock_run.side_effect = FileNotFoundError()
        with pytest.raises(SceneFrameError, match="ffmpeg not found"):
            extractor._extract_with_ffmpeg("https://stream.example.com/v.mp4", output_dir, 50)

    @patch("mcptube.ingestion.scene_frames.subprocess.run")
    def test_ffmpeg_nonzero_but_frames_produced(self, mock_run, extractor, output_dir):
        """ffmpeg sometimes returns non-zero but still writes frames."""
        (output_dir / "scene_0001.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 50)
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="[Parsed_showinfo_2 @ 0x1] n:0 pts:0 pts_time:3.000 pos:0\n",
        )
        frames = extractor._extract_with_ffmpeg("https://stream.example.com/v.mp4", output_dir, 50)
        assert len(frames) == 1


class TestExtractSceneFrames:
    @patch.object(SceneFrameExtractor, "_output_dir")
    def test_returns_cached(self, mock_dir, extractor, output_dir, cached_frames):
        mock_dir.return_value = output_dir
        frames = extractor.extract_scene_frames(
            "abc123", "https://www.youtube.com/watch?v=abc123"
        )
        assert len(frames) == 3

    @patch.object(SceneFrameExtractor, "_output_dir")
    def test_max_frames_limits_cached(self, mock_dir, extractor, output_dir, cached_frames):
        mock_dir.return_value = output_dir
        frames = extractor.extract_scene_frames(
            "abc123", "https://www.youtube.com/watch?v=abc123", max_frames=2
        )
        assert len(frames) == 2

    @patch.object(SceneFrameExtractor, "_output_dir")
    def test_runs_ffmpeg_on_a_downloaded_local_file(
        self, mock_dir, extractor, output_dir, fake_download, monkeypatch
    ):
        mock_dir.return_value = output_dir
        seen = {}

        def fake_run(cmd, **kwargs):
            source = Path(cmd[cmd.index("-i") + 1])
            seen["existed_during_ffmpeg"] = source.is_file()
            (output_dir / "scene_0001.jpg").write_bytes(b"\xff\xd8fake")
            return MagicMock(
                returncode=0,
                stderr="[Parsed_showinfo_2 @ 0x1] n:0 pts:0 pts_time:3.000 pos:0\n",
            )

        monkeypatch.setattr("mcptube.ingestion.scene_frames.subprocess.run", fake_run)
        frames = extractor.extract_scene_frames("abc123", "https://www.youtube.com/watch?v=abc123")

        assert seen["existed_during_ffmpeg"]
        assert [f["timestamp"] for f in frames] == [3.0]

    @patch.object(SceneFrameExtractor, "_output_dir")
    def test_temp_video_removed_after_success(
        self, mock_dir, extractor, output_dir, fake_download, monkeypatch
    ):
        mock_dir.return_value = output_dir
        seen = {}

        def fake_run(cmd, **kwargs):
            seen["source"] = Path(cmd[cmd.index("-i") + 1])
            (output_dir / "scene_0001.jpg").write_bytes(b"\xff\xd8fake")
            return MagicMock(returncode=0, stderr="")

        monkeypatch.setattr("mcptube.ingestion.scene_frames.subprocess.run", fake_run)
        extractor.extract_scene_frames("abc123", "https://www.youtube.com/watch?v=abc123")

        assert not seen["source"].exists()

    @patch.object(SceneFrameExtractor, "_output_dir")
    def test_temp_video_removed_when_ffmpeg_fails(
        self, mock_dir, extractor, output_dir, fake_download, monkeypatch
    ):
        mock_dir.return_value = output_dir
        seen = {}

        def fake_run(cmd, **kwargs):
            seen["source"] = Path(cmd[cmd.index("-i") + 1])
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=120)

        monkeypatch.setattr("mcptube.ingestion.scene_frames.subprocess.run", fake_run)
        with pytest.raises(SceneFrameError, match="timed out"):
            extractor.extract_scene_frames("abc123", "https://www.youtube.com/watch?v=abc123")

        assert not seen["source"].exists()
