"""Split aircraft between engineers so the workload is balanced (plain code).

PLACEHOLDER: the real assignment comes from Planning. The data pack has no roster,
so the demo suggests one: aircraft are ranked by urgency, then dealt out in a
"snake" order (1,2,3,3,2,1,...) so the most urgent aircraft are spread out.
"""
from __future__ import annotations


def snake_assign(ranked_regs: list[str], engineers: list[str]) -> dict[str, str]:
    if not engineers:
        raise ValueError("At least one engineer is required")
    out: dict[str, str] = {}
    n = len(engineers)
    for i, reg in enumerate(ranked_regs):
        lap, pos = divmod(i, n)
        out[reg] = engineers[pos if lap % 2 == 0 else n - 1 - pos]
    return out
