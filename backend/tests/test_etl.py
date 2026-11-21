"""The loaders must accept the real file layouts. Tiny files with the same columns."""
from datetime import date

import pandas as pd

from app import db
from app.etl import load_data as etl


def test_all_loaders_accept_the_real_layouts(tmp_path):
    pd.DataFrame({"Store": ["SHJLINE"], "Location": ["L1"], "Part No.:": ["P-1"], "Serial/Batch No.": ["S1"],
                  "Description": ["TEST PART"], "Mat. Class": ["R"], "Qty": [2], "Cond.": ["N"], "Order No.": [None],
                  "Rec. Date": [pd.Timestamp("2026-01-02")], "Owner": ["ABY"], "Entity": ["ABY"]}
                 ).to_excel(tmp_path / "Inventory_List.xlsx", index=False)
    tool_cols = {"Part Number": ["T-1"], "SN/BN": ["S"], "Description": ["TOOL"], "ID": [123], "MC": ["R"], "Co": ["N"],
                 "Received": [pd.Timestamp("2025-01-01")], "Expires": [pd.Timestamp("2026-11-20")], "Partly Rec.": [False],
                 "Station": ["SHJ"], "Store": ["LINEWH"], "Location": ["X"], "Workload": [None], "Qty": [1]}
    pd.DataFrame(tool_cols).to_excel(tmp_path / "Tools_SHJLINE.xlsx", index=False)
    pd.DataFrame({**tool_cols, "Store": ["SHJMAINW"]}).to_excel(tmp_path / "Tools_SHJMAIN.xlsx", index=False)
    pd.DataFrame({"wo_number": [5], "aircraft_reg": ["A6-XXX"], "operator_code": ["ABY"], "wo_type": ["MAREP"],
                  "date_opened": ["2026-11-01"], "date_closed": [None], "ata": ["25-00"], "wo_description": ["D"],
                  "wo_actions": ["A"], "wo_state": ["Open"]}).to_excel(tmp_path / "Maintenance_History.xlsx", index=False)
    pd.DataFrame({"Max Severity": ["Alert"], "ACREG": ["A6-XXX"], "ATA": [32], "Use Case": ["Brake Temperature"],
                  "Title": ["High Brake 1 Temperature"], "System": ["max-temperature"], "Case Type": ["right"], "Remarks": [0],
                  "Classification": ["Ambiguous"], "Impact": ["High"], "Opened": ["13-11-2026 18:32:19"],
                  "Updated": ["14-11-2026 08:00:00"], "Status": ["OPEN"], "Case File Link": ["https://x"]}
                 ).to_csv(tmp_path / "PHA_Case_Tracking_x.csv", index=False, encoding="utf-8-sig")
    av = {"Prio": ["HIGH"], "Msg Code": [None], "Message": ["M"], "Message Type": ["FAULT_MESSAGE"], "A/C Type": ["A320"],
          "A/C": ["A6-XXX"], "Flight": ["G1"], "Phase": [6], "Ata": ["34-00"], "Source": [None], "Class": [None],
          "Level": [None], "Occurrence": ["2026-11-20 06:07:00"], "Repetitive": [True], "Multiple": [False]}
    pd.DataFrame(av).to_csv(tmp_path / "AVIATAR Faults TIME 1.csv", index=False)
    pd.DataFrame(av).to_csv(tmp_path / "AVIATAR Faults TIME 2.csv", index=False)   # exact duplicate file

    from tests.test_amm import SAMPLE
    (tmp_path / "SGML").mkdir()
    (tmp_path / "SGML" / "AMM.SGM").write_text(SAMPLE, encoding="latin1")
    from tests.test_mmel import write_sample
    write_sample(tmp_path)

    saved = {t: db.query_one(f"SELECT count(*) AS n FROM {t}")["n"] for t in etl.TABLES.values()}
    try:
        for key, loader in etl.LOADERS.items():
            files = etl.find_files(tmp_path, key)
            assert files, f"no file found for {key}"
            db.execute(f"TRUNCATE {etl.TABLES[key]} RESTART IDENTITY" + (" CASCADE" if key == "amm" else ""))
            expected = 2 if key in ("tools", "mmel") else 1   # tools: two files; mmel: two conditions; aviatar drops the duplicate
            assert loader(files) == expected, key
        row = db.query_one("SELECT * FROM pha_cases")
        assert row["opened"].day == 13 and row["opened"].month == 11     # dd-mm-yyyy read correctly
        assert db.query_one("SELECT source_row FROM parts_stock")["source_row"] == 2
        assert db.query_one("SELECT search_norm FROM parts_stock")["search_norm"].startswith("P1")
        assert db.query_one("SELECT msn FROM fleet_msn WHERE aircraft_reg = 'A6-ANS'")["msn"] == "05772"
        assert db.query_one("SELECT count(*) AS n FROM mmel_ecam WHERE item_code = '36-11-07B'")["n"] == 2
        info = etl.update_meta()
        assert info["as_of"] == date(2026, 11, 20) and info["tools_placeholder_expiry"] == date(2026, 11, 20)
    finally:                                                             # put the seeded test data back
        db.execute("TRUNCATE parts_stock, tools, work_orders, aviatar_faults, pha_cases, amm_tasks, mmel_items, mmel_ecam, fleet_msn CASCADE")
        from tests import conftest
        conftest.seed(db)
