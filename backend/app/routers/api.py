"""All HTTP routes (JSON under /api)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .. import config, db
from ..ai import client as ai
from ..rules import citations  # noqa: F401  (re-exported for tests)
from ..rules.text import heuristic_keywords
from ..services import aircraft_service, amm_service, brief_service, context, parts_service, tools_service

router = APIRouter(prefix="/api")


def _actor(x_user: str | None) -> str:
    return (x_user or "").strip() or "unknown"


# ------------------------------------------------------------------ system
@router.get("/health")
def health():
    db.query_one("SELECT 1 AS ok")
    return {"status": "ok"}


@router.get("/meta")
def meta(as_of: str | None = None):
    resolved = context.resolve_as_of(as_of)
    placeholder = db.get_meta("tools_placeholder_expiry")
    return {
        "as_of": resolved,
        "as_of_source": "request" if as_of else "setting" if config.AS_OF_DATE else "newest record in the data",
        "ai_enabled": ai.enabled(), "ai_model": config.OPENAI_MODEL if ai.enabled() else None,
        "engineers": config.ENGINEERS, "own_operator": config.OWN_OPERATOR,
        "load_summary": db.get_meta("load_summary"),
        "assumptions": [
            {"id": "mmel", "text": "Deferral categories B, C and D are counted as 3, 10 and 120 calendar days "
                                   "(standard MMEL practice). The MMEL repair-interval page is not in the data pack: confirm it."},
            {"id": "tools", "text": ("Nearly every tool shows the same expiry date" + (f" ({placeholder})" if placeholder else "")
                                     + ", which looks like an export placeholder. Calibration is shown as unverified.")},
            {"id": "stores", "text": "Only condition code US is treated as unserviceable, and the Owner column decides ownership. "
                                      "Confirm both with Stores."},
            {"id": "roster", "text": "There is no roster in the data. Aircraft are split between engineers automatically, "
                                      "only for the demo."},
            {"id": "notes", "text": "Handover notes are derived from work-log entries of the last two days. "
                                    "No real handover records were provided."},
        ] + ([{"id": "cutoff", "text": f"Open work orders whose deadline was before {config.CLOSE_DEADLINES_BEFORE} "
                                       "are treated as closed: the work is assumed done but never closed in the source "
                                       "system. Records already closed in the data are not changed."}]
             if config.CLOSE_DEADLINES_BEFORE else []),
    }


@router.get("/audit")
def audit(limit: int = Query(100, ge=1, le=500)):
    return context.recent_log(limit)


# ------------------------------------------------------------ parts and tools
@router.get("/parts/search")
def parts_search(q: str = "", stores: list[str] | None = Query(None), own_only: bool = False,
                 include_unserviceable: bool = True, x_user: str | None = Header(None)):
    result = parts_service.search(q, stores, own_only, include_unserviceable)
    if result["query"]:
        context.log(_actor(x_user), "parts_search",
                    {"query": result["query"], "parts_found": result.get("parts_found", 0),
                     "stores": stores, "own_only": own_only, "include_unserviceable": include_unserviceable})
    return result


@router.get("/tools/search")
def tools_search(q: str = "", where: str | None = Query(None, pattern="^(line|main)$"),
                 as_of: str | None = None, x_user: str | None = Header(None)):
    result = tools_service.search(q, context.resolve_as_of(as_of), where)
    if result["query"]:
        context.log(_actor(x_user), "tools_search", {"query": result["query"], "where": where, "found": result["total"]})
    return result


# ------------------------------------------------------------------ aircraft
@router.get("/aircraft")
def aircraft_list(as_of: str | None = None):
    return aircraft_service.list_aircraft(context.resolve_as_of(as_of))


@router.get("/aircraft/{reg}")
def aircraft_detail(reg: str, as_of: str | None = None, x_user: str | None = Header(None)):
    reg = reg.upper()
    detail = aircraft_service.aircraft_detail(reg, context.resolve_as_of(as_of))
    context.log(_actor(x_user), "aircraft_view", {"aircraft": reg})
    return detail


@router.get("/workorders/{wo_number}")
def work_order(wo_number: int):
    row = aircraft_service.work_order_full(wo_number)
    if not row:
        raise HTTPException(404, f"Work order {wo_number} not found")
    return row


@router.get("/faults/{wo_number}/keywords")
def fault_keywords(wo_number: int):
    """Words to search the parts list with. AI suggestion if enabled, else a simple fallback."""
    row = aircraft_service.work_order_full(wo_number)
    if not row:
        raise HTTPException(404, f"Work order {wo_number} not found")
    text = (row["wo_description"] or "").split(" | ")[0]
    method = "simple"
    words: list[str] = []
    if ai.enabled():
        try:
            words, method = ai.suggest_keywords(text), "ai"
        except Exception:
            words = []
    if not words:
        words, method = heuristic_keywords(text), "simple"
    return {"wo_number": wo_number, "fault": text[:300], "keywords": words, "method": method,
            "note": "A suggestion only. Change the words if they are wrong."}


@router.get("/faults/{wo_number}/amm")
def fault_amm(wo_number: int):
    """AMM tasks named in the work order text, with the tools, consumables and parts each one uses."""
    res = amm_service.for_work_order(wo_number)
    if res is None:
        raise HTTPException(404, f"Work order {wo_number} not found")
    return res


@router.get("/amm/tasks/{base_task}")
def amm_task(base_task: str):
    res = amm_service.get_task(base_task)
    if res is None:
        raise HTTPException(404, f"AMM task {base_task} not found")
    return res


# --------------------------------------------------------------- roster, brief
class RosterChange(BaseModel):
    aircraft_reg: str
    engineer: str | None = Field(None, description="empty/None removes the aircraft from the shift")
    shift_date: str | None = None


@router.get("/roster")
def roster(shift_date: str | None = None):
    sd = context.resolve_as_of(shift_date)
    return {"shift_date": sd, "assignments": brief_service.get_roster(sd), "engineers": config.ENGINEERS}


@router.post("/roster/auto")
def roster_auto(shift_date: str | None = None, x_user: str | None = Header(None)):
    sd = context.resolve_as_of(shift_date)
    mapping = brief_service.auto_roster(sd, context.resolve_as_of(shift_date))
    context.log(_actor(x_user), "roster_auto", {"shift_date": sd, "assignments": mapping})
    return {"shift_date": sd, "assignments": mapping}


@router.put("/roster")
def roster_change(change: RosterChange, x_user: str | None = Header(None)):
    sd = context.resolve_as_of(change.shift_date)
    reg = change.aircraft_reg.upper()
    before = brief_service.get_roster(sd).get(reg)
    brief_service.set_assignment(sd, reg, (change.engineer or "").strip() or None)
    context.log(_actor(x_user), "roster_change",
                {"shift_date": sd, "aircraft": reg, "before": before, "after": (change.engineer or None)})
    return {"shift_date": sd, "assignments": brief_service.get_roster(sd)}


@router.get("/brief")
def brief(as_of: str | None = None, x_user: str | None = Header(None)):
    resolved = context.resolve_as_of(as_of)
    result = brief_service.build_brief(resolved)
    context.log(_actor(x_user), "brief_view",
                {"as_of": resolved, "aircraft": result["shift_counts"]["aircraft"], "flags": result["shift_counts"]["flags"]})
    return result


class Ack(BaseModel):
    wo_number: int
    note: str = Field("", max_length=500)


@router.post("/flags/ack")
def flag_ack(body: Ack, x_user: str | None = Header(None)):
    """The engineer confirms they have seen a flag. The agent never closes or changes the item."""
    if not aircraft_service.work_order_full(body.wo_number):
        raise HTTPException(404, f"Work order {body.wo_number} not found")
    context.log(_actor(x_user), "ack_flag", {"wo_number": body.wo_number, "note": body.note},
                [{"file": "Maintenance_History.xlsx", "wo_number": body.wo_number}])
    return {"ok": True}


class Done(BaseModel):
    wo_number: int
    note: str = Field(..., min_length=3, max_length=2000)
    as_of: str | None = None


@router.post("/workorders/done")
def work_order_done(body: Done, x_user: str | None = Header(None)):
    """An engineer marks an open work order as done, with a work-log note. The source data is not changed:
    the completion is stored in the app's own table and the work order then counts as closed."""
    row = aircraft_service.work_order_full(body.wo_number)
    if not row:
        raise HTTPException(404, f"Work order {body.wo_number} not found")
    if row["wo_state"] != "Open":
        raise HTTPException(409, f"Work order {body.wo_number} is already {row['wo_state']} in the data")
    actor = _actor(x_user)
    if actor == "unknown":
        raise HTTPException(400, "Type your name in the top bar first: completions must show who did the work")
    on = context.resolve_as_of(body.as_of)
    done = aircraft_service.complete_work_order(body.wo_number, body.note.strip(), actor, on)
    context.log(actor, "work_done", {"wo_number": body.wo_number, "aircraft": row["aircraft_reg"],
                                     "completed_on": on, "note": done["note"]},
                [{"file": "Maintenance_History.xlsx", "row": row["source_row"], "wo_number": body.wo_number}])
    return done


@router.delete("/workorders/{wo_number}/done")
def work_order_undo(wo_number: int, x_user: str | None = Header(None)):
    before = aircraft_service.undo_completion(wo_number)
    if not before:
        raise HTTPException(404, f"Work order {wo_number} was not marked as done in this app")
    context.log(_actor(x_user), "work_done_undo", {"wo_number": wo_number, "removed_note": before["note"],
                                                   "was_done_by": before["completed_by"]})
    return {"ok": True}


# ------------------------------------------------------------------------- AI
class AircraftAsk(BaseModel):
    aircraft_reg: str
    question: str | None = Field(None, max_length=500)
    as_of: str | None = None


class PartsAsk(BaseModel):
    query: str
    question: str = Field(..., max_length=500)


def _ai_guard():
    if not ai.enabled():
        raise HTTPException(503, "AI is off. Add OPENAI_API_KEY to the .env file and restart the backend.")


@router.post("/ai/aircraft")
def ai_aircraft(body: AircraftAsk, x_user: str | None = Header(None)):
    _ai_guard()
    reg = body.aircraft_reg.upper()
    detail = aircraft_service.aircraft_detail(reg, context.resolve_as_of(body.as_of))
    try:
        result = ai.summarise_aircraft(detail, body.question)
    except Exception as exc:
        raise HTTPException(502, f"The AI service could not answer: {exc}")
    context.log(_actor(x_user), "ai_aircraft", {"aircraft": reg, "question": body.question, "answer": result["answer"],
                                                "citations_ok": result["citations"]["ok"]},
                [{"records": result["records_sent"]}])
    return result


@router.post("/ai/parts")
def ai_parts(body: PartsAsk, x_user: str | None = Header(None)):
    _ai_guard()
    found = parts_service.search(body.query)
    rows = [r for p in found["parts"] for r in p["rows"]]
    if not rows:
        raise HTTPException(404, "No stock rows match that search.")
    try:
        result = ai.answer_parts(body.question, rows)
    except Exception as exc:
        raise HTTPException(502, f"The AI service could not answer: {exc}")
    context.log(_actor(x_user), "ai_parts", {"query": body.query, "question": body.question, "answer": result["answer"],
                                             "citations_ok": result["citations"]["ok"]},
                [{"records": result["records_sent"]}])
    return result
