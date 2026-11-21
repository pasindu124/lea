"""Read the Airbus AMM (SGML) delivery and store, per maintenance task, the tools, consumables,
expendable parts (replace-every-time parts), warnings and references.

    python -m app.etl.extract_amm                 # parse + load into the database
    python -m app.etl.extract_amm --dump amm.json # parse only, write a JSON file (no database needed)

It is also run by `python -m app.etl.load_data` (dataset "amm"). AMM.SGM is ~300 MB and is read through
mmap, one TASK at a time, so memory stays small. The SGML is not valid XML, so tasks are read with
regular expressions on the tags documented in the Airbus SGML Data User Guide (data/.../USER_GUIDE).
"""
from __future__ import annotations

import argparse
import html
import json
import mmap
import re
from pathlib import Path
from typing import Iterator

from .. import config
from ..rules.amm import function_label

SGM_GLOB = "**/SGML/AMM.SGM"
TASK_START = re.compile(rb"<TASK ([^>]*)>")
ATTR = re.compile(r'([A-Z]+)="([^"]*)"')
TAG = re.compile(r"<[^>]+>")
ENTITY_REF = re.compile(r"&([WC]\.\d+);")


def clean(fragment: str) -> str:
    """Tags out, entities decoded, spaces collapsed."""
    text = html.unescape(TAG.sub(" ", fragment))
    return re.sub(r"\s+", " ", text).strip(" -")


def load_notes(sgml_dir: Path) -> dict[str, str]:
    """Warning (W.1234) and caution (C.1234) texts from the AMM.SWE / AMM.SCE entity files."""
    notes: dict[str, str] = {}
    for name in ("AMM.SWE", "AMM.SCE"):
        p = sgml_dir / name
        if not p.exists():
            continue
        raw = p.read_text(encoding="latin1")
        for m in re.finditer(r'<!ENTITY\s+([WC]\.\d+)\s+"(.*?)"\s*>', raw, re.S):
            notes[m.group(1)] = clean(m.group(2))
    return notes


def _torque(cell: str) -> str:
    """'Torque wrench: range <TOR><TORVALUE MIN=.. MAX=.. UNIT=..>' -> 'Torque wrench 0.3 to 0.35 m.daN'."""
    m = re.search(r'<TORVALUE MAX="([^"]*)" MIN="([^"]*)" UNIT="([^"]*)"', cell) or \
        re.search(r'<TORVALUE[^>]*MIN="([^"]*)"[^>]*MAX="([^"]*)"[^>]*UNIT="([^"]*)"', cell)
    base = clean(re.sub(r"<TOR>.*?</TOR>", "", cell, flags=re.S)).replace("range", "").strip(" :")
    if not m:
        return base
    hi, lo, unit = m.groups() if 'MAX="' in m.group(0).split("MIN")[0] else (m.group(2), m.group(1), m.group(3))
    return f"{base} {lo} to {hi} {unit}"


def _rows(table: str) -> Iterator[list[str]]:
    table = re.sub(r"<THEAD>.*?</THEAD>", "", table, flags=re.S)
    for row in re.findall(r"<ROW[ >].*?</ROW>", table, re.S):
        yield re.findall(r"<ENTRY[^>]*>(.*?)</ENTRY>", row, re.S)


def _section_tables(tfmatr: str) -> Iterator[tuple[str, str]]:
    for item in re.findall(r"<L1ITEM>(.*?)</L1ITEM>", tfmatr, re.S):
        m = re.match(r"\s*<PARA>(.*?)</PARA>", item, re.S)
        if m and "<TABLE" in item:
            yield clean(m.group(1)), item


def parse_items(tfmatr: str) -> list[dict]:
    """Rows of the job set-up tables: tools, consumables, expendable parts, referenced tasks."""
    items: list[dict] = []
    for title, section in _section_tables(tfmatr):
        low = title.lower()
        if low.startswith("fixtures"):
            kind = "tool"
        elif low.startswith("consumable"):
            kind = "consumable"
        elif low.startswith("expendable") or low.startswith("replacement") or low.startswith("spare"):
            kind = "part"
        elif low.startswith("referenced"):
            kind = "reference"
        else:
            continue
        for cells in _rows(section):
            if kind == "tool" and len(cells) >= 3:
                ref = clean(cells[0])
                tool_no = re.search(r"<TOOLNBR>(.*?)</TOOLNBR>", cells[0], re.S)
                ref = clean(tool_no.group(1)) if tool_no else ("" if ref.lower().startswith("no specific") else ref)
                items.append({"kind": kind, "ref": ref or None, "qty": clean(cells[1]) or None,
                              "designation": _torque(cells[2]) if "<TOR>" in cells[2] else clean(cells[2]), "extra": None})
            elif kind == "tool" and len(cells) == 2:  # torque wrench rows have no quantity cell
                items.append({"kind": kind, "ref": None, "qty": None, "designation": _torque(cells[1]), "extra": None})
            elif kind == "consumable" and len(cells) >= 2:
                items.append({"kind": kind, "ref": clean(cells[0]) or None, "qty": None,
                              "designation": clean(cells[1]), "extra": None})
            elif kind == "part" and len(cells) >= 3:
                items.append({"kind": kind, "ref": clean(cells[0]) or None, "qty": None,
                              "designation": clean(cells[1]), "extra": clean(cells[2]) or None})
            elif kind == "reference" and len(cells) >= 2:
                ref = clean(cells[0])
                if re.match(r"\d{2}-\d{2}-", ref):
                    items.append({"kind": kind, "ref": ref, "qty": None, "designation": clean(cells[1]), "extra": None})
    return items


def parse_task(chunk: str, attrs: dict[str, str], notes: dict[str, str]) -> dict:
    """One <TASK>...</TASK> block -> a plain dict ready for the database."""
    base = "-".join([attrs["CHAPNBR"], attrs["SECTNBR"], attrs["SUBJNBR"], attrs["FUNC"], attrs["SEQ"]])
    title = re.search(r"<TITLE>(.*?)</TITLE>", chunk, re.S)
    tf = re.search(r"<TFMATR>.*?</TFMATR>", chunk, re.S)
    note_list: list[dict] = []
    seen: set[str] = set()
    for code in ENTITY_REF.findall(chunk):
        if code in seen or code not in notes:
            continue
        seen.add(code)
        note_list.append({"kind": "warning" if code.startswith("W") else "caution", "code": code, "text": notes[code]})
    fins = sorted(set(clean(f) for f in re.findall(r"<EIN[^>]*>(.*?)</EIN>", chunk, re.S)))
    zones = sorted(set(clean(z) for z in re.findall(r"<ZONE>(.*?)</ZONE>", chunk, re.S)))
    identical = re.search(r"IDENTICAL TASK[^<]{0,400}", chunk, re.I)
    return {
        "task_no": f"{base}-{attrs.get('CONFLTR', 'A')}" + (f"-{attrs['VARNBR']}" if attrs.get("VARNBR") else ""),
        "base_task": base,
        "title": clean(title.group(1)) if title else base,
        "ata": f"{attrs['CHAPNBR']}-{attrs['SECTNBR']}-{attrs['SUBJNBR']}",
        "function_code": attrs["FUNC"], "function_label": function_label(attrs["FUNC"]),
        "config": attrs.get("CONFLTR", "A") + (f" v{attrs['VARNBR']}" if attrs.get("VARNBR") else ""), "rev_date": attrs.get("REVDATE"),
        "fins": fins, "zones": zones,
        "identical_task_note": clean(identical.group(0)) if identical else None,
        "items": parse_items(tf.group(0)) if tf else [], "notes": note_list,
    }


def iter_tasks(sgm: Path) -> Iterator[dict]:
    notes = load_notes(sgm.parent)
    with open(sgm, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        for m in TASK_START.finditer(mm):
            end = mm.find(b"</TASK>", m.end())
            attrs = dict(ATTR.findall(m.group(1).decode("latin1")))
            if end < 0 or not {"CHAPNBR", "SECTNBR", "SUBJNBR", "FUNC", "SEQ"} <= attrs.keys():
                continue
            yield parse_task(mm[m.start():end].decode("latin1"), attrs, notes)


def find_sgm(data_dir: Path) -> Path | None:
    hits = sorted(data_dir.glob(SGM_GLOB))
    return hits[0] if hits else None


def load_amm(files: list[Path]) -> int:
    """Used by load_data: tables are emptied by the caller (amm_tasks cascades to the other two)."""
    from .. import db
    sgm = files[0]
    n = 0
    with db.get_pool().connection() as conn, conn.cursor() as cur:
        for t in iter_tasks(sgm):
            cur.execute(
                "INSERT INTO amm_tasks (task_no, base_task, title, ata, function_code, function_label, config, rev_date, "
                "fins, zones, identical_task_note, source_file) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (task_no) DO NOTHING",
                (t["task_no"], t["base_task"], t["title"], t["ata"], t["function_code"], t["function_label"],
                 t["config"], t["rev_date"], t["fins"], t["zones"], t["identical_task_note"], sgm.name))
            if cur.rowcount == 0:
                continue
            n += 1
            for pos, it in enumerate(t["items"]):
                cur.execute("INSERT INTO amm_task_items (task_no, pos, kind, ref, qty, designation, extra) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            (t["task_no"], pos, it["kind"], it["ref"], it["qty"], it["designation"], it["extra"]))
            for pos, nt in enumerate(t["notes"]):
                cur.execute("INSERT INTO amm_task_notes (task_no, pos, kind, code, text) VALUES (%s,%s,%s,%s,%s)",
                            (t["task_no"], pos, nt["kind"], nt["code"], nt["text"]))
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    ap.add_argument("--dump", type=Path, help="write the parsed tasks to this JSON file and skip the database")
    args = ap.parse_args()
    sgm = find_sgm(args.data_dir)
    if not sgm:
        raise SystemExit(f"No AMM.SGM found under {args.data_dir} (looked for {SGM_GLOB})")
    if args.dump:
        tasks = list(iter_tasks(sgm))
        args.dump.write_text(json.dumps(tasks, indent=1), encoding="utf-8")
        print(f"{len(tasks):,} tasks written to {args.dump}")
        return
    from .. import db
    db.apply_schema()
    db.execute("TRUNCATE amm_tasks RESTART IDENTITY CASCADE")
    print(f"{load_amm([sgm]):,} tasks loaded from {sgm}")


if __name__ == "__main__":
    main()
