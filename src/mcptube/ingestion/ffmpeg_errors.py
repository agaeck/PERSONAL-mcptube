"""Readable error text from ffmpeg's stderr."""

import re

_URL_RE = re.compile(r"https?://\S+")
_MAX_CHARS = 300


def ffmpeg_error_tail(stderr: str) -> str:
    """Return the end of ffmpeg's stderr, which is where it reports the failure.

    The start is always the version/build banner. URLs are masked because a
    signed stream URL alone is longer than the limit and would push the error out.
    """
    return _URL_RE.sub("<url>", stderr).strip()[-_MAX_CHARS:]
