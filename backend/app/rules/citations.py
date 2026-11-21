"""Check that an AI answer only cites records it was actually given."""
from __future__ import annotations

import re

_TAG_RE = re.compile(r"\[([A-Z]{1,4}[0-9]+)\]")


def validate(answer: str, allowed_tags: set[str]) -> dict:
    cited = set(_TAG_RE.findall(answer or ""))
    unknown = sorted(cited - allowed_tags)
    return {
        "cited": sorted(cited & allowed_tags),
        "unknown": unknown,
        "ok": bool(cited) and not unknown,
        "note": ("No source was cited: treat this as information only." if not cited
                 else f"Cites records that were not provided: {', '.join(unknown)}." if unknown else ""),
    }
