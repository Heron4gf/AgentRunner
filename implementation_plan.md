# Coding Agent — Implementation Plan

## Scope, Reason, Objective

### Scope
Build a cloud-native coding agent service (FastAPI, Dockerized) that receives tasks from a VS Code extension harness, executes them via a minimal toolset, and streams real-time progress back over SSE. The agent delegates LLM and applier calls to OpenRouter. A separate Contexter container supplies user preferences merged into the task context.

### Reason
Current coding agents (Cursor, Cline) suffer from context rot, unreliable diff application, and excessive internal complexity. This project minimizes the internal engine count to four while exposing six distinct LLM-facing tools, giving the model good prompting ergonomics without duplicating execution logic.

### Objective
Ship a minimal, maintainable agent service where: (1) file mutations are unified under a diff-based applier system, (2) task lifecycle follows a durable jobs pattern with SSE streaming, (3) all LLM/applier traffic flows through OpenRouter, (4) the Contexter provides preferences at task creation time, and (5) the entire system runs in Docker with workspace volumes.

---

## Architecture Overview

```
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│  VS Code         │  SSE  │  Agent Service   │ HTTP  │  Contexter        │
│  Extension       │◄──────│  (FastAPI)       │──────►│  (preferences)    │
│  (harness)       │  REST │                  │       │                   │
│                  │──────►│  POST /jobs ─────┼──────►│  POST /tasks      │
│                  │       │  ← {id, query,   │       │  ← {id, query,    │
│                  │       │     preferences} │       │     preferences}  │
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

---

## Agent Tools (LLM-Facing)

### 1. run_command
- **Purpose**: Execute a shell command in the workspace.
- **Args**:
  - `command: str` — the shell command to run
  - `cwd: str | None` — working directory, defaults to workspace root
  - `timeout: int` — timeout in seconds (default: 30)
- **Returns**: `{stdout: str, stderr: str, exit_code: int, duration_ms: int}`
- **Engine**: CommandRunner (subprocess)

### 2. create_file
- **Purpose**: Create a new file. Fails if file already exists.
- **Args**:
  - `path: str` — relative to workspace root
  - `content: str` — full file content
- **Returns**: `{operation: "create", path: str, diff: str}`
- **Engine**: FileApplier (direct write, no applier model)
- **Diff format**: Full-file addition diff

### 3. edit_file
- **Purpose**: Edit an existing file using the Morph applier model.
- **Args**:
  - `path: str` — relative to workspace root
  - `instruction: str` — natural language description of the edit (first-person, passed to applier prompt)
  - `update: str` — edit snippet using `// ... existing code ...` convention for unchanged sections
- **Returns**: `{operation: "edit", path: str, diff: str, original_content: str, updated_content: str}`
- **Engine**: FileApplier → OpenRouter (Morph v3 Fast)
- **Applier prompt format** (from Morph docs):
  ```
  <instruction>{instruction}</instruction>
  <code>{original_code}</code>
  <update>{edit_snippet}</update>
  ```
- **Key detail**: The agent reads the current file content before calling the applier, sends `{instruction, original, update}` to Morph, receives merged content, computes a unified diff for the SSE event.

### 4. delete_file
- **Purpose**: Delete a file from the workspace.
- **Args**:
  - `path: str` — relative to workspace root
- **Returns**: `{operation: "delete", path: str, diff: str}`
- **Engine**: FileApplier (direct delete, no applier model)
- **Diff format**: Full-file removal diff

### 5. search_files
- **Purpose**: OS-independent file search. Currently wraps ripgrep.
- **Args**:
  - `query: str` — regex pattern (natural language in future semantic layer)
  - `path: str | None` — directory to search in, defaults to workspace root
  - `file_pattern: str | None` — glob pattern, e.g. "*.py"
  - `max_results: int` — maximum matches (default: 50)
- **Returns**: `{matches: [{path, line, column, match, context}], total: int}`
- **Engine**: SearchEngine (ripgrep subprocess, structured output via `--json` flag)
- **Future**: Swap internal engine to semantic search without changing tool interface

### 6. search_web
- **Purpose**: Search the web for current information via Tavily.
- **Args**:
  - `query: str`
  - `max_results: int` — default: 5
- **Returns**: `{results: [{title, url, content, score}], total: int}`
- **Engine**: WebSearchClient (Tavily Python SDK)

### 7. finish_task
- **Purpose**: Signal task completion.
- **Args**:
  - `summary: str` — task completion summary
- **Returns**: Emits `COMPLETED` event, sets job status, ends loop.
- **Engine**: None (control-flow signal handled by AgentLoop)

---

## Internal Engines (4 total)

| Engine | Tools | Responsibility |
|--------|-------|----------------|
| CommandRunner | run_command | subprocess with timeout, cwd, stdout/stderr capture |
| FileApplier | create_file, edit_file, delete_file | Direct write for create/delete; applier model call for edit. All produce diffs. |
| SearchEngine | search_files | ripgrep subprocess with `--json` output, structured SearchMatch results |
| WebSearchClient | search_web | Tavily Python SDK `search()` call |

---

## API Endpoints (Harness ↔ Agent Service)

### POST /jobs
- **Request**:
  ```json
  { "query": "string", "project_id": "uuid|null", "workspace_id": "uuid|null" }
  ```
- **Response 201**:
  ```json
  { "job_id": "uuid", "task_id": "uuid", "status": "queued" }
  ```
- **Internal flow**:
  1. Call Contexter `POST /tasks {query, projectId}` → receives `{id, query, preferences}`
  2. Create job in JobStore with merged preferences (preferences NOT returned to user)
  3. Launch agent loop as background asyncio task
  4. Return `{job_id, task_id, status: "queued"}`

### GET /jobs/{job_id}/events
- **Response**: SSE stream (`text/event-stream`)
- **Event format** (JobEvent):
  ```json
  {
    "event": "message|tool_call|tool_result|file_change|error|completed|cancelled",
    "timestamp": "2026-06-30T14:30:00Z",
    "call_id": "uuid|null",
    "data": {}
  }
  ```
- **Implementation**: `sse_starlette.EventSourceResponse` wrapping an `asyncio.Queue` per job. Events pushed by the agent loop as they occur.
- **Client disconnect**: Detected via `await request.is_disconnected()`, cleanly stops the generator.

### GET /jobs/{job_id}
- **Response 200**: `{job_id, task_id, status, query, created_at, updated_at, error}`

### GET /jobs
- **Query params**: `skip: int = 0, limit: int = 100`
- **Response 200**: List of `JobStatusResponse`

### POST /jobs/{job_id}/cancel
- **Response 200**: Updated `JobStatusResponse` with `status: "cancelled"`

### POST /jobs/{job_id}/input
- **Request**: `{ "message": "string" }`
- **Response 200**: Updated `JobStatusResponse`
- **Use case**: Send user input when job is in `WAITING_INPUT` state

### GET /health
- **Response**: `{ "status": "ok" }`

---

## Job Lifecycle

```
queued → running → (waiting_input → running)* → completed | failed | cancelled
```

- Every state transition emits an SSE event
- Every tool call emits: `tool_call` event (with args), then `tool_result` event (with result)
- File mutations emit additional `file_change` event with the diff
- `finish_task` emits `completed` event
- Errors emit `error` event and transition to `failed`

---

## Contexter Integration

### Contract (from provided OpenAPI)

**POST /tasks**:
```json
// Request
{ "query": "string", "projectId": "uuid|null" }

// Response 201
{
  "id": "uuid",
  "projectId": "uuid|null",
  "query": "string",
  "preferences": { ... }
}
```

### Integration points
- Called once per job, at `POST /jobs` time
- Agent service acts as Contexter client: `POST /tasks {query, projectId}`
- Preferences are stored in the job record, injected into agent system prompt
- Preferences are NOT returned to the user/harness in any response
- `ContexterClient` interface:
  ```python
  class ContexterClient:
      async def create_task(self, query: str, project_id: str | None = None) -> ContexterTask:
          ...
  ```
- `ContexterTask` maps to Contexter's `Task` schema: `{id, projectId?, query, preferences}`

---

## OpenRouter Integration

### LLM calls (agent reasoning)
- Use LangChain `ChatOpenAI` with OpenRouter base URL:
  ```python
  os.environ["OPENAI_API_KEY"] = os.getenv("OPENROUTER_API_KEY")
  os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
  llm = ChatOpenAI(model="anthropic/claude-sonnet-4.6", temperature=0)
  ```
- Tool calling via `llm.bind_tools(TOOL_DEFINITIONS)`
- Agent loop: invoke LLM with message history + tool results, receive tool calls, execute, feed back

### Applier calls (edit_file only)
- Model: `morph-v3-fast` on OpenRouter
- Prompt format (from Morph docs):
  ```
  <instruction>{instruction}</instruction>
  <code>{initial_code}</code>
  <update>{edit_snippet}</update>
  ```
- Called via OpenRouter API (OpenAI-compatible), not Morph directly
- Zero Data Retention enabled on Morph provider
- Pricing: $0.80/M input tokens, $1.20/M output tokens

---

## SSE Implementation

### Library: sse-starlette
```python
from sse_starlette.sse import EventSourceResponse

@app.get("/jobs/{job_id}/events")
async def stream_events(job_id: str, request: Request):
    queue = job_store.get_event_queue(job_id)
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            event = await queue.get()
            yield {"event": event.event, "data": event.model_dump_json()}
            if event.event in ("completed", "cancelled", "error"):
                break
    return EventSourceResponse(event_generator())
```

### Event queue per job
- Each job gets an `asyncio.Queue` created at job start
- Agent loop pushes events via `queue.put(JobEvent(...))`
- SSE endpoint consumes via `queue.get()`
- On completion/cancel/error, a terminal event is pushed and the generator stops

---

## Docker Architecture

### docker-compose.yml
```yaml
services:
  agent:
    build: ./agent
    ports: ["8000:8000"]
    volumes:
      - workspace-data:/workspace
      - ./agent:/app
    environment:
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - TAVILY_API_KEY=${TAVILY_API_KEY}
      - CONTEXTER_URL=http://contexter:8001
      - WORKSPACE_ROOT=/workspace
    depends_on: [contexter]

  contexter:
    build: ./contexter
    ports: ["8001:8001"]
    volumes:
      - ./contexter:/app

volumes:
  workspace-data:
```

### Agent Dockerfile
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y ripgrep && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Project Structure

```
coding-agent/
├── docker-compose.yml
├── .env
├── agent/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py                 # FastAPI app, route registration
│       ├── config.py               # Settings (env vars, model names, endpoints)
│       ├── api/
│       │   ├── routes.py           # POST /jobs, GET /jobs/{id}/events, etc.
│       │   └── deps.py             # Dependency injection (job_store, contexter_client, llm_client)
│       ├── models/
│       │   ├── job.py               # JobStatus, JobEvent, CreateJobRequest/Response
│       │   ├── tools.py             # Tool arg schemas (RunCommandArgs, EditFileArgs, etc.)
│       │   └── execution.py         # ExecutionResult, BashOutput, SearchMatch, FileChangeResult
│       ├── core/
│       │   ├── agent.py             # AgentLoop: invoke LLM, parse tool calls, dispatch, feed back
│       │   ├── llm.py              # LLMClient: owns ChatOpenAI instance + message history, bind_tools
│       │   ├── executor.py          # ToolExecutor: dispatches tool calls to engines
│       │   └── job_store.py         # In-memory job store with asyncio.Queue per job for SSE
│       ├── engines/
│       │   ├── command_runner.py    # subprocess wrapper with timeout/cwd/capture
│       │   ├── file_applier.py     # create (direct write), edit (Morph via OpenRouter), delete (direct)
│       │   ├── search_engine.py    # ripgrep subprocess with --json, parse to SearchMatch[]
│       │   └── web_search.py       # Tavily SDK wrapper
│       ├── tools/
│       │   ├── definitions.py       # TOOL_DEFINITIONS list for LLM tool-calling
│       │   └── handlers.py          # Tool handler functions (call engine, return result, emit events)
│       ├── clients/
│       │   ├── contexter.py         # ContexterClient: POST /tasks, parse Task response
│       │   └── applier.py           # ApplierClient: format Morph prompt, call OpenRouter
│       └── prompts/
│           └── agent.md             # System prompt for the agent (tool descriptions, conventions)
├── contexter/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       └── ...                     # Existing contexter code
└── README.md
```

### Dependency flow
```
models ← engines ← core ← api ← main
                    ↑
              clients (contexter, applier)
                    ↑
              tools (definitions, handlers)
```

---

## Implementation Phases

### Phase 1: Core Skeleton
1. `config.py` — load env vars (OPENROUTER_API_KEY, TAVILY_API_KEY, CONTEXTER_URL, WORKSPACE_ROOT)
2. `models/job.py` — JobStatus, JobEvent, CreateJobRequest/Response, JobStatusResponse
3. `models/tools.py` — Pydantic schemas for all 7 tool argument types
4. `models/execution.py` — ExecutionResult, SearchMatch, FileChangeResult
5. `core/job_store.py` — in-memory dict of jobs, asyncio.Queue per job for SSE events
6. `api/routes.py` — stub all endpoints, wire SSE endpoint to EventSourceResponse
7. `main.py` — FastAPI app creation, route registration, lifespan startup
8. Dockerfile + docker-compose.yml

### Phase 2: LLM + Agent Loop
1. `core/llm.py` — LLMClient wrapping ChatOpenAI via OpenRouter, bind_tools(TOOL_DEFINITIONS), message history
2. `tools/definitions.py` — JSON tool definitions list matching the 7 tool schemas
3. `core/agent.py` — AgentLoop: invoke LLM → receive tool calls → dispatch to executor → feed back results → repeat until finish_task or error
4. `prompts/agent.md` — system prompt with tool descriptions, `// ... existing code ...` convention, file path conventions
5. Wire `POST /jobs` to: call Contexter → create job → launch AgentLoop as background task

### Phase 3: Engines
1. `engines/command_runner.py` — subprocess.run with timeout, cwd, capture stdout/stderr, return RunCommandResult
2. `engines/file_applier.py`:
   - `create(path, content)` → write file, return diff (full addition)
   - `edit(path, instruction, update)` → read original, call ApplierClient, write merged content, return diff
   - `delete(path)` → remove file, return diff (full removal)
3. `engines/search_engine.py` — run `rg --json {query} {path}` via subprocess, parse JSON lines into SearchMatch[]
4. `engines/web_search.py` — TavilyClient.search(query, max_results), return results list

### Phase 4: Clients
1. `clients/contexter.py` — httpx async POST /tasks, parse ContexterTask
2. `clients/applier.py` — format Morph prompt, call OpenRouter via httpx or ChatOpenAI, return merged content
3. `tools/handlers.py` — for each tool: extract args, call appropriate engine, emit SSE event, return result

### Phase 5: Integration + Docker
1. Wire executor to engines and handlers
2. Wire handlers to SSE event queue
3. Test full flow: create job → Contexter → agent loop → tool calls → SSE events → completion
4. Dockerize both services, test with workspace volume mount
5. End-to-end test with VS Code extension harness

---

## Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| OpenRouter for both LLM and applier | Single API key, unified billing, OpenAI-compatible endpoint |
| LangChain ChatOpenAI (not ChatOpenRouter) | OpenRouter implements OpenAI completions endpoint; ChatOpenAI with base_url override works directly |
| sse-starlette EventSourceResponse | Production-ready SSE for Starlette/FastAPI, handles client disconnects |
| asyncio.Queue per job for SSE | Decouples agent loop from SSE consumer; agent pushes events, SSE endpoint pulls |
| ripgrep with --json flag | Structured machine-readable output, avoids TTY detection issues |
| Morph v3 Fast via OpenRouter | $0.80/M input, 10,500 tokens/sec, 96% accuracy, zero data retention |
| Preferences stored in job, not returned to user | Contexter is internal; preferences injected into agent context only |
| Separate search_files tool (not run_command alias) | OS independence + future semantic search swap without interface change |
| 6 LLM tools, 4 internal engines | Many tools for prompting ergonomics, few engines for maintainability |
| Docker named volume for workspace | Persistent workspace across container restarts, isolated from host |
