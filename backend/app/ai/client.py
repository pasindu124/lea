"""AI layer (OpenAI). It reads and writes; it never decides.

Rules enforced here:
  * The model only sees records the code already retrieved, each with a tag like [WO6232450].
  * It must cite those tags; answers are checked and flagged if they cite anything else.
  * It is told never to advise signing, deferring, releasing or changing a deferral.
  * Predictive (PHA) cases are described as read-only information.
"""
from __future__ import annotations

import json
from typing import Any

from .. import config
from ..rules import citations

GUARDRAILS = (
    "You support a licensed aircraft line engineer. You are an assistant, not a decision maker. "
    "Use ONLY the records provided. Cite every statement with the record tag in square brackets, "
    "for example [WO6232450] or [PHA12] or [AV1]. If the records do not answer, say so. "
    "Never advise signing, deferring, releasing, extending or closing anything. "
    "Predictive (PHA) cases are read-only early warnings: never present them as confirmed faults. "
    "Use plain, short sentences. Do not guess meanings of codes."
)


class AIUnavailable(RuntimeError):
    pass


def enabled() -> bool:
    return bool(config.OPENAI_API_KEY)


def _client():
    if not enabled():
        raise AIUnavailable("OPENAI_API_KEY is not set. Add it to the .env file and restart the backend.")
    from openai import OpenAI
    return OpenAI(api_key=config.OPENAI_API_KEY)


def _chat(system: str, user: str, json_mode: bool = False, client=None) -> str:
    client = client or _client()
    kwargs: dict[str, Any] = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(
        model=config.OPENAI_MODEL, temperature=0,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **kwargs)
    return (resp.choices[0].message.content or "").strip()


# -------------------------------------------------------------- aircraft summary
def aircraft_context(detail: dict) -> tuple[str, set[str]]:
    """Turn an aircraft detail into tagged text lines. Returns (text, allowed tags)."""
    tags: set[str] = set()
    lines = [f"Aircraft {detail['aircraft_reg']}, data as of {detail['as_of']}."]
    for item in detail["deferrals"][:15] + detail["other_faults"][:8]:
        tag = f"WO{item['wo_number']}"
        tags.add(tag)
        d = item["deferral"]
        extra = (f" DEFERRAL status={d['status']} ({d['status_text']}), deadline={d['expires_on'] or 'none'}, rule: {d['rule']}"
                 if d else " open fault, not deferred")
        lines.append(f"[{tag}] opened {item['date_opened']} ATA {item['ata']}: {item['title']}.{extra}")
    for p in detail["pha"][:5]:
        tag = f"PHA{p['source_row']}"
        tags.add(tag)
        lines.append(f"[{tag}] predictive case (read-only): {p['title']}, severity {p['max_severity']}, impact {p['impact']}, "
                     f"classification {p['classification']}")
    for g in detail["aviatar"]["groups"][:8]:
        tags.add(g["tag"])
        lines.append(f"[{g['tag']}] aircraft message {g['message']} (priority {g['prio']}, ATA {g['ata']}), "
                     f"{g['n']} times on {g['flights']} flights")
    for n in detail["notes"][:5]:
        tag = f"WO{n['wo_number']}"
        if tag in tags:
            continue
        tags.add(tag)
        lines.append(f"[{tag}] recent note {n['date']}: {n['text']}")
    return "\n".join(lines), tags


def summarise_aircraft(detail: dict, question: str | None = None, client=None) -> dict:
    text, tags = aircraft_context(detail)
    task = (f"Question from the engineer: {question}" if question else
            "Write a briefing of at most 120 words: what needs attention first, what can wait, and what to check.")
    answer = _chat(GUARDRAILS, f"{task}\n\nRecords:\n{text}", client=client)
    return {"answer": answer, "citations": citations.validate(answer, tags), "records_sent": sorted(tags)}


# ------------------------------------------------------------------ parts answer
def parts_context(rows: list[dict]) -> tuple[str, set[str]]:
    tags, lines = set(), []
    for r in rows:
        tag = f"R{r['source_row']}"
        tags.add(tag)
        lines.append(f"[{tag}] store={r['store']} location={r['location']} part={r['part_no']} serial={r['serial'] or '-'} "
                     f"desc={r['description']} qty={float(r['qty'] or 0):g} cond={r['cond'] or '-'} owner={r['owner'] or '-'}")
    return "\n".join(lines), tags


def answer_parts(question: str, rows: list[dict], client=None) -> dict:
    rows = rows[:40]
    text, tags = parts_context(rows)
    answer = _chat(GUARDRAILS + " Keep the answer under 100 words.",
                   f"Question: {question}\n\nStock rows:\n{text}", client=client)
    return {"answer": answer, "citations": citations.validate(answer, tags), "records_sent": sorted(tags)}


# ----------------------------------------------------------------- part keywords
def suggest_keywords(fault_text: str, client=None) -> list[str]:
    system = ("You help find spare parts. From the aircraft fault text, return JSON "
              '{"keywords": ["..."]} with 1 to 3 short words naming the physical component that probably '
              "needs replacing or repairing (for example BRAKE, VALVE, SEAT TABLE). No part numbers. "
              "If no component is clear, return an empty list.")
    raw = _chat(system, fault_text[:1500], json_mode=True, client=client)
    try:
        words = json.loads(raw).get("keywords", [])
    except (ValueError, AttributeError):
        return []
    return [str(w).strip().upper() for w in words if str(w).strip()][:3]
