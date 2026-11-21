"""Small text helpers: search tokens, part-number normalising, keyword suggestions."""
from __future__ import annotations

import re

_STOP = set("""
ENG ENTRY FOUND DURING ON IN AT OF THE AND OR TO FOR WITH FROM BY IS ARE WAS WERE BE AS PER
REF REFER WORKORDER WO NIL DUE LESS GND GROUND TIME RAISED DEFERRED DEFERRAL DD MEL NSI MCC
APPROVAL FORM CARRIED OUT CHECK CHECKED REPORTED REPORT LH RH LEFT RIGHT AFT FWD NOT NO
DAMAGE DAMAGED FAULTY FAULT U/S UNSERVICEABLE MISSING INOP INOPERATIVE ISSUED PAX ASSY
WALKAROUND WALK AROUND WEEKLY DAILY INSP INSPECTION OBSERVED NOTICED LOCATION FOLLOWING
AREA ITEM TRANSFER FROM PAGE NUMBER NUMBERING THAT THIS HAVE HAS WILL SHOULD ALSO ONLY
""".split())


def norm(text: str) -> str:
    """Upper-case, letters and digits only: '1152682-3' and '11526823' compare equal."""
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def escape_like(token: str) -> str:
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def heuristic_keywords(fault_text: str, limit: int = 3) -> list[str]:
    """Cheap fallback when AI is off: the first few meaningful words of the fault text."""
    words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", (fault_text or "").upper())
    out: list[str] = []
    for w in words:
        if w in _STOP or w in out:
            continue
        out.append(w)
        if len(out) == limit:
            break
    return out
