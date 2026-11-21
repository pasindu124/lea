"""Spare-parts availability verdicts (plain code, no AI)."""
from __future__ import annotations

from typing import Any

from .. import config

VERDICTS = {
    "AVAILABLE_LINE": ("Available at line store", "ok",
                       f"Serviceable stock owned by {config.OWN_OPERATOR} is in store {config.LINE_STORE}."),
    "MAIN_ONLY": ("Only at main store, needs transfer", "caution",
                  f"No usable {config.OWN_OPERATOR} stock in {config.LINE_STORE}, but {config.MAIN_STORE} has some."),
    "OTHER_OWNER": ("Only owned by another operator", "caution",
                    f"Usable stock exists but is not owned by {config.OWN_OPERATOR}. Ask Stores before using it."),
    "UNSERVICEABLE_ONLY": ("Only unserviceable stock", "danger",
                           "Every matching item carries an unserviceable condition code."),
}
_ORDER = {k: i for i, k in enumerate(VERDICTS)}


def is_usable(cond: str | None) -> bool:
    return (cond or "").strip().upper() not in config.UNSERVICEABLE_CODES


def is_own(owner: str | None) -> bool:
    return (owner or "").strip().upper() == config.OWN_OPERATOR


def summarise(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per part number with quantities and a verdict (rows must NOT be pre-filtered)."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["part_no"], []).append(r)

    out = []
    for part_no, g in groups.items():
        line = sum(float(r["qty"] or 0) for r in g if is_usable(r["cond"]) and is_own(r["owner"]) and r["store"] == config.LINE_STORE)
        main = sum(float(r["qty"] or 0) for r in g if is_usable(r["cond"]) and is_own(r["owner"]) and r["store"] == config.MAIN_STORE)
        other = sum(float(r["qty"] or 0) for r in g if is_usable(r["cond"]) and not is_own(r["owner"]))
        unserv = sum(float(r["qty"] or 0) for r in g if not is_usable(r["cond"]))
        if line > 0:
            verdict = "AVAILABLE_LINE"
        elif main > 0:
            verdict = "MAIN_ONLY"
        elif other > 0:
            verdict = "OTHER_OWNER"
        else:
            verdict = "UNSERVICEABLE_ONLY"
        label, tone, why = VERDICTS[verdict]
        out.append({
            "part_no": part_no, "description": g[0]["description"],
            "line_usable": line, "main_usable": main, "other_owner_usable": other, "unserviceable": unserv,
            "verdict": verdict, "label": label, "tone": tone, "why": why,
            "rows": g,
        })
    out.sort(key=lambda x: (_ORDER[x["verdict"]], x["part_no"] or ""))
    return out
