# 🎬 mcptube

**Convert any YouTube video into an AI-queryable MCP server.**

[![PyPI](https://img.shields.io/pypi/v/mcptube)](https://pypi.org/project/mcptube/)
[![Python](https://img.shields.io/pypi/pyversions/mcptube)](https://pypi.org/project/mcptube/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

mcptube extracts metadata, transcripts, and frames from YouTube videos, indexes them for semantic search, and exposes everything as both a CLI tool and an MCP (Model Context Protocol) server. Ask questions, generate reports, discover new videos, and synthesize themes — all from your terminal or AI assistant.

---

## ✨ Features

| Feature | CLI | MCP Server |
|---------|:---:|:----------:|
| Add/remove YouTube videos | ✅ | ✅ |
| List library with tags | ✅ | ✅ |
| Full video details + transcript | ✅ | ✅ |
| Semantic search (single/cross-video) | ✅ | ✅ |
| Frame extraction by timestamp | ✅ | ✅ |
| Frame extraction by query | ✅ | ✅ |
| Ask questions about videos | ✅ (BYOK) | ✅ (passthrough) |
| LLM classification/tagging | ✅ (BYOK) | ✅ (passthrough) |
| Illustrated reports (single video) | ✅ (BYOK) | ✅ (passthrough) |
| Cross-video reports | ✅ (BYOK) | ✅ (passthrough) |
| YouTube discovery + clustering | ✅ (BYOK) | ✅ |
| Cross-video synthesis | ✅ (BYOK) | ✅ (passthrough) |
| Smart video resolver (ID/index/text) | ✅ | — |

**BYOK** = Bring Your Own Key (Anthropic, OpenAI, or Google)
**Passthrough** = The MCP client's own LLM does the analysis — zero API key required on the server

---

## 📦 Installation

### Prerequisites

- **Python 3.12 or 3.13** (ChromaDB is not yet compatible with Python 3.14)
- **ffmpeg** — required for frame extraction ([install guide](https://ffmpeg.org/download.html))

### Recommended: pipx (CLI + MCP server)

```bash
pipx install mcptube --python python3.12
```

This installs `mcptube` globally and makes it available to all MCP clients without activating a virtual environment.

### Alternative: pip (virtual environment)

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install mcptube
```

> ⚠️ **macOS/Homebrew users**: Global `pip install` will fail with "externally-managed-environment". Use `pipx` or a virtual environment instead.

### Verify installation

```bash
mcptube --help
```

---

## 🚀 Quick Start

```bash
# 1. Add a YouTube video
mcptube add "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 2. List your library
mcptube list

# 3. Search the transcript
mcptube search "main topic"

# 4. Extract a frame at 30 seconds
mcptube frame 1 30

# 5. Ask a question about it
mcptube ask "What is this video about?" -v 1
```

> 💡 **Always wrap multi-word arguments in double quotes** — e.g. `mcptube search "neural networks"`, not `mcptube search neural networks`.

---

## 📖 CLI Reference

### Library Management

| Command | Description | Example |
|---------|-------------|---------|
| `mcptube add "<url>"` | Ingest a YouTube video | `mcptube add "https://youtu.be/dQw4w9WgXcQ"` |
| `mcptube list` | List all videos with tags | `mcptube list` |
| `mcptube info <query>` | Show full video details | `mcptube info 1` or `mcptube info "dQw4w9WgXcQ"` |
| `mcptube remove <query>` | Remove a video | `mcptube remove 1` |

### Search & Frames

| Command | Description | Example |
|---------|-------------|---------|
| `mcptube search "<query>"` | Semantic search across all videos | `mcptube search "machine learning"` |
| `mcptube search "<query>" --video <id>` | Search within a specific video | `mcptube search "intro" --video 1` |
| `mcptube frame <video> <timestamp>` | Extract frame at timestamp | `mcptube frame 1 30` |
| `mcptube frame-query <video> "<query>"` | Extract frame by transcript match | `mcptube frame-query 1 "key moment"` |

### Ask Questions (BYOK)

| Command | Description | Example |
|---------|-------------|---------|
| `mcptube ask "<question>" -v <video>` | Ask about a single video | `mcptube ask "What are the main points?" -v 1` |
| `mcptube ask "<question>" -v <id1> -v <id2>` | Ask across multiple videos | `mcptube ask "What do they agree on?" -v 1 -v 2` |

### Analysis & Reports (BYOK)

| Command | Description | Example |
|---------|-------------|---------|
| `mcptube classify <video>` | LLM classification/tagging | `mcptube classify 1` |
| `mcptube report <video> [--focus] [--format] [-o]` | Single-video illustrated report | `mcptube report 1 --format html -o report.html` |
| `mcptube report-query "<topic>" [--tag] [--format] [-o]` | Cross-video report | `mcptube report-query "AI trends" --format html -o report.html` |
| `mcptube discover "<topic>"` | YouTube search + LLM clustering | `mcptube discover "prompt engineering"` |
| `mcptube synthesize-cmd "<topic>" -v <id1> -v <id2>` | Cross-video synthesis | `mcptube synthesize-cmd "AI" -v abc123 -v xyz789 --format html -o synthesis.html` |

### Server

| Command | Description | Example |
|---------|-------------|---------|
| `mcptube serve` | Start MCP server (Streamable HTTP) | `mcptube serve` |
| `mcptube serve --stdio` | Start MCP server (stdio transport) | `mcptube serve --stdio` |
| `mcptube serve --host 0.0.0.0 --port 8080` | Custom host/port | `mcptube serve --host 0.0.0.0 --port 8080` |

### Smart Video Resolver

All commands that accept a `<video>` or `<query>` argument support the smart resolver:

| Input | Resolution |
|-------|-----------|
| `dQw4w9WgXcQ` | Exact YouTube video ID |
| `1` | Index number from `mcptube list` (1-based) |
| `"prompting"` | Case-insensitive substring match on title or channel |

---

## 🔌 MCP Server

mcptube exposes **17 MCP tools** that any MCP-compatible AI assistant can use.

### Transport Modes

| Mode | Command | Use Case |
|------|---------|----------|
| **Streamable HTTP** | `mcptube serve` | Claude Code, remote clients |
| **stdio** | `mcptube serve --stdio` | VS Code Copilot, Claude Desktop, Cursor |

### MCP Tools

| Tool | Description | API Key Required |
|------|-------------|:----------------:|
| `add_video(url)` | Ingest a YouTube video | No |
| `remove_video(video_id)` | Remove from library | No |
| `list_videos()` | List all videos | No |
| `get_info(video_id)` | Full details + transcript | No |
| `search(query, video_id?, limit)` | Semantic search (single video) | No |
| `search_library(query, tags?, limit)` | Semantic search (all videos) | No |
| `get_frame(video_id, timestamp)` | Extract frame (returns image) | No |
| `get_frame_by_query(video_id, query)` | Search + extract frame | No |
| `get_frame_data(video_id, timestamp)` | Frame as base64 | No |
| `ask_video(video_id, question)` | Ask about a video (passthrough) | No |
| `ask_videos(video_ids, question)` | Ask across videos (passthrough) | No |
| `classify_video(video_id)` | Get metadata for classification | No |
| `save_tags(video_id, tags)` | Save classification tags | No |
| `generate_report(video_id, query?)` | Report data (passthrough) | No |
| `generate_report_from_query(query, tags?)` | Cross-video report data | No |
| `discover_videos(topic)` | YouTube search results | No |
| `synthesize(video_ids, topic)` | Cross-video synthesis data | No |

> **Passthrough tools** return raw data (transcripts, metadata) for the connected AI to analyze. This means zero API key cost on the server — the client's own LLM does the work.

---

## 🖥️ MCP Client Setup

### Claude Code (Streamable HTTP)

1. Start the mcptube server:
```bash
mcptube serve
```

2. In a separate terminal, add the MCP server to Claude Code:
```bash
claude mcp add --transport http mcptube http://127.0.0.1:9093/mcp
```

3. Start using it:
```
> Use mcptube to add this video: https://www.youtube.com/watch?v=dQw4w9WgXcQ
> Search mcptube for "main topic"
> Generate a report for the first video
```

> 💡 Claude Code has terminal access, so it can also run CLI commands directly for better report quality.

### VS Code Copilot (stdio)

1. Open MCP configuration (Cmd+Shift+P → "MCP: Open User Configuration") or create `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "mcptube": {
      "command": "mcptube",
      "args": ["serve", "--stdio"]
    }
  }
}
```

2. Click the **Start** button next to the server entry.

3. Open Copilot Chat in **Agent Mode** and start using mcptube tools.

> ⚠️ If you installed mcptube in a virtual environment (not via `pipx`), you'll need the full path to the executable. Find it with `which mcptube`.

### Claude Desktop (stdio)

1. Open the config file:
```bash
open ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

2. Add the mcptube server:
```json
{
  "mcpServers": {
    "mcptube": {
      "command": "/Users/<your-username>/.local/bin/mcptube",
      "args": ["serve", "--stdio"]
    }
  }
}
```

> 💡 Use the full path to `mcptube` (find it with `which mcptube`). If you used `pipx`, it's typically at `~/.local/bin/mcptube`.

3. Restart Claude Desktop. You should see a tools icon (🔨) in the chat input.

### Cursor (stdio)

1. Open Cursor Settings → MCP Servers, or edit `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "mcptube": {
      "command": "mcptube",
      "args": ["serve", "--stdio"]
    }
  }
}
```

2. Restart Cursor and use mcptube tools in Agent mode.

---

## 🔑 API Keys (BYOK)

Some CLI features require an LLM API key. Set one of:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# or
export OPENAI_API_KEY=sk-...
# or
export GOOGLE_API_KEY=AI...
```

### What requires a key?

| Feature | CLI | MCP |
|---------|-----|-----|
| Add video | No (auto-classifies if key set) | No |
| Search / Frames | No | No |
| Ask questions | ✅ Key required | No (passthrough) |
| Classify | ✅ Key required | No (passthrough) |
| Reports | ✅ Key required | No (passthrough) |
| Discover | ✅ Key required | No (via yt-dlp) |
| Synthesize | ✅ Key required | No (passthrough) |

> **MCP passthrough** = The connected AI assistant (Claude, Copilot, etc.) analyzes the data using its own model. No API key needed on the mcptube server.

---

## ⚖️ CLI (BYOK) vs MCP: When to Use Which

| | CLI with BYOK | MCP Passthrough |
|---|---|---|
| **Speed** | Faster — direct API call | Slower — client processes raw data |
| **Accuracy** | More deterministic — fine-tuned prompts per task | Depends on client LLM interpretation |
| **Frame selection** | Guided by specialized prompts | Client may hallucinate timestamps |
| **Context limits** | No limit (streams to LLM API) | May exceed client context window on long videos |
| **Cost** | Uses your API key | Zero cost — uses client's own model |
| **Output** | Markdown or HTML files | Inline in chat |

**Recommendation**: Use CLI commands for reports, synthesis, and discovery. Use MCP tools for quick queries, search, and frame extraction.

---

## 🔄 Workflows

### Discovery → Add → Synthesize

```bash
# 1. Scout YouTube for relevant videos
mcptube discover "transformer architecture"

# 2. Add interesting videos to your library
mcptube add "https://www.youtube.com/watch?v=..."
mcptube add "https://www.youtube.com/watch?v=..."

# 3. Synthesize themes across them
mcptube synthesize-cmd "attention mechanisms" -v <id1> -v <id2> --format html -o synthesis.html
```

> 📌 `discover` results are NOT in your library. You must `add` them before you can search, ask, or synthesize.

### Ask → Deep Dive → Report

```bash
# 1. Ask a quick question
mcptube ask "What are the main arguments?" -v 1

# 2. Search for specific moments
mcptube search "key conclusion" --video 1

# 3. Extract a frame at that moment
mcptube frame 1 245

# 4. Generate a full illustrated report
mcptube report 1 --format html -o report.html
```

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCPTUBE_DATA_DIR` | `~/.mcptube` | Root directory for all data (DB, frames, ChromaDB) |
| `MCPTUBE_FRAMES_DIR` | `<data_dir>/frames` | Directory for cached extracted frames |
| `MCPTUBE_HOST` | `127.0.0.1` | Server bind host |
| `MCPTUBE_PORT` | `9093` | Server bind port |
| `ANTHROPIC_API_KEY` | — | Anthropic API key (for CLI BYOK features) |
| `OPENAI_API_KEY` | — | OpenAI API key (for CLI BYOK features) |
| `GOOGLE_API_KEY` | — | Google API key (for CLI BYOK features) |

---

## 🏗️ Architecture

```
CLI (Typer)  ←──────┐
                     ├── Service Layer (McpTubeService)
MCP Server (FastMCP) ←─┘        │
                           ┌────┴────┐
                     Repository    VectorStore
                     (SQLite)      (ChromaDB)
                           │
                     Ingestion Layer
                     ├── YouTubeExtractor (yt-dlp)
                     ├── FrameExtractor (yt-dlp + ffmpeg)
                     ├── LLMClient (LiteLLM — CLI only)
                     ├── ReportBuilder (CLI only)
                     └── VideoDiscovery (CLI only)
```

---

## ⚠️ Known Issues & Limitations

- **Frame storage**: Frames are cached in `~/.mcptube/frames` (hidden directory). Override with `MCPTUBE_FRAMES_DIR`.
- **Python 3.14**: ChromaDB is not yet compatible with Python 3.14. Use Python 3.12 or 3.13.
- **Long transcripts**: Very long videos may exceed MCP client context limits in passthrough mode. CLI BYOK is recommended for long-form content.
- **Multi-video frame accuracy**: Cross-video reports may occasionally select frames from the wrong video. CLI reports use stricter prompts for better accuracy.
- **Claude Desktop**: Report generation may fail on context-heavy operations. Use shorter videos or CLI for reports.
- **`get_frame_data`**: Returns base64-encoded frames that can exceed client token limits (50K+ characters). Prefer `get_frame` for inline display.
- **Concurrent access**: Running CLI and MCP server simultaneously may cause SQLite conflicts.

---

## 🧪 Development

```bash
git clone https://github.com/0xchamin/mcptube.git
cd mcptube
pip install -e ".[dev]"
pytest -v
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

Built with [FastMCP](https://gofastmcp.com) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [ChromaDB](https://www.trychroma.com) · [LiteLLM](https://github.com/BerriAI/litellm)