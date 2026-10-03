"""Shared fixtures for mcptube tests."""

import copy

import pytest
import yt_dlp
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from mcptube.models import Chapter, TranscriptSegment, Video
from mcptube.storage.sqlite import SQLiteVideoRepository
from mcptube.storage.vectorstore import ChromaVectorStore


SAMPLE_WIKI_EXTRACTION = """{
    "video_summary": "A guide to ML concepts including neural networks.",
    "key_timestamps": {"00:00": "Introduction", "00:10": "Neural Networks", "00:21": "Outro"},
    "entities": [{"name": "TechChannel", "category": "organization", "context": "The channel presenting the video.", "timestamps": ["00:00"]}],
    "topics": [{"name": "Neural Networks", "content": "Introduction to neural network layers and neurons.", "timestamps": ["00:10"], "tags": ["AI", "ML"]}],
    "concepts": [{"name": "Backpropagation", "content": "Training method for neural networks.", "timestamps": ["00:10"], "tags": ["ML"]}]
}"""

SAMPLE_CLASSIFY = '["AI", "Tutorial", "Machine Learning"]'


@pytest.fixture
def sample_segments():
    """List of TranscriptSegment objects for testing."""
    return [
        TranscriptSegment(start=0.0, duration=5.0, text="Hello and welcome to this video."),
        TranscriptSegment(start=5.0, duration=4.5, text="Today we'll talk about machine learning."),
        TranscriptSegment(start=9.5, duration=6.0, text="Let's start with neural networks."),
        TranscriptSegment(start=15.5, duration=5.5, text="A neural network has layers of neurons."),
        TranscriptSegment(start=21.0, duration=4.0, text="Thanks for watching, see you next time."),
    ]


@pytest.fixture
def sample_video(sample_segments):
    """Pre-built Video model with transcript and chapters."""
    return Video(
        video_id="dQw4w9WgXcQ",
        platform="youtube",
        source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="Intro to Machine Learning",
        description="A beginner's guide to ML concepts.",
        channel="TechChannel",
        duration=25.0,
        thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
        chapters=[
            Chapter(title="Introduction", start=0.0),
            Chapter(title="Neural Networks", start=9.5),
            Chapter(title="Outro", start=21.0),
        ],
        transcript=sample_segments,
        tags=["AI", "Machine Learning", "Tutorial"],
        added_at=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sqlite_repo(tmp_path):
    """SQLiteVideoRepository backed by in-memory database."""
    return SQLiteVideoRepository(":memory:")


@pytest.fixture
def chroma_store():
    """ChromaVectorStore backed by in-memory ChromaDB."""
    store = ChromaVectorStore(":memory:")
    yield store
    store._client.delete_collection(store._COLLECTION_NAME)


@pytest.fixture
def mock_extractor(sample_video):
    """MediaExtractor with mocked yt-dlp returning sample_video."""
    from mcptube.ingestion.media import MediaExtractor

    extractor = MediaExtractor()
    with patch.object(extractor, "extract", return_value=sample_video) as mock:
        extractor._mock = mock
        yield extractor


@pytest.fixture
def mock_llm():
    """LLMClient with mocked litellm.completion.

    Returns wiki extraction JSON on the first call,
    then classification JSON on subsequent calls.
    """
    from mcptube.llm import LLMClient

    #
    # responses = [SAMPLE_WIKI_EXTRACTION, SAMPLE_CLASSIFY]
    responses = [SAMPLE_CLASSIFY, SAMPLE_WIKI_EXTRACTION]

    call_count = {"i": 0}

    def pick_response(*args, **kwargs):
        idx = min(call_count["i"], len(responses) - 1)
        call_count["i"] += 1
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = responses[idx]
        return resp

    with patch("mcptube.llm.litellm.completion") as mock_completion:
        mock_completion.side_effect = pick_response

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-123"}):
            client = LLMClient()
            client._mock_completion = mock_completion
            yield client


@pytest.fixture
def mock_frames(tmp_path):
    """FrameExtractor with mocked subprocess and yt-dlp."""
    from mcptube.ingestion.frames import FrameExtractor

    extractor = FrameExtractor()
    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-data")

    with patch.object(extractor, "extract_frame", return_value=frame_path) as mock:
        extractor._mock = mock
        extractor._test_frame_path = frame_path
        yield extractor


@pytest.fixture
def service(sqlite_repo, mock_extractor, mock_frames, mock_llm, tmp_path):
    """Fully wired McpTubeService with all mocked dependencies."""
    from mcptube.service import McpTubeService
    from mcptube.wiki.engine import WikiEngine
    from mcptube.wiki.storage import FileWikiRepository

    wiki_repo = FileWikiRepository(wiki_dir=tmp_path / "wiki", db_path=":memory:")
    wiki_engine = WikiEngine(repo=wiki_repo, llm=mock_llm)

    return McpTubeService(
        repository=sqlite_repo,
        extractor=mock_extractor,
        frame_extractor=mock_frames,
        llm_client=mock_llm,
        wiki_engine=wiki_engine,
    )


def _fmt(format_id, width, height, vcodec, protocol="https", acodec="none", ext="mp4"):
    return {
        "format_id": format_id, "url": f"https://cdn.example/{format_id}", "ext": ext,
        "width": width, "height": height, "vcodec": vcodec, "acodec": acodec, "protocol": protocol,
    }


@pytest.fixture
def youtube_formats():
    """Format list shaped like yt-dlp >= 2026.08 returns for YouTube: nothing pre-muxed."""
    return [
        _fmt("140", None, None, "none", acodec="mp4a.40.2", ext="m4a"),
        _fmt("160", 256, 144, "avc1.4d400c"),
        _fmt("230", 640, 360, "avc1.4D401E", protocol="m3u8_native"),
        _fmt("134", 640, 360, "avc1.4d401e"),
        _fmt("396", 640, 360, "av01.0.01M.08"),
        _fmt("232", 1280, 720, "avc1.4D401F", protocol="m3u8_native"),
        _fmt("136", 1280, 720, "avc1.4d401f"),
        _fmt("247", 1280, 720, "vp9", ext="webm"),
        _fmt("398", 1280, 720, "av01.0.05M.08"),
        _fmt("137", 1920, 1080, "avc1.640028"),
        _fmt("401", 3840, 2160, "av01.0.12M.08"),
    ]


@pytest.fixture
def instagram_formats():
    """Format list shaped like Instagram's: progressive files of unknown codec + DASH video-only."""
    return [
        {"format_id": "1", "url": "https://cdn.example/1", "ext": "mp4"},
        {"format_id": "3", "url": "https://cdn.example/3", "ext": "mp4"},
        _fmt("dash-audio", None, None, "none", acodec="mp4a.40.5", ext="m4a"),
        _fmt("dash-720", 720, 1280, "vp09.00.31.08"),
        _fmt("dash-1080", 1080, 1920, "vp09.00.40.08"),
    ]


@pytest.fixture
def select_format():
    """Run yt-dlp's real format selector, offline, over a canned format list."""
    def select(formats, opts, **video_fields):
        info = {
            "id": "x", "title": "t", "extractor": "test", "extractor_key": "Test",
            "webpage_url": "https://example.com/x", "formats": copy.deepcopy(formats),
            **video_fields,
        }
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True, **opts}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.process_video_result(info, download=False)
    return select
