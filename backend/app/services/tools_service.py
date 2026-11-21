from __future__ import annotations

from datetime import date

from .. import db
from ..rules import tools as rules
from .parts_service import _where

MAX_ROWS = 300


def search(query: str, as_of: date, where: str | None = None, limit: int = MAX_ROWS) -> dict:
    query = (query or "").strip()
    if not query:
        return {"query": "", "rows": [], "total": 0, "truncated": False}
    clause, params = _where("search_text", "search_norm", query)
    extra = ""
    if where == "line":
        extra, params = " AND store = %s", params + ["LINEWH"]
    elif where == "main":
        extra, params = " AND store = %s", params + ["SHJMAINW"]
    rows = db.query(
        f"SELECT source_file, source_row, part_no, serial, description, tool_id, mc, co, received, expires, "
        f"store, location, qty FROM tools WHERE {clause}{extra} ORDER BY part_no, source_row LIMIT %s",
        params + [limit + 1],
    )
    truncated = len(rows) > limit
    placeholder_raw = db.get_meta("tools_placeholder_expiry")
    placeholder = date.fromisoformat(placeholder_raw) if placeholder_raw else None
    summary = rules.summarise(rows[:limit], as_of, placeholder)
    return {"query": query, "rows": summary, "total": len(summary), "truncated": truncated,
            "placeholder_expiry": placeholder.isoformat() if placeholder else None}
