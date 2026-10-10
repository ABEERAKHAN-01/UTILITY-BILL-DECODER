"""Deterministic clean-up of model output: numbers, CR credits, dates, enums, dropped zero lines.

Identifiers are never kept: only the schema keys survive normalisation.
"""
from __future__ import annotations

import datetime
import re

from .schema import (CHARGE_TYPES, DATE_FIELDS, NUMBER_FIELDS, PROVIDERS, TAX_TYPES,
                     empty_level1)

_NULLS = {"", "null", "none", "n/a", "na", "nil", "-", "--", "\u2014"}
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

CHARGE_ALIASES = {
    "fca": "fpa", "fuel_price_adjustment": "fpa", "fuel_charge_adjustment": "fpa",
    "qta": "quarterly_adjustment", "uniform_quarterly_adjustment": "quarterly_adjustment",
    "quarterly": "quarterly_adjustment", "service_rent": "meter_rent",
    "energy_charges": "energy", "fixed_charges": "fixed", "surcharges": "surcharge",
    "relief": "subsidy",
}
TAX_ALIASES = {
    "sales_tax": "gst", "ed": "electricity_duty", "duty": "electricity_duty",
    "muct": "municipal_tax", "kmc": "municipal_tax", "municipal": "municipal_tax",
    "income": "income_tax", "tax": "other_tax", "other": "other_tax",
    "extra_tax": "other_tax", "further_tax": "other_tax", "tv_fee": "other_tax",
}


# ----------------------------------------------------------------------------- numbers
def _tidy(x: float):
    x = round(x, 4)
    return int(x) if x == int(x) else x


def to_number(value):
    """'Rs. 19,964' -> 19964, '38209CR' -> -38209, '(12.5)' -> -12.5, '' -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None if value != value else _tidy(float(value))
    s = str(value).strip()
    if s.lower() in _NULLS:
        return None
    s = s.replace(",", "")
    m = re.search(r"\d+(?:\.\d+)?|\.\d+", s)
    if not m:
        return None
    neg = bool(re.search(r"\bcr\b\.?\s*$|\d\s*cr\.?\s*$|^\s*cr\b", s, re.I))
    neg = neg or (s.startswith("(") and s.endswith(")")) or s.rstrip().endswith("-")
    neg = neg or bool(re.search(r"(?<!\d)-\s*(?=\.?\d)", s))
    val = float(m.group())
    return _tidy(-val if neg else val)


# ----------------------------------------------------------------------------- dates
def _mk(y: int, m: int, d: int):
    if y < 100:
        y += 2000
    try:
        return datetime.date(y, m, d).isoformat()
    except ValueError:
        return None


def to_date(value):
    """'22nd Sep 2026' -> '2026-09-22'; '07-Apr-26' -> '2026-04-07'; unknown -> None."""
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in _NULLS:
        return None
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return _mk(y, mo, d)
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?[\s\-/.,]*([A-Za-z]{3,9})\.?[\s\-/.,]*(\d{2,4})", s)
    if m and _MONTHS.get(m.group(2)[:3].lower()):
        return _mk(int(m.group(3)), _MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", s)
    if m:
        d, mo, y = map(int, m.groups())
        return _mk(y, mo, d)
    return None


def to_month(value):
    """'MAR 2026' -> '2026-03'; 'Apr-26' -> '2026-04'; '2026-04-07' -> '2026-04'."""
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in _NULLS:
        return None
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})(?:[-/.]\d{1,2})?", s)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{int(m.group(1))}-{int(m.group(2)):02d}"
    for m in re.finditer(r"([A-Za-z]{3,9})\.?[\s\-/.,']*(\d{4}|\d{2})\b", s):
        mo = _MONTHS.get(m.group(1)[:3].lower())
        if mo:
            y = int(m.group(2))
            y = y + 2000 if y < 100 else y
            return f"{y}-{mo:02d}"
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{4}|\d{2})", s)
    if m and 1 <= int(m.group(1)) <= 12:
        y = int(m.group(2))
        y = y + 2000 if y < 100 else y
        return f"{y}-{int(m.group(1)):02d}"
    d = to_date(s)
    return d[:7] if d else None


# ----------------------------------------------------------------------------- text / enums
def _text(value):
    if value is None:
        return None
    s = str(value).strip()
    return None if s.lower() in _NULLS else s


def to_provider(value):
    s = re.sub(r"[^A-Z]", "", str(value or "").upper())
    if s in {"KE", "KESC", "KELECTRIC", "KELECTRICLIMITED", "KELECTRICLTD"}:
        return "KE"
    for p in PROVIDERS:
        if s.startswith(p):
            return p
    return None


def _norm_type(value, allowed, default, aliases):
    s = re.sub(r"[\s\-]+", "_", str(value or "").strip().lower())
    if s in allowed:
        return s
    return aliases.get(s, default)


def _lines(items, allowed, default, aliases) -> list[dict]:
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        amount = to_number(it.get("amount"))
        if amount is None or amount == 0:      # blank / "0" lines are skipped
            continue
        typ = _norm_type(it.get("type"), allowed, default, aliases)
        if typ == "subsidy" and amount > 0:    # subsidies are deductions
            amount = -amount
        out.append({"type": typ, "amount": amount})
    return out


# ----------------------------------------------------------------------------- Level 1
def normalize(raw) -> dict:
    out = empty_level1()
    if not isinstance(raw, dict):
        return out
    out["provider"] = to_provider(raw.get("provider"))
    out["tariff"] = _text(raw.get("tariff"))
    out["bill_month"] = to_month(raw.get("bill_month"))
    for k in DATE_FIELDS:
        out[k] = to_date(raw.get(k))
    for k in NUMBER_FIELDS:
        out[k] = to_number(raw.get(k))
    out["charges"] = _lines(raw.get("charges"), CHARGE_TYPES, "other", CHARGE_ALIASES)
    out["taxes"] = _lines(raw.get("taxes"), TAX_TYPES, "other_tax", TAX_ALIASES)
    return out


def consistency_issues(bill: dict, tol: float = 1.5) -> list[str]:
    """Cheap self-consistency checks used to decide whether the model gets a second look."""
    issues: list[str] = []
    ch, tc = bill.get("charges") or [], bill.get("total_charges")
    tx, tt = bill.get("taxes") or [], bill.get("total_taxes")
    if ch and tc is not None:
        s = sum(c["amount"] for c in ch)
        if abs(s - tc) > tol:
            issues.append(f"charge lines add up to {s:.2f} but total_charges is {tc}")
    if tx and tt is not None:
        s = sum(t["amount"] for t in tx)
        if abs(s - tt) > tol:
            issues.append(f"tax lines add up to {s:.2f} but total_taxes is {tt}")
    pr, cr, u = bill.get("previous_reading"), bill.get("current_reading"), bill.get("units_consumed")
    if None not in (pr, cr, u) and abs((cr - pr) - u) > tol:
        issues.append(f"current_reading - previous_reading = {cr - pr:g} but units_consumed is {u}")
    cb = bill.get("current_bill")
    if None not in (tc, tt, cb) and abs(tc + tt - cb) > 2 * tol:
        issues.append(f"total_charges + total_taxes = {tc + tt:.2f} but current_bill is {cb}")
    return issues


# ----------------------------------------------------------------------------- extra facts
def normalize_facts(raw) -> dict:
    facts = {"usage_history": [], "billing_history": [], "calc_lines": [], "late_payment": [],
             "message_board": None, "energy_share_percent": None, "tax_share_percent": None,
             "notes": None}
    if not isinstance(raw, dict):
        return facts

    def rows(key):
        return [r for r in (raw.get(key) if isinstance(raw.get(key), list) else [])
                if isinstance(r, dict)]

    for r in rows("usage_history"):
        units = to_number(r.get("units"))
        if units is not None:
            facts["usage_history"].append({
                "month": to_month(r.get("month")) or _text(r.get("month")),
                "units": units, "is_current_month": bool(r.get("is_current_month"))})
    for r in rows("billing_history"):
        facts["billing_history"].append({
            "month": to_month(r.get("month")) or _text(r.get("month")),
            "billed": to_number(r.get("billed")), "paid_date": to_date(r.get("paid_date")),
            "paid": to_number(r.get("paid"))})
    for r in rows("calc_lines"):
        facts["calc_lines"].append({
            "label": _text(r.get("label")), "units": to_number(r.get("units")),
            "rate": to_number(r.get("rate")), "amount": to_number(r.get("amount"))})
    for r in rows("late_payment"):
        facts["late_payment"].append({"label": _text(r.get("label")),
                                      "amount": to_number(r.get("amount"))})
    facts["message_board"] = _text(raw.get("message_board"))
    facts["energy_share_percent"] = to_number(raw.get("energy_share_percent"))
    facts["tax_share_percent"] = to_number(raw.get("tax_share_percent"))
    facts["notes"] = _text(raw.get("notes"))
    return facts
