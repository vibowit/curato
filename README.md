# Curato 🎬🍿

[![CI](https://github.com/vibowit/curato/actions/workflows/ci.yml/badge.svg)](https://github.com/vibowit/curato/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Model Context Protocol](https://img.shields.io/badge/MCP-2.0+-purple.svg)](https://modelcontextprotocol.io/)
[![SQLite WAL](https://img.shields.io/badge/SQLite-WAL%20mode-003B57.svg?logo=sqlite&logoColor=white)](https://www.sqlite.org/wal.html)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Curato** is a self-hosted, private movie and TV show recommendation engine. It continuously learns from your personal watch history and ratings on **Simkl**, builds a versioned taste profile, sources candidates from **TMDB**, and leverages **LLMs (Google Gemini / OpenAI)** for multi-factor semantic scoring and reasoning.

It provides a lightweight web dashboard, a full REST API, and native **Model Context Protocol (MCP)** integration for AI assistants (Antigravity IDE/CLI, Cursor, Claude Desktop, and ChatGPT).

---

## ✨ Key Features

- **🎯 Provenance-Aware Taste Profiling**: Analyzes your watch history, ratings, and directorial affinities. Automatically versions profiles (`v1.0-gemini`, `v2.0-gemini`) with provenance timestamps and supports manual fine-tuning (`v1.1-manual`).
- **🛡️ Strict Anti-Recommendation Filtering**: Never recommends titles you have already watched, currently have on *Plan to Watch*, or previously rejected/hidden. Respects negative genre biases (e.g. anti-animation filters).
- **⚖️ Hybrid Discovery & Scoring**: Combines rule-based TMDB discovery (40% favorites similarity, 35% genre preferences, 15% preferred creators, 10% curated exploration) with structured semantic LLM evaluation (match score, confidence, positive signals, and risks).
- **🎬 Integrated Trailer Player**: Automatically resolves official high-quality YouTube trailers via TMDB Videos, embedded in a responsive 16:9 player (`youtube-nocookie.com`) or fallback search.
- **🔒 Human-in-the-Loop Simkl Sync**: **Zero writes without explicit approval**. Recommendations must be explicitly accepted (`accept`) before you can batch-sync them to your Simkl *Plan to Watch* list. All operations are strictly idempotent.
- **🤖 Dual-Mode MCP Server**:
  - **STDIO**: Seamless local agent integration for Antigravity, Claude Desktop, and Cursor.
  - **Streamable HTTP / SSE**: Secure endpoint for remote AI agents (such as ChatGPT Custom GPTs) protected by Bearer token authentication.
- **⚡ Homelab-Ready Architecture**: Runs on FastAPI, SQLAlchemy 2.0, and SQLite configured with **Write-Ahead Logging (WAL)** and busy timeouts for concurrent, collision-free 24/7 background scheduling.

---

## 🏗️ Architecture Overview

```
                 ┌──────────────────────────────────────────────────┐
                 │                   Clients                        │
                 │   Web SPA (Vanilla JS)  │  Antigravity / Cursor  │  ChatGPT (SSE)
                 └─────────────┬───────────┴───────────┬────────────┴───────┬──────┘
                               │ HTTP / REST           │ STDIO MCP          │ SSE MCP
                               ▼                       ▼                    ▼
                 ┌─────────────────────────────────────────────────────────────────┐
                 │                    Curato FastAPI Backend                       │
                 │                                                                 │
                 │   [ REST API /api/v1 ]         [ MCP Server & Tools ]           │
                 │   [ Static SPA Files ]         [ Async Background Scheduler ]   │
                 │                                                                 │
                 │   Domain Services:                                              │
                 │     • SyncService         (Simkl history & ratings)             │
                 │     • TasteService        (LLM profiling & versioning)          │
                 │     • DiscoveryService    (TMDB multi-strategy candidates)      │
                 │     • RecommendationEngine(Anti-filter, scoring & diversity)    │
                 │     • WatchlistService    (Controlled, idempotent Simkl export) │
                 └──────────────────────────────┬──────────────────────────────────┘
                                                │
                     ┌──────────────────────────┼──────────────────────────┐
                     ▼                          ▼                          ▼
            [ SQLite (WAL Mode) ]      [ External APIs ]          [ External APIs ]
            • media_items              • Simkl API (OAuth 2.0)    • Google Gemini /
            • watch_history            • TMDB API (v3/v4)           OpenAI API
            • taste_profiles
            • recommendations
            • user_decisions
```

---

## 🚀 Quickstart with Docker Compose

Curato is packaged for instant deployment using Docker Compose:

1. **Clone the repository:**
   ```bash
   git clone git@github.com:vibowit/curato.git
   cd curato
   ```

2. **Configure your environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env and supply your API keys (see Configuration below)
   ```

3. **Ensure the data volume directory has appropriate permissions (UID 1000):**
   ```bash
   mkdir -p data
   # On Linux/Proxmox: sudo chown -R 1000:1000 data && sudo chmod 775 data
   ```

4. **Start the service:**
   ```bash
   docker compose up -d --build
   ```

5. Open your browser:
   - **Review Dashboard**: [http://localhost:8000/](http://localhost:8000/)
   - **API Docs (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Healthcheck**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

---

## ⚙️ Configuration (`.env`)

Copy `.env.example` to `.env` and configure:

| Variable | Description | Required |
| :--- | :--- | :---: |
| `SIMKL_CLIENT_ID` | Simkl Developer Client ID ([Simkl Developer](https://simkl.com/settings/developer/)) | **Yes** |
| `SIMKL_CLIENT_SECRET` | Simkl Developer Client Secret | **Yes** |
| `SIMKL_USER_TOKEN` | Simkl User Access Token (obtainable via `python scripts/get_simkl_token.py`) | **Yes** |
| `TMDB_API_KEY` | The Movie Database API Key v3 ([TMDB Settings](https://www.themoviedb.org/settings/api)) | **Yes** |
| `GEMINI_API_KEY` | Google Gemini API Key ([Google AI Studio](https://aistudio.google.com/)) | **Yes** |
| `GEMINI_MODEL` | Preferred Gemini model (default: `gemini-2.5-flash`) | No |
| `MCP_API_KEY` | Shared secret token protecting remote `/mcp/sse` endpoints | Recommended |
| `SCHEDULER_ENABLED` | Enables weekly automated background sync and recommendation generation | No (default: `true`) |
| `SQLITE_DB_PATH` | Path to SQLite database file (default: `/app/data/movie_recommend.db`) | No |

---

## 🤖 Model Context Protocol (MCP) Integration

Curato exposes 9 domain tools to AI agents:

- `get_taste_profile()`: Current active taste profile (genres, motifs, directors, anti-preferences).
- `get_library_stats()`: Synchronized library counters and sync timestamps.
- `sync_simkl(full_sync)`: Trigger on-demand sync from Simkl.
- `generate_recommendations(movie_limit, show_limit)`: Run the recommendation pipeline.
- `get_recommendations(run_id)`: Retrieve candidates with scores, reasoning, and trailer URLs.
- `get_trailer(recommendation_id)`: Fetch official YouTube trailer details.
- `record_decision(recommendation_id, decision, note)`: Register user choice (`accept`, `reject`, `seen`, `later`).
- `approve_recommendations(recommendation_ids)`: Safely export approved items to Simkl *Plan to Watch*.
- `get_recommendation_history(limit)`: History of past runs and editions.

### Antigravity IDE / Cursor / Claude Desktop (STDIO)
Add to your client configuration (e.g. `~/.gemini/settings.json`):

```json
{
  "mcpServers": {
    "curato": {
      "command": "/path/to/curato/.venv/bin/python",
      "args": ["-m", "app.mcp.cli"],
      "cwd": "/path/to/curato"
    }
  }
}
```

### ChatGPT / Remote Assistant (SSE)
- **SSE Endpoint**: `https://your-domain.com/mcp/sse`
- **Messages Endpoint**: `https://your-domain.com/mcp/messages/`
- **Authentication**: Bearer header with your `MCP_API_KEY`

---

## 🛠️ Local Development

Curato uses [`uv`](https://github.com/astral-sh/uv) for fast, reproducible dependency management.

```bash
# 1. Install dependencies
uv sync

# 2. Apply database migrations
uv run alembic upgrade head

# 3. Start development server with hot-reload
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 4. Run full test suite (108 tests)
uv run pytest

# 5. Run linter
uv run ruff check app tests
```

---

## 📄 License & Showcase Notice

This project is licensed under the **[MIT License](LICENSE)**.

Curato is a personal portfolio project. Issues and Pull Requests are disabled. You are welcome to fork and adapt it for your own homelab setup.
