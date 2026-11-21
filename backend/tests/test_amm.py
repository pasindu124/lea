"""AMM task numbers in text, the SGML reader, and the work-order AMM endpoint."""
import pytest
from fastapi.testclient import TestClient

from app import db
from app.etl import extract_amm
from app.rules.amm import extract_task_refs, function_label

SAMPLE = (
    '<AMM><TASK CHAPNBR="26" CONFLTR="A" CONFNBR="00" FUNC="400" KEY="EN1" SECTNBR="23" SEQ="004" SUBJNBR="41" REVDATE="20260501">'
    '<TITLE>Installation of the Cargo Fire-Extinguisher Bottle</TITLE><WARNING>&W.1;</WARNING>'
    '<ASSODATA><ZONELST><ZONE>130</ZONE></ZONELST><EINLST><EINDATA><EIN TYPE="EXACT">4005-WX</EIN></EINDATA></EINLST></ASSODATA>'
    '<TFMATR><PRETOPIC><LIST1>'
    '<L1ITEM><PARA>Fixtures, Tools, Test and Support Equipment</PARA><TABLE><TBODY>'
    '<THEAD><ROW><ENTRY><PARA>REFERENCE</PARA></ENTRY><ENTRY><PARA>QTY</PARA></ENTRY><ENTRY><PARA>DESIGNATION</PARA></ENTRY></ROW></THEAD>'
    '<ROW><ENTRY><PARA><TOOLNBR>10-101950-81</TOOLNBR></PARA></ENTRY><ENTRY><PARA>2</PARA></ENTRY><ENTRY><PARA>SHUNT PLUG</PARA></ENTRY></ROW>'
    '<ROW><ENTRY><PARA>No specific</PARA></ENTRY><ENTRY><PARA>AR</PARA></ENTRY><ENTRY><PARA><STDNAME>CAP - BLANKING</STDNAME></PARA></ENTRY></ROW>'
    '</TBODY></TABLE></L1ITEM>'
    '<L1ITEM><PARA>Expendable Parts</PARA><TABLE><TBODY>'
    '<THEAD><ROW><ENTRY><PARA>FIG.ITEM</PARA></ENTRY><ENTRY><PARA>DESIGNATION</PARA></ENTRY><ENTRY><PARA>IPC-CSN</PARA></ENTRY></ROW></THEAD>'
    '<ROW><ENTRY><PARA>12</PARA></ENTRY><ENTRY><PARA>LOCK WASHER</PARA></ENTRY><ENTRY><PARA><EXPD><CSN>26230202-100</CSN></EXPD></PARA></ENTRY></ROW>'
    '</TBODY></TABLE></L1ITEM></LIST1></PRETOPIC></TFMATR></TASK></AMM>'
)


def test_task_refs_found_in_free_text():
    text = ("REMOVE CARGO FIRE EXTINGUISHER IAW AMM 26-23-41-000-004 OR AMM TASK 26-23-42-000-001-A. "
            "REF 26-16-00-710-001. DEFER 36-11-07B AND DD000667; again 26-23-41-000-004")
    assert extract_task_refs(text) == ["26-23-41-000-004", "26-23-42-000-001", "26-16-00-710-001"]
    assert extract_task_refs(None) == []
    assert extract_task_refs("part 126-23-41-000-0045") == []


def test_function_labels():
    assert function_label("000") == "Removal" and function_label("400") == "Installation"
    assert function_label("999") == "Task type 999"


def test_parse_task_reads_tools_parts_and_notes():
    t = extract_amm.parse_task(SAMPLE, {"CHAPNBR": "26", "SECTNBR": "23", "SUBJNBR": "41", "FUNC": "400", "SEQ": "004",
                                        "CONFLTR": "A", "REVDATE": "20260501"}, {"W.1": "BE CAREFUL"})
    assert t["task_no"] == "26-23-41-400-004-A" and t["fins"] == ["4005-WX"] and t["zones"] == ["130"]
    assert t["notes"] == [{"kind": "warning", "code": "W.1", "text": "BE CAREFUL"}]
    kinds = [(i["kind"], i["ref"], i["designation"], i["extra"]) for i in t["items"]]
    assert ("tool", "10-101950-81", "SHUNT PLUG", None) in kinds
    assert ("tool", None, "CAP - BLANKING", None) in kinds
    assert ("part", "12", "LOCK WASHER", "26230202-100") in kinds
    assert not any(i["ref"] in ("REFERENCE", "FIG.ITEM") for i in t["items"])      # header rows skipped


@pytest.fixture()
def client(tmp_path):
    sgm = tmp_path / "SGML" / "AMM.SGM"
    sgm.parent.mkdir()
    sgm.write_text(SAMPLE, encoding="latin1")
    (sgm.parent / "AMM.SWE").write_text('<!ENTITY W.1 "<PARA>BE CAREFUL</PARA>">', encoding="latin1")
    db.execute("TRUNCATE amm_tasks CASCADE")
    assert extract_amm.load_amm([sgm]) == 1
    db.execute("DELETE FROM work_orders WHERE wo_number = 777001")
    db.execute("INSERT INTO work_orders (source_row, wo_number, aircraft_reg, operator_code, wo_type, date_opened, wo_state, "
               "wo_description, wo_actions) VALUES (9, 777001, 'A6-AMM', 'ABY', 'MAREP', '2026-11-01', 'O', "
               "'REPLACE BOTTLE IAW AMM 26-23-41-400-004 AND AMM 99-99-99-000-001', NULL)")
    from app.main import app
    yield TestClient(app)
    db.execute("DELETE FROM work_orders WHERE wo_number = 777001")
    db.execute("TRUNCATE amm_tasks CASCADE")


def test_work_order_amm_endpoint(client):
    r = client.get("/api/faults/777001/amm").json()
    assert r["not_in_amm"] == ["99-99-99-000-001"]
    task = r["tasks"][0]
    assert task["base_task"] == "26-23-41-400-004" and task["function_label"] == "Installation"
    v = task["variants"][0]
    assert [i["designation"] for i in v["items"] if i["kind"] == "part"] == ["LOCK WASHER"]
    assert v["notes"][0]["text"] == "BE CAREFUL"
    shunt = next(i for i in v["items"] if i["ref"] == "10-101950-81")
    assert shunt["stock"] == {"rows": 0, "qty": 0.0}
    assert client.get("/api/faults/1/amm").status_code == 404
    assert client.get("/api/amm/tasks/26-23-41-400-004").status_code == 200
    assert client.get("/api/amm/tasks/00-00-00-000-000").status_code == 404
