"""Tests for turning ffmpeg's stderr into a readable error message."""

from mcptube.ingestion.ffmpeg_errors import ffmpeg_error_tail

BANNER = (
    "ffmpeg version 7.1.5-0+deb13u1 Copyright (c) 2000-2026 the FFmpeg developers\n"
    "  built with gcc 14 (Debian 14.2.0-19)\n"
    "  configuration: " + "--enable-something " * 60 + "\n"
)
STREAM_URL = "https://rr3---sn-abc.googlevideo.com/videoplayback?expire=1&sig=" + "A" * 900
# Shape of the real failure captured in production on 2026-10-03.
FORBIDDEN = BANNER + (
    "[https @ 0x1] HTTP error 403 Forbidden\n"
    "[in#0 @ 0x2] Error opening input: Server returned 403 Forbidden (access denied)\n"
    f"Error opening input file {STREAM_URL}.\n"
    "Error opening input files: Server returned 403 Forbidden (access denied)\n"
)


def test_returns_the_error_not_the_banner():
    tail = ffmpeg_error_tail(FORBIDDEN)
    assert "Server returned 403 Forbidden" in tail
    assert "ffmpeg version" not in tail


def test_masks_urls_so_they_cannot_crowd_out_the_error():
    tail = ffmpeg_error_tail(FORBIDDEN)
    assert "googlevideo.com" not in tail
    assert "HTTP error 403 Forbidden" in tail  # first error line only fits once the URL is masked


def test_long_stderr_is_cut_to_a_readable_length():
    assert len(ffmpeg_error_tail("x" * 1000)) == 300


def test_short_stderr_is_returned_whole():
    assert ffmpeg_error_tail("Some error\n") == "Some error"


def test_empty_stderr():
    assert ffmpeg_error_tail("") == ""
