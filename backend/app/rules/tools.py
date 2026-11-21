"""Tool availability and calibration status (plain code, no AI).

FINDING: in the supplied export almost every tool has Expires = 2026-11-20, which is
the export date itself. That cannot be a real calibration date, so when the most
common expiry date covers >= 90% of tools we call it a placeholder and report
calibration as UNVERIFIED instead of flagging thousands of tools as expired.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .. import config

PLACEHOLDER_SHARE = 0.90


def detect_placeholder_expiry(expiry_dates: list[date | None]) -> date | None:
    """The most common expiry date if it covers >= 90% of tools that have one, else None."""
    dated = [d for d in expiry_dates if d is not None]
    if not dated:
        return None
    counts: dict[date, int] = {}
    for d in dated:
        counts[d] = counts.get(d, 0) + 1
    top, n = max(counts.items(), key=lambda kv: kv[1])
    return top if n / len(dated) >= PLACEHOLDER_SHARE else None


def calibration_status(expires: date | None, as_of: date, placeholder: date | None) -> dict[str, str]:
    if expires is None:
        return {"status": "NO_EXPIRY", "tone": "neutral",
                "why": "No expiry date is recorded. This may mean no calibration is needed. Confirm with the tool store."}
    if placeholder is not None and expires == placeholder:
        return {"status": "UNVERIFIED", "tone": "caution",
                "why": f"The expiry date {expires} is the same for almost every tool in the export, so it looks like "
                       f"a placeholder and not a real calibration date. Check the calibration label on the tool."}
    days = (expires - as_of).days
    if days < 0:
        return {"status": "EXPIRED", "tone": "danger", "why": f"Calibration expired on {expires}."}
    if days <= 30:
        return {"status": "EXPIRES_SOON", "tone": "caution", "why": f"Calibration expires on {expires} ({days} days)."}
    return {"status": "IN_DATE", "tone": "ok", "why": f"Calibration valid until {expires}."}


def summarise(rows: list[dict[str, Any]], as_of: date, placeholder: date | None) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        cal = calibration_status(r["expires"], as_of, placeholder)
        where = "line" if r["store"] == config.TOOL_LINE_STORE else "main" if r["store"] == config.TOOL_MAIN_STORE else "other"
        out.append({**r, "where": where, "calibration": cal})
    order = {"line": 0, "main": 1, "other": 2}
    out.sort(key=lambda x: (order[x["where"]], x["part_no"] or "", x["source_row"]))
    return out
