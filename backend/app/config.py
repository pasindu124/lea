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
# ASSUMPTION: standard Airbus/EASA MMEL repair intervals, counted in calendar days
# and not counting the day the fault was found. The MMEL pages that define them
# (MI-00-05) are NOT in the data pack: confirm before operational use.
CATEGORY_DAYS = {"B": 3, "C": 10, "D": 120}
SOON_DAYS = 3                 # "expires soon" threshold, in days
