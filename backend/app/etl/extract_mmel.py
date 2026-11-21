"""Read the Airbus MMEL XML (Master Minimum Equipment List) into PostgreSQL.

    python -m app.etl.load_data --only mmel

Expected layout (unpack Part_1 (4)/XML_000043031700.tar from the data pack's
XML_C_Ops_MMEL zip into data/, keeping the DATA folder):

    data/<any>/DATA/XML_N_MMEL_ABY_..._mdata.xml   fleet list: registration -> MSN, issue date
    data/<any>/DATA/XML_N_MMEL_ABY_....xml         contents: document code -> item number
    data/<any>/DATA/DU/*.xml                       one file per item version or ECAM warning
    data/<any>/DATA/MU/*_mdata.xml                 applicability (MSN list) per file

Fills: mmel_items (one row per dispatch condition and item version), mmel_ecam
(ECAM warning -> MMEL item or "no dispatch"), fleet_msn (registration -> MSN).
Reference data only: nothing here decides anything.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .. import db
from ..rules import mmel as rules

_SPACE = re.compile(r"\s+")
_LINK_ITEM = re.compile(r"Item\s+(\d{2}-\d{2}-\d{2}(?:-\d{2})?[A-Z]?)")


def _norm(text: str | None) -> str:
    return _SPACE.sub(" ", text or "").strip()


def _text(elem: ET.Element | None, inventory: dict[str, str]) -> str:
    """Element text with MMEL cross-references written out ("Refer to Item 36-11-01")."""
    if elem is None:
        return ""
    parts: list[str] = [elem.text or ""]
    for child in elem:
        if child.tag == "duref":
            link = child.find("linktext")
            if link is not None:
                parts.append("Refer to " + _norm("".join(link.itertext())))
            elif child.get("product") == "MMEL" and child.get("ref") in inventory:
                parts.append(f"Refer to Item {inventory[child.get('ref')]}")
        else:
            parts.append(_text(child, inventory))
        parts.append(child.tail or "")
    return _norm(" ".join(parts))


# ------------------------------------------------------------ pure parsers (tested)
def parse_fleet(product_mdata_xml: str) -> tuple[str | None, list[dict]]:
    """(issue date "2026-08-19", [{aircraft_reg, msn, model}]) from the product metadata."""
    root = ET.fromstring(product_mdata_xml)
    issue = (root.get("revdate") or "")[:10] or None
    fleet = [{"aircraft_reg": a.get("acn"), "msn": a.get("msn"), "model": a.get("aircraft-model")}
             for a in root.iter("aircraft-item") if a.get("acn") and a.get("msn")]
    return issue, fleet


def parse_inventory(product_xml: str) -> dict[str, str]:
    """Document code -> item number, e.g. "00008798" -> "36-11-07"."""
    root = ET.fromstring(product_xml)
    return {inv.get("code"): inv.get("func-code") for inv in root.iter("du-inv") if inv.get("func-code")}


def parse_effect(mu_xml: str) -> list[str]:
    """Applicable MSN tokens for one document version (closed list only, not future aircraft)."""
    root = ET.fromstring(mu_xml)
    tokens: list[str] = []
    for eff in root.iter("effact"):
        if eff.find("all") is not None:
            return [rules.ALL_AIRCRAFT]
        for rng in eff.iter("aircraft-range"):
            tokens += rules.msn_tokens(rng.text)
    return tokens


def parse_dispatch_item(du_xml: str, inventory: dict[str, str]) -> list[dict]:
    """One dict per dispatch condition (36-11-07A, 36-11-07B, ...). [] if not a dispatch item."""
    root = ET.fromstring(du_xml)
    if root.tag != "dispatchitem":
        return []
    func = root.get("func-code")
    body = root.find("ditembody")
    installed = body.get("nb-installed") if body is not None else None
    rows = []
    for cond in root.iter("dispcond"):
        label = cond.get("dispcond-label")
        normal = cond.find("normal-dispcond")
        redirect = cond.find("dispatch-redirection")
        if normal is not None:
            paras = [_text(p, inventory) for p in normal.iter("para")]
            interval = normal.get("rectification-interval")
            required = normal.get("nb-required")
        else:
            paras = [_text(redirect, inventory)] if redirect is not None else []
            interval = required = None
        scope = normal if normal is not None else cond
        rows.append({
            "item_code": rules.item_code(func, label),
            "base_item": func,
            "du_code": root.get("code"),
            "item_title": _norm("".join(root.find("title").itertext())) if root.find("title") is not None else None,
            "condition_title": _norm("".join(cond.find("title").itertext())) if cond.find("title") is not None else None,
            "repair_interval": interval if interval in ("A", "B", "C", "D") else None,
            "nb_installed": installed if installed not in (None, "-") else None,
            "nb_required": required if required not in (None, "-") else None,
            "placard": scope.find(".//placard") is not None,
            "ops_proc": scope.find(".//opsproc-ref") is not None,
            "maint_proc": scope.find(".//maintenance-ref") is not None,
            "requirements": "\n".join(p for p in paras if p) or None,
            "amm_tasks": [rules.amm_task_no(t.get("chap-nbr"), t.get("sect-nbr"), t.get("subj-nbr"),
                                            t.get("func"), t.get("seq"))
                          for t in scope.iter("taskref") if t.get("product") == "AMM Task"],
            "qualifiers": [q.get("value") for q in scope.iter("qualifier") if q.get("value")],
            "rev_date": (root.get("revdate") or "")[:10] or None,
        })
    return rows


# First child of <dispatch-assessment> -> outcome. "dablock" combines several items (AND/OR);
# "complementary-actions" only routes to nested conditions, which are read as their own rows.
_OUTCOMES = {"dispatchitemref": "ITEM", "dablock": "ITEM", "no-dispatch": "NO_DISPATCH",
             "not-applicable": "NOT_APPLICABLE", "complementary-actions": "SEE_CONDITIONS"}


def parse_malfunction(du_xml: str, inventory: dict[str, str]) -> list[dict]:
    """ECAM warning -> what the MMEL says: an item, "no dispatch" or "not applicable"."""
    root = ET.fromstring(du_xml)
    if root.tag != "malfunctionassessment":
        return []
    codes = [_norm(c) for c in (root.get("fault-code") or "").split(";") if _norm(c)]
    title = _text(root.find("xtitle"), inventory) or None
    rows = []
    for assess in root.iter("assessment"):
        # Direct children only: nested assessments (inside complementary-actions) are visited by root.iter.
        condition = _text(assess.find("routing/cond-routing/intro"), inventory) or None
        for da in assess.findall("dispatch-assessment"):
            first = da[0] if len(da) else None
            kind = _OUTCOMES.get(first.tag, "OTHER") if first is not None else "OTHER"
            refs = ([(d.find("linktext"), d.get("ref")) for d in first.iter("duref") if d.get("product") == "MMEL"]
                    if kind == "ITEM" else [])
            note = condition
            if first is not None and first.tag == "dablock":
                joined = "all of these items" if first.get("operator") == "AND" else "one of these items"
                note = f"{condition or ''} ({joined})".strip()
            items = []
            for link, ref in refs:
                m = _LINK_ITEM.search(_norm("".join(link.itertext()))) if link is not None else None
                items.append(m.group(1) if m else inventory.get(ref))
            for code in codes or [title]:
                for item in (items or [None]):
                    rows.append({"fault_code": code, "warning_title": title, "condition": note,
                                 "outcome": kind, "item_code": item, "du_code": root.get("code")})
    return rows


# --------------------------------------------------------------------- loader
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_mmel(files: list[Path]) -> int:
    """`files` = the product metadata file(s) found by load_data. Returns mmel_items rows."""
    mdata_file = files[0]
    data_dir = mdata_file.parent
    product_file = mdata_file.with_name(mdata_file.name.replace("_mdata.xml", ".xml"))
    issue, fleet = parse_fleet(_read(mdata_file))
    inventory = parse_inventory(_read(product_file)) if product_file.exists() else {}

    items, ecam = [], []
    for du in sorted((data_dir / "DU").glob("*.xml")):
        text = _read(du)
        mu = data_dir / "MU" / f"{du.stem}_mdata.xml"
        msns = parse_effect(_read(mu)) if mu.exists() else []
        for row in parse_dispatch_item(text, inventory):
            items.append({**row, "msn_ranges": msns, "issue_date": issue, "source_file": f"DU/{du.name}"})
        for row in parse_malfunction(text, inventory):
            ecam.append({**row, "source_file": f"DU/{du.name}"})

    with db.get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE mmel_items, mmel_ecam, fleet_msn RESTART IDENTITY")
            if items:
                cols = list(items[0])
                cur.executemany(f"INSERT INTO mmel_items ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                                [tuple(r[c] for c in cols) for r in items])
            if ecam:
                cols = list(ecam[0])
                cur.executemany(f"INSERT INTO mmel_ecam ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                                [tuple(r[c] for c in cols) for r in ecam])
            cur.executemany("INSERT INTO fleet_msn (aircraft_reg, msn, model, source_file) VALUES (%s, %s, %s, %s) "
                            "ON CONFLICT (aircraft_reg) DO NOTHING",
                            [(a["aircraft_reg"], a["msn"], a["model"], mdata_file.name) for a in fleet])
    print(f"    mmel: issue {issue}, {len(items):,} dispatch conditions, {len(ecam):,} ECAM links, "
          f"{len(fleet)} aircraft")
    db.set_meta("mmel_issue", issue)
    return len(items)
