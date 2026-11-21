"""Shift roster and the per-engineer brief."""
from __future__ import annotations

from datetime import date
from typing import Any

from .. import config, db
from ..rules.roster import snake_assign
from . import aircraft_service, context


def get_roster(shift_date: date) -> dict[str, str]:
    rows = db.query("SELECT aircraft_reg, engineer FROM roster WHERE shift_date = %s", (shift_date,))
    return {r["aircraft_reg"]: r["engineer"] for r in rows}


def auto_roster(shift_date: date, as_of: date, n: int | None = None, engineers: list[str] | None = None) -> dict[str, str]:
    engineers = engineers or config.ENGINEERS
    everything = aircraft_service.list_aircraft(as_of)
    # Aircraft with a deadline today or soon are always on tonight's list, then the highest scores fill the rest.
    critical = [a for a in everything if a["expires_today"] or a["expires_soon"]]
    rest = [a for a in everything if a not in critical]
    limit = max(n or config.AIRCRAFT_PER_SHIFT, len(critical))
    ranked = [a["aircraft_reg"] for a in (critical + rest)[:limit]]
    mapping = snake_assign(ranked, engineers)
    with db.get_pool().connection() as conn:
        conn.execute("DELETE FROM roster WHERE shift_date = %s", (shift_date,))
        for reg, eng in mapping.items():
            conn.execute("INSERT INTO roster (shift_date, aircraft_reg, engineer) VALUES (%s, %s, %s)",
                         (shift_date, reg, eng))
    return mapping


def set_assignment(shift_date: date, reg: str, engineer: str | None) -> None:
    if engineer:
        db.execute(
            "INSERT INTO roster (shift_date, aircraft_reg, engineer) VALUES (%s, %s, %s) "
            "ON CONFLICT (shift_date, aircraft_reg) DO UPDATE SET engineer = EXCLUDED.engineer",
            (shift_date, reg, engineer))
    else:
        db.execute("DELETE FROM roster WHERE shift_date = %s AND aircraft_reg = %s", (shift_date, reg))


def _acks(wo_numbers: list[int]) -> dict[int, dict]:
    if not wo_numbers:
        return {}
    rows = db.query(
        "SELECT DISTINCT ON ((details->>'wo_number')) (details->>'wo_number')::bigint AS wo, actor, ts, "
        "details->>'note' AS note FROM audit_log WHERE action = 'ack_flag' "
        "AND (details->>'wo_number')::bigint = ANY(%s) ORDER BY (details->>'wo_number'), id DESC", (wo_numbers,))
    return {r["wo"]: {"actor": r["actor"], "ts": r["ts"], "note": r["note"]} for r in rows}


def _flag(item: dict) -> dict:
    d = item["deferral"]
    return {"aircraft_reg": item["aircraft_reg"], "wo_number": item["wo_number"], "title": item["title"],
            "status": d["status"], "status_text": d["status_text"], "days_left": d["days_left"],
            "expires_on": d["expires_on"], "rule": d["rule"], "source": item["source"]}


def build_brief(as_of: date, shift_date: date | None = None) -> dict[str, Any]:
    shift_date = shift_date or as_of
    roster = get_roster(shift_date)
    created = False
    if not roster:
        roster, created = auto_roster(shift_date, as_of), True

    details = {reg: aircraft_service.aircraft_detail(reg, as_of) for reg in roster}
    engineers = []
    names = list(config.ENGINEERS) + [e for e in sorted(set(roster.values())) if e not in config.ENGINEERS]
    for name in names:
        regs = sorted((r for r, e in roster.items() if e == name), key=lambda r: -details[r]["score"])
        if not regs and name not in config.ENGINEERS:
            continue
        aircraft = [details[r] for r in regs]
        flags = sorted((f for a in aircraft for f in a["urgent"]), key=aircraft_service_flag_key)
        engineers.append({
            "name": name, "aircraft": aircraft,
            "counts": {k: sum(a["counts"][k] for a in aircraft)
                       for k in ("open_faults", "deferrals", "overdue", "expires_today", "expires_soon", "pha_open")},
            "flags": [_flag(f) for f in flags],
        })

    all_flags = [f for e in engineers for f in e["flags"]]
    all_flags.sort(key=lambda f: (0 if f["status"] == "EXPIRES_TODAY" else 1 if f["status"] == "EXPIRES_SOON" else 2,
                                  f["days_left"] if f["status"] != "OVERDUE" else -f["days_left"], f["wo_number"]))
    acks = _acks([f["wo_number"] for f in all_flags])
    for f in all_flags:
        f["ack"] = acks.get(f["wo_number"])
    for e in engineers:
        for f in e["flags"]:
            f["ack"] = acks.get(f["wo_number"])
    for e in engineers:
        for a in e["aircraft"]:
            for item in a["deferrals"]:
                item["ack"] = acks.get(item["wo_number"])

    return {"as_of": as_of, "shift_date": shift_date, "roster_is_placeholder": True, "roster_created_now": created,
            "engineers": engineers, "shift_top_flag": all_flags[0] if all_flags else None,
            "shift_counts": {"aircraft": len(roster), "flags": len(all_flags)}}


def aircraft_service_flag_key(item: dict) -> tuple:
    s = item["deferral"]["status"]
    rank = {"EXPIRES_TODAY": 0, "EXPIRES_SOON": 1, "OVERDUE": 2}[s]
    dl = item["deferral"]["days_left"]
    return (rank, dl if s != "OVERDUE" else -dl, item["wo_number"])
