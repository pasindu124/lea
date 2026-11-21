from __future__ import annotations

from .. import db
from ..rules import parts as rules
from ..rules.text import escape_like, norm

MAX_ROWS = 5000
MAX_PARTS = 30
MAX_ROWS_PER_PART = 25


def _where(table_alias_text: str, table_alias_norm: str, query: str) -> tuple[str, list]:
    clauses, params = [], []
    for token in query.split():
        t = escape_like(token.upper())
        n = escape_like(norm(token))
        if len(n) >= 3:
            clauses.append(f"({table_alias_text} LIKE %s OR {table_alias_norm} LIKE %s)")
            params += [f"%{t}%", f"%{n}%"]
        else:
            clauses.append(f"{table_alias_text} LIKE %s")
            params.append(f"%{t}%")
    return " AND ".join(clauses), params


def search(query: str, stores: list[str] | None = None, own_only: bool = False,
           include_unserviceable: bool = True) -> dict:
    query = (query or "").strip()
    if not query:
        return {"query": "", "total_rows": 0, "truncated": False, "parts": [], "displayed_rows": 0}

    where, params = _where("search_text", "search_norm", query)
    rows = db.query(
        f"SELECT source_row, store, location, part_no, serial, description, mat_class, qty, cond, "
        f"order_no, rec_date, owner FROM parts_stock WHERE {where} ORDER BY part_no, store, source_row LIMIT %s",
        params + [MAX_ROWS + 1],
    )
    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]

    summary = rules.summarise(rows)          # verdicts use ALL matches, not the filtered view
    shown = 0
    for part in summary:
        view = [r for r in part["rows"]
                if (not stores or r["store"] in stores)
                and (not own_only or rules.is_own(r["owner"]))
                and (include_unserviceable or rules.is_usable(r["cond"]))]
        part["rows_total"] = len(part["rows"])
        part["rows"] = [{**r, "usable": rules.is_usable(r["cond"]), "own": rules.is_own(r["owner"])}
                        for r in view[:MAX_ROWS_PER_PART]]
        part["rows_shown"] = len(part["rows"])
        part["rows_hidden_by_filters"] = part["rows_total"] - len(view)
        shown += len(view)

    return {"query": query, "total_rows": len(rows), "truncated": truncated,
            "parts_found": len(summary), "parts": summary[:MAX_PARTS], "displayed_rows": shown,
            "source_file": "Inventory_List.xlsx"}
