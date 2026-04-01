# NanoClaw — FastAPI Agent Service Plan

## Context

The NFL platform has three services: `nfl-data-platform` (:8000), `nfl-model-platform` (:8080), and `nfl-dashboard` (:3000). This service, **NanoClaw**, runs on **:8002** as a standalone FastAPI agent that sits between the dashboard and the two backend APIs, using Claude tool-calling to route natural-language queries intelligently. The dashboard's NanoClaw chat page stub (`POST /nanoclaw/chat`) will be re-pointed to NanoClaw's `/chat` endpoint.

---

## Feedback: What's Good

- **FastAPI** — correct, matches the rest of the stack
- **Claude API tool calling** — the right pattern; avoids brittle regex routing
- **YAML tool registry** — good for configurability; models expose `/schema` endpoints so tools can even be self-describing
- **SQLite conversation history** — dashboard sends full message history on each request, so this works well as a backing store
- **Supervised mode** — essential: draft-optimizer is the one model with async jobs, making it the clearest candidate for confirmation-before-run
- **Response composer with viz specs** — dashboard has SHAP viz stubs and chart pages already waiting for a structured payload

---

## Feedback: What Needs Adjusting

### 1. Naming — `nanoclaw` confirmed, but watch the directory collision
The `nanoclaw/` directory in this repo is an **unrelated Claude Code agent runtime framework** — the new service must live in a different directory (e.g. `nanoclaw_service/` or `src/`). The dashboard's existing stub routes to `/nullclaw/chat` — that will need to be updated to point to NanoClaw's endpoint on `:8002`.

### 2. Port — NanoClaw runs on :8002
```
nfl-data-platform  (:8000)
nfl-model-platform (:8080)
nfl-dashboard      (:3000)
nanoclaw           (:8002)  ← new
```
Standalone service, no changes needed to either backend.

### 3. SQLite alone is suboptimal — use Redis + SQLite hybrid
FTS5 is overkill for simple conversation retrieval. However, SQLite alone is also not ideal for hot session state. The model platform already runs Redis (for caching + async job tracking), so NanoClaw can reuse that instance:

- **Redis** — hot session memory: last N messages (per session key), `awaiting_confirmation` state, agent turn state. Use TTL (e.g. 24h) for auto-expiry of idle sessions.
- **SQLite** — cold/durable log: append-only conversation record for audit, replay, or future search.

> ⚠️ **Note on RedisGraph**: RedisGraph was deprecated and removed in Redis 7.x. Do not use it. For graph-like memory queries, FTS5 on SQLite is the right tool — but only if you actually build that feature.

**Concrete split:**
| What | Where | Why |
|---|---|---|
| Active session messages (last N) | Redis `LIST` with LPUSH/LTRIM | Sub-millisecond read, no DB overhead per turn |
| `awaiting_confirmation` state | Redis `HASH` | Ephemeral, should auto-expire with session |
| Full conversation history | SQLite `messages` table | Durable, queryable, no Redis memory cost for old data |

### 4. Streaming — dashboard expects a live "thinking" indicator
The dashboard has an **animated thinking indicator**, which strongly implies SSE or streaming. Plan for `text/event-stream` on `POST /nanoclaw/chat` so the dashboard can render partial output. A non-streaming fallback is acceptable for v1, but note it as a known gap.

### 5. Schema-driven tools — use `/schema` endpoints
Both APIs expose `GET /<model>/schema` endpoints. Rather than hand-coding YAML for every model input field, the tool registry should fetch schemas at startup and build Claude tool definitions dynamically. The YAML registry then only needs to list the endpoint URL + metadata (cost tier, supervised flag).

---

## Recommended Architecture

```
nanoclaw/
├── main.py                  # FastAPI app, mounts /nanoclaw router
├── config.yaml              # Providers (data-platform, model-platform), agent settings
├── agent/
│   ├── core.py              # Agentic loop: send to Claude, execute tools, loop until final response
│   └── tool_executor.py     # Dispatches tool calls to HTTP client
├── tools/
│   ├── registry.py          # Loads YAML + fetches /schema from model platform at startup
│   └── definitions.py       # Converts provider config → Claude tool JSON schemas
├── providers/
│   └── http_client.py       # Async httpx client, one instance per provider base URL
├── memory/
│   ├── redis_store.py       # Hot session cache: LPUSH/LTRIM message lists, confirmation state hash
│   └── sqlite_store.py      # Cold durable log: sessions + messages tables
├── composer/
│   └── response.py          # Maps raw API results → {text, visualizations: [{type, data, config}]}
└── routers/
    └── chat.py              # POST /nanoclaw/chat → runs agent loop, returns NanoClawResponse
```

### `config.yaml` structure
```yaml
providers:
  data_lake:
    base_url: http://localhost:8000
    timeout: 10
  model_platform:
    base_url: http://localhost:8080   # nfl-model-platform
    timeout: 30

tools:
  - name: get_players
    provider: data_lake
    method: GET
    path: /players
    description: "List players from the data lake with optional filters"
    supervised: false
  - name: run_sql_query
    provider: data_lake
    method: POST
    path: /query
    description: "Run a DuckDB SQL query against the data lake"
    supervised: false
  - name: get_graph_roster
    provider: data_lake
    method: GET
    path: /graph/team/{abbr}/roster
    description: "Get team roster from Neo4j graph"
    supervised: false
  - name: player_projection
    provider: model_platform
    method: POST
    path: /player-projection/predict
    schema_path: /player-projection/schema
    description: "Predict player performance projection"
    supervised: false
  - name: draft_optimizer
    provider: model_platform
    method: POST
    path: /draft-optimizer/predict
    schema_path: /draft-optimizer/schema
    description: "Run draft optimization (expensive)"
    supervised: true   # ← ask before running
  # ... remaining 5 models

agent:
  model: claude-opus-4-6
  system_prompt: |
    You are NanoClaw, an NFL analytics assistant. You have access to a data lake
    (players, teams, SQL queries, graph traversal) and 7 ML models. Use tools to
    answer questions precisely. For supervised tools, describe what you intend to
    run and wait for confirmation before executing.
  max_tool_rounds: 5
```

### `POST /nanoclaw/chat` contract
```
Request:
{
  "session_id": "uuid",
  "messages": [{"role": "user"|"assistant", "content": "..."}]
}

Response:
{
  "message": {"role": "assistant", "content": "..."},
  "visualizations": [
    {"type": "bar"|"line"|"table"|"shap", "title": "...", "data": [...], "config": {...}}
  ],
  "tool_calls_made": ["player_projection", "get_players"],
  "awaiting_confirmation": null | {"tool": "draft_optimizer", "args": {...}}
}
```

---

## Implementation Order

1. `main.py` + `config.yaml` — FastAPI shell, health endpoint
2. `providers/http_client.py` — async httpx client factory
3. `tools/registry.py` — load YAML + fetch `/schema` endpoints, build Claude tool definitions
4. `memory/redis_store.py` + `memory/sqlite_store.py` — Redis hot cache + SQLite durable log
5. `agent/core.py` + `tool_executor.py` — agentic loop with supervised-mode check
6. `composer/response.py` — map raw results to visualization specs
7. `routers/chat.py` — wire everything together

---

## Verification

1. `uvicorn nanoclaw.main:app --port 8002` starts cleanly
2. `GET /health` returns `{"status": "ok"}`
3. `GET /nanoclaw/tools` returns the full tool list with schema-fetched definitions
4. `POST /nanoclaw/chat` with `{"session_id": "test", "messages": [{"role": "user", "content": "List all quarterbacks"}]}` returns a response with `tool_calls_made: ["get_players"]`
5. A supervised tool call returns `awaiting_confirmation` instead of executing
6. Conversation history persists to SQLite and is retrievable
