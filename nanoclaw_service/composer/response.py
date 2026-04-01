from __future__ import annotations

# Maps tool names to the visualization type they produce.
# The dashboard uses this to decide which chart component to render.
_TOOL_VIZ_TYPE: dict[str, str] = {
    # Leaderboards → bar charts
    "leaderboard_athletic": "bar",
    "leaderboard_production": "bar",
    "leaderboard_draft_value": "bar",
    # Player scores/projections → bar (SHAP breakdown)
    "player_projection_predict": "shap",
    "positional_flexibility_predict": "bar",
    "career_simulator_predict": "line",
    "roster_fit_predict": "bar",
    "health_analyzer_predict": "bar",
    "team_diagnosis_predict": "bar",
    # Tabular data
    "list_players": "table",
    "search_players": "table",
    "get_player_profile": "table",
    "get_player_athletic": "table",
    "get_player_production": "table",
    "get_player_durability": "table",
    "get_player_draft_value": "table",
    "get_team_stats": "table",
    "get_team_draft_history": "table",
    "get_team_roster_graph": "table",
    "run_sql_query": "table",
    # Graph snapshots → no chart (text only)
    "get_player_graph_neighbors": "graph",
    "get_player_career_path": "graph",
    "get_college_pipeline": "graph",
}


def compose(tool_calls_made: list[str], raw_results: list[dict]) -> list[dict]:
    """
    Map raw tool results to visualization specs the dashboard can render.
    Returns a list of visualization objects, one per tool result that has
    a known visualization type.
    """
    visualizations = []
    allowed_tools = set(tool_calls_made)

    for entry in raw_results:
        tool_name = entry.get("tool", "")
        if allowed_tools and tool_name not in allowed_tools:
            continue
        result = entry.get("result", {})
        viz_type = _TOOL_VIZ_TYPE.get(tool_name)

        if viz_type is None:
            continue  # tool produces no chart (health checks, schema fetches, etc.)

        viz = _build_viz(tool_name, viz_type, result)
        if viz:
            visualizations.append(viz)

    return visualizations


def _build_viz(tool_name: str, viz_type: str, result: dict) -> dict | None:
    if viz_type == "table":
        return _table_viz(tool_name, result)
    if viz_type == "bar":
        return _bar_viz(tool_name, result)
    if viz_type == "line":
        return _line_viz(tool_name, result)
    if viz_type == "shap":
        return _shap_viz(tool_name, result)
    if viz_type == "graph":
        return _graph_viz(tool_name, result)
    return None


# ── Visualization builders ───────────────────────────────────────────────────


def _table_viz(tool_name: str, result: dict) -> dict | None:
    # Most list endpoints return {"data": [...]} or a plain list
    rows = (
        result.get("data")
        or result.get("players")
        or result.get("results")
        or result.get("rows")
    )
    if isinstance(result, list):
        rows = result
    if not rows:
        return None
    return {
        "type": "table",
        "title": _tool_title(tool_name),
        "data": rows,
        "config": {"columns": list(rows[0].keys()) if rows else []},
    }


def _bar_viz(tool_name: str, result: dict) -> dict | None:
    # Model predict endpoints return {"score": float, "confidence": float, ...}
    # Leaderboards return a list of {name, score}
    items = result.get("data") or result.get("rankings") or result.get("scores")
    if isinstance(result, list):
        items = result

    if items and isinstance(items, list):
        return {
            "type": "bar",
            "title": _tool_title(tool_name),
            "data": items,
            "config": {
                "x": _guess_label_key(items[0]),
                "y": _guess_value_key(items[0]),
            },
        }

    # Single prediction result — bar of feature scores
    score_fields = {k: v for k, v in result.items() if isinstance(v, (int, float))}
    if score_fields:
        data = [{"metric": k, "value": v} for k, v in score_fields.items()]
        return {
            "type": "bar",
            "title": _tool_title(tool_name),
            "data": data,
            "config": {"x": "metric", "y": "value"},
        }
    return None


def _line_viz(tool_name: str, result: dict) -> dict | None:
    # Career simulator returns projected seasons as a time series
    series = result.get("trajectory") or result.get("seasons") or result.get("data")
    if not series:
        return None
    return {
        "type": "line",
        "title": _tool_title(tool_name),
        "data": series,
        "config": {"x": "season", "y": "projected_value"},
    }


def _shap_viz(tool_name: str, result: dict) -> dict | None:
    shap_values = result.get("shap_values") or result.get("feature_importance")
    if not shap_values:
        return _bar_viz(tool_name, result)  # fallback to bar if no SHAP
    data = [{"feature": k, "impact": v} for k, v in shap_values.items()]
    return {
        "type": "shap",
        "title": _tool_title(tool_name),
        "data": sorted(data, key=lambda x: abs(x["impact"]), reverse=True),
        "config": {"x": "impact", "y": "feature"},
    }


def _graph_viz(tool_name: str, result: dict) -> dict | None:
    nodes = result.get("nodes") or []
    edges = result.get("edges") or result.get("relationships") or []
    if not nodes:
        return None
    return {
        "type": "graph",
        "title": _tool_title(tool_name),
        "data": {"nodes": nodes, "edges": edges},
        "config": {},
    }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _tool_title(tool_name: str) -> str:
    return tool_name.replace("_", " ").title()


def _guess_label_key(row: dict) -> str:
    if not row:
        return "label"
    for key in ("name", "player", "team", "label", "position"):
        if key in row:
            return key
    return list(row.keys())[0]


def _guess_value_key(row: dict) -> str:
    if not row:
        return "value"
    for key in ("score", "value", "rating", "projection", "count"):
        if key in row:
            return key
    # pick first numeric field
    for k, v in row.items():
        if isinstance(v, (int, float)):
            return k
    return list(row.keys())[-1]
