# NanoClaw: An Agentic AI for NFL Analytics

**NanoClaw** is a sophisticated, conversational AI agent designed to make complex NFL data and machine learning models accessible through natural language. It serves as the intelligent core of the NFL Analytics Platform, translating user questions into actionable queries and presenting the results in a clear, digestible format.

> **The Goal:** To empower analysts, fans, and developers to unlock insights from a vast NFL data lake without writing a single line of SQL or code. A user can simply ask, "Who were the top 5 fastest ball carriers last season?" and receive a precise, data-driven answer.

---

## The Agentic Approach: How It Works

NanoClaw is not a monolithic application; it is a lightweight, stateless FastAPI service that orchestrates a distributed system of data and model APIs. Its intelligence lies in its ability to reason about a user's intent and decompose a complex question into a sequence of smaller, solvable steps.

For a visual representation of the system, please see the [**Agent Architecture Diagram**](files/agent_diagram.md).

The core of the agent operates in a loop:

1.  **Understand the Goal**: A user's prompt is received from the dashboard.
2.  **Plan the Attack**: The prompt is sent to a Large Language Model (Claude), which, instead of answering directly, selects the appropriate tool(s) from its registry to gather the required data. For example, it might choose `get_players` to find player IDs and then `get_player_stats` to retrieve their metrics.
3.  **Execute and Observe**: The agent executes these tool calls against the backend APIs, which handle the heavy lifting of querying the data lake (DuckDB) and graph database (Neo4j).
4.  **Synthesize and Respond**: The results from the tool calls are collected and sent back to the LLM in the next turn. The model then either decides to call another tool for more information or, if the goal is met, synthesizes a final, human-readable answer.

---

## Key Technical Innovations

This project showcases several advanced software architecture patterns for building robust, production-ready AI agents.

### 1. Dynamic, Schema-Driven Tooling
The agent's capabilities are not static. At startup, it dynamically discovers available tools by introspecting the OpenAPI schemas of the downstream `nfl-data-platform` and `nfl-model-platform` APIs.

> **Why it matters:** This makes the system incredibly extensible. A new API endpoint on the backend can be made available to the agent instantly, without requiring any changes to the agent's own code. It simply learns on the fly.

### 2. Hybrid Memory for Performance and Persistence
Conversational context is managed through a two-tiered memory system to optimize for both speed and durability.

-   **Redis (Hot Storage)**: Active session data, like recent messages and pending user confirmations, is kept in an in-memory Redis cache for millisecond-level access.
-   **SQLite (Cold Storage)**: The complete history of every conversation is logged to a SQLite database, providing a durable, auditable record for analysis and fine-tuning.

### 3. Supervised Execution for Safety and Cost Control
Not all tools are created equal. Computationally expensive or state-changing operations can be flagged as `supervised`.

> **How it works:** If the LLM decides to use a supervised tool, the agent pauses its execution loop and asks the user for explicit confirmation before proceeding. This provides a critical human-in-the-loop safeguard.

### 4. Decoupled, Composable Response Payloads
The agent's final output is a structured JSON object that separates the textual answer from data intended for visualization. This allows the frontend dashboard to cleanly render tables, charts, and graphs without needing to parse the LLM's text response.

---

## Getting Started

A concise guide for developers to run the service locally.

-   **Prerequisites**: Python 3.9+, Docker, and an `ANTHROPIC_API_KEY`.
-   **Run Dependencies**: `pip install -r requirements.txt` and start a Neo4j instance with Docker.
-   **Launch Agent**: `uvicorn nanoclaw_service.main:app --reload`

*(This assumes the `nfl-data-platform` (:8000) and `nfl-model-platform` (:8080) services are already running).*

