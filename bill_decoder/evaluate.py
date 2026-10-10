"""Score Level 1 output like the competition does: text/dates exact, numbers within +-1."""
from __future__ import annotations

from .schema import SCALAR_FIELDS


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _eq(got, exp) -> bool:
    if got is None or exp is None:
        return got is None and exp is None  # a correct null counts as correct
    if _num(exp):
        return _num(got) and abs(got - exp) <= 1
    return str(got).strip() == str(exp).strip()


def compare(got: dict, expected: dict) -> tuple[int, int, list[str]]:
    """Returns (correct, total, list of problems). Extra (invented) lines count against you."""
    ok = total = 0
    bad: list[str] = []
    for key in SCALAR_FIELDS:
        total += 1
        if _eq(got.get(key), expected.get(key)):
            ok += 1
        else:
            bad.append(f"{key}: got {got.get(key)!r}, expected {expected.get(key)!r}")
    for key in ("charges", "taxes"):
        remaining = list(got.get(key) or [])
        for exp in expected.get(key) or []:
            total += 1
            idx = next((i for i, g in enumerate(remaining)
                        if g.get("type") == exp.get("type") and _eq(g.get("amount"), exp.get("amount"))),
                       None)
            if idx is None:
                bad.append(f"{key}: missing {exp}")
            else:
                ok += 1
                remaining.pop(idx)
        for extra in remaining:
            total += 1
            bad.append(f"{key}: extra line {extra}")
    return ok, total, bad
