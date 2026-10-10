"""Level 1 schema constants (section 5 of the participant guide)."""
from __future__ import annotations

PROVIDERS = ("KE", "LESCO", "IESCO")
CHARGE_TYPES = ("energy", "fixed", "fpa", "quarterly_adjustment", "surcharge",
                "meter_rent", "subsidy", "other")
TAX_TYPES = ("gst", "electricity_duty", "income_tax", "municipal_tax", "other_tax")

TEXT_FIELDS = ("provider", "tariff")
DATE_FIELDS = ("reading_date", "issue_date", "due_date")
NUMBER_FIELDS = ("sanctioned_load_kw", "previous_reading", "current_reading", "units_consumed",
                 "total_charges", "total_taxes", "current_bill", "arrears",
                 "payable_within_due_date", "payable_after_due_date")
# Scalar fields scored one by one
SCALAR_FIELDS = ("provider", "tariff", "sanctioned_load_kw", "bill_month", "reading_date",
                 "issue_date", "due_date", "previous_reading", "current_reading",
                 "units_consumed", "total_charges", "total_taxes", "current_bill", "arrears",
                 "payable_within_due_date", "payable_after_due_date")


def empty_level1() -> dict:
    """Every key present, nothing invented (used as the safe fallback for failed bills)."""
    return {
        "provider": None, "tariff": None, "sanctioned_load_kw": None, "bill_month": None,
        "reading_date": None, "issue_date": None, "due_date": None,
        "previous_reading": None, "current_reading": None, "units_consumed": None,
        "charges": [], "total_charges": None, "taxes": [], "total_taxes": None,
        "current_bill": None, "arrears": None,
        "payable_within_due_date": None, "payable_after_due_date": None,
    }
