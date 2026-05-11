from datetime import datetime, date
from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class RuleFlag:
    rule_id:  str
    severity: str        # "error" | "warning" | "info"
    message:  str
    field:    Optional[str] = None


def _safe_float(val) -> Optional[float]:
    try:
        return float(
            str(val).replace(",", ".").replace("₺", "")
                    .replace("TL", "").replace("$", "")
                    .replace("%", "").strip()
        )
    except Exception:
        return None


def _safe_date(val) -> Optional[date]:
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
                "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d",
                "%B %d, %Y", "%b %d, %Y"]:
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except Exception:
            continue
    return None


def run_rules(invoice: dict) -> list[RuleFlag]:
    """Tüm kural kontrollerini çalıştırır, flag listesi döndürür."""
    flags: list[RuleFlag] = []

    subtotal    = _safe_float(invoice.get("subtotal"))
    tax_amount  = _safe_float(invoice.get("tax_amount"))
    total       = _safe_float(invoice.get("total"))
    discount    = _safe_float(invoice.get("discount_amount")) or 0.0
    inv_date    = _safe_date(invoice.get("invoice_date"))
    due_date    = _safe_date(invoice.get("due_date"))
    vendor_vkn  = str(invoice.get("vendor_vkn") or "").strip()
    buyer_vkn   = str(invoice.get("buyer_vkn")  or "").strip()

    # ── R1  Zorunlu alanlar ───────────────────────────────────────────────────
    for field in ["vendor_name", "total", "invoice_date"]:
        if not invoice.get(field):
            flags.append(RuleFlag(
                rule_id="R1_MISSING_FIELD", severity="error",
                message=f"Zorunlu alan eksik: '{field}'",
                field=field,
            ))

    # ── R2  Matematik tutarlılığı — iskonto varsa hesaba kat ─────────────────
    # Beklenen: subtotal - iskonto + kdv = toplam  (±0.05 tolerans)
    if subtotal is not None and tax_amount is not None and total is not None:
        expected = subtotal - discount + tax_amount
        diff = abs(expected - total)
        if diff > 0.05:
            flags.append(RuleFlag(
                rule_id="R2_MATH_MISMATCH", severity="error",
                message=(
                    f"Tutar uyuşmazlığı: {subtotal:.2f} - {discount:.2f} (iskonto) "
                    f"+ {tax_amount:.2f} (KDV) = {expected:.2f}, "
                    f"ancak toplam {total:.2f} (fark: {diff:.2f})"
                ),
            ))

    # ── R3  KDV oranı aralığı ─────────────────────────────────────────────────
    net = (subtotal or 0) - discount
    if net > 0 and tax_amount is not None:
        effective_rate = tax_amount / net
        if not (0.0 <= effective_rate <= 0.50):
            flags.append(RuleFlag(
                rule_id="R3_TAX_RATE_UNUSUAL", severity="warning",
                message=f"Efektif KDV oranı {effective_rate:.1%} beklenen aralık dışında [0%–50%].",
            ))

    # ── R4  Tarih geçerliliği ─────────────────────────────────────────────────
    if invoice.get("invoice_date"):
        if inv_date is None:
            flags.append(RuleFlag(
                rule_id="R4_DATE_PARSE_FAIL", severity="warning",
                message=f"Fatura tarihi okunamadı: '{invoice['invoice_date']}'",
                field="invoice_date",
            ))
        elif inv_date > date.today():
            flags.append(RuleFlag(
                rule_id="R4_FUTURE_DATE", severity="warning",
                message=f"Fatura tarihi gelecekte: {inv_date}",
                field="invoice_date",
            ))

    # ── R5  Negatif değerler ──────────────────────────────────────────────────
    for fname, fval in [("subtotal", subtotal), ("tax_amount", tax_amount), ("total", total)]:
        if fval is not None and fval < 0:
            flags.append(RuleFlag(
                rule_id="R5_NEGATIVE_VALUE", severity="error",
                message=f"'{fname}' negatif değer içeriyor: {fval}",
                field=fname,
            ))

    # ── R6  Aşırı / önemsiz tutar ────────────────────────────────────────────
    if total is not None:
        if total > 1_000_000:
            flags.append(RuleFlag(
                rule_id="R6_EXCESSIVE_TOTAL", severity="warning",
                message=f"Toplam tutar {total:,.2f} TL — 1.000.000 TL eşiğini aşıyor.",
            ))
        elif 0 < total < 0.01:
            flags.append(RuleFlag(
                rule_id="R6_TRIVIAL_TOTAL", severity="info",
                message=f"Toplam tutar {total} TL — olağandışı küçük.",
            ))

    # ── R7  VKN / TCKN format doğrulaması ────────────────────────────────────
    for label, vkn in [("Satıcı", vendor_vkn), ("Alıcı", buyer_vkn)]:
        if not vkn:
            continue
        digits_only = re.sub(r"\D", "", vkn)
        if len(digits_only) not in (10, 11):
            flags.append(RuleFlag(
                rule_id="R7_INVALID_VKN", severity="warning",
                message=f"{label} VKN/TCKN geçersiz format: '{vkn}' (10 veya 11 hane olmalı)",
                field="vendor_vkn" if label == "Satıcı" else "buyer_vkn",
            ))
        elif not vkn.isdigit():
            flags.append(RuleFlag(
                rule_id="R7_INVALID_VKN", severity="warning",
                message=f"{label} VKN/TCKN sadece rakam içermeli: '{vkn}'",
                field="vendor_vkn" if label == "Satıcı" else "buyer_vkn",
            ))

    # ── R8  Vade tarihi tutarlılığı ───────────────────────────────────────────
    if due_date:
        if inv_date and due_date < inv_date:
            flags.append(RuleFlag(
                rule_id="R8_DUE_BEFORE_ISSUE", severity="error",
                message=f"Vade tarihi ({due_date}) fatura tarihinden ({inv_date}) önce.",
                field="due_date",
            ))
        elif due_date < date.today():
            flags.append(RuleFlag(
                rule_id="R8_OVERDUE", severity="warning",
                message=f"Vade tarihi geçmiş: {due_date} — ödeme yapıldı mı?",
                field="due_date",
            ))

    # ── R9  İskonto sınırı ────────────────────────────────────────────────────
    if subtotal and discount > 0:
        if discount > subtotal:
            flags.append(RuleFlag(
                rule_id="R9_DISCOUNT_EXCEEDS_SUBTOTAL", severity="error",
                message=f"İskonto ({discount:.2f}) ara toplamı ({subtotal:.2f}) aşıyor.",
                field="discount_amount",
            ))
        elif discount / subtotal > 0.50:
            flags.append(RuleFlag(
                rule_id="R9_HIGH_DISCOUNT", severity="warning",
                message=f"İskonto oranı {discount/subtotal:.0%} — ara toplamın %50'sini aşıyor.",
                field="discount_amount",
            ))

    # ── R10  Yuvarlak tutar uyarısı (sahtecilik sinyali) ─────────────────────
    if total and total >= 1000:
        if total == round(total, -3):   # tam bin
            flags.append(RuleFlag(
                rule_id="R10_ROUND_AMOUNT", severity="info",
                message=f"Toplam tutar tam yuvarlak: {total:,.0f} TL — manuel kontrol önerilir.",
            ))

    return flags
