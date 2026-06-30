# Coding Agent Service

A cloud-native coding agent service (FastAPI, Dockerized) that receives tasks from a VS Code extension harness, executes them via a minimal toolset, and streams real-time progress back over SSE. The agent delegates LLM and applier calls to OpenRouter. A separate Contexter container supplies user preferences merged into the task context.

## Architecture

```
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│  VS Code         │  SSE  │  Agent Service   │ HTTP  │  Contexter        │
│  Extension       │◄──────│  (FastAPI)       │──────►│  (preferences)    │
│  (harness)       │  REST │                  │       │                   │
│                  │──────►│  POST /jobs ─────┼──────►│  POST /tasks      │
└──────────────────┘       └───┬──────────────┘       └──────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                 ▼
        ┌──────────┐    ┌───────────┐    ┌───────────┐
        │ OpenRouter│    │ Tavily API│    │  ripgrep  │
        │ (LLM +    │    │           │    │ (binary)  │
        │  Applier) │    │           │    │           │
        └──────────┘    └───────────┘    └───────────┘
```

## Agent Tools (6 LLM-facing)

| Tool | Engine | Purpose |
|------|--------|---------|
| `run_command` | CommandRunner | Execute shell commands in the workspace |
| `create_file` | FileApplier | Create new files (direct write) |
| `edit_file` | FileApplier → OpenRouter (Morph v3 Fast) | Edit existing files via applier model |
| `delete_file` | FileApplier | Delete files (direct) |
| `search_files` | SearchEngine (ripgrep) | Regex search with structured JSON output |
| `search_web` | WebSearchClient (Tavily) | Web search for current information |
| `finish_task` | AgentLoop (control flow) | Signal task completion |

## Internal Engines (4)

- **CommandRunner** — subprocess with timeout, cwd, stdout/stderr capture
- **FileApplier** — direct write for create/delete; Morph applier model for edit
- **SearchEngine** — ripgrep subprocess with `--json` output
- **WebSearchClient** — Tavily Python SDK

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/jobs` | Create a new job |
| GET | `/jobs` | List jobs |
| GET | `/jobs/{job_id}` | Get job status |
| GET | `/jobs/{job_id}/events` | SSE event stream |
| POST | `/jobs/{job_id}/cancel` | Cancel a job |
| POST | `/jobs/{job_id}/input` | Send user input |
| GET | `/health` | Health check |

## Job Lifecycle

```
queued → running → (waiting_input → running)* → completed | failed | cancelled
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- OpenRouter API key
- Tavily API key

### Setup

1. Copy `.env.example` to `.env` and fill in your API keys:
   ```bash
   cp .env.example .env
   ```

2. Build and run with Docker Compose:
   ```bash
   docker compose up --build
   ```

3. The agent service will be available at `http://localhost:8000`.

### Local Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Project Structure

```
app/
├── main.py                 # FastAPI app, route registration
├── config.py               # Settings (env vars, model names, endpoints)
├── api/
│   └── deps.py             # Dependency injection
├── routers/
│   ├── health.py           # Health check endpoint
│   └── jobs.py             # Job endpoints + SSE streaming
├── models/
│   ├── job.py              # JobStatus, JobEvent, request/response schemas
│   ├── tools.py            # Tool argument schemas
│   └── execution.py        # Execution result models
├── core/
│   ├── agent.py            # AgentLoop: LLM orchestration
│   ├── llm.py              # LLMClient: ChatOpenAI via OpenRouter
│   ├── executor.py         # ToolExecutor: dispatches to handlers
│   └── job_store.py        # In-memory job store with asyncio.Queue per job
├── engines/
│   ├── command_runner.py   # subprocess wrapper
│   ├── file_applier.py     # create/edit/delete with diffs
│   ├── search_engine.py    # ripgrep --json
│   └── web_search.py       # Tavily SDK
├── tools/
│   ├── definitions.py      # JSON tool definitions for LLM
│   └── handlers.py         # Tool handler functions + SSE events
├── clients/
│   ├── contexter.py        # ContexterClient
│   └── applier.py          # ApplierClient (Morph via OpenRouter)
└── prompts/
    └── agent.md            # System prompt
```

## Key Technical Decisions

- **OpenRouter** for both LLM and applier — single API key, unified billing
- **LangChain ChatOpenAI** with base_url override — OpenRouter is OpenAI-compatible
- **sse-starlette** for production-ready SSE with client disconnect handling
- **asyncio.Queue per job** — decouples agent loop from SSE consumer
- **ripgrep with --json** — structured, machine-readable output
- **Morph v3 Fast** via OpenRouter — $0.80/M input, 10,500 tokens/sec, 96% accuracy
- **Preferences stored in job, not returned** — Contexter is internal only
- **Docker named volume** for persistent workspace across restarts