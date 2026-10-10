"""Level 2: the LLM plans arithmetic -> code computes it exactly -> the LLM writes the answers."""
from __future__ import annotations

import logging
import re

from . import prompts
from .calc import safe_eval

log = logging.getLogger(__name__)

FALLBACK = "I could not reliably determine an answer to this question from the bill image."


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def build_env(bill: dict, facts: dict) -> dict:
    """Named values the planner may reference in expressions."""
    env: dict = {k: v for k, v in bill.items() if _is_num(v)}
    for group, key in (("charges", "charges_"), ("taxes", "taxes_")):
        for line in bill.get(group) or []:
            name = key + line["type"]
            env[name] = round(env.get(name, 0) + line["amount"], 4)
    env["num_charge_lines"] = len(bill.get("charges") or [])
    env["num_tax_lines"] = len(bill.get("taxes") or [])
    after, within = bill.get("payable_after_due_date"), bill.get("payable_within_due_date")
    if _is_num(after) and _is_num(within):
        env["late_surcharge"] = round(after - within, 4)
    usage = facts.get("usage_history") or []
    if usage:
        env["usage_history"] = [u["units"] for u in usage]
        previous = [u["units"] for u in usage if not u.get("is_current_month")]
        if previous:
            env["usage_previous_months"] = previous
    billing = facts.get("billing_history") or []
    billed = [b["billed"] for b in billing if _is_num(b.get("billed"))]
    paid = [b["paid"] for b in billing if _is_num(b.get("paid"))]
    if billed:
        env["billed_amounts"] = billed
    if paid:
        env["paid_amounts"] = paid
    return env


def run_plans(plans, env: dict) -> dict:
    computed: dict = {}
    for plan in plans if isinstance(plans, list) else []:
        if not isinstance(plan, dict):
            continue
        local, out = dict(env), {}
        for comp in plan.get("computations") or []:
            if not isinstance(comp, dict):
                continue
            name, expr = str(comp.get("name") or "").strip(), str(comp.get("expr") or "").strip()
            if not name or not expr:
                continue
            ident = re.sub(r"\W", "_", name)
            try:
                value = safe_eval(expr, local)
            except Exception as exc:
                out[name] = f"ERROR: {exc}"
                continue
            if isinstance(value, float):
                value = round(value, 4)
            local[ident] = value
            out[name] = value
        computed[str(plan.get("id"))] = {"interpretation": plan.get("interpretation", ""),
                                         "computed": out}
    return computed


def _extract_answers(raw) -> dict:
    data = raw.get("answers") if isinstance(raw, dict) and "answers" in raw else raw
    found: dict = {}
    if isinstance(data, dict):
        items = data.items()
    elif isinstance(data, list):
        items = [(d.get("id"), d.get("answer")) for d in data if isinstance(d, dict)]
    else:
        return found
    for qid, text in items:
        text = (text if isinstance(text, str) else str(text or "")).strip()
        if qid and text:
            found[str(qid).strip()] = text
    return found


def answer_questions(llm, image, bill: dict, facts: dict, questions) -> dict:
    """questions: list of (question_id, question). Always returns an answer for every id."""
    questions = list(questions)
    computed: dict = {}
    try:
        plan = llm.ask_json(prompts.qa_plan_prompt(bill, facts, build_env(bill, facts), questions), image)
        computed = run_plans(plan.get("plans") if isinstance(plan, dict) else None,
                             build_env(bill, facts))
    except Exception as exc:
        log.warning("planning step failed (%s); answering without computed values", exc)

    answers: dict = {}
    pending = questions
    for _ in range(2):  # second round only re-asks what is still missing
        if not pending:
            break
        try:
            raw = llm.ask_json(prompts.qa_answer_prompt(bill, facts, pending, computed), image)
        except Exception as exc:
            log.warning("answer step failed: %s", exc)
            continue
        got = _extract_answers(raw)
        for qid, _ in pending:
            if qid in got:
                answers[qid] = got[qid]
        pending = [(i, q) for i, q in pending if i not in answers]
    for qid, _ in pending:
        answers[qid] = FALLBACK
    return answers
