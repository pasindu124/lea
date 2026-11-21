"""API tests against the small seeded test database."""
import pytest
from fastapi.testclient import TestClient

from app.ai import client as ai
from app.main import app

AS_OF = "2026-11-20"
H = {"X-User": "tester"}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_health_and_meta(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    m = client.get("/api/meta").json()
    assert m["as_of"] == "2026-11-19" and m["as_of_source"] == "newest record in the data"   # newest seeded record
    assert client.get("/api/meta", params={"as_of": AS_OF}).json()["as_of"] == AS_OF            # request overrides it
    assert m["ai_enabled"] is False
    assert {a["id"] for a in m["assumptions"]} >= {"mmel", "tools", "stores", "roster", "notes"}


# ---------------------------------------------------------------- parts / tools
def test_parts_search_verdicts_and_source_rows(client):
    r = client.get("/api/parts/search", params={"q": "1152682 3"}, headers=H).json()
    assert r["parts_found"] == 1
    p = r["parts"][0]
    assert p["verdict"] == "AVAILABLE_LINE" and p["line_usable"] == 1 and p["main_usable"] == 2
    assert {row["source_row"] for row in p["rows"]} == {2, 3}


def test_parts_filters_change_rows_not_verdict(client):
    r = client.get("/api/parts/search", params={"q": "brake", "include_unserviceable": "false"}, headers=H).json()
    by = {p["part_no"]: p for p in r["parts"]}
    assert by["BRK-2"]["verdict"] == "UNSERVICEABLE_ONLY" and by["BRK-2"]["rows"] == []
    assert by["BRK-1"]["verdict"] == "MAIN_ONLY"
    only_line = client.get("/api/parts/search", params={"q": "brake", "stores": "SHJLINE"}, headers=H).json()
    assert {p["part_no"]: p["rows_shown"] for p in only_line["parts"]} == {"BRK-1": 0, "BRK-2": 1}


def test_parts_search_handles_wildcards_safely(client):
    assert client.get("/api/parts/search", params={"q": "%"}, headers=H).json()["parts_found"] == 0
    assert client.get("/api/parts/search", params={"q": ""}, headers=H).json()["parts"] == []


def test_tools_placeholder_expiry_is_unverified(client):
    r = client.get("/api/tools/search", params={"q": "torque wrench", "as_of": AS_OF}, headers=H).json()
    assert r["placeholder_expiry"] == "2026-11-20"
    assert {t["calibration"]["status"] for t in r["rows"]} == {"UNVERIFIED"}
    assert [t["where"] for t in r["rows"]] == ["line", "line", "main"]
    line_only = client.get("/api/tools/search", params={"q": "torque", "where": "line"}).json()
    assert line_only["total"] == 2


def test_tools_real_and_missing_dates(client):
    r = client.get("/api/tools/search", params={"q": "tool", "as_of": AS_OF}).json()
    status = {t["part_no"]: t["calibration"]["status"] for t in r["rows"]}
    assert status == {"REAL-1": "IN_DATE", "NONE-1": "NO_EXPIRY"}


# ---------------------------------------------------------------------- aircraft
def test_aircraft_detail_statuses(client):
    a = client.get("/api/aircraft/A6-AAA", params={"as_of": AS_OF}, headers=H).json()
    by = {d["wo_number"]: d["deferral"] for d in a["deferrals"]}
    assert by[1001]["status"] == "OK" and by[1001]["expires_on"] == "2027-03-01"
    assert by[1002]["status"] == "OVERDUE" and by[1002]["days_left"] == -7
    assert 1008 not in by                                    # closed work orders are not open faults
    assert [u["wo_number"] for u in a["urgent"]] == [1002]
    assert a["counts"]["overdue"] == 1


def test_aircraft_detail_other_airlines_and_test_rows_excluded(client):
    regs = {a["aircraft_reg"] for a in client.get("/api/aircraft", params={"as_of": AS_OF}).json()}
    assert "AP-ZZZ" not in regs and "C4100" not in regs
    assert {"A6-AAA", "A6-AAB", "A6-AAC"} <= regs


def test_item_letter_trap_and_reference_numbers(client):
    a = client.get("/api/aircraft/A6-AAC", params={"as_of": AS_OF}).json()
    trap = next(d for d in a["deferrals"] if d["wo_number"] == 1007)
    assert trap["deferral"]["status"] == "CHECK_SOURCE" and trap["deferral"]["expires_on"] is None
    assert {f["wo_number"] for f in a["other_faults"]} == {1005, 1006}   # 1006 only mentions DD000667


def test_pha_is_open_only_and_has_link(client):
    a = client.get("/api/aircraft/A6-AAB", params={"as_of": AS_OF}).json()
    assert len(a["pha"]) == 1 and a["pha"][0]["case_link"] == "https://example/1"


def test_aviatar_groups_repeats_and_window(client):
    a = client.get("/api/aircraft/A6-AAA", params={"as_of": AS_OF}).json()["aviatar"]
    assert [(g["message"], g["n"], g["flights"]) for g in a["groups"]] == [("FUEL SENSOR FAULT", 5, 5)]
    assert a["total_messages"] == 6                          # the October message is outside the window


def test_derived_notes_deduplicated(client):
    notes = client.get("/api/aircraft/A6-AAA", params={"as_of": AS_OF}).json()["notes"]
    assert [n["text"] for n in notes if n["wo_number"] == 1011] == ["CHECK CARRIED OUT AUTHORISED BY: A. TECH"]


def test_work_order_full_text_and_404(client):
    wo = client.get("/api/workorders/1002").json()
    assert wo["source"]["row"] == 3 and "CAT B" in wo["wo_actions"]
    assert client.get("/api/workorders/999999").status_code == 404


# ------------------------------------------------------------------------ brief
def test_brief_roster_and_top_flag(client):
    b = client.get("/api/brief", params={"as_of": AS_OF}, headers=H).json()
    assert b["roster_is_placeholder"] is True
    assert sorted(a["aircraft_reg"] for e in b["engineers"] for a in e["aircraft"]) == ["A6-AAA", "A6-AAB", "A6-AAC"]
    assert len(b["engineers"]) == 3
    top = b["shift_top_flag"]
    assert (top["wo_number"], top["status"]) == (1003, "EXPIRES_TODAY")      # deadline today beats soon and overdue
    order = [f["wo_number"] for e in b["engineers"] for f in e["flags"]]
    assert set(order) == {1002, 1003, 1004}


def test_brief_includes_time_critical_aircraft_even_when_shift_is_small(client):
    from app.services import brief_service
    mapping = brief_service.auto_roster(__import__("datetime").date(2026, 11, 20), __import__("datetime").date(2026, 11, 20), n=1)
    assert "A6-AAB" in mapping                               # has items due today and soon


def test_roster_change_is_logged_and_used(client):
    client.post("/api/roster/auto", params={"shift_date": AS_OF}, headers=H)
    r = client.put("/api/roster", json={"aircraft_reg": "a6-aac", "engineer": "Engineer 3", "shift_date": AS_OF}, headers=H).json()
    assert r["assignments"]["A6-AAC"] == "Engineer 3"
    log = client.get("/api/audit?limit=5").json()
    assert log[0]["action"] == "roster_change" and log[0]["details"]["after"] == "Engineer 3" and log[0]["actor"] == "tester"
    client.put("/api/roster", json={"aircraft_reg": "A6-AAC", "engineer": None, "shift_date": AS_OF}, headers=H)
    assert "A6-AAC" not in client.get("/api/roster", params={"shift_date": AS_OF}).json()["assignments"]
    client.post("/api/roster/auto", params={"shift_date": AS_OF}, headers=H)


def test_ack_is_logged_and_shown_but_changes_nothing(client):
    assert client.post("/api/flags/ack", json={"wo_number": 1003, "note": "checked with MCC"}, headers=H).json() == {"ok": True}
    b = client.get("/api/brief", params={"as_of": AS_OF}).json()
    assert b["shift_top_flag"]["ack"]["note"] == "checked with MCC" and b["shift_top_flag"]["ack"]["actor"] == "tester"
    assert b["shift_top_flag"]["status"] == "EXPIRES_TODAY"      # the flag stays: the agent never closes anything
    assert client.post("/api/flags/ack", json={"wo_number": 424242}, headers=H).status_code == 404


def test_every_flag_has_a_rule_and_a_source(client):
    b = client.get("/api/brief", params={"as_of": AS_OF}).json()
    for e in b["engineers"]:
        for f in e["flags"]:
            assert f["rule"] and f["source"]["file"] == "Maintenance_History.xlsx" and f["source"]["row"]


def test_searches_are_audited(client):
    client.get("/api/parts/search", params={"q": "wrench"}, headers={"X-User": "audit-check"})
    last = [r for r in client.get("/api/audit?limit=20").json() if r["actor"] == "audit-check"]
    assert last and last[0]["action"] == "parts_search" and last[0]["details"]["query"] == "wrench"


# --------------------------------------------------------------------------- AI
def test_ai_is_off_without_a_key(client):
    assert client.post("/api/ai/aircraft", json={"aircraft_reg": "A6-AAA"}).status_code == 503
    assert client.post("/api/ai/parts", json={"query": "brake", "question": "where?"}).status_code == 503


@pytest.fixture
def ai_on(monkeypatch):
    monkeypatch.setattr(ai.config, "OPENAI_API_KEY", "test-key")
    sent = {}

    def fake_chat(system, user, json_mode=False, client=None):
        sent.update(system=system, user=user, json_mode=json_mode)
        return sent.get("reply", "Check [WO1002] first. Fuel message on [AV1].")
    monkeypatch.setattr(ai, "_chat", fake_chat)
    return sent


def test_ai_aircraft_gets_only_tagged_records_and_guardrails(client, ai_on):
    r = client.post("/api/ai/aircraft", json={"aircraft_reg": "A6-AAA", "as_of": AS_OF}, headers=H).json()
    assert r["citations"]["ok"] and set(r["records_sent"]) >= {"WO1002", "AV1"}
    assert "Never advise signing" in ai_on["system"] and "[WO1002]" in ai_on["user"]
    assert "A6-AAB" not in ai_on["user"] and "OLD FAULT" not in ai_on["user"]


def test_ai_answer_citing_unknown_record_is_flagged(client, ai_on):
    ai_on["reply"] = "Replace it now [WO999]."
    r = client.post("/api/ai/aircraft", json={"aircraft_reg": "A6-AAA", "as_of": AS_OF}, headers=H).json()
    assert r["citations"]["ok"] is False and r["citations"]["unknown"] == ["WO999"]


def test_ai_parts_cites_row_numbers_and_is_logged(client, ai_on):
    ai_on["reply"] = "Available at the line store [R2]."
    r = client.post("/api/ai/parts", json={"query": "1152682-3", "question": "Where is it?"}, headers=H).json()
    assert r["citations"]["ok"] and "[R2]" in ai_on["user"]
    log = client.get("/api/audit?limit=1").json()[0]
    assert log["action"] == "ai_parts" and log["sources"][0]["records"]


def test_keywords_use_ai_when_on_and_fall_back_when_it_fails(client, ai_on, monkeypatch):
    ai_on["reply"] = '{"keywords": ["fan", "galley"]}'
    k = client.get("/api/faults/1003/keywords").json()
    assert k["method"] == "ai" and k["keywords"] == ["FAN", "GALLEY"]
    monkeypatch.setattr(ai, "_chat", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("quota")))
    k = client.get("/api/faults/1003/keywords").json()
    assert k["method"] == "simple" and k["keywords"]


def test_keywords_without_ai(client):
    assert client.get("/api/faults/1003/keywords").json()["method"] == "simple"


# ------------------------------------------------------- closing work orders
def test_deadline_cutoff_treats_old_open_items_as_closed(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "CLOSE_DEADLINES_BEFORE", "2026-11-14")
    a = client.get("/api/aircraft/A6-AAA", params={"as_of": AS_OF}).json()
    wos = [d["wo_number"] for d in a["deferrals"]]
    assert 1002 not in wos and 1001 in wos               # 1002 expired 13 Nov: closed; 1001 is in date
    assert a["counts"]["closed_by_cutoff"] == 1 and a["counts"]["overdue"] == 0
    b = client.get("/api/aircraft/A6-AAB", params={"as_of": AS_OF}).json()
    assert 1003 in [d["wo_number"] for d in b["deferrals"]]   # deadline 20 Nov: after the cut-off, stays open
    wo = client.get("/api/workorders/1002").json()
    assert wo["closed_by_cutoff"] is True and wo["wo_state"] == "Open"   # the source data is not changed
    assert any(x["id"] == "cutoff" for x in client.get("/api/meta").json()["assumptions"])


def test_mark_done_closes_item_and_shows_in_recent_work(client):
    note = "Door seal replaced IAW AMM 52-10-00. Checked OK."
    assert client.post("/api/workorders/done", json={"wo_number": 1005, "note": note}).status_code == 400  # no name
    r = client.post("/api/workorders/done", json={"wo_number": 1005, "note": note, "as_of": AS_OF}, headers=H)
    assert r.status_code == 200 and r.json()["completed_by"] == "tester"
    a = client.get("/api/aircraft/A6-AAC", params={"as_of": AS_OF}).json()
    assert 1005 not in [i["wo_number"] for i in a["other_faults"] + a["deferrals"]]
    assert {"text": note, "done_by": "tester"}.items() <= next(n for n in a["notes"] if n["wo_number"] == 1005).items()
    wo = client.get("/api/workorders/1005").json()
    assert wo["completion"]["note"] == note and wo["wo_state"] == "Closed" and wo["date_closed"] == AS_OF
    assert wo["wo_actions"].endswith(f" | [20-Nov-2026] {note}")              # appended to the row's work log
    # A data reload brings the Excel row back as Open: the app closes it again.
    from app import db
    from app.services.aircraft_service import reapply_completions
    db.execute("UPDATE work_orders SET wo_state = 'Open', date_closed = NULL, "
               "wo_actions = '[19-Nov-2026] INSPECTED, SEAL TO BE REPLACED' WHERE wo_number = 1005")
    assert reapply_completions() == 1 and client.get("/api/workorders/1005").json()["wo_state"] == "Closed"
    assert "work_done" in [x["action"] for x in client.get("/api/audit?limit=5").json()]
    assert client.delete("/api/workorders/1005/done", headers=H).json() == {"ok": True}
    a = client.get("/api/aircraft/A6-AAC", params={"as_of": AS_OF}).json()
    assert 1005 in [i["wo_number"] for i in a["other_faults"]]
    wo = client.get("/api/workorders/1005").json()
    assert (wo["wo_state"], wo["date_closed"], wo["wo_actions"]) == ("Open", None, "[19-Nov-2026] INSPECTED, SEAL TO BE REPLACED")
    assert client.post("/api/workorders/done", json={"wo_number": 1005, "note": "x" * 5}, headers=H).status_code == 200
    assert client.post("/api/workorders/done", json={"wo_number": 1005, "note": "again"}, headers=H).status_code == 409
    client.delete("/api/workorders/1005/done", headers=H)
    assert "work_done_undo" in [x["action"] for x in client.get("/api/audit?limit=5").json()]


def test_mark_done_refuses_closed_or_missing_work_orders(client):
    assert client.post("/api/workorders/done", json={"wo_number": 1008, "note": "again"}, headers=H).status_code == 409
    assert client.post("/api/workorders/done", json={"wo_number": 424242, "note": "nope"}, headers=H).status_code == 404
    assert client.delete("/api/workorders/1001/done", headers=H).status_code == 404
