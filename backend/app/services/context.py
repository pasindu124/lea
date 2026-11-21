"""Shared helpers: the 'as of' date and the audit log."""
from __future__ import annotations

import json
from datetime import date, datetime

from .. import config, db


def resolve_as_of(override: str | None = None) -> date:
    """Priority: request override > AS_OF_DATE setting > newest record in the data > today."""
    for candidate in (override, config.AS_OF_DATE, db.get_meta("as_of_default")):
        if candidate:
            try:
                return datetime.strptime(str(candidate)[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
    return date.today()


def log(actor: str | None, action: str, details: dict | None = None, sources: list | None = None) -> None:
    db.execute(
        "INSERT INTO audit_log (actor, action, details, sources) VALUES (%s, %s, %s::jsonb, %s::jsonb)",
        ((actor or "unknown").strip() or "unknown", action,
         json.dumps(details or {}, default=str), json.dumps(sources or [], default=str)),
    )


def recent_log(limit: int = 100) -> list[dict]:
    return db.query("SELECT id, ts, actor, action, details, sources FROM audit_log ORDER BY id DESC LIMIT %s", (limit,))
