"""AMM (Aircraft Maintenance Manual) helpers: find task numbers in free text, name the task type.

Pure functions, no SQL. An AMM task number looks like 26-23-41-000-004 (ATA chapter-section-subject,
function code, sequence), sometimes with a configuration letter on the end: 26-23-41-000-004-A.
"""
from __future__ import annotations

import re

TASK_RE = re.compile(r"(?<![\d-])(\d{2})-(\d{2})-(\d{2})-(\d{3})-(\d{3})(?:-([A-Z]))?(?![\d])")

# Function code = 4th block of the task number. Only codes whose meaning is standard ATA are named.
FUNCTION_LABELS = {
    "000": "Removal", "400": "Installation", "200": "Servicing", "210": "Inspection",
    "710": "Operational test", "720": "Functional test", "040": "Fault isolation",
    "100": "Cleaning", "600": "Adjustment",
}


def function_label(code: str) -> str:
    return FUNCTION_LABELS.get(code, f"Task type {code}")


def extract_task_refs(text: str | None) -> list[str]:
    """Base task numbers (without the configuration letter) in the order they first appear."""
    out: list[str] = []
    for m in TASK_RE.finditer(text or ""):
        ref = "-".join(m.group(i) for i in range(1, 6))
        if ref not in out:
            out.append(ref)
    return out
