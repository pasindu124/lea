"""Everything the brief needs to know about one aircraft (read-only)."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from .. import config, db
from ..rules import deadlines
from ..rules.amm import extract_task_refs

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
        "has_amm_ref": bool(extract_task_refs(f"{row['wo_description'] or ''} {row['wo_actions'] or ''}")),
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


# ------------------------------------------------------ work orders the app treats as closed
def close_cutoff() -> date | None:
    """Deadline cut-off from config: open deferrals that expired before it count as closed."""
    return deadlines._as_date(config.CLOSE_DEADLINES_BEFORE) if config.CLOSE_DEADLINES_BEFORE else None


def closed_by_cutoff(item: dict) -> bool:
    d = item["deferral"]
    cutoff = close_cutoff()
    expires = deadlines._as_date(d["expires_on"]) if d else None
    return bool(cutoff and expires and expires < cutoff)


def completions(reg: str | None = None, wo_numbers: list[int] | None = None) -> dict[int, dict]:
    """Work orders an engineer marked as done in this app, by work-order number."""
    sql, params = "SELECT * FROM work_completion WHERE true", []
    if reg:
        sql += " AND aircraft_reg = %s"
        params.append(reg)
    if wo_numbers is not None:
        sql += " AND wo_number = ANY(%s)"
        params.append(wo_numbers)
    return {r["wo_number"]: r for r in db.query(sql, params)}


def _still_open(items: list[dict], done: dict[int, dict]) -> tuple[list[dict], int]:
    """Drop items done in the app or closed by the cut-off. Returns (open items, number closed by cut-off)."""
    kept, cut = [], 0
    for i in items:
        if i["wo_number"] in done:
            continue
        if closed_by_cutoff(i):
            cut += 1
            continue
        kept.append(i)
    return kept, cut


def log_entry(on: date, note: str) -> str:
    """A work-log entry in the same format as the source data: [20-Nov-2026] text."""
    return f"[{on.strftime('%d-%b-%Y')}] {note}"


_CLOSE_SQL = ("UPDATE work_orders SET wo_state = 'Closed', date_closed = %s, "
              "wo_actions = CASE WHEN coalesce(wo_actions, '') = '' THEN %s ELSE wo_actions || ' | ' || %s END "
              "WHERE wo_number = %s AND wo_state = 'Open'")


def complete_work_order(wo_number: int, note: str, actor: str, on: date) -> dict:
    """Close the work order row: state Closed, close date, the note appended to its work log."""
    row = work_order_full(wo_number)
    entry = log_entry(on, note)
    with db.get_pool().connection() as conn:          # one transaction: both writes or neither
        conn.execute(
            "INSERT INTO work_completion (wo_number, aircraft_reg, completed_by, completed_on, note, prev_state, prev_actions) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (wo_number, row["aircraft_reg"], actor, on, note, row["wo_state"], row["wo_actions"]))
        conn.execute(_CLOSE_SQL, (on, entry, entry, wo_number))
    return completions(wo_numbers=[wo_number])[wo_number]


def undo_completion(wo_number: int) -> dict | None:
    """Put the work order row back as it was before it was marked done."""
    before = completions(wo_numbers=[wo_number]).get(wo_number)
    if not before:
        return None
    with db.get_pool().connection() as conn:
        conn.execute("UPDATE work_orders SET wo_state = %s, date_closed = NULL, wo_actions = %s WHERE wo_number = %s",
                     (before["prev_state"] or "Open", before["prev_actions"], wo_number))
        conn.execute("DELETE FROM work_completion WHERE wo_number = %s", (wo_number,))
    return before


def reapply_completions() -> int:
    """After work orders are reloaded from Excel, close again the ones done in this app.
    A work order the new data already shows as closed is left as the data says."""
    n = 0
    for c in completions().values():
        entry = log_entry(c["completed_on"], c["note"])
        with db.get_pool().connection() as conn:
            # Remember the freshly loaded values, so Undo restores what the data says now.
            conn.execute(
                "UPDATE work_completion c SET prev_state = w.wo_state, prev_actions = w.wo_actions "
                "FROM (SELECT wo_state, wo_actions FROM work_orders WHERE wo_number = %s AND wo_state = 'Open' "
                "ORDER BY id LIMIT 1) w WHERE c.wo_number = %s", (c["wo_number"], c["wo_number"]))
            n += conn.execute(_CLOSE_SQL, (c["completed_on"], entry, entry, c["wo_number"])).rowcount
    return n


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
        "SELECT wo_number, wo_type, wo_state, wo_description, wo_actions, source_row FROM work_orders "
        "WHERE aircraft_reg = %s AND wo_actions IS NOT NULL AND (wo_state = 'Open' OR date_closed >= %s "
        "OR date_opened >= %s) ORDER BY wo_number DESC LIMIT 400",
        (reg, as_of - timedelta(days=2), as_of - timedelta(days=2)))
    done = completions(reg)
    notes = []
    for r in rows:
        c = done.get(r["wo_number"])
        for e in deadlines.recent_entries(r["wo_actions"], as_of):
            text = e["text"][:300] + ("…" if len(e["text"]) > 300 else "")
            note = {"date": e["date"], "text": text, "wo_number": r["wo_number"], "wo_type": r["wo_type"],
                    "wo_state": r["wo_state"],
                    "has_amm_ref": bool(extract_task_refs(f"{r['wo_description'] or ''} {r['wo_actions'] or ''}")),
                    "source": {"file": "Maintenance_History.xlsx", "row": r["source_row"], "wo_number": r["wo_number"]}}
            # The entry this app appended when an engineer marked the work order done.
            if c and e["text"] == " ".join(c["note"].split()) and e["date"] == c["completed_on"].isoformat():
                note["done_by"] = c["completed_by"]
                note["fault"] = _title(r["wo_description"])    # shown as the title, like the open items
            notes.append(note)
    notes.sort(key=lambda n: (n["date"], "done_by" in n, n["wo_number"]), reverse=True)
    return notes[:limit]


def score(items: list[dict], pha: list[dict]) -> int:
    total = sum(SCORE[i["deferral"]["status"]] for i in items if i["deferral"])
    total += len([i for i in items if not i["deferral"]])
    total += sum(PHA_SCORE.get(p["max_severity"], 0) + (20 if p["impact"] == "High" else 0) for p in pha)
    return total


def aircraft_detail(reg: str, as_of: date) -> dict:
    items, closed_cut = _still_open([fault_item(r, as_of) for r in _open_fault_rows(reg)], completions(reg))
    deferrals = sorted([i for i in items if i["deferral"]], key=_sort_key)
    others = [i for i in items if not i["deferral"]]
    pha = pha_cases(reg)
    urgent = urgent_items(items)
    counts = {"open_faults": len(items), "deferrals": len(deferrals), "other_faults": len(others),
              "overdue": sum(1 for i in deferrals if i["deferral"]["status"] == "OVERDUE"),
              "expires_today": sum(1 for i in deferrals if i["deferral"]["status"] == "EXPIRES_TODAY"),
              "expires_soon": sum(1 for i in deferrals if i["deferral"]["status"] == "EXPIRES_SOON"),
              "pha_open": len(pha), "closed_by_cutoff": closed_cut}
    return {"aircraft_reg": reg, "as_of": as_of, "score": score(items, pha), "counts": counts,
            "urgent": urgent, "deferrals": deferrals, "other_faults": others, "pha": pha,
            "aviatar": aviatar_groups(reg, as_of), "notes": recent_notes(reg, as_of)}


def list_aircraft(as_of: date) -> list[dict]:
    """All Air Arabia aircraft with open items: one cheap row each (used for ranking and pickers)."""
    by_reg: dict[str, list[dict]] = {}
    done = completions()
    for row in _open_fault_rows():
        item = fault_item(row, as_of)
        if item["wo_number"] not in done and not closed_by_cutoff(item):
            by_reg.setdefault(row["aircraft_reg"], []).append(item)
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
        row["completion"] = completions(wo_numbers=[wo_number]).get(wo_number)
        d = deadlines.parse_deferral(row["wo_description"], row["wo_actions"], row["date_opened"])
        cutoff = close_cutoff()
        row["closed_by_cutoff"] = bool(row["wo_state"] == "Open" and cutoff and d and d.expires_on
                                       and d.expires_on < cutoff)
        row["cutoff_date"] = cutoff
    return row
