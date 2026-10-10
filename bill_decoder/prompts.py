"""All prompt text lives here. Every prompt starts with a [TASK:...] tag line."""
from __future__ import annotations

import json

PROMPT_VERSION = "v1"  # bump to invalidate the cache after editing prompts

SCHEMA_TEXT = """{
  "provider": "KE | LESCO | IESCO",
  "tariff": "string",
  "sanctioned_load_kw": number,
  "bill_month": "YYYY-MM",
  "reading_date": "YYYY-MM-DD",
  "issue_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD",
  "previous_reading": number,
  "current_reading": number,
  "units_consumed": number,
  "charges": [{"type": "energy | fixed | fpa | quarterly_adjustment | surcharge | meter_rent | subsidy | other", "amount": number}],
  "total_charges": number,
  "taxes": [{"type": "gst | electricity_duty | income_tax | municipal_tax | other_tax", "amount": number}],
  "total_taxes": number,
  "current_bill": number,
  "arrears": number,
  "payable_within_due_date": number,
  "payable_after_due_date": number
}"""

EXAMPLE_JSON = """{"provider":"KE","tariff":"A1-R","sanctioned_load_kw":3,"bill_month":"2026-04","reading_date":"2026-04-03","issue_date":"2026-04-07","due_date":"2026-04-21","previous_reading":8819,"current_reading":8970,"units_consumed":151,"charges":[{"type":"fixed","amount":900},{"type":"energy","amount":1054},{"type":"energy","amount":663.51},{"type":"quarterly_adjustment","amount":52.91},{"type":"fpa","amount":125.27},{"type":"surcharge","amount":64.93}],"total_charges":2860.62,"taxes":[{"type":"electricity_duty","amount":29.41},{"type":"gst","amount":520.21},{"type":"municipal_tax","amount":20}],"total_taxes":569.62,"current_bill":3430.24,"arrears":-0.53,"payable_within_due_date":3430,"payable_after_due_date":3716}"""

LEVEL1_PROMPT = """[TASK:LEVEL1]
You are reading ONE electricity bill image (K-Electric, LESCO or IESCO). It may be a scan, a screenshot or a tilted photo and parts may be in Urdu. Names, addresses and ID numbers are covered by grey boxes.

Return ONE JSON object with EXACTLY these keys (all keys required; use null when a value is unavailable):
""" + SCHEMA_TEXT + """

RULES
1. Extract values AS PRINTED. Never recalculate, round or "correct" an amount.
2. Amounts are plain JSON numbers in PKR: "Rs. 19,964" -> 19964. No currency text, no commas, no quoted numbers.
3. Credits are negative: "38209CR" -> -38209. Subsidy / relief lines are negative deductions.
4. Dates are YYYY-MM-DD ("22nd Sep 2026" -> "2026-09-22"). bill_month is YYYY-MM ("MAR 2026" -> "2026-03").
5. If a value is not printed, blank, covered by a grey box or unreadable, use null. Do not guess. Use [] for an empty list.
6. NEVER output names, addresses, CNIC, account / reference / consumer / contract / invoice / meter numbers.
7. provider: "KE" for K-Electric (KESC), "LESCO", or "IESCO".
8. tariff: exactly as printed (e.g. A1-R, A-1a(01)). sanctioned_load_kw: the kW figure labelled Sanc Load / S.Load / San Load.
9. due_date is the last date to pay WITHOUT a late payment surcharge.
10. units_consumed: units billed for the current month as printed. previous_reading / current_reading: the printed meter readings.
11. charges: one entry per line of the charges section. Skip blank lines and lines printed as 0. Keep separate entries when the same type appears more than once (e.g. two energy slabs). total_charges = the printed charges subtotal, or null if none is printed.
12. Charge types: energy (cost of units used: "Variable Upto ... Units", "Cost of Electricity", "Energy Charges"), fixed, fpa (use for both FPA and FCA), quarterly_adjustment (QTA / Uniform Quarterly Adjustment), surcharge (Additional Surcharge (PHL), F.C Surcharge), meter_rent (meter or service rent), subsidy (negative), other.
13. taxes: one entry per line of the TAX / GOVERNMENT section. Classify a line by the SECTION it is printed in, not by its name. Types: gst (sales tax / GST, including GST on FPA), electricity_duty (ED), income_tax, municipal_tax (e.g. KE MUCT (KMC)), other_tax (extra tax, further tax, TV fee, anything else). If only ONE combined tax amount is printed, use taxes = [] and put that amount in total_taxes. total_taxes = the printed tax subtotal, or null.
14. current_bill: the printed amount for this month's bill. arrears: previous dues carried forward, keep the printed sign (null if blank). payable_within_due_date: amount payable by the due date. payable_after_due_date: amount payable after the due date; if several late-payment amounts are shown use the HIGHEST.

WORKED EXAMPLE (a different K-Electric bill, shown only for format; never copy its values):
""" + EXAMPLE_JSON + """

Return ONLY the JSON object. No commentary, no markdown."""


def relook_prompt(first_pass: dict, issues: list[str]) -> str:
    return ("[TASK:RELOOK]\n"
            "You previously extracted the JSON below from this electricity bill image. "
            "An automatic check found possible misreads:\n- " + "\n- ".join(issues) + "\n\n"
            "PREVIOUS JSON:\n" + json.dumps(first_pass, ensure_ascii=False) + "\n\n"
            "Look at the image again, line by line. Fix ONLY values you actually misread "
            "(a wrong digit, a missed or duplicated line, a wrong section). Bills sometimes print "
            "values that do not add up; if the bill really prints what you extracted, keep it - "
            "never recalculate or adjust amounts to make them add up. Keep the same schema, "
            "number formats, CR/negative rules and null rules as before, and never output "
            "personal identifiers.\n\nSchema:\n" + SCHEMA_TEXT +
            "\n\nReturn ONLY the full corrected JSON object.")


FACTS_PROMPT = """[TASK:FACTS]
You are reading ONE electricity bill image (K-Electric, LESCO or IESCO), possibly tilted or partly in Urdu. Personal identifiers are covered by grey boxes; never output names, addresses, CNIC, account, consumer or meter numbers.

Transcribe the extra information on the bill that customers ask questions about. Use JSON numbers (no commas, no currency text; credits "CR" are negative). Use null or [] when something is not printed or unreadable. Do not guess.

Return ONLY this JSON object:
{
  "usage_history": [{"month": "YYYY-MM or label as printed", "units": number, "is_current_month": true|false}],
  "billing_history": [{"month": "YYYY-MM or as printed", "billed": number, "paid_date": "YYYY-MM-DD or null", "paid": number}],
  "calc_lines": [{"label": "line label as printed", "units": number|null, "rate": number|null, "amount": number|null}],
  "late_payment": [{"label": "e.g. Late payment surcharge 5% / amount payable after due date", "amount": number}],
  "message_board": "text of the message board / notices, in English (translate Urdu), or null",
  "energy_share_percent": number|null,
  "tax_share_percent": number|null,
  "notes": "anything else useful for explaining the bill (e.g. bill charge mode, number of months billed, installation date), or null"
}

Notes:
- usage_history: the monthly usage bar chart / usage table, in chronological order (oldest first). Read every bar label carefully. Work out each month from the chart's year labels and month labels when possible; set is_current_month true for the bar that is this bill's month.
- billing_history: the billing & payment history table, newest first as printed.
- calc_lines: every line of the bill calculation / charges breakdown (including slab lines, adjustments, taxes, subtotals) in printed order.
- late_payment: every late-payment surcharge or amount payable after the due date that is printed.
- energy_share_percent / tax_share_percent: only if percentages are printed on the bill (e.g. 83.39% / 16.61%).
Return ONLY the JSON object."""

QA_RULES = """ANSWER RULES
- Answer in plain English (even if the bill has Urdu), using ONLY information from this bill. Never use outside tariff or rate knowledge.
- Get the numbers right. Use the COMPUTED values exactly as given; do not recompute them yourself.
- If a needed value is not shown on the bill (or was covered / unreadable), say so clearly instead of guessing.
- Label estimates: say the value is an estimate and explain in a short phrase how it was calculated.
- If the question has more than one reasonable meaning, state the meaning you used or answer both.
- Never mention names, addresses, CNIC, account, reference, consumer or meter numbers.
- Be specific and concise: lead with the direct answer, include the key figures (PKR with thousands separators), then a brief explanation. Usually 1-4 sentences."""

QA_EXAMPLES = """STYLE EXAMPLES (other bill)
Q: How much of my bill is taxes?
A: Taxes and duties total PKR 569.62 out of your current bill of PKR 3,430.24, or about 16.6%. The bill shows a split of 83.39% energy charges and 16.61% taxes. The tax lines are sales tax (PKR 520.21), electricity duty (PKR 29.41), and MUCT (KMC) (PKR 20.00).
Q: How many months in my history went above 200 units?
A: Two of the 12 previous months exceeded 200 units: July 2025 (239) and August 2025 (203). The current month used 151 units, so the count is two whether or not the current month is included."""


def _questions_block(questions) -> str:
    return "\n".join(f"{qid}: {text}" for qid, text in questions)


def qa_plan_prompt(bill: dict, facts: dict, env: dict, questions) -> str:
    var_lines = "\n".join(f"{k} = {json.dumps(v)}" for k, v in env.items())
    return ("[TASK:QA_PLAN]\n"
            "You help explain ONE electricity bill. First PLAN the arithmetic needed for each customer "
            "question; code will compute it exactly. You can also see the bill image.\n\n"
            "BILL (extracted JSON):\n" + json.dumps(bill, ensure_ascii=False) + "\n\n"
            "EXTRA FACTS from the bill:\n" + json.dumps(facts, ensure_ascii=False) + "\n\n"
            "VARIABLES you may use in expressions (name = value):\n" + var_lines + "\n\n"
            "QUESTIONS:\n" + _questions_block(questions) + "\n\n"
            "For EACH question return a plan:\n"
            '{"plans": [{"id": "Q1", "interpretation": "one sentence: what the question means; if ambiguous, list the meanings to cover", '
            '"computations": [{"name": "snake_case_name", "expr": "arithmetic expression"}]}]}\n'
            "Expression rules: only numbers, the VARIABLE names above (or names of earlier computations in the same plan), "
            "+ - * / ** ( ), comparisons, list literals like [1, 2, 3], list indexing, and these functions: "
            "sum(list), avg(list), min(list), max(list), round(x, n), abs(x), len(list), "
            "count_gt(list, x), count_ge(list, x), count_lt(list, x), count_le(list, x), pct(part, whole). "
            "If a list you need is not in VARIABLES, write it as a literal copied from the data above. "
            "Use an empty computations list when no arithmetic is needed. Estimates (e.g. projections) are fine, "
            "but they must be based only on numbers shown on this bill.\n"
            "Return ONLY the JSON object.")


def qa_answer_prompt(bill: dict, facts: dict, questions, computed: dict) -> str:
    return ("[TASK:QA_ANSWER]\n"
            "You explain ONE electricity bill to its customer in plain English. You can see the bill image; "
            "the extracted data and exactly computed numbers are below.\n\n"
            + QA_RULES + "\n\n" + QA_EXAMPLES + "\n\n"
            "BILL (extracted JSON):\n" + json.dumps(bill, ensure_ascii=False) + "\n\n"
            "EXTRA FACTS from the bill:\n" + json.dumps(facts, ensure_ascii=False) + "\n\n"
            "PLANS AND COMPUTED VALUES (computed exactly by code; an ERROR means the value could not be computed):\n"
            + json.dumps(computed, ensure_ascii=False) + "\n\n"
            "QUESTIONS:\n" + _questions_block(questions) + "\n\n"
            'Return ONLY this JSON: {"answers": {"Q1": "answer text", "Q2": "answer text"}} with one entry for EVERY question id above.')
