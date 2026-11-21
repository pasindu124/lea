"""Load the hackathon data files into PostgreSQL.

    python -m app.etl.load_data                 # everything found in ./data
    python -m app.etl.load_data --only parts,tools
    python -m app.etl.load_data --data-dir D:\\hackathon\\data

Safe to re-run: the data tables are emptied and re-filled. The audit log,
roster and settings tables are never touched.
"""
from __future__ import annotations

import argparse
import re
import time
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd

from .. import config, db
from ..rules import tools as tool_rules

# Patterns tolerate both "Inventory_List.xlsx" and "Inventory List.xlsx".
PATTERNS = {
    "parts": ["*Inventory*List*.xlsx"],
    "tools": ["*Tools*SHJLINE*.xlsx", "*Tools*SHJMAIN*.xlsx"],
    "work_orders": ["*Maintenance*History*.xlsx"],
    "pha": ["*PHA*Case*Tracking*.csv"],
    "aviatar": ["*AVIATAR*Faults*.csv"],
}
TABLES = {"parts": "parts_stock", "tools": "tools", "work_orders": "work_orders",
          "pha": "pha_cases", "aviatar": "aviatar_faults"}


def find_files(data_dir: Path, key: str) -> list[Path]:
    found: dict[str, Path] = {}
    for pattern in PATTERNS[key]:
        for p in sorted(data_dir.glob(pattern)):
            if not p.name.startswith("~$"):
                found[p.name] = p
    return list(found.values())


def _clean(df: pd.DataFrame) -> list[tuple]:
    """DataFrame -> list of tuples with None for missing values (psycopg-friendly)."""
    obj = df.astype(object).where(df.notna(), None)
    return list(obj.itertuples(index=False, name=None))


def copy_rows(table: str, columns: list[str], df: pd.DataFrame) -> int:
    rows = _clean(df[columns])
    with db.get_pool().connection() as conn:
        with conn.cursor() as cur:
            with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as cp:
                for row in rows:
                    cp.write_row(row)
    return len(rows)


def _txt(series: pd.Series) -> pd.Series:
    return series.where(series.notna(), None).map(lambda v: None if v is None else str(v).strip() or None)


def _date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.date.where(pd.to_datetime(series, errors="coerce").notna(), None)


# ------------------------------------------------------------------ loaders
def load_parts(files: list[Path]) -> int:
    df = pd.read_excel(files[0], dtype=str)
    df.columns = [c.strip() for c in df.columns]
    out = pd.DataFrame({
        "source_row": df.index + 2,
        "store": _txt(df["Store"]), "location": _txt(df["Location"]), "part_no": _txt(df["Part No.:"]),
        "serial": _txt(df["Serial/Batch No."]), "description": _txt(df["Description"]),
        "mat_class": _txt(df["Mat. Class"]),
        "qty": pd.to_numeric(df["Qty"], errors="coerce").fillna(0.0),
        "cond": _txt(df["Cond."]), "order_no": _txt(df["Order No."]), "rec_date": _date(df["Rec. Date"]),
        "owner": _txt(df["Owner"]), "entity": _txt(df["Entity"]),
    })
    out = out[out["part_no"].notna()]
    return copy_rows("parts_stock", list(out.columns), out)


def load_tools(files: list[Path]) -> int:
    total = 0
    for f in files:
        df = pd.read_excel(f, dtype=str)
        df.columns = [c.strip() for c in df.columns]
        out = pd.DataFrame({
            "source_file": f.name, "source_row": df.index + 2,
            "part_no": _txt(df["Part Number"]), "serial": _txt(df["SN/BN"]),
            "description": _txt(df["Description"]), "tool_id": _txt(df["ID"]),
            "mc": _txt(df["MC"]), "co": _txt(df["Co"]),
            "received": _date(df["Received"]), "expires": _date(df["Expires"]),
            "partly_rec": df["Partly Rec."].astype(str).str.upper().eq("TRUE"),
            "station": _txt(df["Station"]), "store": _txt(df["Store"]), "location": _txt(df["Location"]),
            "workload": _txt(df["Workload"]),
            "qty": pd.to_numeric(df["Qty"], errors="coerce").fillna(0.0),
        })
        total += copy_rows("tools", list(out.columns), out)
    return total


def load_work_orders(files: list[Path]) -> int:
    df = pd.read_excel(files[0], dtype={"ata": str, "wo_description": str, "wo_actions": str})
    out = pd.DataFrame({
        "source_row": df.index + 2,
        "wo_number": pd.to_numeric(df["wo_number"], errors="coerce").astype("Int64"),
        "aircraft_reg": _txt(df["aircraft_reg"]), "operator_code": _txt(df["operator_code"]),
        "wo_type": _txt(df["wo_type"]),
        "date_opened": _date(df["date_opened"]), "date_closed": _date(df["date_closed"]),
        "ata": _txt(df["ata"]), "wo_description": df["wo_description"].where(df["wo_description"].notna(), None),
        "wo_actions": df["wo_actions"].where(df["wo_actions"].notna(), None),
        "wo_state": _txt(df["wo_state"]),
    })
    return copy_rows("work_orders", list(out.columns), out)


def load_pha(files: list[Path]) -> int:
    df = pd.read_csv(files[0], encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    out = pd.DataFrame({
        "source_row": df.index + 2,
        "max_severity": _txt(df["Max Severity"]), "acreg": _txt(df["ACREG"]),
        "ata": pd.to_numeric(df["ATA"], errors="coerce").astype("Int64"),
        "use_case": _txt(df["Use Case"]), "title": _txt(df["Title"]), "system": _txt(df["System"]),
        "case_type": _txt(df["Case Type"]),
        "remarks": pd.to_numeric(df["Remarks"], errors="coerce").astype("Int64"),
        "classification": _txt(df["Classification"]), "impact": _txt(df["Impact"]),
        "opened": pd.to_datetime(df["Opened"], dayfirst=True, errors="coerce"),
        "updated": pd.to_datetime(df["Updated"], dayfirst=True, errors="coerce"),
        "status": _txt(df["Status"]), "case_link": _txt(df["Case File Link"]),
    })
    return copy_rows("pha_cases", list(out.columns), out)


def load_aviatar(files: list[Path]) -> int:
    frames = []
    for f in files:
        d = pd.read_csv(f, low_memory=False)
        d["source_file"] = f.name
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    before = len(df)
    df = df.drop_duplicates(subset=[c for c in df.columns if c != "source_file"])
    print(f"    aviatar: {before:,} rows read, {before - len(df):,} exact duplicates dropped")
    out = pd.DataFrame({
        "prio": _txt(df["Prio"]), "msg_code": pd.to_numeric(df["Msg Code"], errors="coerce"),
        "message": _txt(df["Message"]), "message_type": _txt(df["Message Type"]),
        "ac_type": _txt(df["A/C Type"]), "ac": _txt(df["A/C"]), "flight": _txt(df["Flight"]),
        "phase": pd.to_numeric(df["Phase"], errors="coerce").astype("Int64"),
        "ata": _txt(df["Ata"]), "source": _txt(df["Source"]),
        "occurrence": pd.to_datetime(df["Occurrence"], errors="coerce"),
        "repetitive": df["Repetitive"].astype(str).str.upper().eq("TRUE"),
        "multiple": df["Multiple"].astype(str).str.upper().eq("TRUE"),
        "source_file": df["source_file"],
    })
    return copy_rows("aviatar_faults", list(out.columns), out)


LOADERS: dict[str, Callable[[list[Path]], int]] = {
    "parts": load_parts, "tools": load_tools, "work_orders": load_work_orders,
    "pha": load_pha, "aviatar": load_aviatar,
}


# ---------------------------------------------------------------- derived meta
def update_meta() -> dict:
    wo = db.query_one("SELECT max(date_opened) AS d FROM work_orders") or {}
    av = db.query_one("SELECT max(occurrence)::date AS d FROM aviatar_faults") or {}
    candidates = [d for d in (wo.get("d"), av.get("d")) if d]
    as_of = max(candidates) if candidates else None

    expiries = [r["expires"] for r in db.query("SELECT expires FROM tools")]
    placeholder = tool_rules.detect_placeholder_expiry(expiries)

    counts = {t: db.query_one(f"SELECT count(*) AS n FROM {t}")["n"] for t in TABLES.values()}
    db.set_meta("as_of_default", as_of.isoformat() if as_of else None)
    db.set_meta("tools_placeholder_expiry", placeholder.isoformat() if placeholder else None)
    db.set_meta("load_summary", {"counts": counts, "loaded_at": time.strftime("%Y-%m-%d %H:%M:%S")})
    return {"as_of": as_of, "tools_placeholder_expiry": placeholder, "counts": counts}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    ap.add_argument("--only", default="", help="comma list of: " + ", ".join(LOADERS))
    args = ap.parse_args()

    wanted = [k.strip() for k in args.only.split(",") if k.strip()] or list(LOADERS)
    unknown = [k for k in wanted if k not in LOADERS]
    if unknown:
        raise SystemExit(f"Unknown dataset(s): {unknown}")

    print(f"Data folder: {args.data_dir}")
    db.apply_schema()
    for key in wanted:
        files = find_files(args.data_dir, key)
        if not files:
            print(f"  [skip] {key}: no file matching {PATTERNS[key]}")
            continue
        start = time.time()
        print(f"  [load] {key}: {', '.join(f.name for f in files)}")
        db.execute(f"TRUNCATE {TABLES[key]} RESTART IDENTITY")
        n = LOADERS[key](files)
        print(f"         {n:,} rows in {time.time() - start:.1f}s")

    info = update_meta()
    print("\nDone.")
    print(f"  Data as of           : {info['as_of']}")
    print(f"  Tool expiry placeholder: {info['tools_placeholder_expiry']}")
    print(f"  Row counts           : {info['counts']}")


if __name__ == "__main__":
    main()
