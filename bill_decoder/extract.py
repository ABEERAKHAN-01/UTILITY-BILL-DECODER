"""Level 1 extraction (+ one self-consistency re-look) and the extra-facts pass."""
from __future__ import annotations

import logging

from . import prompts
from .postprocess import consistency_issues, normalize, normalize_facts

log = logging.getLogger(__name__)


def extract_level1(llm, image) -> dict:
    bill = normalize(llm.ask_json(prompts.LEVEL1_PROMPT, image))
    issues = consistency_issues(bill)
    if issues:
        log.info("consistency issues, taking one more look: %s", "; ".join(issues))
        try:
            second = normalize(llm.ask_json(prompts.relook_prompt(bill, issues), image))
            if len(consistency_issues(second)) < len(issues):
                bill = second  # keep whichever result is more self-consistent
        except Exception as exc:  # the first pass is still usable
            log.warning("re-look failed (%s); keeping first pass", exc)
    return bill


def extract_facts(llm, image) -> dict:
    return normalize_facts(llm.ask_json(prompts.FACTS_PROMPT, image))
