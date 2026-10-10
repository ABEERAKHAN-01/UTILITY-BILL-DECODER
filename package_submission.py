"""Validate results and build the submission ZIP.

  python package_submission.py --output output [--demo demo/demo.mp4] [--zip my-team.zip]

Layout produced: output/, source/ (this project minus secrets/caches), demo/ (optional).
Run it AFTER generating output/level1.csv and output/level2.csv.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

from bill_decoder.csv_io import read_rows
from bill_decoder.schema import empty_level1

ROOT = Path(__file__).resolve().parent
SKIP_DIRS = {".venv", "venv", "__pycache__", ".cache", ".git", "output", "demo", "data", "test",
             "train", ".pytest_cache", ".vscode"}
SKIP_FILES = {".env"}
SKIP_SUFFIXES = {".zip", ".pyc", ".mp4", ".mov", ".webm", ".png", ".jpg", ".jpeg"}
MAX_BYTES = 15 * 1024 * 1024
SECRET_PATTERNS = [re.compile(p) for p in (r"sk-[A-Za-z0-9_\-]{20,}", r"AIza[0-9A-Za-z_\-]{30,}",
                                           r"sk-ant-[A-Za-z0-9_\-]{20,}", r"AQ\.[A-Za-z0-9_\-]{20,}")]


def validate(output: Path) -> list[str]:
    errs: list[str] = []
    try:
        _, l1 = read_rows(output / "level1.csv")
        _, l2 = read_rows(output / "level2.csv")
    except FileNotFoundError as exc:
        return [f"missing file: {exc.filename}"]
    keys = set(empty_level1())
    if len(l1) != 10:
        errs.append(f"level1.csv has {len(l1)} rows (expected 10)")
    if len(l2) != 120:
        errs.append(f"level2.csv has {len(l2)} rows (expected 120)")
    for r in l1:
        try:
            obj = json.loads(r["json"])
            if set(obj) != keys:
                errs.append(f"{r['bill_id']}: JSON keys differ from schema")
            if all(v in (None, []) for v in obj.values()):
                errs.append(f"{r['bill_id']}: extraction is all-null (failed run?)")
        except (json.JSONDecodeError, TypeError, KeyError):
            errs.append(f"{r.get('bill_id')}: json cell empty/invalid")
    for r in l2:
        if not (r.get("answer") or "").strip():
            errs.append(f"{r['bill_id']} {r['question_id']}: empty answer")
        elif r["answer"].startswith("I could not reliably determine"):
            errs.append(f"{r['bill_id']} {r['question_id']}: fallback answer (check logs)")
    return errs


def source_files() -> list[Path]:
    out = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if p.is_dir() or set(rel.parts) & SKIP_DIRS or p.name in SKIP_FILES:
            continue
        if p.suffix.lower() in SKIP_SUFFIXES:
            continue
        out.append(p)
    return out


def _real_key() -> str:
    """The API key currently in .env (so we can make sure it is not inside any packaged file)."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("API_KEY") and "=" in line:
                return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def scan_for_secrets(files: list[Path]) -> list[str]:
    hits = []
    key = _real_key()
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(pat.search(text) for pat in SECRET_PATTERNS) or (len(key) > 8 and key in text):
            hits.append(str(p.relative_to(ROOT)))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="output")
    ap.add_argument("--demo", default=None)
    ap.add_argument("--zip", default="submission.zip")
    a = ap.parse_args()

    out_dir = (ROOT / a.output) if not Path(a.output).is_absolute() else Path(a.output)
    errs = validate(out_dir)
    files = source_files()
    leaked = scan_for_secrets(files)
    if leaked:
        errs.append(f"possible API key in: {leaked}")
    if errs:
        print("PROBLEMS FOUND:\n  - " + "\n  - ".join(errs))
        if input("Continue anyway? [y/N] ").strip().lower() != "y":
            return 1

    zpath = ROOT / a.zip
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("level1.csv", "level2.csv"):
            z.write(out_dir / name, f"output/{name}")
        for p in files:
            if p == zpath:
                continue
            z.write(p, f"source/{p.relative_to(ROOT).as_posix()}")
        if a.demo:
            d = Path(a.demo)
            z.write(d, f"demo/demo{d.suffix.lower()}")
    size = zpath.stat().st_size
    print(f"Wrote {zpath} ({size / 1e6:.2f} MB)")
    if size > MAX_BYTES:
        print("WARNING: ZIP is larger than 15 MB - shrink the demo video!")
        return 1
    print("Now OPEN the zip and check output/, source/ (README.md, .env.example), demo/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
