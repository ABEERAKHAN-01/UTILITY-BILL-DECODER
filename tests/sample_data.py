"""KESC_0008 ground truth from the participant guide (section 5.7) plus its history tables."""
SAMPLE_BILL = {
    "provider": "KE", "tariff": "A1-R", "sanctioned_load_kw": 3, "bill_month": "2026-04",
    "reading_date": "2026-04-03", "issue_date": "2026-04-07", "due_date": "2026-04-21",
    "previous_reading": 8819, "current_reading": 8970, "units_consumed": 151,
    "charges": [{"type": "fixed", "amount": 900}, {"type": "energy", "amount": 1054},
                {"type": "energy", "amount": 663.51}, {"type": "quarterly_adjustment", "amount": 52.91},
                {"type": "fpa", "amount": 125.27}, {"type": "surcharge", "amount": 64.93}],
    "total_charges": 2860.62,
    "taxes": [{"type": "electricity_duty", "amount": 29.41}, {"type": "gst", "amount": 520.21},
              {"type": "municipal_tax", "amount": 20}],
    "total_taxes": 569.62, "current_bill": 3430.24, "arrears": -0.53,
    "payable_within_due_date": 3430, "payable_after_due_date": 3716,
}

_UNITS = [141, 138, 197, 239, 203, 179, 173, 187, 124, 96, 88, 115, 151]
_MONTHS = ["2025-04", "2025-05", "2025-06", "2025-07", "2025-08", "2025-09", "2025-10",
           "2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04"]
SAMPLE_FACTS = {
    "usage_history": [{"month": m, "units": u, "is_current_month": m == "2026-04"}
                      for m, u in zip(_MONTHS, _UNITS)],
    "billing_history": [
        {"month": "2026-03", "billed": 2577.31, "paid_date": "2026-03-16", "paid": 2577},
        {"month": "2026-02", "billed": 2782.51, "paid_date": "2026-02-19", "paid": 2783},
        {"month": "2026-01", "billed": 2780.55, "paid_date": "2026-01-15", "paid": 2780}],
    "calc_lines": [], "late_payment": [{"label": "after 24-Apr", "amount": 3716}],
    "message_board": None, "energy_share_percent": 83.39, "tax_share_percent": 16.61, "notes": None,
}
