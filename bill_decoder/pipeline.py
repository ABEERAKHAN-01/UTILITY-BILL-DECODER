"""Orchestration: per-bill analysis with caching and graceful degradation, plus the full CSV run."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import prompts
from .csv_io import find_image, read_rows, write_rows
from .extract import extract_facts, extract_level1
from .llm import LLM
from .qa import FALLBACK, answer_questions
from .schema import empty_level1

log = logging.getLogger(__name__)


class Cache:
    """Tiny JSON-file cache so a crashed run resumes without paying for finished work again."""

    def __init__(self, directory):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, bill_id: str, kind: str) -> Path:
        return self.dir / f"{bill_id}.{kind}.json"

    def load(self, bill_id: str, kind: str, token: str):
        try:
            data = json.loads(self._path(bill_id, kind).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data.get("value") if data.get("token") == token else None

    def save(self, bill_id: str, kind: str, token: str, value) -> None:
        path = self._path(bill_id, kind)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"token": token, "value": value}, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, path)


def make_cache(settings) -> Cache:
    return Cache(settings.cache_dir)


def _token(image: Path, model: str, extra: str = "") -> str:
    h = hashlib.sha1()
    h.update(image.read_bytes())
    h.update(f"|{model}|{prompts.PROMPT_VERSION}|{extra}".encode())
    return h.hexdigest()[:16]


def analyse_bill(llm, cache: Cache, bill_id: str, image, questions=None):
    """Returns (level1_json, extra_facts, {question_id: answer}). Never raises for model failures."""
    image = Path(image)
    token = _token(image, llm.settings.model)

    bill = cache.load(bill_id, "level1", token)
    if bill is None:
        try:
            bill = extract_level1(llm, image)
            cache.save(bill_id, "level1", token, bill)
        except Exception:
            log.exception("%s: Level 1 extraction failed - using nulls", bill_id)
            bill = empty_level1()

    facts = cache.load(bill_id, "facts", token)
    if facts is None:
        try:
            facts = extract_facts(llm, image)
            cache.save(bill_id, "facts", token, facts)
        except Exception:
            log.exception("%s: extra-facts pass failed - continuing without", bill_id)
            facts = {}

    answers: dict = {}
    if questions:
        qtoken = _token(image, llm.settings.model, json.dumps(questions, ensure_ascii=False))
        answers = cache.load(bill_id, "qa", qtoken) or {}
        if not answers:
            try:
                answers = answer_questions(llm, image, bill, facts, questions)
                if not any(a == FALLBACK for a in answers.values()):
                    cache.save(bill_id, "qa", qtoken, answers)
            except Exception:
                log.exception("%s: question answering failed", bill_id)
                answers = {qid: FALLBACK for qid, _ in questions}
    return bill, facts, answers


def run_all(settings, bills_dir, level1_csv, level2_csv, out_dir, llm=None) -> None:
    f1, rows1 = read_rows(level1_csv)
    f2, rows2 = read_rows(level2_csv)
    llm = llm or LLM(settings)
    cache = make_cache(settings)

    questions: dict[str, list] = {}
    for r in rows2:
        questions.setdefault(r["bill_id"], []).append((r["question_id"], r["question"]))
    bill_ids = list(dict.fromkeys([r["bill_id"] for r in rows1] + list(questions)))

    def work(bill_id: str):
        qs = questions.get(bill_id, [])
        image = find_image(bills_dir, bill_id)
        if image is None:
            log.error("%s: image not found in %s", bill_id, bills_dir)
            return empty_level1(), {qid: FALLBACK for qid, _ in qs}
        log.info("%s: analysing", bill_id)
        bill, _, answers = analyse_bill(llm, cache, bill_id, image, qs)
        log.info("%s: done", bill_id)
        return bill, answers

    results: dict = {}
    with ThreadPoolExecutor(max_workers=max(1, settings.max_workers)) as pool:
        futures = {pool.submit(work, b): b for b in bill_ids}
        for fut in as_completed(futures):
            bill_id = futures[fut]
            try:
                results[bill_id] = fut.result()
            except Exception:
                log.exception("%s: unexpected failure - writing fallback values", bill_id)
                results[bill_id] = (empty_level1(),
                                    {qid: FALLBACK for qid, _ in questions.get(bill_id, [])})

    for r in rows1:  # keep original row order and untouched columns
        r["json"] = json.dumps(results[r["bill_id"]][0], ensure_ascii=False, separators=(",", ":"))
    for r in rows2:
        r["answer"] = (results[r["bill_id"]][1].get(r["question_id"]) or FALLBACK)

    out = Path(out_dir)
    write_rows(out / "level1.csv", f1, rows1)
    write_rows(out / "level2.csv", f2, rows2)
    bad = sum(1 for r in rows2 if r["answer"] == FALLBACK)
    log.info("wrote %s (%d rows) and %s (%d rows, %d fallback answers)",
             out / "level1.csv", len(rows1), out / "level2.csv", len(rows2), bad)
