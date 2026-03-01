"""FastMCP server — thin wrapper exposing McpTubeService as MCP tools."""

# import base64

from fastmcp import FastMCP
from fastmcp.utilities.types import Image


from mcptube.config import settings
from mcptube.ingestion.frames import FrameExtractionError
from mcptube.ingestion.youtube import YouTubeExtractor
from mcptube.models import Video
from mcptube.service import McpTubeService, VideoAlreadyExistsError, VideoNotFoundError
from mcptube.storage.sqlite import SQLiteVideoRepository
from mcptube.storage.vectorstore import ChromaVectorStore


mcp = FastMCP(
    name="mcptube",
    instructions = """
        mcptube is a YouTube video library and analysis platform. It extracts metadata, 
        transcripts, and frames from YouTube videos and makes them searchable and queryable.

        ## Tool Categories

        ### Library Management
        - `add_video(url)` — Ingest a YouTube video. Always use this first before any other operation on a video.
        - `remove_video(video_id)` — Remove a video from the library.
        - `list_videos()` — List all videos with metadata. Call this first to see what's available.
        - `get_info(video_id)` — Get full details including transcript and chapters for a specific video.

        ### Search
        - `search(query, video_id?, limit)` — Semantic search within a single video's transcript.
        - `search_library(query, tags?, limit)` — Semantic search across ALL videos in the library.

        ### Frame Extraction
        - `get_frame(video_id, timestamp)` — Extract a frame at an exact timestamp. Returns an inline image.
        - `get_frame_by_query(video_id, query)` — Find the best transcript match and extract that frame. Returns an inline image.
        - `get_frame_data(video_id, timestamp)` — Returns base64-encoded frame. Use ONLY when the user explicitly needs base64 or embed_html. Prefer get_frame for display.

        ### Analysis (Passthrough — you do the analysis)
        - `classify_video(video_id)` — Returns metadata for YOU to classify. Suggest tags and present them to the user.
        - `generate_report(video_id, query?)` — Returns transcript + metadata for YOU to write an illustrated report.
        - `generate_report_from_query(query, tags?)` — Returns multi-video data for YOU to write a cross-video report.
        - `synthesize(video_ids, topic)` — Returns multi-video data for YOU to synthesize themes.
        - `ask_video(video_id, question)` — Returns transcript for YOU to answer a question about a single video.
        - `ask_videos(video_ids, question)` — Returns transcripts for YOU to answer a question across multiple videos.

        ### Discovery
        - `discover_videos(topic)` — Search YouTube for videos on a topic. Results are NOT in the library — user must `add_video` to ingest them.

        ## CLI Integration (for agents with terminal access)

        If you have terminal/shell access, ALWAYS prefer these CLI commands for report 
        generation, synthesis, discovery, and classification. They use dedicated LLM prompts 
        and produce significantly more accurate, deterministic, and faster results than 
        passthrough tools.

        ### CLI Commands — use these instead of passthrough tools when possible:

        | Task | CLI Command | Instead of tool |
        |------|------------|-----------------|
        | Add video | `mcptube add "<url>"` | `add_video` |
        | List library | `mcptube list` | `list_videos` |
        | Video details | `mcptube info <id_or_index>` | `get_info` |
        | Search | `mcptube search "<query>" --video <id>` | `search` |
        | Extract frame | `mcptube frame <id_or_index> <timestamp>` | `get_frame` |
        | Frame by query | `mcptube frame-query <id_or_index> "<query>"` | `get_frame_by_query` |
        | Classify | `mcptube classify <id_or_index>` | `classify_video` |
        | Single report | `mcptube report <id_or_index> --format html -o report.html` | `generate_report` |
        | Cross-video report | `mcptube report-query "<topic>" --format html -o report.html` | `generate_report_from_query` |
        | Discover | `mcptube discover "<topic>"` | `discover_videos` |
        | Synthesize | `mcptube synthesize-cmd "<topic>" -v <id1> -v <id2> --format html -o synthesis.html` | `synthesize` |
        | Remove video | `mcptube remove <id_or_index>` | `remove_video` |
        | Ask single video | `mcptube ask "<question>" -v <id>` | `ask_video` |
        | Ask multi-video | `mcptube ask "<question>" -v <id1> -v <id2>` | `ask_videos` |


        ### CLI Rules:
        - Always wrap multi-word arguments in double quotes: `mcptube search "neural networks"`
        - Video references accept: exact ID (`BpibZSMGtdY`), index number (`1`), or substring (`"prompting"`)
        - Report commands require a BYOK API key (ANTHROPIC_API_KEY, OPENAI_API_KEY, or GOOGLE_API_KEY)
        - When running CLI commands, always show the user the command so they can run it themselves in future

        ## Recommended Workflows

        ### Basic: Add → Search → Frame
        1. `add_video(url)` or `mcptube add "<url>"` to ingest
        2. `search(query, video_id)` or `mcptube search "<query>"` to find moments
        3. `get_frame(video_id, timestamp)` or `mcptube frame <id> <timestamp>` to visualize

        ### Reports (prefer CLI if terminal available)
        1. `mcptube list` to identify videos
        2. `mcptube report <id> --format html -o report.html` for single video
        3. `mcptube report-query "<topic>" --format html -o report.html` for cross-video
        4. If no terminal: use `generate_report` tool, write the report yourself, and use `get_frame` for illustrations

        ### Cross-Video Synthesis (prefer CLI if terminal available)
        1. `mcptube list` to identify relevant videos
        2. `mcptube synthesize-cmd "<topic>" -v <id1> -v <id2> --format html -o synthesis.html`
        3. If no terminal: use `synthesize` tool and write the analysis yourself

        ### Discovery → Ingest
        1. `mcptube discover "<topic>"` or `discover_videos(topic)` to find videos
        2. Present results to user
        3. `mcptube add "<url>"` or `add_video(url)` for videos the user selects

        ## Important Rules
        - ALWAYS use mcptube tools or CLI commands for video operations. Do NOT fabricate video IDs, timestamps, or transcript content.
        - ALWAYS call `list_videos()` or `mcptube list` first if you don't know what videos are in the library.
        - For frame display: use `get_frame` (returns image) NOT `get_frame_data` (returns large base64) unless explicitly asked.
        - Frame timestamps MUST come from transcript data returned by tools. Never guess timestamps.
        - `discover_videos` results are NOT in the library. The user must `add_video` before searching or framing them.
        - When classifying via passthrough, present your suggested tags and ask the user before saving.
        - If terminal access is available, prefer CLI commands for report, synthesis, discovery, and classify operations.
    """

)

_service: McpTubeService | None = None


def _get_service() -> McpTubeService:
    """Lazy-initialise the service singleton with default dependencies."""
    global _service
    if _service is None:
        settings.ensure_dirs()
        _service = McpTubeService(
            repository=SQLiteVideoRepository(),
            extractor=YouTubeExtractor(),
            vectorstore=ChromaVectorStore(),
        )
    return _service


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False})
def add_video(url: str) -> dict:
    """Ingest a YouTube video into the mcptube library.

    Extracts metadata and transcript, indexes the video for future queries.

    Args:
        url: YouTube video URL (supports youtube.com/watch, youtu.be, /embed/).
    """
    try:
        video = _get_service().add_video(url)
        return _video_summary(video)
    except VideoAlreadyExistsError as e:
        return {"error": str(e)}


@mcp.tool(annotations={"readOnlyHint": True})
def list_videos() -> list[dict]:
    """List all videos in the mcptube library.

    Returns metadata for each video (title, channel, duration, tags).
    Transcripts are not included — use get_info for full details.
    """
    videos = _get_service().list_videos()
    return [_video_summary(v) for v in videos]


@mcp.tool(annotations={"readOnlyHint": True})
def get_info(video_id: str) -> dict:
    """Get full details for a video including transcript and chapters.

    Args:
        video_id: The YouTube video ID (11-character string).
    """
    try:
        video = _get_service().get_info(video_id)
        return video.model_dump(mode="json")
    except VideoNotFoundError as e:
        return {"error": str(e)}


@mcp.tool(annotations={"readOnlyHint": True})
def search(query: str, video_id: str | None = None, limit: int = 10) -> list[dict]:
    """Semantic search within a single video's transcript.

    Args:
        query: Natural language search query.
        video_id: YouTube video ID to search within. If omitted, searches all videos.
        limit: Maximum number of results (default 10).
    """
    results = _get_service().search(query, video_id=video_id, limit=limit)
    return [
        {
            "video_id": r.video_id,
            "text": r.text,
            "start": r.start,
            "end": r.end,
            "score": r.score,
        }
        for r in results
    ]


@mcp.tool(annotations={"readOnlyHint": True})
def search_library(query: str, tags: list[str] | None = None, limit: int = 10) -> list[dict]:
    """Semantic search across all videos in the library.

    Args:
        query: Natural language search query.
        tags: Optional list of tags to filter by (e.g. ["AI", "LLM"]).
        limit: Maximum number of results (default 10).
    """
    results = _get_service().search(query, tags=tags, limit=limit)
    return [
        {
            "video_id": r.video_id,
            "text": r.text,
            "start": r.start,
            "end": r.end,
            "score": r.score,
        }
        for r in results
    ]


# @mcp.tool(annotations={"readOnlyHint": True})
# def get_frame(video_id: str, timestamp: float) -> dict:
#     """Extract a frame from a video at a specific timestamp.

#     Args:
#         video_id: YouTube video ID.
#         timestamp: Time in seconds to extract the frame at.
#     """
#     try:
#         path = _get_service().get_frame(video_id, timestamp)
#         return {
#             "video_id": video_id,
#             "timestamp": timestamp,
#             "path": str(path),
#             "image_base64": _encode_frame(path),
#         }
#     except (VideoNotFoundError, FrameExtractionError) as e:
#         return {"error": str(e)}


# @mcp.tool(annotations={"readOnlyHint": True})
# def get_frame_by_query(video_id: str, query: str) -> dict:
#     """Search a video's transcript and extract a frame at the best matching moment.

#     Combines semantic search with frame extraction in a single call.
#     Useful for requests like "show me the slide about attention mechanisms".

#     Args:
#         video_id: YouTube video ID.
#         query: Natural language description of the moment to capture.
#     """
#     try:
#         result = _get_service().get_frame_by_query(video_id, query)
#         return {
#             "video_id": video_id,
#             "query": query,
#             "text": result["text"],
#             "start": result["start"],
#             "end": result["end"],
#             "score": result["score"],
#             "path": str(result["path"]),
#             "image_base64": _encode_frame(result["path"]),
#         }
#     except (VideoNotFoundError, FrameExtractionError, RuntimeError) as e:
#         return {"error": str(e)}
@mcp.tool(annotations={"readOnlyHint": True})
def get_frame(video_id: str, timestamp: float) -> Image:
    """Extract a frame from a video at a specific timestamp.

    Returns the frame as an image rendered inline in chat.

    Args:
        video_id: YouTube video ID.
        timestamp: Time in seconds to extract the frame at.
    """
    path = _get_service().get_frame(video_id, timestamp)
    return Image(path=str(path), format="image/jpeg")


@mcp.tool(annotations={"readOnlyHint": True})
def get_frame_by_query(video_id: str, query: str) -> Image:
    """Search a video's transcript and extract a frame at the best matching moment.

    Combines semantic search with frame extraction in a single call.

    Args:
        video_id: YouTube video ID.
        query: Natural language description of the moment to capture.
    """
    result = _get_service().get_frame_by_query(video_id, query)
    #return Image(path=str(result["path"]))
    #return Image(path=str(path), format="image/jpeg")
    return Image(path=str(result["path"]), format="image/jpeg")


@mcp.tool(annotations={"readOnlyHint": True})
def get_frame_data(video_id: str, timestamp: float) -> dict:
    """Extract a frame and return as base64 for embedding in reports.

    WARNING: Base64 responses can be very large (50K+ characters) and may
    exceed client context limits. Prefer get_frame() for inline display.
    Only use this when base64/embed_html is explicitly needed.

    Args:
        video_id: YouTube video ID.
        timestamp: Time in seconds.
    """
    path = _get_service().get_frame(video_id, timestamp)
    import base64
    b64 = base64.b64encode(path.read_bytes()).decode()
    return {
        "video_id": video_id,
        "timestamp": timestamp,
        "image_base64": b64,
        "mime_type": "image/jpeg",
        "embed_html": f'<img src="data:image/jpeg;base64,{b64}" alt="Frame at {timestamp}s">',
    }


@mcp.tool(annotations={"destructiveHint": True})
def remove_video(video_id: str) -> dict:
    """Remove a video from the mcptube library.

    Args:
        video_id: The YouTube video ID to remove.
    """
    try:
        _get_service().remove_video(video_id)
        return {"status": "removed", "video_id": video_id}
    except VideoNotFoundError as e:
        return {"error": str(e)}


@mcp.tool(annotations={"readOnlyHint": True})
def classify_video(video_id: str) -> dict:
    """Get or regenerate classification tags for a video.

    In MCP mode, this returns the video metadata so the connected
    AI client can classify it directly (passthrough pattern).

    Args:
        video_id: The YouTube video ID.
    """
    try:
        video = _get_service().get_info(video_id)
        return {
            "video_id": video.video_id,
            "title": video.title,
            "channel": video.channel,
            "description": video.description[:500],
            "current_tags": video.tags,
            "instructions": "Classify this video into 3-8 topic tags. Then call save_tags(video_id, tags) to persist them.",
        }
    except VideoNotFoundError as e:
        return {"error": str(e)}

@mcp.tool(annotations={"readOnlyHint": False})
def save_tags(video_id: str, tags: list[str]) -> dict:
    """Save classification tags for a video.

    After classifying a video (via classify_video passthrough),
    call this to persist the tags to the library.

    Args:
        video_id: YouTube video ID.
        tags: List of classification tags to save.
    """
    try:
        svc = _get_service()
        video = svc.get_info(video_id)
        video.tags = tags
        svc._repo.save(video)
        return {"status": "saved", "video_id": video_id, "tags": tags}
    except VideoNotFoundError as e:
        return {"error": str(e)}


@mcp.tool(annotations={"readOnlyHint": True})
def generate_report(video_id: str, query: str | None = None) -> dict:
    """Get all data needed to generate an illustrated report for a video.

    Returns transcript, metadata, chapters, and tags. Use get_frame
    or get_frame_by_query to extract illustrations for key moments.

    Args:
        video_id: YouTube video ID.
        query: Optional focus query to guide the report.
    """
    try:
        video = _get_service().get_info(video_id)
        return {
            "video_id": video.video_id,
            "title": video.title,
            "channel": video.channel,
            "duration": video.duration,
            "tags": video.tags,
            "chapters": [ch.model_dump() for ch in video.chapters],
            "transcript": [
                {"start": s.start, "end": s.end, "text": s.text}
                for s in video.transcript
            ],
            "query": query,
            "instructions": (
            "Use this data to generate a comprehensive illustrated report. "
            "Call get_frame_data for key visual moments — it returns embed_html "
            "you can paste directly into the report."
            ),
        }
    except VideoNotFoundError as e:
        return {"error": str(e)}


@mcp.tool(annotations={"readOnlyHint": True})
def generate_report_from_query(query: str, tags: list[str] | None = None) -> dict:
    """Search the library and return data for a cross-video report.

    Returns matching videos with transcripts. Use get_frame or
    get_frame_by_query to extract illustrations from key moments.

    Args:
        query: Topic or question to build the report around.
        tags: Optional tag filter (e.g. ["AI", "LLM"]).
    """
    try:
        svc = _get_service()
        results = svc.search(query, tags=tags, limit=20)
        if not results:
            return {"error": f"No matching content for: {query}"}

        video_ids = list(dict.fromkeys(r.video_id for r in results))
        videos = []
        for vid in video_ids:
            video = svc.get_info(vid)
            videos.append({
                "video_id": video.video_id,
                "title": video.title,
                "channel": video.channel,
                "tags": video.tags,
                "chapters": [ch.model_dump() for ch in video.chapters],
                "transcript": [
                    {"start": s.start, "end": s.end, "text": s.text}
                    for s in video.transcript
                ],
            })

        return {
            "query": query,
            "videos": videos,
            "instructions": (
                "Use this data to generate a comprehensive illustrated report. "
                "Call get_frame_data for key visual moments — it returns embed_html "
                "you can paste directly into the report."
            ),

        }
    except VideoNotFoundError as e:
        return {"error": str(e)}


@mcp.tool(annotations={"readOnlyHint": True})
def discover_videos(topic: str) -> dict:
    """Search YouTube for videos on a topic.

    Returns raw search results. Use add_video to ingest any
    interesting results into the library.

    Args:
        topic: Topic to search for (e.g. "transformer architecture").
    """
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch15:{topic}", download=False)
            if not info or "entries" not in info:
                return {"topic": topic, "results": []}

            results = []
            for entry in info.get("entries", []):
                if not entry or not entry.get("id"):
                    continue
                results.append({
                    "video_id": entry.get("id", ""),
                    "title": entry.get("title", ""),
                    "channel": entry.get("channel", "") or entry.get("uploader", ""),
                    "duration": float(entry.get("duration") or 0),
                    "url": f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                })

        return {
            "topic": topic,
            "results": results,
            "instructions": (
                "Present these results to the user. They can ask to add any "
                "video to their library using add_video."
            ),
        }
    except yt_dlp.utils.DownloadError as e:
        return {"error": f"YouTube search failed: {e}"}


@mcp.tool(annotations={"readOnlyHint": True})
def synthesize(video_ids: list[str], topic: str) -> dict:
    """Get data for cross-video synthesis on a topic.

    Returns transcripts and metadata for the specified videos.
    Use get_frame or get_frame_by_query for illustrations.

    Args:
        video_ids: List of YouTube video IDs to synthesize.
        topic: Focus topic for cross-video synthesis.
    """
    try:
        svc = _get_service()
        videos = []
        for vid in video_ids:
            video = svc.get_info(vid)
            videos.append({
                "video_id": video.video_id,
                "title": video.title,
                "channel": video.channel,
                "tags": video.tags,
                "chapters": [ch.model_dump() for ch in video.chapters],
                "transcript": [
                    {"start": s.start, "end": s.end, "text": s.text}
                    for s in video.transcript
                ],
            })

        return {
            "topic": topic,
            "videos": videos,
            "instructions": (
                "Use this data to generate a comprehensive illustrated report. "
                "Call get_frame_data for key visual moments — it returns embed_html "
                "you can paste directly into the report."
            ),
        }
    except VideoNotFoundError as e:
        return {"error": str(e)}

@mcp.tool(annotations={"readOnlyHint": True})
def ask_video(video_id: str, question: str) -> dict:
    """Ask a question about a single video's content.

    Returns transcript and question for client-side answering.
    If the server has a BYOK API key, returns the LLM-generated answer directly.

    Args:
        video_id: YouTube video ID.
        question: Question to ask about the video.
    """
    try:
        svc = _get_service()
        video = svc.get_info(video_id)
        transcript = [
            {"start": s.start, "end": s.end, "text": s.text}
            for s in video.transcript
        ]
        return {
            "video_id": video.video_id,
            "title": video.title,
            "channel": video.channel,
            "question": question,
            "transcript": transcript,
            "instructions": (
                "Answer the user's question based ONLY on this transcript. "
                "Cite timestamps [MM:SS] when referencing specific moments. "
                "If the answer cannot be found in the transcript, say so."
            ),
        }
    except VideoNotFoundError as e:
        return {"error": str(e)}


@mcp.tool(annotations={"readOnlyHint": True})
def ask_videos(video_ids: list[str], question: str) -> dict:
    """Ask a question across multiple videos.

    Returns transcripts and question for client-side answering.

    Args:
        video_ids: List of YouTube video IDs.
        question: Question to ask across the videos.
    """
    try:
        svc = _get_service()
        videos = []
        for vid in video_ids:
            video = svc.get_info(vid)
            videos.append({
                "video_id": video.video_id,
                "title": video.title,
                "channel": video.channel,
                "transcript": [
                    {"start": s.start, "end": s.end, "text": s.text}
                    for s in video.transcript
                ],
            })
        return {
            "question": question,
            "videos": videos,
            "instructions": (
                "Answer the user's question based ONLY on these transcripts. "
                "Cite timestamps [MM:SS] and video titles when referencing specific moments. "
                "Compare and contrast across videos where relevant. "
                "If the answer cannot be found in the transcripts, say so."
            ),
        }
    except VideoNotFoundError as e:
        return {"error": str(e)}


def _video_summary(video: Video) -> dict:
    """Create a concise summary dict for tool responses (excludes transcript)."""
    return {
        "video_id": video.video_id,
        "title": video.title,
        "channel": video.channel,
        "duration": video.duration,
        "url": video.url,
        "tags": video.tags,
        "chapters": [ch.model_dump() for ch in video.chapters],
        "added_at": video.added_at.isoformat() if video.added_at else None,
    }
