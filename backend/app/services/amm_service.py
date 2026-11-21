"""AMM reference lookup: which maintenance tasks a work order mentions, and what each task uses."""
from __future__ import annotations

from .. import db
from ..rules.amm import extract_task_refs
from ..rules.text import norm
from . import aircraft_service


def _tool_stock(part_no: str) -> dict:
    row = db.query_one(
        "SELECT count(*) AS n, coalesce(sum(qty),0) AS qty FROM tools "
        "WHERE regexp_replace(upper(part_no),'[^A-Z0-9]','','g') = %s", [norm(part_no)])
    return {"rows": int(row["n"]), "qty": float(row["qty"])}


def get_task(base_task: str) -> dict | None:
    """All configuration variants (A, B, ...) of one task, with items and warnings."""
    tasks = db.query("SELECT * FROM amm_tasks WHERE base_task = %s ORDER BY task_no", [base_task])
    if not tasks:
        return None
    variants = []
    for t in tasks:
        items = db.query("SELECT kind, ref, qty, designation, extra FROM amm_task_items WHERE task_no = %s ORDER BY pos",
                         [t["task_no"]])
        for it in items:
            if it["kind"] == "tool" and it["ref"]:
                it["stock"] = _tool_stock(it["ref"])
        notes = db.query("SELECT kind, code, text FROM amm_task_notes WHERE task_no = %s ORDER BY pos", [t["task_no"]])
        variants.append({**t, "items": items, "notes": notes})
    first = variants[0]
    return {"base_task": base_task, "title": first["title"], "function_label": first["function_label"],
            "ata": first["ata"], "variants": variants,
            "source": {"file": first["source_file"], "task": base_task}}


def for_work_order(wo_number: int) -> dict | None:
    row = aircraft_service.work_order_full(wo_number)
    if not row:
        return None
    text = f"{row.get('wo_description') or ''} {row.get('wo_actions') or ''}"
    refs = extract_task_refs(text)
    tasks, unknown = [], []
    for ref in refs:
        t = get_task(ref)
        (tasks if t else unknown).append(t or ref)
    return {"wo_number": wo_number, "tasks": tasks, "not_in_amm": unknown}
