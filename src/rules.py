from datetime import datetime, date
from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class RuleFlag:
    rule_id: str
    severity: str       # "error" | "warning" | "info"
    message: str
    field: Optional[str] = None


def _safe_float(val) -> Optional[float]:
    try:
        return float(str(val).replace(",", ".").replace("$", "").strip())
    except Exception:
        return None


def _safe_date(val) -> Optional[date]:
    formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
        "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y",
        "%d.%m.%Y", "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except Exception:
            continue
    return None


def run_rules(invoice: dict) -> list[RuleFlag]:
    """Tüm kural kontrollerini çalıştırır, flag listesi döndürür."""
    flags: list[RuleFlag] = []

    subtotal   = _safe_float(invoice.get("subtotal"))
    tax_amount = _safe_float(invoice.get("tax_amount"))
    total      = _safe_float(invoice.get("total"))
    inv_date   = _safe_date(invoice.get("invoice_date"))

    # R1 — Zorunlu alanlar
    for field in ["vendor_name", "total", "invoice_date"]:
        if not invoice.get(field):
            flags.append(RuleFlag(
                rule_id="R1_MISSING_FIELD",
                severity="error",
                message=f"Required field '{field}' is missing or empty.",
                field=field,
            ))

    # R2 — Matematik tutarlılığı (subtotal + tax ≈ total)
    if subtotal is not None and tax_amount is not None and total is not None:
        expected = subtotal + tax_amount
        if abs(expected - total) > 0.02:
            flags.append(RuleFlag(
                rule_id="R2_MATH_MISMATCH",
                severity="error",
                message=(
                    f"subtotal ({subtotal}) + tax_amount ({tax_amount}) = {expected:.2f} "
                    f"but total is {total:.2f} (diff={abs(expected - total):.2f})"
                ),
            ))

    # R3 — KDV oranı aralığı
    if subtotal and tax_amount is not None and subtotal > 0:
        tax_rate = tax_amount / subtotal
        if not (0.0 <= tax_rate <= 0.50):
            flags.append(RuleFlag(
                rule_id="R3_TAX_RATE_UNUSUAL",
                severity="warning",
                message=f"Tax rate {tax_rate:.1%} is outside expected range [0%, 50%].",
            ))

    # R4 — Tarih geçerliliği
    if invoice.get("invoice_date") and inv_date is None:
        flags.append(RuleFlag(
            rule_id="R4_DATE_PARSE_FAIL",
            severity="warning",
            message=f"Cannot parse invoice_date: '{invoice['invoice_date']}'",
            field="invoice_date",
        ))
    elif inv_date and inv_date > date.today():
        flags.append(RuleFlag(
            rule_id="R4_FUTURE_DATE",
            severity="warning",
            message=f"Invoice date {inv_date} is in the future.",
            field="invoice_date",
        ))

    # R5 — Negatif değerler
    for fname, fval in [("subtotal", subtotal), ("tax_amount", tax_amount), ("total", total)]:
        if fval is not None and fval < 0:
            flags.append(RuleFlag(
                rule_id="R5_NEGATIVE_VALUE",
                severity="error",
                message=f"Field '{fname}' has negative value: {fval}",
                field=fname,
            ))

    # R6 — Aşırı veya önemsiz tutar
    if total is not None:
        if total > 1_000_000:
            flags.append(RuleFlag(
                rule_id="R6_EXCESSIVE_TOTAL",
                severity="warning",
                message=f"Total amount {total:,.2f} exceeds $1,000,000 threshold.",
            ))
        elif 0 < total < 0.01:
            flags.append(RuleFlag(
                rule_id="R6_TRIVIAL_TOTAL",
                severity="info",
                message=f"Total amount {total} seems unusually small.",
            ))

    return flags
