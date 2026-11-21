"""Shift roster and the per-engineer brief."""
from __future__ import annotations

from datetime import date
from typing import Any

from .. import config, db
from ..rules import ground
from ..rules.roster import snake_assign
from . import aircraft_service, context, schedule_service


def get_roster(shift_date: date) -> dict[str, str]:
    rows = db.query("SELECT aircraft_reg, engineer FROM roster WHERE shift_date = %s", (shift_date,))
    return {r["aircraft_reg"]: r["engineer"] for r in rows}


def plan_roster(shift_date: date, as_of: date, n: int | None = None, engineers: list[str] | None = None) -> dict[str, Any]:
    """Choose tonight's aircraft and split them between engineers, then save the roster.

    With a flight schedule: only aircraft that are on the ground at the station during the shift, and the split
    avoids giving one engineer several aircraft that need work at the same time. Without one: the old behaviour.
    """
    engineers = engineers or config.ENGINEERS
    everything = aircraft_service.list_aircraft(as_of)
    overview = schedule_service.shift_overview(shift_date, everything)
    if overview["available"]:
        here = set(overview["on_ground"])
        pool = [a for a in everything if a["aircraft_reg"] in here]
        strategy = "time_balanced"
    else:
        pool, strategy = everything, "snake_fallback"
    # Aircraft with a deadline today or soon are always on tonight's list, then the highest scores fill the rest.
    critical = [a for a in pool if a["expires_today"] or a["expires_soon"]]
    rest = [a for a in pool if a not in critical]
    limit = max(n or config.AIRCRAFT_PER_SHIFT, len(critical))
    chosen = (critical + rest)[:limit]
    if strategy == "time_balanced":
        mapping = ground.balance_by_time({a["aircraft_reg"]: a["score"] for a in chosen}, overview["_windows"], engineers,
                                         clip=(overview["shift_start"], overview["shift_end"]))
    else:
        mapping = snake_assign([a["aircraft_reg"] for a in chosen], engineers)
    with db.get_pool().connection() as conn:
        conn.execute("DELETE FROM roster WHERE shift_date = %s", (shift_date,))
        for reg, eng in mapping.items():
            conn.execute("INSERT INTO roster (shift_date, aircraft_reg, engineer) VALUES (%s, %s, %s)",
                         (shift_date, reg, eng))
    return {"assignments": mapping, "strategy": strategy, "schedule": schedule_service.public(overview)}


def auto_roster(shift_date: date, as_of: date, n: int | None = None, engineers: list[str] | None = None) -> dict[str, str]:
    return plan_roster(shift_date, as_of, n, engineers)["assignments"]


def schedule_context(shift_date: date, as_of: date, assignments: dict[str, str]) -> dict[str, Any]:
    """Schedule facts for the current roster: overview, ground window per aircraft, not-at-Sharjah list, warnings."""
    overview = schedule_service.public(schedule_service.shift_overview(shift_date, aircraft_service.list_aircraft(as_of)))
    ground_info = schedule_service.ground_for_roster(shift_date, assignments)
    overview.pop("on_ground", None)
    return {**overview, **ground_info}


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
        plan = plan_roster(shift_date, as_of)
        roster, created = plan["assignments"], True
        context.log("auto (brief)", "roster_auto", {"shift_date": shift_date, "strategy": plan["strategy"],
                                                    "assignments": roster, "schedule_available": plan["schedule"]["available"]})

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

    sched = schedule_context(shift_date, as_of, roster)
    for e in engineers:
        e["overlap_warnings"] = sched["overlap_warnings"].get(e["name"], [])
    return {"as_of": as_of, "shift_date": shift_date, "roster_is_placeholder": True, "roster_created_now": created,
            "schedule": sched, "engineers": engineers, "shift_top_flag": all_flags[0] if all_flags else None,
            "shift_counts": {"aircraft": len(roster), "flags": len(all_flags)}}


def aircraft_service_flag_key(item: dict) -> tuple:
    s = item["deferral"]["status"]
    rank = {"EXPIRES_TODAY": 0, "EXPIRES_SOON": 1, "OVERDUE": 2}[s]
    dl = item["deferral"]["days_left"]
    return (rank, dl if s != "OVERDUE" else -dl, item["wo_number"])
