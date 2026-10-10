"""Offline unit tests (no API key, no network):  python -m tests.test_offline"""
import csv
import io
import json

from bill_decoder.calc import CalcError, safe_eval
from bill_decoder.evaluate import compare
from bill_decoder.postprocess import (consistency_issues, normalize, to_date, to_month,
                                      to_number)
from bill_decoder.qa import build_env, run_plans
from bill_decoder.schema import empty_level1
from test.sample_data import SAMPLE_BILL, SAMPLE_FACTS


def test_numbers():
    assert to_number("Rs. 19,964") == 19964
    assert to_number("38209CR") == -38209
    assert to_number("Rs. -0.53") == -0.53
    assert to_number("(12.5)") == -12.5
    assert to_number("1,054.00") == 1054
    assert to_number("") is None and to_number("null") is None and to_number(None) is None


def test_dates():
    assert to_date("22nd Sep 2026") == "2026-09-22"
    assert to_date("07-Apr-2026") == "2026-04-07"
    assert to_date("03-Apr-26") == "2026-04-03"
    assert to_date("2026-04-07") == "2026-04-07"
    assert to_date("31/02/2026") is None
    assert to_month("MAR 2026") == "2026-03"
    assert to_month("Apr-26") == "2026-04"
    assert to_month("2026-04-07") == "2026-04"


def test_normalize_messy_input():
    raw = json.loads(json.dumps(SAMPLE_BILL))
    raw.update(provider="K-Electric", bill_month="Apr-26", due_date="21-Apr-2026",
               arrears="Rs. -0.53", account_number="123456789", name="X")
    raw["charges"] = [{"type": "Fixed", "amount": "900.00"}, {"type": "FCA", "amount": "125.27"},
                      {"type": "energy", "amount": "0"}, {"type": "subsidy", "amount": "50"}]
    raw["taxes"] = [{"type": "sales tax", "amount": "Rs. 520.21"}]
    out = normalize(raw)
    assert set(out) == set(empty_level1()), "unknown keys (identifiers) must be dropped"
    assert out["provider"] == "KE" and out["bill_month"] == "2026-04" and out["due_date"] == "2026-04-21"
    assert out["charges"] == [{"type": "fixed", "amount": 900}, {"type": "fpa", "amount": 125.27},
                              {"type": "subsidy", "amount": -50}]
    assert out["taxes"] == [{"type": "gst", "amount": 520.21}]
    assert out["arrears"] == -0.53


def test_consistency():
    assert consistency_issues(SAMPLE_BILL) == []
    bad = json.loads(json.dumps(SAMPLE_BILL))
    bad["charges"][0]["amount"] = 90
    assert consistency_issues(bad)


def test_calc():
    assert abs(safe_eval("(569.62/3430.24)*100") - 16.6058) < 0.001
    assert safe_eval("count_gt([239, 203, 151], 200)") == 2
    assert safe_eval("avg(x)", {"x": [1, 2, 3]}) == 2
    assert safe_eval("x[-1] + 1", {"x": [1, 2, 3]}) == 4
    assert safe_eval("pct(1, 4)") == 25
    for evil in ("__import__('os').system('x')", "().__class__", "open('f')", "2**999", "1/0", "y"):
        try:
            safe_eval(evil, {})
        except CalcError:
            continue
        raise AssertionError(f"should have been rejected: {evil}")


def test_planner_env():
    env = build_env(SAMPLE_BILL, SAMPLE_FACTS)
    assert env["charges_energy"] == 1717.51 and env["late_surcharge"] == 286
    res = run_plans([{"id": "Q2", "computations": [
        {"name": "n", "expr": "count_gt(usage_previous_months, 200)"},
        {"name": "bad", "expr": "nope + 1"}]}], env)
    assert res["Q2"]["computed"]["n"] == 2 and str(res["Q2"]["computed"]["bad"]).startswith("ERROR")


def test_evaluate():
    assert compare(SAMPLE_BILL, SAMPLE_BILL)[:2] == (25, 25)
    off = json.loads(json.dumps(SAMPLE_BILL))
    off["current_bill"] = 3500
    off["taxes"].append({"type": "other_tax", "amount": 5})
    ok, total, bad = compare(off, SAMPLE_BILL)
    assert ok == 24 and total == 26 and len(bad) == 2


def test_csv_quoting():
    from bill_decoder.csv_io import write_rows, read_rows
    import tempfile, pathlib
    d = pathlib.Path(tempfile.mkdtemp())
    value = json.dumps(SAMPLE_BILL, ensure_ascii=False, separators=(",", ":"))
    write_rows(d / "x.csv", ["bill_id", "json"], [{"bill_id": "KESC_0008", "json": value}])
    raw = (d / "x.csv").read_text(encoding="utf-8")
    assert '""provider""' in raw and raw.count("\n") == 2  # doubled quotes, one line per row
    assert json.loads(read_rows(d / "x.csv")[1][0]["json"]) == SAMPLE_BILL


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
    print("ALL OFFLINE TESTS PASSED")
