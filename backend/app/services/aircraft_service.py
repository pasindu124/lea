"""Everything the brief needs to know about one aircraft (read-only)."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from .. import config, db
from ..rules import deadlines

MAX_DESC = 600
MAX_ACTIONS = 900

# How much each kind of item adds to an aircraft's urgency score (used to pick tonight's aircraft).
SCORE = {"OVERDUE": 300, "EXPIRES_TODAY": 600, "EXPIRES_SOON": 200, "OK": 10, "CHECK_SOURCE": 5}
PHA_SCORE = {"Alert": 40, "Warning": 15, "Ok": 2}

_PREFIX_RE = re.compile(r"^\s*ENG ENTRY\s*:\s*", re.IGNORECASE)


def _title(description: str | None) -> str:
    first = (description or "").split(" | ")[0]
    first = _PREFIX_RE.sub("", " ".join(first.split()))
    return first[:160] + ("…" if len(first) > 160 else "")


def _cut(text: str | None, limit: int) -> tuple[str, bool]:
    text = text or ""
    return (text[:limit] + "…", True) if len(text) > limit else (text, False)


def fault_item(row: dict, as_of: date) -> dict[str, Any]:
    """One open work order -> a dict with the parsed deferral (if any) and its source."""
    d = deadlines.parse_deferral(row["wo_description"], row["wo_actions"], row["date_opened"])
    deferral = None
    if d:
        status, days_left = deadlines.classify(d.expires_on, as_of)
        deferral = {**d.to_dict(), "status": status, "days_left": days_left,
                    "status_text": deadlines.status_text(status, days_left)}
    desc, desc_cut = _cut(row["wo_description"], MAX_DESC)
    acts, acts_cut = _cut(row["wo_actions"], MAX_ACTIONS)
    return {
        "wo_number": row["wo_number"], "aircraft_reg": row["aircraft_reg"], "wo_type": row["wo_type"],
        "date_opened": row["date_opened"], "ata": row["ata"], "title": _title(row["wo_description"]),
        "description": desc, "actions": acts, "text_truncated": desc_cut or acts_cut,
        "deferral": deferral,
        "source": {"file": "Maintenance_History.xlsx", "row": row["source_row"], "wo_number": row["wo_number"]},
    }


def _open_fault_rows(reg: str | None = None) -> list[dict]:
    sql = ("SELECT wo_number, aircraft_reg, wo_type, date_opened, ata, wo_description, wo_actions, source_row "
           "FROM work_orders WHERE wo_state = 'Open' AND wo_type IN ('MAREP','PIREP') "
           "AND operator_code = %s AND aircraft_reg LIKE %s")
    params: list[Any] = [config.OWN_OPERATOR, config.OWN_REG_PREFIX + "%"]
    if reg:
        sql += " AND aircraft_reg = %s"
        params.append(reg)
    return db.query(sql + " ORDER BY date_opened DESC, wo_number DESC", params)


def _sort_key(item: dict) -> tuple:
    d = item["deferral"]
    if not d:
        return (9, 0)
    return (deadlines.STATUS_ORDER[d["status"]], d["days_left"] if d["days_left"] is not None else 10**6)


def urgent_items(items: list[dict]) -> list[dict]:
    """Deferrals that are overdue, due today or due soon, most urgent first."""
    flagged = [i for i in items if i["deferral"] and i["deferral"]["status"] in ("OVERDUE", "EXPIRES_TODAY", "EXPIRES_SOON")]
    # Today's deadlines first, then soonest, then overdue (these may be stale records: verify).
    def key(i):
        s = i["deferral"]["status"]
        rank = {"EXPIRES_TODAY": 0, "EXPIRES_SOON": 1, "OVERDUE": 2}[s]
        return (rank, i["deferral"]["days_left"] if s != "OVERDUE" else -i["deferral"]["days_left"], i["wo_number"])
    return sorted(flagged, key=key)


def pha_cases(reg: str) -> list[dict]:
    rows = db.query(
        "SELECT source_row, max_severity, acreg, ata, use_case, title, system, classification, impact, "
        "opened, updated, status, case_link FROM pha_cases WHERE acreg = %s AND status = 'OPEN' "
        "ORDER BY CASE max_severity WHEN 'Alert' THEN 0 WHEN 'Warning' THEN 1 ELSE 2 END, opened DESC", (reg,))
    for r in rows:
        r["source"] = {"file": "PHA case tracking export", "row": r["source_row"]}
    return rows


def aviatar_groups(reg: str, as_of: date, days: int = 3) -> dict:
    start = as_of - timedelta(days=days - 1)
    end = as_of + timedelta(days=1)
    total = db.query_one(
        "SELECT count(*) AS n FROM aviatar_faults WHERE ac = %s AND occurrence >= %s AND occurrence < %s "
        "AND message_type <> 'EMPTY_REPORT'", (reg, start, end))["n"]
    groups = db.query(
        "SELECT message, prio, ata, message_type, count(*) AS n, count(DISTINCT flight) AS flights, "
        "min(occurrence) AS first_seen, max(occurrence) AS last_seen "
        "FROM aviatar_faults WHERE ac = %s AND occurrence >= %s AND occurrence < %s "
        "AND prio IN ('HIGH','MEDIUM') GROUP BY message, prio, ata, message_type "
        "ORDER BY CASE prio WHEN 'HIGH' THEN 0 ELSE 1 END, n DESC LIMIT 12", (reg, start, end))
    for i, g in enumerate(groups, 1):
        g["tag"] = f"AV{i}"
        g["source"] = {"file": "AVIATAR faults export", "aircraft": reg,
                       "from": g["first_seen"], "to": g["last_seen"]}
    return {"window_from": start, "window_to": as_of, "total_messages": total, "groups": groups}


def recent_notes(reg: str, as_of: date, limit: int = 8) -> list[dict]:
    """Derived handover notes: dated work-log entries from the last two days."""
    rows = db.query(
        "SELECT wo_number, wo_type, wo_state, wo_actions, source_row FROM work_orders "
        "WHERE aircraft_reg = %s AND wo_actions IS NOT NULL AND (wo_state = 'Open' OR date_closed >= %s "
        "OR date_opened >= %s) ORDER BY wo_number DESC LIMIT 400",
        (reg, as_of - timedelta(days=2), as_of - timedelta(days=2)))
    notes = []
    for r in rows:
        for e in deadlines.recent_entries(r["wo_actions"], as_of):
            text = e["text"][:300] + ("…" if len(e["text"]) > 300 else "")
            notes.append({"date": e["date"], "text": text, "wo_number": r["wo_number"], "wo_type": r["wo_type"],
                          "source": {"file": "Maintenance_History.xlsx", "row": r["source_row"],
                                     "wo_number": r["wo_number"]}})
    notes.sort(key=lambda n: (n["date"], n["wo_number"]), reverse=True)
    return notes[:limit]


def score(items: list[dict], pha: list[dict]) -> int:
    total = sum(SCORE[i["deferral"]["status"]] for i in items if i["deferral"])
    total += len([i for i in items if not i["deferral"]])
    total += sum(PHA_SCORE.get(p["max_severity"], 0) + (20 if p["impact"] == "High" else 0) for p in pha)
    return total


def aircraft_detail(reg: str, as_of: date) -> dict:
    items = [fault_item(r, as_of) for r in _open_fault_rows(reg)]
    deferrals = sorted([i for i in items if i["deferral"]], key=_sort_key)
    others = [i for i in items if not i["deferral"]]
    pha = pha_cases(reg)
    urgent = urgent_items(items)
    counts = {"open_faults": len(items), "deferrals": len(deferrals), "other_faults": len(others),
              "overdue": sum(1 for i in deferrals if i["deferral"]["status"] == "OVERDUE"),
              "expires_today": sum(1 for i in deferrals if i["deferral"]["status"] == "EXPIRES_TODAY"),
              "expires_soon": sum(1 for i in deferrals if i["deferral"]["status"] == "EXPIRES_SOON"),
              "pha_open": len(pha)}
    return {"aircraft_reg": reg, "as_of": as_of, "score": score(items, pha), "counts": counts,
            "urgent": urgent, "deferrals": deferrals, "other_faults": others, "pha": pha,
            "aviatar": aviatar_groups(reg, as_of), "notes": recent_notes(reg, as_of)}


def list_aircraft(as_of: date) -> list[dict]:
    """All Air Arabia aircraft with open items: one cheap row each (used for ranking and pickers)."""
    by_reg: dict[str, list[dict]] = {}
    for row in _open_fault_rows():
        by_reg.setdefault(row["aircraft_reg"], []).append(fault_item(row, as_of))
    pha_by_reg: dict[str, list[dict]] = {}
    for p in db.query("SELECT acreg, max_severity, impact FROM pha_cases WHERE status = 'OPEN'"):
        pha_by_reg.setdefault(p["acreg"], []).append(p)

    out = []
    for reg in sorted(set(by_reg) | {r for r in pha_by_reg if r.startswith(config.OWN_REG_PREFIX)}):
        items, pha = by_reg.get(reg, []), pha_by_reg.get(reg, [])
        defs = [i for i in items if i["deferral"]]
        dated = [i["deferral"] for i in defs if i["deferral"]["days_left"] is not None]
        nearest = min(dated, key=lambda d: d["days_left"]) if dated else None
        out.append({
            "aircraft_reg": reg, "score": score(items, pha),
            "open_faults": len(items), "deferrals": len(defs),
            "overdue": sum(1 for i in defs if i["deferral"]["status"] == "OVERDUE"),
            "expires_today": sum(1 for i in defs if i["deferral"]["status"] == "EXPIRES_TODAY"),
            "expires_soon": sum(1 for i in defs if i["deferral"]["status"] == "EXPIRES_SOON"),
            "pha_open": len(pha),
            "nearest_days_left": nearest["days_left"] if nearest else None,
        })
    out.sort(key=lambda a: (-a["score"], a["aircraft_reg"]))
    return out


def work_order_full(wo_number: int) -> dict | None:
    row = db.query_one(
        "SELECT wo_number, aircraft_reg, operator_code, wo_type, wo_state, date_opened, date_closed, ata, "
        "wo_description, wo_actions, source_row FROM work_orders WHERE wo_number = %s ORDER BY id LIMIT 1", (wo_number,))
    if row:
        row["source"] = {"file": "Maintenance_History.xlsx", "row": row["source_row"], "wo_number": wo_number}
    return row
