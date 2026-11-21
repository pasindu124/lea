"""Flight schedule: ground time at Sharjah for each aircraft (read-only). The rules live in rules/ground.py."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .. import config, db
from ..rules import ground

FILE_NAME = "Flights_Export (Flight Summary)"


def _local(v: datetime | None) -> datetime | None:
    return ground.to_local(v, config.FLIGHT_TIMES_ARE, config.LOCAL_UTC_OFFSET_HOURS)


def coverage() -> dict | None:
    """First and last schedule date and the time of the last actual flight, or None when no schedule is loaded."""
    return db.get_meta("schedule")


def window_for(shift_date: date) -> tuple[datetime, datetime]:
    return ground.shift_window(shift_date, config.SHIFT_START, config.SHIFT_END)


def available_for(shift_date: date) -> tuple[bool, str]:
    cov = coverage()
    if not cov:
        return False, "No flight schedule is loaded."
    start, end = window_for(shift_date)
    first = datetime.fromisoformat(cov["first_date"])
    last = datetime.fromisoformat(cov["last_date"]).replace(hour=23, minute=59)
    if end < _local(first) or start > _local(last):
        return False, f"The flight schedule covers {cov['first_date']} to {cov['last_date']}, not this shift."
    return True, ""


def _flight_rows(regs: list[str] | None = None) -> list[dict]:
    sql = ("SELECT reg, flight_no, dep, arr, std, atd, sta, ata, eta, has_actuals, source_row FROM flights "
           "WHERE reg LIKE %s")
    params: list[Any] = [config.OWN_REG_PREFIX + "%"]
    if regs is not None:
        sql += " AND reg = ANY(%s)"
        params.append(list(regs))
    rows = db.query(sql, tuple(params))
    for r in rows:
        for k in ("std", "atd", "sta", "ata", "eta"):
            r[k] = _local(r[k])
    return rows


def windows_by_reg(regs: list[str] | None = None) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for w in ground.ground_windows(_flight_rows(regs), config.STATION):
        out.setdefault(w["reg"], []).append(w)
    return out


def _source(row: int | None, flight_no: str | None = None) -> dict | None:
    return {"file": FILE_NAME, "row": row, "flight_no": flight_no} if row else None


def _window_out(w: dict | None) -> dict | None:
    if not w:
        return None
    return {
        "kind": w["kind"], "note": w["note"], "uncertain": w["uncertain"],
        "arrival_flight": w["arrival_flight"], "arrival_time": w["arrival_time"], "arrival_from": w["arrival_from"],
        "departure_flight": w["departure_flight"], "departure_time": w["departure_time"],
        "next_destination": w["next_destination"],
        "ground_hours": round(w["ground_hours"], 2) if w["ground_hours"] is not None else None,
        "tight": w["ground_hours"] is not None and w["ground_hours"] < config.SHORT_GROUND_HOURS,
        "used_actuals": w["used_actuals"], "overlap_minutes": w.get("overlap_minutes"),
        "sources": [s for s in (_source(w["arrival_row"], w["arrival_flight"]), _source(w["departure_row"], w["departure_flight"])) if s],
    }


def for_aircraft(reg: str, shift_date: date, flagged: list[dict]) -> dict:
    """The "schedule" block of the aircraft detail: tonight's ground window, next 3 flights, notes per flagged item."""
    ok, why = available_for(shift_date)
    cov = coverage()
    base: dict[str, Any] = {"available": ok, "reason": why, "times_are": config.FLIGHT_TIMES_ARE,
                            "station": config.STATION, "last_actual": (cov or {}).get("last_actual"),
                            "shift_start": None, "shift_end": None, "tonight": None, "next_flights": [], "notes": {}}
    if not ok:
        return base
    start, end = window_for(shift_date)
    rows = _flight_rows([reg])
    wins = ground.ground_windows(rows, config.STATION)
    tonight = ground.on_ground_during(wins, start, end, config.MIN_GROUND_MINUTES)
    # the window with the most time inside the shift
    best = max(tonight, key=lambda w: w["overlap_minutes"]) if tonight else None
    upcoming = [r for r in rows if ground.arr_time(r) and ground.arr_time(r) >= start]
    upcoming.sort(key=lambda r: ground.dep_time(r))
    next_flights = [{
        "flight_no": r["flight_no"], "dep": r["dep"], "arr": r["arr"], "std": r["std"], "sta": r["sta"],
        "atd": r["atd"], "ata": r["ata"], "actual": bool(r["has_actuals"]),
        "source": {"file": FILE_NAME, "row": r["source_row"], "flight_no": r["flight_no"]},
    } for r in upcoming[:3]]
    notes = {}
    for item in flagged:
        notes[str(item["wo_number"])] = ground.timing_notes(item["deferral"], wins, start, len(flagged),
                                                            config.SHORT_GROUND_HOURS)
    base.update(shift_start=start, shift_end=end, tonight=_window_out(best), next_flights=next_flights, notes=notes,
                next_arrival=_window_out(ground.next_arrival(wins, start)) if best is None else None)
    return base


def shift_overview(shift_date: date, aircraft: list[dict]) -> dict:
    """Who is at the station during the shift, and which urgent aircraft are away. `aircraft` is list_aircraft()."""
    ok, why = available_for(shift_date)
    cov = coverage()
    info: dict[str, Any] = {"available": ok, "reason": why, "times_are": config.FLIGHT_TIMES_ARE,
                            "station": config.STATION, "last_actual": (cov or {}).get("last_actual"),
                            "first_date": (cov or {}).get("first_date"), "last_date": (cov or {}).get("last_date"),
                            "shift_start": None, "shift_end": None}
    if not ok:
        return {**info, "_windows": {}, "on_ground": [], "not_at_sharjah": [], "other_away": 0}
    start, end = window_for(shift_date)
    wins = windows_by_reg([a["aircraft_reg"] for a in aircraft])
    here: dict[str, list[dict]] = {}
    not_here = []
    for a in aircraft:
        reg = a["aircraft_reg"]
        tonight = ground.on_ground_during(wins.get(reg, []), start, end, config.MIN_GROUND_MINUTES)
        if tonight:
            here[reg] = tonight
        else:
            not_here.append(a)
    urgent_away = [a for a in not_here if a["expires_today"] or a["expires_soon"]]
    away_out = []
    for a in urgent_away:
        nxt = ground.next_arrival(wins.get(a["aircraft_reg"], []), start)
        away_out.append({"aircraft_reg": a["aircraft_reg"], "expires_today": a["expires_today"],
                         "expires_soon": a["expires_soon"], "overdue": a["overdue"], "score": a["score"],
                         "next_arrival": _window_out(nxt)})
    return {**info, "shift_start": start, "shift_end": end, "_windows": here,
            "on_ground": sorted(here), "not_at_sharjah": away_out,
            "other_away": len(not_here) - len(urgent_away)}


def public(overview: dict) -> dict:
    """The overview without the internal window objects (safe to send to the browser)."""
    return {k: v for k, v in overview.items() if not k.startswith("_")}


def ground_for_roster(shift_date: date, assignments: dict[str, str]) -> dict:
    """Tonight's ground window for each rostered aircraft, plus the per-engineer overlap warnings."""
    ok, _ = available_for(shift_date)
    if not ok or not assignments:
        return {"ground": {}, "overlap_warnings": {}}
    start, end = window_for(shift_date)
    wins = windows_by_reg(list(assignments))
    ground_out = {}
    for reg in assignments:
        tonight = ground.on_ground_during(wins.get(reg, []), start, end, config.MIN_GROUND_MINUTES)
        best = max(tonight, key=lambda w: w["overlap_minutes"]) if tonight else None
        ground_out[reg] = _window_out(best)
    warnings = ground.overlap_warnings(assignments, wins, (start, end), config.SHORT_GROUND_HOURS, config.MIN_GROUND_MINUTES)
    return {"ground": ground_out, "overlap_warnings": warnings}
