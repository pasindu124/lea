"""All settings and business rules in one place.

Anything marked ASSUMPTION is something the team guessed and must confirm with
Air Arabia (Stores, Planning, Quality) before real operational use.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(PROJECT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://lea:lea@localhost:5432/lea")
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_DIR / "data"))
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Optional shared password for a public demo (HTTP Basic, any user name). Empty = no password.
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "")

# Optional manual override of "today" (YYYY-MM-DD). Normally the app uses the
# date of the newest record, so a demo on old data still tells a sensible story.
AS_OF_DATE = os.getenv("AS_OF_DATE", "")

ENGINEERS = [e.strip() for e in os.getenv("ENGINEERS", "Engineer 1,Engineer 2,Engineer 3").split(",") if e.strip()]
AIRCRAFT_PER_SHIFT = int(os.getenv("AIRCRAFT_PER_SHIFT", "10"))

# ---------------------------------------------------------------- fleet rules
OWN_OPERATOR = "ABY"          # Air Arabia
OWN_REG_PREFIX = "A6-"        # Air Arabia (Sharjah) registrations

# ----------------------------------------------------------------- store rules
LINE_STORE = "SHJLINE"        # parts store next to the aircraft
MAIN_STORE = "SHJMAIN"        # main base parts store
TOOL_LINE_STORE = "LINEWH"    # tools at the line
TOOL_MAIN_STORE = "SHJMAINW"  # tools at the main workshop

# ASSUMPTION: only "US" means unserviceable. Confirm every condition code with Stores.
UNSERVICEABLE_CODES = {"US"}

# ------------------------------------------------------------- deferral rules
# MMEL repair intervals in calendar days, not counting the day the fault was found.
# Source: Airbus MMEL page MI-00-05 (ABY fleet MMEL, issue 19 AUG 26, in the data pack).
# ASSUMPTION still: Air Arabia's own MEL uses the same intervals (the operator MEL is not in the pack).
CATEGORY_DAYS = {"B": 3, "C": 10, "D": 120}
SOON_DAYS = 3                 # "expires soon" threshold, in days

# ASSUMPTION: open work orders whose deferral deadline is before this date were done but never
# closed in the source system, so the app treats them as closed. Records already closed in the
# data are not touched. Empty = off. Format YYYY-MM-DD.
CLOSE_DEADLINES_BEFORE = os.getenv("CLOSE_DEADLINES_BEFORE", "")

# ------------------------------------------------------------- flight schedule
STATION = os.getenv("STATION", "SHJ")   # the base where the line engineers work

# ASSUMPTION: the file does not say whether its times are UTC or Sharjah local time. Default: local, as written.
# Set FLIGHT_TIMES_ARE=utc if Planning says the export is in UTC (then LOCAL_UTC_OFFSET_HOURS is added).
FLIGHT_TIMES_ARE = os.getenv("FLIGHT_TIMES_ARE", "local").strip().lower()
LOCAL_UTC_OFFSET_HOURS = float(os.getenv("LOCAL_UTC_OFFSET_HOURS", "4"))   # Sharjah = UTC+4


def _hhmm(value: str, fallback: str) -> tuple[int, int]:
    try:
        h, m = (value or fallback).strip().split(":")
        return int(h), int(m)
    except ValueError:
        h, m = fallback.split(":")
        return int(h), int(m)


# ASSUMPTION: the night shift runs 22:00 to 06:00 Sharjah local time (confirm with Planning).
SHIFT_START = _hhmm(os.getenv("SHIFT_START", "22:00"), "22:00")
SHIFT_END = _hhmm(os.getenv("SHIFT_END", "06:00"), "06:00")
# ASSUMPTION: an aircraft counts as "on the ground during the shift" when it is at the station for at least
# this many minutes inside the shift window. Shorter overlaps are ignored.
MIN_GROUND_MINUTES = int(os.getenv("MIN_GROUND_MINUTES", "30"))
# A ground time under this many hours is shown as tight (amber) and used for the overlap warning.
SHORT_GROUND_HOURS = float(os.getenv("SHORT_GROUND_HOURS", "2"))
