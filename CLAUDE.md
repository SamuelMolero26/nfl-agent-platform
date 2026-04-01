# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NFL Agent Platform — a conversational AI system for NFL analytics. Users interact with Claude (claude-opus-4-6) via a chat API; Claude calls registered tools to query a DuckDB/Parquet data lake, Neo4j graph, and ML models.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start Neo4j (required for graph features)
docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5

# Run the API server (port 8002)
uvicorn nanoclaw_service.main:app --reload

# Or via Docker Compose
docker compose up

# Run data ingestion pipeline
python ingestion/pipeline.py

# Build Neo4j graph
python graph/builder.py
```

## Architecture

**Data layer (medallion):** Raw sources → staged Parquet files → curated master/feature tables. DuckDB registers curated Parquet files dynamically as SQL tables at startup.

**Agent service (`nanoclaw_service/`):**
- `main.py` — FastAPI app, port 8002
- `agent/core.py` — Agentic loop: call Claude → parse tool calls → execute → repeat (max 6 rounds by default)
- `tools/registry.py` — Dynamic tool registration; tools are registered with JSON schemas
- `tools/definitions.py` — Tool definitions; some tools are flagged `supervised=True`, requiring user confirmation before execution (stored in Redis)
- `routers/chat.py` — `/chat` endpoint, session and message management
- `memory/` — Redis (primary) or SQLite (fallback) for conversation state and pending confirmations
- `composer/` — Response composition and visualizations

**Configuration:** `nanoclaw_service/config.yaml` controls Claude model, max tool rounds, providers, and tool supervision settings. Requires `.env` with `ANTHROPIC_API_KEY`.

**Key design patterns:**
- Supervised tools pause the agentic loop and store a pending confirmation in Redis; the client polls or confirms before execution resumes
- Player ID resolution uses fuzzy matching (`nanoclaw_service/player_id_resolver.py`) to map names to canonical IDs across data sources
- DuckDB tables are auto-registered from the curated directory on startup — add new Parquet files there to make them queryable

# context-mode — MANDATORY routing rules

You have context-mode MCP tools available. These rules are NOT optional — they protect your context window from flooding. A single unrouted command can dump 56 KB into context and waste the entire session.

## BLOCKED commands — do NOT attempt these

### curl / wget — BLOCKED
Any Bash command containing `curl` or `wget` is intercepted and replaced with an error message. Do NOT retry.
Instead use:
- `ctx_fetch_and_index(url, source)` to fetch and index web pages
- `ctx_execute(language: "javascript", code: "const r = await fetch(...)")` to run HTTP calls in sandbox

### Inline HTTP — BLOCKED
Any Bash command containing `fetch('http`, `requests.get(`, `requests.post(`, `http.get(`, or `http.request(` is intercepted and replaced with an error message. Do NOT retry with Bash.
Instead use:
- `ctx_execute(language, code)` to run HTTP calls in sandbox — only stdout enters context

### WebFetch — BLOCKED
WebFetch calls are denied entirely. The URL is extracted and you are told to use `ctx_fetch_and_index` instead.
Instead use:
- `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` to query the indexed content

## REDIRECTED tools — use sandbox equivalents

### Bash (>20 lines output)
Bash is ONLY for: `git`, `mkdir`, `rm`, `mv`, `cd`, `ls`, `npm install`, `pip install`, and other short-output commands.
For everything else, use:
- `ctx_batch_execute(commands, queries)` — run multiple commands + search in ONE call
- `ctx_execute(language: "shell", code: "...")` — run in sandbox, only stdout enters context

### Read (for analysis)
If you are reading a file to **Edit** it → Read is correct (Edit needs content in context).
If you are reading to **analyze, explore, or summarize** → use `ctx_execute_file(path, language, code)` instead. Only your printed summary enters context. The raw file content stays in the sandbox.

### Grep (large results)
Grep results can flood context. Use `ctx_execute(language: "shell", code: "grep ...")` to run searches in sandbox. Only your printed summary enters context.

## Tool selection hierarchy

1. **GATHER**: `ctx_batch_execute(commands, queries)` — Primary tool. Runs all commands, auto-indexes output, returns search results. ONE call replaces 30+ individual calls.
2. **FOLLOW-UP**: `ctx_search(queries: ["q1", "q2", ...])` — Query indexed content. Pass ALL questions as array in ONE call.
3. **PROCESSING**: `ctx_execute(language, code)` | `ctx_execute_file(path, language, code)` — Sandbox execution. Only stdout enters context.
4. **WEB**: `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` — Fetch, chunk, index, query. Raw HTML never enters context.
5. **INDEX**: `ctx_index(content, source)` — Store content in FTS5 knowledge base for later search.

## Subagent routing

When spawning subagents (Agent/Task tool), the routing block is automatically injected into their prompt. Bash-type subagents are upgraded to general-purpose so they have access to MCP tools. You do NOT need to manually instruct subagents about context-mode.

## Output constraints

- Keep responses under 500 words.
- Write artifacts (code, configs, PRDs) to FILES — never return them as inline text. Return only: file path + 1-line description.
- When indexing content, use descriptive source labels so others can `ctx_search(source: "label")` later.

## ctx commands

| Command | Action |
|---------|--------|
| `ctx stats` | Call the `ctx_stats` MCP tool and display the full output verbatim |
| `ctx doctor` | Call the `ctx_doctor` MCP tool, run the returned shell command, display as checklist |
| `ctx upgrade` | Call the `ctx_upgrade` MCP tool, run the returned shell command, display as checklist |
