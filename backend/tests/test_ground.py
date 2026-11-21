"""Ground time rules (pure) and the schedule in the app (seeded test database)."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.rules import ground
from app.services import brief_service, schedule_service

AS_OF = "2026-11-20"
D = date(2026, 11, 20)
H = {"X-User": "tester"}


def dt(day: int, hhmm: str) -> datetime:
    h, m = hhmm.split(":")
    return datetime(2026, 11, day, int(h), int(m))


def fl(reg, no, dep, arr, std, sta, atd=None, ata=None, row=2):
    return {"reg": reg, "flight_no": no, "dep": dep, "arr": arr, "std": std, "sta": sta, "atd": atd, "ata": ata, "source_row": row}


# --------------------------------------------------------------- ground_windows
def test_turnaround_pairs_arrival_with_next_departure():
    w, = ground.ground_windows([fl("A6-X", "G1", "DXB", "SHJ", dt(21, "00:00"), dt(21, "02:30")),
                                fl("A6-X", "G2", "SHJ", "ISB", dt(21, "04:20"), dt(21, "08:00"))])
    assert (w["kind"], w["arrival_flight"], w["departure_flight"], w["next_destination"]) == ("turnaround", "G1", "G2", "ISB")
    assert w["ground_hours"] == pytest.approx(1 + 50 / 60) and w["used_actuals"] is False and not w["uncertain"]


def test_flights_are_sorted_and_aircraft_kept_apart():
    rows = [fl("A6-X", "G2", "SHJ", "ISB", dt(21, "04:20"), dt(21, "08:00")), fl("A6-Y", "H1", "DXB", "SHJ", dt(21, "00:00"), dt(21, "01:00")),
            fl("A6-X", "G1", "DXB", "SHJ", dt(21, "00:00"), dt(21, "02:30")), fl("A6-Y", "H2", "SHJ", "KHI", dt(21, "03:00"), dt(21, "05:00"))]
    ws = {w["reg"]: w for w in ground.ground_windows(rows)}
    assert ws["A6-X"]["ground_hours"] == pytest.approx(1.8333, abs=1e-3) and ws["A6-Y"]["ground_hours"] == 2.0


def test_actual_times_beat_planned_times():
    w, = ground.ground_windows([fl("A6-X", "G1", "DXB", "SHJ", dt(21, "00:00"), dt(21, "02:30"), ata=dt(21, "03:00")),
                                fl("A6-X", "G2", "SHJ", "ISB", dt(21, "04:20"), dt(21, "08:00"), atd=dt(21, "04:50"))])
    assert w["arrival_time"] == dt(21, "03:00") and w["departure_time"] == dt(21, "04:50")
    assert w["ground_hours"] == pytest.approx(1 + 50 / 60) and w["used_actuals"] is True


def test_first_flight_already_leaves_the_station():
    w, = ground.ground_windows([fl("A6-X", "G2", "SHJ", "ISB", dt(20, "08:30"), dt(20, "12:00"))])
    assert w["kind"] == ground.ARRIVAL_NOT_IN_SCHEDULE and w["arrival_time"] is None and w["ground_hours"] is None
    assert w["departure_time"] == dt(20, "08:30") and not w["uncertain"]


def test_last_flight_arrives_and_nothing_follows():
    w, = ground.ground_windows([fl("A6-X", "G1", "DXB", "SHJ", dt(30, "20:00"), dt(30, "22:00"))])
    assert w["kind"] == ground.NO_LATER_DEPARTURE and w["departure_time"] is None and not w["uncertain"]


def test_arrival_then_departure_from_another_airport_is_a_marked_gap():
    ws = ground.ground_windows([fl("A6-X", "G1", "DXB", "SHJ", dt(21, "00:00"), dt(21, "02:30")),
                                fl("A6-X", "G2", "AUH", "KHI", dt(21, "09:00"), dt(21, "12:00"))])
    gap, = [w for w in ws if w["arrival_flight"] == "G1"]
    assert gap["kind"] == ground.DATA_GAP and gap["uncertain"] and gap["ground_hours"] is None and "not guessed" in gap["note"]
    assert not ground.on_ground_during(ws, dt(21, "00:00"), dt(21, "06:00"))               # not counted as on the ground
    assert ground.on_ground_during(ws, dt(21, "00:00"), dt(21, "06:00"), include_uncertain=True)


def test_other_stations_and_missing_registration_make_no_windows():
    ws = ground.ground_windows([fl("A6-X", "G1", "AUH", "KHI", dt(21, "00:00"), dt(21, "03:00")),
                                fl(None, "G2", "SHJ", "KHI", dt(21, "00:00"), dt(21, "03:00"))])
    assert ws == []


# ---------------------------------------------------------------- shift overlap
SHIFT = (dt(20, "22:00"), dt(21, "06:00"))


def test_on_ground_during_uses_overlap_and_minimum_minutes():
    ws = ground.ground_windows([fl("A6-X", "G1", "DXB", "SHJ", dt(20, "10:00"), dt(20, "12:00")),
                                fl("A6-X", "G2", "SHJ", "ISB", dt(20, "22:10"), dt(21, "01:00"))])
    assert [w["overlap_minutes"] for w in ground.on_ground_during(ws, *SHIFT)] == [10.0]
    assert ground.on_ground_during(ws, *SHIFT, min_minutes=30) == []
    assert ground.on_ground_during(ws, dt(20, "22:10"), dt(20, "23:00")) == []             # after the departure


def test_open_ended_windows_stay_on_the_ground():
    ws = ground.ground_windows([fl("A6-X", "G1", "DXB", "SHJ", dt(20, "20:00"), dt(20, "23:00"))])
    assert len(ground.on_ground_during(ws, *SHIFT)) == 1


def test_next_arrival():
    ws = ground.ground_windows([fl("A6-X", "G1", "DXB", "SHJ", dt(22, "20:00"), dt(22, "23:00")),
                                fl("A6-X", "G2", "SHJ", "DXB", dt(23, "20:00"), dt(23, "23:00"))])
    assert ground.next_arrival(ws, dt(20, "22:00"))["arrival_flight"] == "G1"
    assert ground.next_arrival(ws, dt(24, "00:00")) is None


# ----------------------------------------------------------------------- time zone
def test_time_zone_setting():
    t = datetime(2026, 11, 20, 22, 0)
    assert ground.to_local(t, "local", 4) == t
    assert ground.to_local(t, "utc", 4) == datetime(2026, 11, 21, 2, 0)
    assert ground.to_local(None, "utc", 4) is None


def test_shift_window_crosses_midnight():
    assert ground.shift_window(D, (22, 0), (6, 0)) == (dt(20, "22:00"), dt(21, "06:00"))
    assert ground.shift_window(D, (8, 0), (18, 0)) == (dt(20, "08:00"), dt(20, "18:00"))


# ------------------------------------------------------------------- timing notes
BANNED = ("cannot", "can't", "must", "may depart", "should", "grounded", "safe", "unsafe")


def _wins():
    return ground.ground_windows([fl("A6-X", "G1", "DXB", "SHJ", dt(21, "00:00"), dt(21, "02:30"), row=5),
                                  fl("A6-X", "G2", "SHJ", "ISB", dt(22, "08:30"), dt(22, "12:00"), row=6)])


def test_notes_next_departure_after_the_deadline_and_planned_label():
    notes = ground.timing_notes({"expires_on": "2026-11-20"}, _wins(), dt(20, "22:00"), flagged_count=1)
    assert "Next departure (22 Nov 08:30) is after the deadline date (20 Nov)." in notes
    assert "Times are the planned schedule, not actual times." in notes


def test_notes_departure_on_or_before_the_deadline():
    notes = ground.timing_notes({"expires_on": date(2026, 11, 25)}, _wins(), dt(20, "22:00"))
    assert any("on or before the deadline date (25 Nov)" in n for n in notes)


def test_notes_short_ground_time_and_flag_count():
    ws = ground.ground_windows([fl("A6-X", "G1", "DXB", "SHJ", dt(21, "00:00"), dt(21, "02:30")),
                                fl("A6-X", "G2", "SHJ", "ISB", dt(21, "03:42"), dt(21, "07:00"))])
    notes = ground.timing_notes({"expires_on": "2026-11-21"}, ws, dt(20, "22:00"), flagged_count=3)
    assert "Only 1h12 on the ground and 3 items are flagged." in notes
    assert ground.timing_notes(None, ws, dt(20, "22:00"), flagged_count=1)[-2] == "Only 1h12 on the ground and 1 item is flagged."


def test_notes_aircraft_not_at_the_station_and_no_schedule():
    notes = ground.timing_notes({"expires_on": "2026-11-20"}, _wins(), dt(20, "10:00"))
    assert notes[0].startswith("Not at Sharjah when the shift starts. Next arrival at Sharjah: 21 Nov 02:30 (G1)")
    assert ground.timing_notes({"expires_on": "2026-11-20"}, [], dt(20, "22:00")) == \
        ["The schedule has no more Sharjah ground time for this aircraft."]


def test_notes_never_use_decision_words():
    cases = [(d, w, r, n) for d in ({"expires_on": "2026-11-20"}, None) for w in (_wins(), []) for r in (dt(20, "10:00"), dt(22, "09:00"))
             for n in (1, 4)]
    for d, w, r, n in cases:
        text = " ".join(ground.timing_notes(d, w, r, n)).lower()
        assert not any(word in text for word in BANNED), text


# ------------------------------------------------------------ balancing engineers
def _three_at_0230():
    rows = []
    for i, reg in enumerate(["A6-A", "A6-B", "A6-C", "A6-D", "A6-E"]):
        rows += [fl(reg, f"I{i}", "DXB", "SHJ", dt(21, "00:30"), dt(21, "02:30")), fl(reg, f"O{i}", "SHJ", "ISB", dt(21, "04:30"), dt(21, "08:00"))]
    wins = {}
    for w in ground.ground_windows(rows):
        wins.setdefault(w["reg"], []).append(w)
    return wins


def test_balance_does_not_stack_aircraft_that_land_together():
    wins = _three_at_0230()
    scores = {"A6-A": 900, "A6-B": 800, "A6-C": 700, "A6-D": 100, "A6-E": 50}
    out = ground.balance_by_time(scores, wins, ["E1", "E2", "E3"], clip=SHIFT)
    assert {out["A6-A"], out["A6-B"], out["A6-C"]} == {"E1", "E2", "E3"}                # top three are spread out
    assert max(list(out.values()).count(e) for e in ("E1", "E2", "E3")) == 2


def test_balance_prefers_the_engineer_whose_aircraft_do_not_overlap():
    rows = [fl("A6-A", "I1", "DXB", "SHJ", dt(20, "22:00"), dt(20, "23:00")), fl("A6-A", "O1", "SHJ", "ISB", dt(21, "01:00"), dt(21, "03:00")),
            fl("A6-B", "I2", "DXB", "SHJ", dt(20, "22:00"), dt(20, "22:30")), fl("A6-B", "O2", "SHJ", "ISB", dt(21, "01:30"), dt(21, "03:00")),
            fl("A6-C", "I3", "DXB", "SHJ", dt(21, "00:00"), dt(21, "01:00")), fl("A6-C", "O3", "SHJ", "ISB", dt(21, "03:00"), dt(21, "07:00"))]
    wins = {}
    for w in ground.ground_windows(rows):
        wins.setdefault(w["reg"], []).append(w)
    out = ground.balance_by_time({"A6-A": 300, "A6-B": 200, "A6-C": 100}, wins, ["E1", "E2"], clip=SHIFT)
    assert out["A6-A"] == "E1" and out["A6-B"] == "E2"
    assert out["A6-C"] == "E1"                      # A6-C overlaps A6-B (30 min) but not A6-A, so it joins E1


def test_balance_without_windows_falls_back_to_workload_and_needs_engineers():
    out = ground.balance_by_time({"A6-A": 3, "A6-B": 2, "A6-C": 1, "A6-D": 0}, {}, ["E1", "E2"])
    assert sorted(out.values()) == ["E1", "E1", "E2", "E2"]
    with pytest.raises(ValueError):
        ground.balance_by_time({"A6-A": 1}, {}, [])


def test_overlap_warning_needs_two_short_ground_times():
    wins = _three_at_0230()
    warn = ground.overlap_warnings({"A6-A": "E1", "A6-B": "E1", "A6-C": "E2"}, wins, SHIFT, short_hours=2.5)
    assert list(warn) == ["E1"] and warn["E1"][0]["aircraft"] == ["A6-A", "A6-B"] and warn["E1"][0]["overlap_minutes"] == 120
    assert ground.overlap_warnings({"A6-A": "E1", "A6-B": "E1"}, wins, SHIFT, short_hours=1.0) == {}      # nobody is tight
    wins["A6-LONG"] = [w for w in ground.ground_windows([fl("A6-LONG", "L1", "DXB", "SHJ", dt(20, "12:00"), dt(20, "14:00")),
                                                          fl("A6-LONG", "L2", "SHJ", "ISB", dt(22, "08:00"), dt(22, "12:00"))])]
    assert ground.overlap_warnings({"A6-A": "E1", "A6-LONG": "E1"}, wins, SHIFT, short_hours=2.5) == {}    # one short + one parked all night


# ============================================================ app (seeded database)
@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_meta_gets_schedule_facts_and_the_time_zone_assumption(client):
    m = client.get("/api/meta").json()
    assert m["schedule"]["times_are"] == "local" and m["schedule"]["flights"] == 8
    assert m["schedule"]["last_actual"] == "2026-11-19T11:02:00"
    text = {a["id"]: a["text"] for a in m["assumptions"]}["times"]
    assert "Sharjah local time, as written" in text and "11:02" in text and "22:00 to 06:00" in text


def test_aircraft_detail_has_a_schedule_block_with_sources(client):
    s = client.get("/api/aircraft/A6-AAB", params={"as_of": AS_OF}).json()["schedule"]
    assert s["available"] and s["tonight"]["arrival_flight"] == "G9011" and s["tonight"]["departure_flight"] == "G9012"
    assert s["tonight"]["ground_hours"] == pytest.approx(1.83) and s["tonight"]["tight"] and s["tonight"]["used_actuals"] is False
    assert s["tonight"]["sources"] == [{"file": schedule_service.FILE_NAME, "row": 5, "flight_no": "G9011"},
                                      {"file": schedule_service.FILE_NAME, "row": 6, "flight_no": "G9012"}]
    assert [f["flight_no"] for f in s["next_flights"]] == ["G9011", "G9012"]
    assert s["next_flights"][0]["source"]["row"] == 5 and s["next_flights"][0]["actual"] is False
    notes = s["notes"]["1003"]                                   # the item due today
    assert any("is after the deadline date" in n or "on or before" in n for n in notes)
    assert any("Only 1h50 on the ground" in n for n in notes)


def test_actual_times_are_labelled(client):
    s = client.get("/api/aircraft/A6-AAA", params={"as_of": "2026-11-19"}).json()["schedule"]
    assert s["last_actual"] == "2026-11-19T11:02:00"


def test_times_in_utc_are_shown_as_sharjah_time(client, monkeypatch):
    monkeypatch.setattr(config, "FLIGHT_TIMES_ARE", "utc")
    s = client.get("/api/aircraft/A6-AAA", params={"as_of": AS_OF}).json()["schedule"]
    assert s["times_are"] == "utc" and s["tonight"]["arrival_time"].startswith("2026-11-21T01:00")      # 21:00 + 4 h
    assert "UTC, shown as Sharjah time" in {a["id"]: a["text"] for a in client.get("/api/meta").json()["assumptions"]}["times"]


def test_roster_is_chosen_from_aircraft_on_the_ground_and_spread_in_time(client):
    plan = brief_service.plan_roster(D, D)
    assert plan["strategy"] == "time_balanced" and plan["schedule"]["available"]
    assert sorted(plan["assignments"]) == ["A6-AAA", "A6-AAB", "A6-AAC"]
    assert sorted(plan["assignments"].values()) == ["Engineer 1", "Engineer 2", "Engineer 3"]    # AAB and AAC land together
    r = client.post("/api/roster/auto", params={"shift_date": AS_OF}, headers=H).json()
    assert r["strategy"] == "time_balanced" and "overlap_warnings" in r["schedule"]
    last = client.get("/api/audit?limit=3").json()
    assert next(x for x in last if x["action"] == "roster_auto")["details"]["strategy"] == "time_balanced"


def test_overlap_warning_for_two_tight_aircraft_with_one_engineer(client):
    client.put("/api/roster", json={"aircraft_reg": "A6-AAB", "engineer": "Engineer 1", "shift_date": AS_OF}, headers=H)
    r = client.put("/api/roster", json={"aircraft_reg": "A6-AAC", "engineer": "Engineer 1", "shift_date": AS_OF}, headers=H).json()
    warn = r["schedule"]["overlap_warnings"]["Engineer 1"]
    assert warn[0]["aircraft"] == ["A6-AAB", "A6-AAC"] and warn[0]["overlap_minutes"] > 0
    b = client.get("/api/brief", params={"as_of": AS_OF}, headers=H).json()
    assert next(e for e in b["engineers"] if e["name"] == "Engineer 1")["overlap_warnings"]
    client.post("/api/roster/auto", params={"shift_date": AS_OF}, headers=H)


def test_urgent_aircraft_that_is_away_is_listed_not_dropped(client, monkeypatch):
    monkeypatch.setattr(config, "SHIFT_START", (14, 0))
    monkeypatch.setattr(config, "SHIFT_END", (17, 0))
    plan = brief_service.plan_roster(D, D)
    away = {a["aircraft_reg"]: a for a in plan["schedule"]["not_at_sharjah"]}
    assert "A6-AAB" not in plan["assignments"] and "A6-AAB" in away      # has items due today and soon
    assert away["A6-AAB"]["next_arrival"]["arrival_flight"] == "G9011"
    assert away["A6-AAB"]["next_arrival"]["arrival_time"] == dt(21, "02:30")
    client.post("/api/roster/auto", params={"shift_date": AS_OF}, headers=H)


def test_no_schedule_for_the_shift_falls_back_to_the_old_split(client):
    plan = brief_service.plan_roster(date(2026, 12, 25), D)
    assert plan["strategy"] == "snake_fallback" and plan["schedule"]["available"] is False
    assert "covers 2026-11-19 to 2026-11-19" not in plan["schedule"]["reason"] and plan["schedule"]["reason"]
    assert len(plan["assignments"]) == 3
    brief_service.set_assignment(date(2026, 12, 25), "A6-AAA", None)
    from app import db
    db.execute("DELETE FROM roster WHERE shift_date = %s", (date(2026, 12, 25),))
    s = client.get("/api/aircraft/A6-AAB", params={"as_of": "2026-12-25"}).json()["schedule"]
    assert s["available"] is False and s["tonight"] is None
