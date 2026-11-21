"""MMEL XML parsing and helpers. Samples are cut down from the real Airbus files (same tags)."""
from pathlib import Path

from app.etl import extract_mmel as x
from app.rules import mmel

PRODUCT_MDATA = """<?xml version="1.0" encoding="UTF-8"?>
<product-mdata revdate="2026-08-19T20:04:20"><aircraft-list>
<aircraft-item acn="A6-ANS" aircraft-model="320-214" msn="05772"/>
<aircraft-item acn="A6-XXX" aircraft-model="320-214" msn="09999"/>
</aircraft-list></product-mdata>"""

PRODUCT = """<?xml version="1.0" encoding="UTF-8"?>
<product><du-inv code="00008798" func-code="36-11-07"/><du-inv code="00008788" func-code="36-11-01"/></product>"""

ITEM = """<?xml version="1.0" encoding="UTF-8"?>
<dispatchitem code="00008798.0001001" func-code="36-11-07" revdate="2019-05-22T00:00:00">
<title>Engine Bleed <abb>HP</abb> Valve</title><ditembody nb-installed="2">
<dispcond dispcond-label="A"><title>Associated bleed considered inoperative</title>
<normal-dispcond nb-required="1" rectification-interval="C"><remark><requirement>
<para>One may be inoperative in the closed position.</para><para><duref product="MMEL" ref="00008788"/></para>
</requirement></remark></normal-dispcond></dispcond>
<dispcond dispcond-label="B"><title><abb>HP</abb> valve secured in the closed position</title>
<normal-dispcond nb-required="1" rectification-interval="C"><placard/><remark><requirementblock><requirement>
<opsproc-ref><duref product="MMEL" ref="00008872"/></opsproc-ref>
<maintenance-ref><taskref chap-nbr="36" func="040" product="AMM Task" sect-nbr="11" seq="003" subj-nbr="00"/></maintenance-ref>
<qualifiers><qualifier value="CREW_OPS"/></qualifiers><para>One may be inoperative provided that:</para></requirement>
<addrequ><requirement><para>The opposite engine bleed supply system is operative.</para></requirement></addrequ>
</requirementblock></remark></normal-dispcond></dispcond>
</ditembody></dispatchitem>"""

ITEM_MDATA = """<?xml version="1.0" encoding="UTF-8"?>
<dumdata code="00008798.0001001"><effect len="5" type="MSN"><aircraft-ranges>
<effact><aircraft-range>03152 05772 0722507226</aircraft-range></effact>
<open-effact><aircraft-range>0315299999</aircraft-range></open-effact>
</aircraft-ranges></effect></dumdata>"""

ECAM = """<?xml version="1.0" encoding="UTF-8"?>
<malfunctionassessment code="00008247.0002001" fault-code="AIR ENG 1 BLEED FAULT;AIR ENG 2 BLEED FAULT" type="ecamcaution">
<xtitle><ecamsystem>AIR</ecamsystem><title>ENG 1(2) BLEED FAULT</title></xtitle>
<assessment><routing><cond-routing><intro>If the Engine Bleed HP Valve is failed open</intro></cond-routing></routing>
<dispatch-assessment><dispatchitemref><duref product="MMEL" ref="00008798"><linktext>Item
36-11-07B Engine Bleed HP Valve</linktext></duref></dispatchitemref></dispatch-assessment></assessment>
<assessment><dispatch-assessment><no-dispatch/></dispatch-assessment></assessment>
</malfunctionassessment>"""

INVENTORY = x.parse_inventory(PRODUCT)


def write_sample(folder: Path) -> None:
    """The real folder layout, used by test_etl too."""
    data = folder / "MMEL_XML" / "DATA"
    (data / "DU").mkdir(parents=True)
    (data / "MU").mkdir()
    (data / "XML_N_MMEL_ABY_TF_N_EU__20260819_mdata.xml").write_text(PRODUCT_MDATA, encoding="utf-8")
    (data / "XML_N_MMEL_ABY_TF_N_EU__20260819.xml").write_text(PRODUCT, encoding="utf-8")
    (data / "DU" / "00008798.0001001.xml").write_text(ITEM, encoding="utf-8")   # 2 dispatch conditions
    (data / "MU" / "00008798.0001001_mdata.xml").write_text(ITEM_MDATA, encoding="utf-8")
    (data / "DU" / "00008247.0002001.xml").write_text(ECAM, encoding="utf-8")


# ------------------------------------------------------------------ rules
def test_msn_tokens_reads_ten_digit_runs_as_ranges():
    assert mmel.msn_tokens("03152 0722507226 5772") == ["03152", "07225-07226", "05772"]


def test_msn_applies():
    tokens = ["03152", "07225-07226"]
    assert mmel.msn_applies("07225", tokens) and mmel.msn_applies("07226", tokens)
    assert mmel.msn_applies("03152", tokens)
    assert not mmel.msn_applies("07227", tokens) and not mmel.msn_applies(None, tokens)


def test_find_items_normalises_written_item_numbers():
    assert mmel.find_items("MDD RAISED. MEL 33-20-01-A CAT C, SEE 36-11-07B") == ["33-20-01A", "36-11-07B"]
    assert mmel.find_items("PER MEL 21-01-01-01") == ["21-01-01-01"]
    assert mmel.base_item("36-11-07B") == "36-11-07"


# ------------------------------------------------------------------ XML
def test_fleet_maps_registration_to_msn():
    issue, fleet = x.parse_fleet(PRODUCT_MDATA)
    assert issue == "2026-08-19"
    assert {"aircraft_reg": "A6-ANS", "msn": "05772", "model": "320-214"} in fleet


def test_effect_uses_closed_list_only():
    assert x.parse_effect(ITEM_MDATA) == ["03152", "05772", "07225-07226"]


def test_dispatch_item_conditions():
    rows = x.parse_dispatch_item(ITEM, INVENTORY)
    a, b = rows
    assert a["item_code"] == "36-11-07A" and a["repair_interval"] == "C" and a["nb_installed"] == "2"
    assert "Refer to Item 36-11-01" in a["requirements"] and a["placard"] is False
    assert b["item_code"] == "36-11-07B" and b["condition_title"] == "HP valve secured in the closed position"
    assert b["placard"] and b["ops_proc"] and b["maint_proc"]
    assert b["amm_tasks"] == ["36-11-00-040-003"] and b["qualifiers"] == ["CREW_OPS"]
    assert b["requirements"].splitlines() == ["One may be inoperative provided that:",
                                              "The opposite engine bleed supply system is operative."]


def test_ecam_warning_links_to_item_or_no_dispatch():
    rows = x.parse_malfunction(ECAM, INVENTORY)
    item_rows = [r for r in rows if r["outcome"] == "ITEM"]
    assert {r["fault_code"] for r in item_rows} == {"AIR ENG 1 BLEED FAULT", "AIR ENG 2 BLEED FAULT"}
    assert item_rows[0]["item_code"] == "36-11-07B"
    assert item_rows[0]["condition"] == "If the Engine Bleed HP Valve is failed open"
    assert {r["outcome"] for r in rows} == {"ITEM", "NO_DISPATCH"}


def test_other_files_are_ignored():
    assert x.parse_dispatch_item(ECAM, INVENTORY) == [] and x.parse_malfunction(ITEM, INVENTORY) == []


def test_all_aircraft_applicability():
    assert x.parse_effect('<dumdata><effect><aircraft-ranges><effact><all/></effact></aircraft-ranges></effect></dumdata>') == ["ALL"]
    assert mmel.msn_applies("05772", ["ALL"])


def test_combined_items_and_nested_routing():
    xml = """<malfunctionassessment code="1" fault-code="X FAULT"><assessment><dispatch-assessment>
    <dablock operator="AND"><dispatchitemref><duref product="MMEL" ref="00008798"/></dispatchitemref>
    <dispatchitemref><duref product="MMEL" ref="00008788"/></dispatchitemref></dablock></dispatch-assessment></assessment>
    <assessment><dispatch-assessment><complementary-actions><assessment><dispatch-assessment><no-dispatch/>
    </dispatch-assessment></assessment></complementary-actions></dispatch-assessment></assessment></malfunctionassessment>"""
    rows = x.parse_malfunction(xml, INVENTORY)
    items = [r for r in rows if r["outcome"] == "ITEM"]
    assert [r["item_code"] for r in items] == ["36-11-07", "36-11-01"]
    assert items[0]["condition"] == "(all of these items)"
    assert sorted(r["outcome"] for r in rows if r["outcome"] != "ITEM") == ["NO_DISPATCH", "SEE_CONDITIONS"]
