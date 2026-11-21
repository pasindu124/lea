"""MMEL (Master Minimum Equipment List) helpers: plain code, no AI, no SQL.

The MMEL lists equipment the aircraft may fly without for a limited time. Each item
(36-11-07) has one or more dispatch conditions (36-11-07A, -B, ...), each with a repair
interval letter (A/B/C/D) defined on MMEL page MI-00-05. Airbus keeps several versions
of an item; each version applies to a list of aircraft serial numbers (MSN).

Source: Airbus MMEL XML for the ABY fleet (the data pack's "XML_C_Ops_MMEL" file).
This is the manufacturer's MASTER list. Air Arabia's own MEL may be stricter and is
not in the data pack, so the UI must call it "MMEL", never "MEL".
"""
from __future__ import annotations

import re

ALL_AIRCRAFT = "ALL"   # applicability token: the item version applies to every aircraft

# Item numbers as engineers write them: 36-11-07, 36-11-07B, 21-01-01-01, 33-20-01-A.
_ITEM_RE = re.compile(r"\b(\d{2})-(\d{2})-(\d{2})(?:-(\d{2}))?(?:-?([A-Z]))?\b")


def msn_tokens(text: str | None) -> list[str]:
    """Airbus MSN list -> tokens. "03152 0722507226" -> ["03152", "07225-07226"].

    In the XML a 10-digit run is a range: first five digits to last five digits.
    """
    out: list[str] = []
    for tok in (text or "").split():
        if len(tok) == 10 and tok.isdigit():
            out.append(f"{tok[:5]}-{tok[5:]}")
        elif tok.isdigit():
            out.append(tok.zfill(5))
    return out


def msn_applies(msn: str | None, tokens: list[str] | None) -> bool:
    """True if the aircraft serial number is in the item's applicability list."""
    if not msn or not tokens:
        return False
    if ALL_AIRCRAFT in tokens:
        return True
    n = int(msn)
    for tok in tokens:
        low, _, high = tok.partition("-")
        if int(low) <= n <= int(high or low):
            return True
    return False


def amm_task_no(chap: str, sect: str, subj: str, func: str, seq: str) -> str:
    """AMM task reference parts -> "36-11-00-040-003" (same format as amm_tasks.base_task)."""
    return f"{chap}-{sect}-{subj}-{func}-{seq}"


def item_code(func_code: str, label: str | None) -> str:
    """"36-11-07" + "B" -> "36-11-07B"."""
    return f"{func_code}{label or ''}"


def find_items(text: str | None) -> list[str]:
    """MMEL item numbers written in free text, normalised: "MEL 33-20-01-A" -> "33-20-01A".

    Callers must still check the number exists in mmel_items: AMM tasks and SRM
    references use the same digit pattern.
    """
    found: list[str] = []
    for m in _ITEM_RE.finditer(text or ""):
        code = "-".join(p for p in m.group(1, 2, 3, 4) if p) + (m.group(5) or "")
        if code not in found:
            found.append(code)
    return found


def base_item(code: str) -> str:
    """"36-11-07B" -> "36-11-07"."""
    return code[:-1] if code and code[-1].isalpha() else code
