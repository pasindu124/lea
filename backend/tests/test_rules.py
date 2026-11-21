from datetime import date

import pytest

from app.rules import citations, deadlines, parts, text, tools
from app.rules.roster import snake_assign

OPENED = date(2026, 11, 1)


def parse(actions, desc="FAULT", opened=OPENED):
    return deadlines.parse_deferral(desc, actions, opened)


# ------------------------------------------------------------- deadlines
def test_category_b_c_d_days():
    assert parse("DEFERRED PER MEL 25-00-01 CAT B").expires_on == date(2026, 11, 4)
    assert parse("DEFERRED PER MEL 25-00-01 CAT C").expires_on == date(2026, 11, 11)
    assert parse("DEFERRED PER MEL 25-00-01 CAT. D").expires_on == date(2027, 3, 1)


def test_category_is_assumption_but_stated_days_is_not():
    assert parse("MEL 25-00-01 CAT C").is_assumption is True
    assert parse("NSI DEFERRAL FOR 120 DAYS").is_assumption is False


def test_item_letter_is_not_the_category():
    d = parse("DEFERRED PER MEL 36-11-07B.")
    assert d.kind == "UNKNOWN" and d.expires_on is None and d.category is None


def test_category_a_has_no_date():
    d = parse("DEFERRED MEL 21-31-01 CAT A")
    assert d.kind == "CATEGORY_A" and d.expires_on is None


def test_nsi_stated_days():
    d = parse("DD RAISED NSI 444.26 FOR 120 DAYS")
    assert d.kind == "STATED_DAYS" and d.days == 120 and d.expires_on == date(2027, 3, 1)


def test_within_days_is_read_as_stated():
    assert parse("ADD RAISED FOR TEST RESULTS WITHIN 30 DAYS").expires_on == date(2026, 12, 1)


def test_days_or_flight_whichever_first():
    d = parse("DD RAISED RE-INSPECTION AT 750FC OR 750FH OR 120DAYS WHICHEVER OCCURS FIRST", "FOR 120 DAYS")
    assert d.kind == "DAYS_OR_FLIGHT" and d.expires_on == date(2027, 3, 1) and "LATEST" in d.rule


def test_flight_cycles_only_gives_no_date():
    d = parse("DD RAISED. REPEAT BSI EVERY 400 FC")
    assert d.kind == "FLIGHT_ONLY" and d.expires_on is None


def test_repeat_inspection_every_days_gives_no_date():
    d = parse("ADD RAISED INSPECTION EVERY 10 DAYS IAW SRM")
    assert d.kind == "REPEAT_INTERVAL" and d.expires_on is None


def test_next_check_gives_no_date():
    assert parse("ADD RAISED FOR REPAIR AT NEXT MAINT CHECK").kind == "NEXT_CHECK"


def test_reference_number_is_not_a_deferral():
    assert parse("REFERENCE ONLY", desc="REF TO DD000667 BSI PERFORMED") is None


def test_plain_fault_is_not_a_deferral():
    assert parse("INSPECTED, SEAL TO BE REPLACED", desc="DOOR SEAL WORN") is None


def test_description_only_is_marked():
    d = deadlines.parse_deferral("DD TO BE RAISED CAT B", "", OPENED)
    assert d.where_found == "description"


def test_missing_open_date_gives_no_deadline():
    assert parse("MEL CAT B", opened=None).expires_on is None


@pytest.mark.parametrize("expires,status,left", [
    (date(2026, 11, 17), "OVERDUE", -3), (date(2026, 11, 20), "EXPIRES_TODAY", 0),
    (date(2026, 11, 23), "EXPIRES_SOON", 3), (date(2026, 11, 24), "OK", 4), (None, "CHECK_SOURCE", None)])
def test_classify(expires, status, left):
    assert deadlines.classify(expires, date(2026, 11, 20)) == (status, left)


def test_recent_entries_window_and_duplicates():
    actions = "[19-Nov-2026] DONE A | [19-Nov-2026] DONE A | [10-Nov-2026] OLD | [20-Nov-2026] DONE B"
    got = deadlines.recent_entries(actions, date(2026, 11, 20))
    assert [e["text"] for e in got] == ["DONE A", "DONE B"]


# ------------------------------------------------------------------ parts
def row(store, cond, owner, qty=1, part="P1"):
    return {"part_no": part, "description": "X", "store": store, "cond": cond, "owner": owner, "qty": qty}


@pytest.mark.parametrize("rows,verdict", [
    ([row("SHJLINE", "N", "ABY")], "AVAILABLE_LINE"),
    ([row("SHJMAIN", "N", "ABY")], "MAIN_ONLY"),
    ([row("SHJLINE", "N", "MAC")], "OTHER_OWNER"),
    ([row("SHJLINE", "US", "ABY")], "UNSERVICEABLE_ONLY"),
    ([row("SHJLINE", "US", "ABY"), row("SHJMAIN", "N", "ABY")], "MAIN_ONLY"),
    ([row("SHJLINE", None, "ABY")], "AVAILABLE_LINE"),
])
def test_parts_verdicts(rows, verdict):
    assert parts.summarise(rows)[0]["verdict"] == verdict


def test_unserviceable_never_counts_as_available():
    s = parts.summarise([row("SHJLINE", "US", "ABY", qty=5)])[0]
    assert s["line_usable"] == 0 and s["unserviceable"] == 5


# ------------------------------------------------------------------ tools
def test_placeholder_expiry_detected_only_when_dominant():
    same = [date(2026, 11, 20)] * 95 + [date(2027, 1, 1)] * 5
    assert tools.detect_placeholder_expiry(same) == date(2026, 11, 20)
    varied = [date(2026, 11, 20)] * 40 + [date.fromordinal(date(2027, 1, 1).toordinal() + i) for i in range(60)]
    assert tools.detect_placeholder_expiry(varied) is None


def test_calibration_statuses():
    today, ph = date(2026, 11, 20), date(2026, 11, 20)
    assert tools.calibration_status(None, today, ph)["status"] == "NO_EXPIRY"
    assert tools.calibration_status(ph, today, ph)["status"] == "UNVERIFIED"
    assert tools.calibration_status(date(2026, 1, 1), today, ph)["status"] == "EXPIRED"
    assert tools.calibration_status(date(2026, 12, 1), today, ph)["status"] == "EXPIRES_SOON"
    assert tools.calibration_status(date(2027, 6, 1), today, ph)["status"] == "IN_DATE"


# --------------------------------------------------------- text and citations
def test_norm_and_keywords():
    assert text.norm("1152682-3") == "11526823"
    assert text.heuristic_keywords("ENG ENTRY: DURING CHECK FOUND BRAKE UNIT DAMAGED")[:1] == ["BRAKE"]


def test_citation_validation():
    ok = citations.validate("Fix it [WO1] and see [AV1].", {"WO1", "AV1"})
    assert ok["ok"] and ok["cited"] == ["AV1", "WO1"]
    bad = citations.validate("See [WO999].", {"WO1"})
    assert not bad["ok"] and bad["unknown"] == ["WO999"]
    assert not citations.validate("No sources here.", {"WO1"})["ok"]


# ------------------------------------------------------------------ roster
def test_snake_assign_balances():
    got = snake_assign(["a", "b", "c", "d", "e", "f", "g"], ["E1", "E2", "E3"])
    assert [got[k] for k in "abcdefg"] == ["E1", "E2", "E3", "E3", "E2", "E1", "E1"]
    with pytest.raises(ValueError):
        snake_assign(["a"], [])
