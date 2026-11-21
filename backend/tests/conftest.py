"""Test setup: a separate PostgreSQL database (lea_test) filled with small, known data."""
import os
from datetime import date

import psycopg
import pytest

TEST_URL = os.getenv("TEST_DATABASE_URL", "postgresql://lea:lea@localhost:5432/lea_test")
os.environ["DATABASE_URL"] = TEST_URL            # must happen before the app is imported
os.environ.pop("OPENAI_API_KEY", None)
os.environ["AS_OF_DATE"] = ""
os.environ["CLOSE_DEADLINES_BEFORE"] = ""        # off by default; the cut-off test switches it on
os.environ["ENGINEERS"] = "Engineer 1,Engineer 2,Engineer 3"


def _ensure_database():
    admin = TEST_URL.rsplit("/", 1)[0] + "/postgres"
    name = TEST_URL.rsplit("/", 1)[1]
    with psycopg.connect(admin, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
            conn.execute(f'CREATE DATABASE "{name}"')


@pytest.fixture(scope="session", autouse=True)
def database():
    _ensure_database()
    from app import db
    db.reset_pool()
    db.apply_schema()
    db.execute("TRUNCATE parts_stock, tools, work_orders, aviatar_faults, pha_cases, amm_tasks, amm_task_items, amm_task_notes, audit_log, roster, meta, work_completion RESTART IDENTITY")
    seed(db)
    yield db
    db.reset_pool()


AS_OF = "2026-11-20"


def seed(db):
    parts = [  # source_row, store, location, part_no, serial, description, mat_class, qty, cond, owner
        (2, "SHJLINE", "L1", "1152682-3", "S1", "TRANSMITTER, EMERGENCY LOCATOR", "R", 1, "N", "ABY"),
        (3, "SHJMAIN", "K1", "1152682-3", "S2", "TRANSMITTER, EMERGENCY LOCATOR", "R", 2, "N", "ABY"),
        (4, "SHJMAIN", "K2", "BRK-1", "S3", "BRAKE ASSY-MLG", "R", 1, "N", "ABY"),
        (5, "SHJLINE", "L2", "BRK-2", "S4", "BRAKE ASSY-MLG", "R", 1, "US", "ABY"),
        (6, "SHJLINE", "L3", "TC-1", "S5", "THERMOCOUPLE", "CR", 1, "N", "MAC"),
    ]
    for p in parts:
        db.execute("INSERT INTO parts_stock (source_row, store, location, part_no, serial, description, mat_class, qty, cond, owner) "
                   "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", p)

    tools = [("T.xlsx", 2, "TW-1", "A1", "TORQUE WRENCH", "LINEWH", "2026-11-20"), ("T.xlsx", 3, "TW-2", "A2", "TORQUE WRENCH", "LINEWH", "2026-11-20"),
             ("T.xlsx", 4, "TW-3", "A3", "TORQUE WRENCH", "SHJMAINW", "2026-11-20"), ("T.xlsx", 5, "GA-1", "A4", "GAUGE", "SHJMAINW", "2026-11-20"),
             ("T.xlsx", 6, "GA-2", "A5", "GAUGE", "SHJMAINW", "2026-11-20"), ("T.xlsx", 7, "GA-3", "A6", "GAUGE", "SHJMAINW", "2026-11-20"),
             ("T.xlsx", 8, "GA-4", "A7", "GAUGE", "SHJMAINW", "2026-11-20"), ("T.xlsx", 9, "GA-5", "A8", "GAUGE", "SHJMAINW", "2026-11-20"),
             ("T.xlsx", 10, "GA-6", "A9", "GAUGE", "SHJMAINW", "2026-11-20"), ("T.xlsx", 11, "GA-7", "A10", "GAUGE", "SHJMAINW", "2026-11-20"),
             ("T.xlsx", 12, "REAL-1", "A11", "REAL DATE TOOL", "LINEWH", "2027-06-01"), ("T.xlsx", 13, "NONE-1", "A12", "NO DATE TOOL", "LINEWH", None)]
    for t in tools:
        db.execute("INSERT INTO tools (source_file, source_row, part_no, serial, description, store, location, qty, expires) "
                   "VALUES (%s,%s,%s,%s,%s,%s,'X',1,%s)", (t[0], t[1], t[2], t[3], t[4], t[5], t[6]))

    wo = [  # wo_number, reg, op, type, opened, state, description, actions
        (1001, "A6-AAA", "ABY", "PIREP", "2026-11-01", "Open", "ENG ENTRY: PAX SEAT TABLE MISSING", "[01-Nov-2026] DD RAISED, NSI DEFERRAL CARRIED OUT FOR 120 DAYS."),
        (1002, "A6-AAA", "ABY", "MAREP", "2026-11-10", "Open", "READING LIGHT INOP", "[10-Nov-2026] DEFERRED AS PER MEL 33-40-07A CAT B."),
        (1003, "A6-AAB", "ABY", "MAREP", "2026-11-10", "Open", "GALLEY FAN INOP", "[10-Nov-2026] DEFERRED PER MEL 25-30-01 CAT C."),
        (1004, "A6-AAB", "ABY", "PIREP", "2026-11-18", "Open", "LAV LIGHT INOP", "[18-Nov-2026] DEFERRED PER MEL 33-20-01 CAT B."),
        (1005, "A6-AAC", "ABY", "PIREP", "2026-11-19", "Open", "DOOR SEAL WORN", "[19-Nov-2026] INSPECTED, SEAL TO BE REPLACED"),
        (1006, "A6-AAC", "ABY", "MAREP", "2026-11-12", "Open", "REF TO DD000667 BSI DONE", "[12-Nov-2026] REFERENCE ONLY"),
        (1007, "A6-AAC", "ABY", "MAREP", "2026-11-14", "Open", "TRAP ITEM", "[14-Nov-2026] DEFERRED PER MEL 36-11-07B."),
        (1008, "A6-AAA", "ABY", "MAREP", "2026-10-01", "Closed", "OLD FAULT", "[01-Oct-2026] FIXED. DEFERRED PER MEL 21-00-01 CAT B."),
        (1009, "AP-ZZZ", "FJL", "MAREP", "2026-11-10", "Open", "OTHER AIRLINE", "[10-Nov-2026] DEFERRED CAT B"),
        (1010, "C4100", "ABY", "MAREP", "2026-11-10", "Open", "TEST ROW", "[10-Nov-2026] DEFERRED CAT B"),
        (1011, "A6-AAA", "ABY", "Scheduled", "2026-11-19", "Closed", "ETOPS CHECK", "[19-Nov-2026] CHECK CARRIED OUT AUTHORISED BY: A. TECH | [19-Nov-2026] CHECK CARRIED OUT AUTHORISED BY: A. TECH"),
    ]
    for i, w in enumerate(wo, start=2):
        db.execute("INSERT INTO work_orders (source_row, wo_number, aircraft_reg, operator_code, wo_type, date_opened, wo_state, wo_description, wo_actions, date_closed) "
                   "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (i, *w, "2026-11-19" if w[5] == "Closed" and w[0] == 1011 else None))

    for i in range(5):  # same message repeated, and some noise
        db.execute("INSERT INTO aviatar_faults (prio, message, message_type, ac, flight, ata, occurrence) VALUES "
                   "('HIGH','FUEL SENSOR FAULT','FAULT_MESSAGE','A6-AAA',%s,'28-41','2026-11-19 10:00:00')", (f"G9{i}",))
    db.execute("INSERT INTO aviatar_faults (prio, message, message_type, ac, flight, ata, occurrence) VALUES "
               "('LOW','COSMETIC','FAULT_MESSAGE','A6-AAA','G9','21-00','2026-11-19 11:00:00')")
    db.execute("INSERT INTO aviatar_faults (prio, message, message_type, ac, flight, ata, occurrence) VALUES "
               "('HIGH','OLD','FAULT_MESSAGE','A6-AAA','G9','21-00','2026-10-01 11:00:00')")

    db.execute("INSERT INTO pha_cases (source_row, max_severity, acreg, ata, title, impact, classification, status, opened, case_link) VALUES "
               "(2,'Alert','A6-AAB',32,'High Brake 1 Temperature','High','Ambiguous','OPEN','2026-11-19 04:00:00','https://example/1'),"
               "(3,'Alert','A6-AAB',32,'Old case','Low','-','COMPLETED','2026-11-01 04:00:00','https://example/2')")

    from app.etl import load_data
    load_data.update_meta()
