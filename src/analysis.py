"""
Çoklu fatura analizi:
- Mükerrer fatura tespiti
- Aynı firma faturaları
- Dönem bazlı harcama özeti
- Firma bazlı harcama özeti
"""
import json
from datetime import datetime, date
from typing import Optional
from src.database import get_all_invoices, get_stats


def _parse_date(val: str) -> Optional[date]:
    if not val:
        return None
    formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
        "%d-%m-%Y", "%d %b %Y", "%d %B %Y",
        "%d-%b-%Y", "%d-%B-%Y",
        "%d %b-%Y", "%B %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except Exception:
            continue
    return None


def _safe_float(val) -> float:
    try:
        return float(str(val).replace(",", ".").replace("$", "").strip())
    except Exception:
        return 0.0


# ─── Mükerrer Tespit ─────────────────────────────────────────────────

def find_duplicates(invoices: list[dict], amount_tol: float = 0.01) -> list[dict]:
    """
    Aynı vendor + aynı tutar + aynı tarih → mükerrer.
    amount_tol: tutar farkı toleransı (varsayılan: 1 kuruş)
    """
    duplicates = []
    seen = []

    for inv in invoices:
        vendor = (inv.get("vendor_name") or "").strip().lower()
        total  = _safe_float(inv.get("total"))
        dstr   = inv.get("invoice_date", "")
        inv_no = (inv.get("invoice_number") or "").strip()

        for prev in seen:
            same_vendor = vendor and vendor == (prev.get("vendor_name") or "").strip().lower()
            same_amount = total > 0 and abs(total - _safe_float(prev.get("total"))) <= amount_tol
            same_date   = dstr and dstr == prev.get("invoice_date", "")
            same_inv_no = inv_no and inv_no == (prev.get("invoice_number") or "").strip()

            if same_vendor and (same_amount or same_inv_no) and same_date:
                duplicates.append({
                    "invoice_id_1": prev["id"],
                    "invoice_id_2": inv["id"],
                    "vendor_name":  inv.get("vendor_name"),
                    "total":        total,
                    "invoice_date": dstr,
                    "reason":       "Ayni firma + tutar + tarih" if not same_inv_no else "Ayni fatura numarasi",
                })
        seen.append(inv)

    return duplicates


# ─── Firma Analizi ───────────────────────────────────────────────────

def vendor_summary(invoices: list[dict]) -> list[dict]:
    """Firma bazlı toplam harcama ve fatura sayısı."""
    summary: dict[str, dict] = {}

    for inv in invoices:
        vendor = (inv.get("vendor_name") or "Bilinmeyen").strip()
        if not vendor:
            vendor = "Bilinmeyen"
        total = _safe_float(inv.get("total"))

        if vendor not in summary:
            summary[vendor] = {"vendor_name": vendor, "count": 0, "total": 0.0, "invoices": []}
        summary[vendor]["count"]   += 1
        summary[vendor]["total"]   += total
        summary[vendor]["invoices"].append(inv["id"])

    result = sorted(summary.values(), key=lambda x: x["total"], reverse=True)
    return result


# ─── Dönem Analizi ───────────────────────────────────────────────────

def monthly_summary(invoices: list[dict]) -> list[dict]:
    """Ay bazlı toplam harcama."""
    monthly: dict[str, dict] = {}

    for inv in invoices:
        d = _parse_date(inv.get("invoice_date", ""))
        key = d.strftime("%Y-%m") if d else "Tarihi bilinmeyen"
        total = _safe_float(inv.get("total"))

        if key not in monthly:
            monthly[key] = {"period": key, "count": 0, "total": 0.0}
        monthly[key]["count"] += 1
        monthly[key]["total"] += total

    result = sorted(monthly.values(), key=lambda x: x["period"])
    return result


# ─── Tek Firma Derinlemesine ─────────────────────────────────────────

def vendor_detail(invoices: list[dict], vendor_name: str) -> dict:
    """Belirli bir firma için tüm fatura geçmişi ve istatistikler."""
    vendor_lower = vendor_name.strip().lower()
    filtered = [
        inv for inv in invoices
        if (inv.get("vendor_name") or "").strip().lower() == vendor_lower
    ]

    if not filtered:
        return {"vendor_name": vendor_name, "count": 0, "invoices": []}

    totals = [_safe_float(inv.get("total")) for inv in filtered]
    return {
        "vendor_name": vendor_name,
        "count":       len(filtered),
        "total":       sum(totals),
        "avg":         sum(totals) / len(totals),
        "min":         min(totals),
        "max":         max(totals),
        "invoices":    filtered,
    }


# ─── Genel Rapor ─────────────────────────────────────────────────────

def full_report() -> dict:
    """Tüm veritabanı üzerinde tam analiz raporu döndürür."""
    invoices = get_all_invoices()

    if not invoices:
        return {"error": "Henuz hic fatura yuklenmemis."}

    stats      = get_stats()
    duplicates = find_duplicates(invoices)
    vendors    = vendor_summary(invoices)
    monthly    = monthly_summary(invoices)

    anomalies = [inv for inv in invoices if inv.get("is_anomaly")]

    return {
        "toplam_fatura":     stats["total_count"],
        "toplam_tutar":      round(stats["total_amount"], 2),
        "ortalama_tutar":    round(stats["avg_amount"], 2),
        "en_buyuk_fatura":   round(stats["max_amount"], 2),
        "anomali_sayisi":    stats["anomaly_count"],
        "mukerrer_sayisi":   len(duplicates),
        "firma_sayisi":      len(vendors),
        "mukerrerler":       duplicates,
        "firma_ozeti":       vendors,
        "aylik_ozet":        monthly,
        "anomali_faturalar": [
            {"id": inv["id"], "vendor": inv.get("vendor_name"), "total": inv.get("total")}
            for inv in anomalies
        ],
    }
