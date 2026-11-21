"""Deferral detection and deadline calculation (plain code, no AI).

A "deferral" is a fault that was postponed instead of fixed (MEL / NSI / DD).
The work-order text is free text, so we only compute a date when the record
itself states how long the deferral may last:

  1. "CAT B/C/D" written in the record  -> 3 / 10 / 120 days (config.CATEGORY_DAYS,
     an ASSUMPTION until the MMEL repair-interval page is confirmed).
  2. "FOR 120 DAYS" written in the record (typical for NSI deferrals) -> that number.
  2b. "WITHIN 30 DAYS" is read the same way as "FOR 30 DAYS".
  3. "... 120 DAYS WHICHEVER OCCURS FIRST" together with flight cycles/hours ->
     the day count is an upper limit only (flight cycles may expire it sooner).
  4. Only flight cycles/hours ("EVERY 400 FC") -> no date is computed.
  4b. "EVERY 10 DAYS" is a repeat inspection, and "NEXT MAINT CHECK" has no calendar
      date: no date is computed for either.
  5. Category A -> "as stated in the MMEL item": no date is computed.
  6. Nothing stated -> "check the source".

The trailing letter of an item number such as 36-11-07B is an item variant,
NOT the repair category, so it is never used.

"CAT B" is also used by the Structural Repair Manual (SRM) for dents and repairs
("permanent allowable damage (CAT B)", "repair category B"). That is a damage
class, not an MEL repair interval, so it never gives a 3/10/120-day deadline.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any

from .. import config

# Words that show a fault was deferred. "DD000667" (a reference number) does not
# match because \b needs a word boundary after DD.
_DEFERRAL_RE = re.compile(
    r"\b(?:MEL|MDD|NSI|DD|ADD)\b|DE(?:F|FF)ERR?(?:ED|AL)|DERERRAL|DEFERRAL",
    re.IGNORECASE,
)
_CAT_RE = re.compile(r"\bCAT(?:EGORY|\.)?\s*([ABCD])\b", re.IGNORECASE)
# Words near "CAT x" that show it is an SRM structural damage/repair category.
_STRUCTURAL_RE = re.compile(
    r"\bSRM\b|\bSRI\b|ALLOWABLE\s+DAMAGE|REPAIR\s+CAT|\bRDAF\b|DAMAGE\s+SIZE|\bADL\b|\bDENT\b",
    re.IGNORECASE,
)
_STRUCTURAL_BEFORE, _STRUCTURAL_AFTER = 200, 60   # characters looked at around "CAT x"
_FOR_DAYS_RE = re.compile(r"\b(?:FOR|WITHIN)\s+(\d{1,3})\s*DAYS?\b", re.IGNORECASE)
_EVERY_DAYS_RE = re.compile(r"\bEVERY\s+(\d{1,3})\s*DAYS?\b", re.IGNORECASE)
_NEXT_CHECK_RE = re.compile(r"\bNEXT\s+(?:MAINT(?:ENANCE)?\s+)?(?:CHECK|C-?CHECK|A-?CHECK)\b", re.IGNORECASE)
_ANY_DAYS_RE = re.compile(r"\b(\d{1,3})\s*DAYS?\b", re.IGNORECASE)
_FLIGHT_RE = re.compile(
    r"\b\d{2,5}\s*(?:FC|FH|FHS|HRS|HOURS|CYCLES)\b|\bFLIGHT\s+(?:CYCLES|HOURS)\b",
    re.IGNORECASE,
)
_WHICHEVER_RE = re.compile(r"WHICH\s*EVER", re.IGNORECASE)
_ACTION_ENTRY_RE = re.compile(
    r"\[(\d{2}-[A-Za-z]{3}-\d{4})\]\s*(.*?)(?=\s*\|\s*\[\d{2}-[A-Za-z]{3}-\d{4}\]|\Z)", re.DOTALL
)

STATUS_ORDER = {"OVERDUE": 0, "EXPIRES_TODAY": 1, "EXPIRES_SOON": 2, "OK": 3, "CHECK_SOURCE": 4}


@dataclass
class Deferral:
    kind: str                 # CATEGORY | STATED_DAYS | DAYS_OR_FLIGHT | FLIGHT_ONLY | REPEAT_INTERVAL | NEXT_CHECK | CATEGORY_A | UNKNOWN
    category: str | None
    days: int | None
    basis_date: date | None
    expires_on: date | None
    evidence: str             # the words in the record that triggered this
    where_found: str          # "actions" or "description"
    rule: str                 # plain-language explanation shown to the engineer
    is_assumption: bool       # True when the interval comes from config (MMEL assumption)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _snippet(text: str, start: int, end: int, pad: int = 70) -> str:
    left, right = max(0, start - pad), min(len(text), end + pad)
    return ("…" if left else "") + text[left:right].strip() + ("…" if right < len(text) else "")


def is_structural_category(text: str, match: re.Match) -> bool:
    """True when this "CAT x" sits next to SRM / allowable-damage wording (a damage class, not MEL)."""
    window = text[max(0, match.start() - _STRUCTURAL_BEFORE): match.end() + _STRUCTURAL_AFTER]
    return bool(_STRUCTURAL_RE.search(window))


def mel_category(text: str) -> tuple[re.Match | None, re.Match | None]:
    """(first MEL "CAT x" match, first structural "CAT x" match that was skipped)."""
    skipped = None
    for match in _CAT_RE.finditer(text):
        if not is_structural_category(text, match):
            return match, skipped
        skipped = skipped or match
    return None, skipped


def parse_deferral(description: str | None, actions: str | None, date_opened: Any) -> Deferral | None:
    """Return a Deferral if the record shows one, else None."""
    description, actions = description or "", actions or ""
    for where, text in (("actions", actions), ("description", description)):
        match = _DEFERRAL_RE.search(text)
        if match:
            break
    else:
        return None

    basis = _as_date(date_opened)
    evidence = _snippet(text, match.start(), match.end())
    scan = actions + " " + description  # numbers may sit in either field

    cat, structural = mel_category(scan)
    structural_note = (
        f" Note: '{structural.group(0).strip()}' in this record is a structural repair (SRM) damage "
        f"category, not an MEL repair interval, so it is not used for a deadline."
        if structural and not cat else ""
    )

    def build(kind, category, days, rule, assumption):
        expires = basis + timedelta(days=days) if (basis and days) else None
        return Deferral(kind, category, days, basis, expires, evidence, where, rule + structural_note, assumption)

    stated = _FOR_DAYS_RE.search(scan)
    flight = _FLIGHT_RE.search(scan)

    if cat:
        letter = cat.group(1).upper()
        if letter == "A":
            return build("CATEGORY_A", "A", None,
                         "Record says category A: the time limit is set in the MMEL item itself. "
                         "No date is calculated; check the MMEL item.", False)
        days = config.CATEGORY_DAYS[letter]
        rule = (f"Record says category {letter}. Category {letter} allows {days} calendar days "
                f"(MMEL practice, to be confirmed), not counting the day the fault was found. "
                f"Deadline = date opened {basis} + {days} days.")
        if stated and int(stated.group(1)) != days:
            rule += f" Note: the record also says {stated.group(1)} days. Check which applies."
        return build("CATEGORY", letter, days, rule, True)

    if stated:
        days = int(stated.group(1))
        if flight and _WHICHEVER_RE.search(scan):
            return build("DAYS_OR_FLIGHT", None, days,
                         f"Record says {days} days or a flight-cycle/hour limit, whichever comes first. "
                         f"The date {basis} + {days} days is the LATEST possible; flight cycles or hours "
                         f"may expire it sooner. Check the source.", False)
        return build("STATED_DAYS", None, days,
                     f"Record states 'FOR {days} DAYS'. Deadline = date opened {basis} + {days} days, "
                     f"not counting the day the fault was found.", False)

    if flight and _WHICHEVER_RE.search(scan):
        any_days = _ANY_DAYS_RE.search(scan)
        if any_days:
            days = int(any_days.group(1))
            return build("DAYS_OR_FLIGHT", None, days,
                         f"Record gives {days} days or a flight-cycle/hour limit, whichever comes first. "
                         f"The date is the LATEST possible. Check the source.", False)

    every = _EVERY_DAYS_RE.search(scan)
    if every and not flight:
        return build("REPEAT_INTERVAL", None, None,
                     f"The record sets a repeat inspection every {every.group(1)} days. The deferral stays open "
                     f"while inspections are done on time. No date is calculated; check the date of the last "
                     f"inspection in the source.", False)

    if flight:
        return build("FLIGHT_ONLY", None, None,
                     "The limit is in flight cycles or flight hours, not days. "
                     "No date is calculated; check the flight-cycle count against the source.", False)

    if _NEXT_CHECK_RE.search(scan):
        return build("NEXT_CHECK", None, None,
                     "The record limits the deferral to the next maintenance check, which has no calendar date "
                     "here. No date is calculated; check the planned check date.", False)

    return build("UNKNOWN", None, None,
                 "A deferral is mentioned but no time limit is written in the record. "
                 "No date is calculated; check the MMEL or the deferral form.", False)


def classify(expires_on: date | None, as_of: date) -> tuple[str, int | None]:
    """Status of a deadline on a given day. Day count is None when there is no date."""
    if expires_on is None:
        return "CHECK_SOURCE", None
    days_left = (expires_on - as_of).days
    if days_left < 0:
        return "OVERDUE", days_left
    if days_left == 0:
        return "EXPIRES_TODAY", 0
    if days_left <= config.SOON_DAYS:
        return "EXPIRES_SOON", days_left
    return "OK", days_left


def status_text(status: str, days_left: int | None) -> str:
    if status == "OVERDUE":
        return f"{abs(days_left)} day{'s' if abs(days_left) != 1 else ''} past deadline"
    if status == "EXPIRES_TODAY":
        return "Due today"
    if status in ("EXPIRES_SOON", "OK"):
        return f"{days_left} day{'s' if days_left != 1 else ''} left"
    return "No date available"


def recent_entries(actions: str | None, as_of: date, window_days: int = 2) -> list[dict[str, str]]:
    """Dated work-log entries from the last `window_days` days (derived handover notes)."""
    out, seen = [], set()
    for stamp, text in _ACTION_ENTRY_RE.findall(actions or ""):
        try:
            when = datetime.strptime(stamp, "%d-%b-%Y").date()
        except ValueError:
            continue
        clean = " ".join(text.split())
        if not clean or clean in seen:
            continue
        if 0 <= (as_of - when).days <= window_days:
            seen.add(clean)
            out.append({"date": when.isoformat(), "text": clean})
    return out
