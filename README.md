# Line Engineer Agent

A night-shift brief for aircraft line engineers (Air Arabia hackathon, Round 1, Use Case 4).

Before the shift, the agent collects what an engineer needs into one page: which deferred faults are about to
hit their deadline, which faults are open, what the aircraft is reporting, what predictive alerts exist, and whether
the parts and tools are in stock. **Every line shows its rule and links to its source record.**
The agent only reads and explains. It never signs, defers or releases anything, and it never changes a record.

```
 React (Vite)  <--HTTP/JSON-->  FastAPI (Python)  <-->  PostgreSQL 16
   screens                       rules + services           your data files, audit log, roster
                                      |
                                 OpenAI API (optional): reads and summarises records the code retrieved
```

* The **rules** (deadlines, parts verdicts, tool status, urgency) are plain Python in `backend/app/rules/`, with tests.
  The AI never decides anything.
* The **AI** only sees records the code retrieved, must cite them (`[WO6232450]`), and its answers are checked:
  citing a record it was not given is flagged on screen.

## What you need

* Python 3.10 or newer, Node.js 18 or newer
* PostgreSQL 16, either with Docker (`docker compose up -d`) or installed on your machine
* Your data files in the `data/` folder (see below)
* An OpenAI API key (optional)

## Set up (about 10 minutes)

**1. Database.** With Docker, from this folder:
```
docker compose up -d
```
Without Docker, create a database `lea` with user `lea` and password `lea` (or change `DATABASE_URL` in `.env`).
Then, as a database admin: `CREATE EXTENSION pg_trgm;` (the loader tries this itself and usually succeeds).

**2. Settings.** Copy `.env.example` to `.env`. Put your OpenAI key in it if you want the AI buttons.

**3. Backend.**
```
cd backend
python -m venv .venv
.venv\Scripts\activate            (Mac or Linux:  source .venv/bin/activate)
pip install -r requirements.txt
```

**4. Load the data.** Copy the Excel and CSV files into `data/`, then:
```
python -m app.etl.load_data
```
It takes about a minute and prints row counts. It is safe to run again. The audit log, roster and settings are never touched.
File names are matched loosely: `Inventory_List.xlsx` or `Inventory List.xlsx` both work. It looks for
`*Inventory*List*.xlsx`, `*Tools*SHJLINE*.xlsx`, `*Tools*SHJMAIN*.xlsx`, `*Maintenance*History*.xlsx`,
`*PHA*Case*Tracking*.csv` and `*AVIATAR*Faults*.csv`.

**5. Run it.**
```
uvicorn app.main:app --reload --port 8000
```
and in a second terminal:
```
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173**.

For a single-process demo: run `npm run build` in `frontend`, then open **http://localhost:8000**
(the Python server serves the built app).

**6. Check it works.** `cd backend && python -m pytest` (109 tests; it creates its own small database `lea_test`).

## The screens

| Screen | What it does |
|---|---|
| Shift brief | The most urgent item as a flight strip, a tab per engineer, a card per aircraft |
| Aircraft | Any Air Arabia aircraft with open items, most urgent first |
| Parts finder | Search spare parts. Verdict per part: line store, main store, other owner, unserviceable |
| Tools | Search tools. Location and calibration status |
| Shift setup | Choose which aircraft each engineer has, with ground time at Sharjah and the list of urgent aircraft that are away. Changes are audited |
| Audit log | Searches, AI answers, roster changes, "seen" confirmations |

The top bar shows the date the data is "as of" (the newest record), and lets you change it to see how deadlines move.
The **Assumptions** button lists every guess listed below.

## How the deadlines are worked out (`backend/app/rules/deadlines.py`)

A deadline is calculated only when the record itself states the limit. Otherwise the app says "check source".

| What the record says | Result |
|---|---|
| `CAT B`, `CAT C`, `CAT D` | 3, 10 or 120 days from the date opened (**assumption**, see below) |
| `FOR 120 DAYS` or `WITHIN 30 DAYS` (typical for NSI deferrals) | that many days |
| Days **and** a flight-cycle or hour limit, "whichever first" | the date is the latest possible; shown as such |
| Only flight cycles or hours, `EVERY 10 DAYS` repeats, `NEXT CHECK`, category A | no date; check the source |
| A deferral word but no limit | "No limit written": check the source |

The last letter of an item number (the `B` in `36-11-07B`) is a variant, not a category, and is never used.
The day of discovery is not counted. Statuses: past deadline, due today, due soon (3 days or fewer), in date, check source.

## Flight schedule and ground time

`data/Flights_Export_*.xls` (sheet "Flight Summary") is loaded into the `flights` table (`python -m app.etl.load_data --only flights`;
the old `.xls` format needs `xlrd`, already in `requirements.txt`). Each flight keeps its Excel row.
`backend/app/rules/ground.py` (pure, tested) pairs every arrival into Sharjah (SHJ) with the same aircraft's next departure from SHJ.
It uses actual times (ATA/ATD) when they exist, otherwise the planned ones (STA/STD), and says which. Edge cases are explicit:
the first flight in the file already leaves SHJ ("arrival not in the schedule": the aircraft is assumed to be there until then),
the last flight arrives with no later departure, and an arrival followed by a departure from another airport is marked a data gap
and never guessed (it is not counted as "on the ground").

* **Aircraft and times** line on every aircraft card, ground windows per engineer on the brief, and a "Not at Sharjah tonight" list for
  aircraft with a deadline today or soon that are away (they are never dropped silently).
* **Roster.** "Suggest a split" now picks aircraft that are on the ground at SHJ during the shift (at least `MIN_GROUND_MINUTES` inside it)
  and gives each aircraft to the engineer whose aircraft overlap it least on the ground. It warns when one engineer has two aircraft with a
  short ground time (under `SHORT_GROUND_HOURS`) at the same time. With no schedule for the shift it falls back to the old split and says so.
* **Timing notes** next to flagged items are plain facts ("Next departure (22 Nov 08:30) is after the deadline date (20 Nov)"). They never say
  whether an aircraft can fly. The licensed engineer decides.
* Delay codes, bays and diversion are loaded but used nowhere (their meaning was not provided).
* The roster strategy used is written to the audit log (`roster_auto`, field `strategy`: `time_balanced` or `snake_fallback`).

Settings (`.env`, see `.env.example`): `FLIGHT_TIMES_ARE=local|utc`, `LOCAL_UTC_OFFSET_HOURS=4`, `SHIFT_START=22:00`, `SHIFT_END=06:00`,
`MIN_GROUND_MINUTES=30`, `SHORT_GROUND_HOURS=2`.

## Assumptions to confirm with Air Arabia

1. **MMEL intervals.** B, C and D as 3, 10 and 120 days is standard practice, but the MMEL page that defines them is not in the data pack.
2. **Tool calibration.** About 99% of tools show the same expiry date (the export date). It looks like a placeholder, so calibration is shown as "Unverified".
3. **Parts condition and owner.** Only condition code `US` counts as unserviceable, and the `Owner` column decides ownership.
4. **Roster.** No roster is in the data. Aircraft are split automatically for the demo.
5. **Flight times and shift hours.** The flight file does not say if its times are UTC or Sharjah local time. The app reads them as local, as written
   (`FLIGHT_TIMES_ARE`). The night shift is taken as 22:00 to 06:00 Sharjah time. Only flights up to 19 Nov 13:47 have actual times; all later
   times are the planned schedule and are labelled that way. Confirm both with Planning.
6. **Handover notes.** None provided. "Recent work logged" shows work-log entries from the last two days and says it is derived.
7. **Overdue items.** Many work orders are still open long after their deadline (some by months). They may be records never closed.
   The app labels them "past deadline" and asks the engineer to confirm the real status.

All of these are single settings in `backend/app/config.py`.

## A five-minute demo

1. **Shift brief.** The strip at the top is the one item that matters tonight. Open "Why this is flagged" to show the rule and the source row.
2. Click **Mark as seen**. Show it appear on the strip, then in the **Audit log**. The item stays open: the agent never closes anything.
3. Open an aircraft card. Show deferrals with deadlines, predictive cases marked **Read only**, grouped aircraft messages, and the **Derived** handover notes.
4. On a fault click **Check parts**, then **Full record** to see the original text.
5. **Parts finder** and **Tools**: show the verdicts, then the calibration warning (the app refuses to trust a placeholder date).
6. **Shift setup**: move an aircraft to another engineer, then show the change in the audit log.
7. Open **Assumptions** and say plainly what is not yet confirmed. This is the "right and explained" point.
8. If the OpenAI key is set, use **Summarise with AI** on an aircraft and show that the answer cites record tags.

## Folder map

```
backend/app/rules/      deadlines, parts verdicts, tool status, ground time, roster split, citation check (pure, tested)
backend/app/services/   SQL queries and assembling the brief
backend/app/routers/    HTTP routes
backend/app/ai/         OpenAI calls and the guardrail prompts
backend/app/etl/        data loader
backend/app/schema.sql  database tables
backend/tests/          109 tests
frontend/src/           React app (pages/, AircraftCard.jsx, styles.css)
```

## Not built yet

* The logbook-entry checker (stretch goal)
* Logins and roles (engineer, shift lead, quality). Names are typed in and sent with each request.
* AI help for reading deferral wording that the rules cannot (79 items today have no limit written)
* Delay and bay data in the schedule (meaning not provided), real flight times beyond 19 Nov, and the operator MEL
* Docker for the whole app (only PostgreSQL has a compose file)
