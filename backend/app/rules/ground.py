"""Ground time at the station (Sharjah) from the flight schedule. Pure functions: no database, no AI.

All datetimes here are naive and already in Sharjah LOCAL time (the service converts them with `to_local`).
A "ground window" is the time one aircraft spends at the station between an arrival and its next departure.
Planned times (STA / STD) are used unless the actual time (ATA / ATD) is in the file.

Words in the notes are neutral on purpose: they give facts and dates, never a verdict on whether an aircraft
can fly or what must be done. The licensed engineer decides.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

STATION = "SHJ"
_NEG, _POS = datetime(1970, 1, 1), datetime(2100, 1, 1)

# Window kinds
TURNAROUND = "turnaround"                    # arrival and the next departure are both in the schedule
ARRIVAL_NOT_IN_SCHEDULE = "arrival_not_in_schedule"   # first flight in the file already leaves the station
NO_LATER_DEPARTURE = "no_later_departure"    # last flight in the file arrives at the station
DATA_GAP = "data_gap"                        # the next flight starts somewhere else: we do not guess


# ------------------------------------------------------------------ time helpers
def to_local(value: datetime | None, times_are: str = "local", utc_offset_hours: float = 4) -> datetime | None:
    """File time -> Sharjah local time. times_are is "local" (as written) or "utc"."""
    if value is None:
        return None
    if str(times_are).lower() == "utc":
        return value + timedelta(hours=utc_offset_hours)
    return value


def shift_window(shift_date: date, start: tuple[int, int] = (22, 0), end: tuple[int, int] = (6, 0)) -> tuple[datetime, datetime]:
    """Local start and end of the night shift that begins on shift_date. An end before the start means "next day"."""
    s = datetime.combine(shift_date, time(*start))
    e = datetime.combine(shift_date, time(*end))
    if e <= s:
        e += timedelta(days=1)
    return s, e


def fmt_when(value: datetime) -> str:
    return f"{value.day} {value:%b %H:%M}"


def fmt_duration(hours: float) -> str:
    minutes = int(round(hours * 60))
    return f"{minutes // 60}h{minutes % 60:02d}"


def dep_time(f: dict) -> datetime | None:
    return f.get("atd") or f.get("std")


def arr_time(f: dict) -> datetime | None:
    return f.get("ata") or f.get("sta")


# --------------------------------------------------------------- ground windows
def _window(reg: str, kind: str, arrival: dict | None, departure: dict | None, note: str = "",
            next_destination: str | None = None) -> dict[str, Any]:
    start = arr_time(arrival) if arrival else None
    end = dep_time(departure) if departure else None
    hours = (end - start).total_seconds() / 3600 if start and end else None
    return {
        "reg": reg, "kind": kind, "uncertain": kind == DATA_GAP, "note": note,
        "arrival_flight": arrival["flight_no"] if arrival else None, "arrival_time": start,
        "arrival_from": arrival.get("dep") if arrival else None, "arrival_row": arrival.get("source_row") if arrival else None,
        "departure_flight": departure["flight_no"] if departure else None, "departure_time": end,
        "departure_row": departure.get("source_row") if departure else None,
        "next_destination": next_destination, "ground_hours": hours,
        "used_actuals": bool((arrival and arrival.get("ata")) or (departure and departure.get("atd"))),
    }


def ground_windows(flights: Iterable[dict], station: str = STATION) -> list[dict]:
    """For each aircraft, pair an arrival into `station` with the same aircraft's NEXT departure from it."""
    by_reg: dict[str, list[dict]] = {}
    for f in flights:
        if f.get("reg") and dep_time(f) and arr_time(f):
            by_reg.setdefault(f["reg"], []).append(f)

    out: list[dict] = []
    for reg in sorted(by_reg):
        seq = sorted(by_reg[reg], key=lambda f: (dep_time(f), arr_time(f)))
        for i, f in enumerate(seq):
            prev = seq[i - 1] if i else None
            nxt = seq[i + 1] if i + 1 < len(seq) else None
            if f["arr"] == station:
                if nxt is None:
                    out.append(_window(reg, NO_LATER_DEPARTURE, f, None,
                                       "No later departure in the schedule: the aircraft stays at the station until the file ends."))
                elif nxt["dep"] == station:
                    w = _window(reg, TURNAROUND, f, nxt, next_destination=nxt["arr"])
                    if w["ground_hours"] is not None and w["ground_hours"] < 0:
                        w = _window(reg, DATA_GAP, f, None, "The next departure is before the arrival: check the schedule.")
                    out.append(w)
                else:
                    out.append(_window(reg, DATA_GAP, f, None,
                                       f"The next flight ({nxt['flight_no']}) leaves from {nxt['dep']}, not {station}: "
                                       "a flight is missing from the schedule. The ground time is not guessed."))
            if f["dep"] == station and (prev is None or prev["arr"] != station):
                if prev is None:
                    out.append(_window(reg, ARRIVAL_NOT_IN_SCHEDULE, None, f,
                                       "The arrival is before the start of the schedule.", next_destination=f["arr"]))
                else:
                    out.append(_window(reg, DATA_GAP, None, f,
                                       f"The previous flight ({prev['flight_no']}) arrives at {prev['arr']}, not {station}: "
                                       "a flight is missing from the schedule.", next_destination=f["arr"]))
    out.sort(key=lambda w: (w["reg"], w["arrival_time"] or w["departure_time"]))
    return out


def overlap_minutes(w: dict, start: datetime, end: datetime) -> float:
    """Minutes of a window that fall inside [start, end]. A missing edge is open-ended."""
    a = max(w["arrival_time"] or _NEG, start)
    b = min(w["departure_time"] or _POS, end)
    return max(0.0, (b - a).total_seconds() / 60)


def on_ground_during(windows: Iterable[dict], start: datetime, end: datetime, min_minutes: float = 0,
                     include_uncertain: bool = False) -> list[dict]:
    """Windows that overlap [start, end] for at least min_minutes. Uncertain (data gap) windows are left out
    unless asked for, because we do not know when the aircraft really leaves."""
    out = []
    for w in windows:
        if w["uncertain"] and not include_uncertain:
            continue
        m = overlap_minutes(w, start, end)
        if m > 0 and m >= min_minutes:
            out.append({**w, "overlap_minutes": round(m, 1)})
    return out


def next_arrival(windows: Iterable[dict], after: datetime) -> dict | None:
    """First arrival into the station after `after` (for aircraft that are away tonight)."""
    later = [w for w in windows if w["arrival_time"] and w["arrival_time"] > after]
    return min(later, key=lambda w: w["arrival_time"]) if later else None


# ------------------------------------------------------------------ timing notes
def _to_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if v:
        try:
            return date.fromisoformat(str(v)[:10])
        except ValueError:
            return None
    return None


def timing_notes(deferral: dict | None, windows: Iterable[dict], ref: datetime, flagged_count: int = 1,
                 short_hours: float = 2.0) -> list[str]:
    """Plain facts next to a flagged item. `ref` is the moment the shift starts (local time)."""
    ws = [w for w in windows if not w["uncertain"]]
    current = next((w for w in ws if (w["arrival_time"] is None or w["arrival_time"] <= ref)
                    and (w["departure_time"] is None or w["departure_time"] > ref)), None)
    upcoming = next(iter(sorted((w for w in ws if w["arrival_time"] and w["arrival_time"] > ref),
                                key=lambda w: w["arrival_time"])), None)
    target = current or upcoming
    notes: list[str] = []
    if target is None:
        return ["The schedule has no more Sharjah ground time for this aircraft."]
    if target is upcoming and current is None:
        notes.append(f"Not at Sharjah when the shift starts. Next arrival at Sharjah: {fmt_when(target['arrival_time'])}"
                     f" ({target['arrival_flight']}).")
    dep = target["departure_time"]
    expires = _to_date(deferral.get("expires_on")) if deferral else None
    if dep is None:
        notes.append("No later departure from Sharjah in the schedule.")
    elif expires:
        rel = "after" if dep.date() > expires else "on or before"
        notes.append(f"Next departure ({fmt_when(dep)}) is {rel} the deadline date ({expires.day} {expires:%b}).")
    else:
        notes.append(f"Next departure from Sharjah: {fmt_when(dep)}.")
    hours = target["ground_hours"]
    if hours is not None and hours < short_hours:
        n = max(flagged_count, 1)
        notes.append(f"Only {fmt_duration(hours)} on the ground and {n} item{'s' if n != 1 else ''} "
                     f"{'are' if n != 1 else 'is'} flagged.")
    if not target["used_actuals"]:
        notes.append("Times are the planned schedule, not actual times.")
    return notes


# ------------------------------------------------------------ balancing engineers
def _clipped(ws: Iterable[dict], clip: tuple[datetime, datetime] | None) -> list[tuple[datetime, datetime]]:
    lo, hi = clip if clip else (_NEG, _POS)
    out = []
    for w in ws:
        if w.get("uncertain"):
            continue
        a, b = max(w["arrival_time"] or lo, lo), min(w["departure_time"] or hi, hi)
        if b > a:
            out.append((a, b))
    return out


def _pair_overlap(a: list[tuple[datetime, datetime]], b: list[tuple[datetime, datetime]]) -> float:
    return sum(max(0.0, (min(x2, y2) - max(x1, y1)).total_seconds()) for x1, x2 in a for y1, y2 in b)


def balance_by_time(aircraft_scores: dict[str, int], windows: dict[str, list[dict]], engineers: list[str],
                    clip: tuple[datetime, datetime] | None = None) -> dict[str, str]:
    """Give each aircraft (most urgent first) to the engineer whose aircraft already overlap it least on the
    ground, then to the one with the fewest aircraft, then the lowest total score."""
    if not engineers:
        raise ValueError("At least one engineer is required")
    spans = {reg: _clipped(windows.get(reg, []), clip) for reg in aircraft_scores}
    mine: dict[str, list[str]] = {e: [] for e in engineers}
    out: dict[str, str] = {}
    for reg in sorted(aircraft_scores, key=lambda r: (-aircraft_scores[r], r)):
        def cost(i_e: tuple[int, str]) -> tuple:
            i, e = i_e
            overlap = sum(_pair_overlap(spans[reg], spans[o]) for o in mine[e])
            return (overlap, len(mine[e]), sum(aircraft_scores[o] for o in mine[e]), i)
        _, chosen = min(enumerate(engineers), key=cost)
        mine[chosen].append(reg)
        out[reg] = chosen
    return out


def overlap_warnings(assignments: dict[str, str], windows: dict[str, list[dict]], clip: tuple[datetime, datetime],
                     short_hours: float = 2.0, min_minutes: float = 30) -> dict[str, list[dict]]:
    """Per engineer: pairs of aircraft on the ground together where BOTH have a short ground time inside the shift
    window. (An aircraft parked all night is not a clash with a short turnaround: its work can be done before or
    after. Two short turnarounds at the same time are the real problem.)"""
    spans = {reg: _clipped(windows.get(reg, []), clip) for reg in assignments}
    total = {reg: sum((b - a).total_seconds() for a, b in s) / 3600 for reg, s in spans.items()}
    out: dict[str, list[dict]] = {}
    regs_by_eng: dict[str, list[str]] = {}
    for reg, eng in assignments.items():
        regs_by_eng.setdefault(eng, []).append(reg)
    for eng, regs in regs_by_eng.items():
        found = []
        regs = sorted(regs)
        for i, a in enumerate(regs):
            for b in regs[i + 1:]:
                minutes = _pair_overlap(spans[a], spans[b]) / 60
                both_short = all(0 < total[r] < short_hours for r in (a, b))
                if minutes >= min_minutes and both_short:
                    found.append({"aircraft": [a, b], "overlap_minutes": round(minutes), "short_ground": [a, b]})
        if found:
            out[eng] = found
    return out
