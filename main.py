"""CLI entry point.

  python main.py run  --bills test/bills --level1 test/csv/level1.csv --level2 test/csv/level2.csv --out output
  python main.py bill path/to/KESC_0008.png [--ask "How much of my bill is taxes?"]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from bill_decoder.config import load_settings
from bill_decoder.llm import LLM
from bill_decoder.csv_io import find_image
from bill_decoder.evaluate import compare
from bill_decoder.pipeline import analyse_bill, make_cache, run_all


def cmd_run(a, settings) -> None:
    run_all(settings, a.bills, a.level1, a.level2, a.out)


def cmd_bill(a, settings) -> None:
    """Single-bill mode, used for development and the demo video."""
    llm = LLM(settings)
    cache = make_cache(settings)
    image = Path(a.image)   
    questions = [(f"Q{i}", q) for i, q in enumerate(a.ask, 1)] or None
    bill, facts, answers = analyse_bill(llm, cache, image.stem, image, questions)
    print("=== Level 1 ===")
    print(json.dumps(bill, indent=2, ensure_ascii=False))
    if a.show_facts:
        print("=== Extra facts ===")
        print(json.dumps(facts, indent=2, ensure_ascii=False))
    for qid, q in questions or []:
        print(f"\n{qid}: {q}\n-> {answers[qid]}")


def cmd_eval(a, settings) -> None:
    """Score Level 1 extraction on bills that have a hand-checked train/expected/<id>.json."""
    llm = LLM(settings)
    cache = make_cache(settings)
    tot_ok = tot = 0
    for exp_path in sorted(Path(a.expected).glob("*.json")):
        bill_id = exp_path.stem
        image = find_image(a.bills, bill_id)
        if image is None:
            print(f"{bill_id}: image not found, skipped")
            continue
        got, _, _ = analyse_bill(llm, cache, bill_id, image, None)
        ok, n, bad = compare(got, json.loads(exp_path.read_text(encoding="utf-8")))
        tot_ok, tot = tot_ok + ok, tot + n
        print(f"{bill_id}: {ok}/{n} fields correct")
        for line in bad:
            print("   x", line)
    if tot:
        print(f"\nOVERALL: {tot_ok}/{tot} = {100 * tot_ok / tot:.1f}%")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Utility Bill Decoder")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="process a folder of bills and write both CSVs")
    r.add_argument("--bills", required=True, help="folder with bill images")
    r.add_argument("--level1", required=True, help="level1.csv template")
    r.add_argument("--level2", required=True, help="level2.csv template")
    r.add_argument("--out", default="output", help="output folder (default: output)")
    r.set_defaults(fn=cmd_run)

    b = sub.add_parser("bill", help="analyse one bill image")
    b.add_argument("image")
    b.add_argument("--ask", action="append", default=[], help="a question (repeatable)")
    b.add_argument("--show-facts", action="store_true")
    b.set_defaults(fn=cmd_bill)

    e = sub.add_parser("eval", help="score Level 1 against train/expected/*.json")
    e.add_argument("--bills", default="train/bills")
    e.add_argument("--expected", default="train/expected")
    e.set_defaults(fn=cmd_eval)

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    args.fn(args, load_settings())
    return 0


if __name__ == "__main__":
    sys.exit(main())
