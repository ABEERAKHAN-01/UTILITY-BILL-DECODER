"""End-to-end run with a fake LLM (no API key):  python -m tests.test_pipeline_fake_llm"""
import copy
import json
import logging
import tempfile
from pathlib import Path

from PIL import Image

from bill_decoder.config import Settings
from bill_decoder.csv_io import read_rows, write_rows
from bill_decoder.pipeline import run_all
from bill_decoder.qa import FALLBACK
from bill_decoder.schema import empty_level1
from test.sample_data import SAMPLE_BILL, SAMPLE_FACTS


class FakeLLM:
    def __init__(self, settings):
        self.settings = settings
        self.calls: list[str] = []
        self.prompts: dict[str, str] = {}

    def ask_json(self, prompt, image=None, system=None):
        tag = prompt.split("\n", 1)[0].strip()
        self.calls.append(tag)
        self.prompts[tag] = prompt
        if tag == "[TASK:LEVEL1]":     # messy + one misread digit -> triggers the re-look
            raw = copy.deepcopy(SAMPLE_BILL)
            raw["charges"][0]["amount"] = "Rs. 90"
            raw["current_bill"] = "Rs. 3,430.24"
            return raw
        if tag == "[TASK:RELOOK]":
            return copy.deepcopy(SAMPLE_BILL)
        if tag == "[TASK:FACTS]":
            return copy.deepcopy(SAMPLE_FACTS)
        if tag == "[TASK:QA_PLAN]":
            return {"plans": [
                {"id": "Q1", "interpretation": "tax share", "computations": [
                    {"name": "tax_pct", "expr": "pct(total_taxes, current_bill)"}]},
                {"id": "Q2", "interpretation": "months over 200", "computations": [
                    {"name": "n", "expr": "count_gt(usage_previous_months, 200)"}]}]}
        if tag == "[TASK:QA_ANSWER]":
            return {"answers": {"Q1": "Taxes are about 16.6% of the bill.",
                                "Q2": "Two previous months exceeded 200 units."}}
        raise AssertionError(f"unexpected prompt {tag}")


def main():
    logging.basicConfig(level=logging.WARNING)
    tmp = Path(tempfile.mkdtemp())
    (tmp / "bills").mkdir()
    Image.new("RGB", (200, 300), "white").save(tmp / "bills" / "KESC_0008.png")
    write_rows(tmp / "l1.csv", ["bill_id", "json"],
               [{"bill_id": "KESC_0008", "json": ""}, {"bill_id": "MISSING_0001", "json": ""}])
    qs = [("Q1", "How much of my bill is taxes?"), ("Q2", "How many months went above 200 units?")]
    write_rows(tmp / "l2.csv", ["bill_id", "question_id", "question", "answer"],
               [{"bill_id": b, "question_id": q, "question": t, "answer": ""}
                for b in ("KESC_0008", "MISSING_0001") for q, t in qs])

    settings = Settings("google", "fake-model", "x", 0.0, 2, str(tmp / "cache"), 2400)
    llm = FakeLLM(settings)
    run_all(settings, tmp / "bills", tmp / "l1.csv", tmp / "l2.csv", tmp / "out", llm=llm)

    _, l1 = read_rows(tmp / "out" / "level1.csv")
    _, l2 = read_rows(tmp / "out" / "level2.csv")
    assert len(l1) == 2 and len(l2) == 4
    assert json.loads(l1[0]["json"]) == SAMPLE_BILL, "re-look should have fixed the misread digit"
    assert json.loads(l1[1]["json"]) == empty_level1(), "missing image degrades to nulls"
    assert "[TASK:RELOOK]" in llm.calls
    assert "16.6058" in llm.prompts["[TASK:QA_ANSWER]"], "arithmetic must be computed by code"
    assert l2[0]["answer"].startswith("Taxes") and l2[2]["answer"] == FALLBACK

    n_calls = len(llm.calls)                      # second run must come from the cache
    run_all(settings, tmp / "bills", tmp / "l1.csv", tmp / "l2.csv", tmp / "out", llm=llm)
    assert len(llm.calls) == n_calls, "cache was not used"
    print("PIPELINE TEST PASSED")


if __name__ == "__main__":
    main()
