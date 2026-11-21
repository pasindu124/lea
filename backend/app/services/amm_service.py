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


def history(reg: str, q: str = "", limit: int = 100, offset: int = 0) -> dict:
    """Past work orders on one aircraft that name an AMM task, newest first.

    `q` matches the work-order text or the AMM task (title, part, tool or material name or number),
    so the engineer can find earlier jobs on one part. Reference only.
    """
    rows = db.query(
        "SELECT wo_number, wo_type, wo_state, wo_description, wo_actions, date_opened, date_closed, source_row "
        "FROM work_orders WHERE aircraft_reg = %s AND wo_state <> 'V' "
        "AND (coalesce(wo_description,'') || ' ' || coalesce(wo_actions,'')) ~ '[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{3}-[0-9]{3}' "
        "ORDER BY wo_number DESC LIMIT 1500", [reg])
    needle = q.strip().lower()
    words = needle.split()
    cache: dict[str, str] = {}

    def task_text(base: str) -> str:
        if base not in cache:
            t = db.query("SELECT title FROM amm_tasks WHERE base_task = %s", [base])
            items = db.query(
                "SELECT i.designation, i.ref, i.extra FROM amm_task_items i JOIN amm_tasks t ON t.task_no = i.task_no "
                "WHERE t.base_task = %s AND i.kind <> 'reference'", [base])
            cache[base] = " ".join([x["title"] or "" for x in t] +
                                   [f"{i['designation'] or ''} {i['ref'] or ''} {i['extra'] or ''}" for i in items]).lower()
        return cache[base]

    summ: dict[str, dict] = {}

    def summary(base: str) -> dict:
        if base not in summ:
            t = db.query("SELECT title, function_label FROM amm_tasks WHERE base_task = %s ORDER BY task_no LIMIT 1", [base])
            items = db.query(
                "SELECT DISTINCT i.kind, i.designation, i.ref FROM amm_task_items i JOIN amm_tasks t ON t.task_no = i.task_no "
                "WHERE t.base_task = %s AND i.kind <> 'reference'", [base])
            def names(kind): return [f"{i['designation']}" + (f" ({i['ref']})" if i["ref"] else "") for i in items if i["kind"] == kind]
            summ[base] = {"base_task": base, "in_manual": bool(t), "title": t[0]["title"] if t else None,
                          "function_label": t[0]["function_label"] if t else None,
                          "parts": names("part"), "tools": names("tool"), "materials": names("consumable")}
        return summ[base]

    out, total = [], 0
    for r in rows:
        text = f"{r['wo_description'] or ''} {r['wo_actions'] or ''}"
        refs = extract_task_refs(text)
        hay = text.lower() + " " + " ".join(task_text(b) for b in refs)
        if words and not all(w in hay for w in words):
            continue
        total += 1
        if offset <= total - 1 < offset + limit:
            out.append({"wo_number": r["wo_number"], "wo_type": r["wo_type"], "wo_state": r["wo_state"],
                        "date_opened": r["date_opened"], "date_closed": r["date_closed"],
                        "text": (r["wo_description"] or "")[:300], "task_refs": refs, "tasks": [summary(b) for b in refs],
                        "source": {"file": "Maintenance_History.xlsx", "row": r["source_row"],
                                   "wo_number": r["wo_number"]}})
    return {"aircraft_reg": reg, "query": q, "total": total, "shown": len(out), "offset": offset, "items": out}
