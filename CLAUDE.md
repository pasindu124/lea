# Line Engineer Agent (Air Arabia hackathon, Round 1, Use Case 4)

Read this first. The team has little aircraft-maintenance background: explain domain terms in plain
language when you introduce them, and keep answers short.

## Goal
An agent that prepares a **night-shift brief** for each line engineer before the shift: what is urgent,
what can wait (MEL/NSI deferrals and their deadlines), open faults, aircraft messages, predictive alerts,
parts and tools availability. Every line links to its source record. Stretch goal (NOT built): check one
draft logbook entry, flag what is missing, cite the CAR-145 / CAR-M rule.
Judged on: one step ahead, right and explained, guardrails kept, useful on Monday, ready to grow.

## Guardrails (a demo that breaks one scores nothing)
1. NEVER sign, defer, release, extend or close anything. A licensed engineer does. The "Mark as seen"
   button only writes an audit row; the item stays open.
2. Only approved sources; show file and row. Anything else is "information only".
3. Every flag shows the rule behind it.
4. Log every suggestion and every change (`audit_log` table).
5. Supports learning: the trainee still does the thinking.
6. Predictive maintenance (PHA/AVIATAR) is READ ONLY.
Deadline maths, urgency ranking and verdicts are plain code in `backend/app/rules/`. The LLM only reads and
writes over records the code retrieved, must cite tags like [WO123], and `rules/citations.py` flags answers
that cite anything else. Never move a decision into the LLM.

## Architecture
React (Vite, JSX) -> FastAPI -> PostgreSQL 16, plus optional OpenAI (`backend/app/ai/client.py`).
- `backend/app/rules/`    pure functions with tests: deadlines, parts, tools, roster, citations, text
- `backend/app/services/` SQL + assembling the brief (psycopg 3, plain SQL, no ORM)
- `backend/app/routers/api.py` all routes under /api
- `backend/app/etl/load_data.py` loads the Excel/CSV files (`python -m app.etl.load_data`)
- `backend/app/config.py` every business rule and ASSUMPTION in one place
- `frontend/src/` pages in `pages/`, shared card in `AircraftCard.jsx`, tokens in `styles.css`
Run: see README.md. Tests: `cd backend && python -m pytest` (58 tests, uses its own `lea_test` database).
Frontend check: `cd frontend && npm run build`.

## Domain glossary
- MEL: list of items an aircraft may fly without for a limited time. Deferral: using it to postpone a fix.
  Categories (standard MMEL practice, ASSUMED): A = per item, B = 3 days, C = 10, D = 120 calendar days,
  not counting the day of discovery. NSI = a deferral not on the MEL, approved by MCC, usually "FOR 120 DAYS".
  DD / ADD = deferred defect (acceptable deferred defect).
- PHA / AVIATAR: predictive health analytics; early warnings from flight data (read only).
- MAREP / PIREP: fault reports (maintenance / pilot). WO = work order. ATA = system chapter number.
- Turnaround: ~1 hour between flights. Release to service: licensed engineer's signature.
- One engineer covers several aircraft per night. Brief is built per aircraft, then grouped per engineer.

## Data findings (verified on the real files)
- Maintenance_History: 209k work orders, 428 open MAREP/PIREP for Air Arabia (A6-, operator ABY).
  Filter out state "V" (void) and test rows (aircraft like "C4100"). Other operators (AP-, CN-, SU-, HZ-) are not ours.
- Deferrals are free text. The trailing letter of an item number (36-11-07B) is a variant, NOT the category.
  Real wording: "CAT C", "FOR 120 DAYS", "WITHIN 30 DAYS", "EVERY 10 DAYS" (repeat inspection, no expiry),
  flight cycles/hours only, "NEXT MAINT CHECK". "DD000667" is a reference number, not a deferral.
  Today: 364 of the 428 are deferrals; 177 get a calculable date (2 due today, 2 due soon, 29 past deadline);
  79 have no limit written; the rest are flight-cycle, repeat-inspection or category A.
- Many open work orders are far past their deadline (months). Probably never closed. The UI says "past deadline,
  confirm the real status"; do not call them "overdue aircraft".
- Tools_*: 99% of tools have Expires = 2026-11-20 = the export date. Placeholder, so calibration is "Unverified".
  `rules/tools.py` detects this automatically (>= 90% same date).
- Inventory: only condition code `US` ASSUMED unserviceable; Owner vs Entity differ for some rows (Owner is used).
- AVIATAR: 375k messages, heavy repeats (group them). PHA: 199 cases, mostly "Ambiguous".
- MMEL PDFs are only index/highlight pages (the "LEDU" file is plain text). No item text, no repair intervals.
- Missing from the pack: flight schedule, engineer roster, handover notes, full MMEL. Roster is auto-split
  (placeholder), handover notes are derived from the last two days of work-log entries and labelled "Derived".
- "As of" date = newest record (20 Nov 2026) unless AS_OF_DATE or the date picker overrides it.

## Conventions
- Python: type hints, `from __future__ import annotations`, pure rules separate from SQL and HTTP.
  Add a test with every rule. Use `config.py` for any number that is an assumption.
- Frontend: plain JSX, no UI framework. Colours red/amber/green mean STATUS only (never decoration).
  Sentence case, no all-caps labels, no "→" in buttons. Dark mode through CSS variables.
- Never put the API key in code or commit `.env` or `data/`. Ask the organisers before sending real data to OpenAI.

## AMM reference (maintenance manual)
`python -m app.etl.extract_amm` (or `load_data --only amm`) reads `data/Part_1/*/SGML/AMM.SGM` (Airbus AMM, 300 MB) into
`amm_tasks`, `amm_task_items` (tool / consumable / part / reference) and `amm_task_notes` (warnings, cautions).
`rules/amm.py` finds task numbers (26-23-41-000-004) in work-order text; `GET /api/faults/{wo}/amm` returns the tasks;
the "Parts used (AMM)" button on a fault shows them (`AmmPanel.jsx`). Reference only: the IPC (part catalogue) is not in
the pack, so expendable parts show the IPC chapter-section-number, not a stock part number.

## Not built yet (good next steps, in rough order)
1. AI-assisted reading of deferral wording the rules cannot parse (79 items), as a suggestion with the source quote.
2. Logbook-entry checker (stretch goal) with CAR-145 / CAR-M citations.
3. Real roster and flight schedule if the organisers provide them; then replace `rules/roster.py`.
4. Logins and roles (engineer, shift lead, quality) instead of a typed name.
5. Docker for the whole app; background refresh of data instead of manual loads.
