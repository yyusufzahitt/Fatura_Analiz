import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from datasets import load_from_disk
from pathlib import Path
from src.dataset import cord_to_donut_json, fatura_to_donut_json
from src.anomaly import AnomalyDetector


def _safe_float(val):
    try:
        return float(str(val).replace(",", ".").replace("$", "").strip())
    except Exception:
        return None


def collect_records():
    records = []

    # CORD v2 - subtotal, tax_amount, total
    print("CORD yukleniyor...")
    cord = load_from_disk("data/raw/cord")
    for split in ["train", "validation"]:
        for item in cord[split]:
            parsed = json.loads(cord_to_donut_json(item))
            subtotal   = _safe_float(parsed.get("subtotal"))
            tax_amount = _safe_float(parsed.get("tax_amount"))
            total      = _safe_float(parsed.get("total"))
            if total and total > 0:
                records.append({
                    "subtotal":   subtotal or 0.0,
                    "tax_amount": tax_amount or 0.0,
                    "total":      total,
                    "tax_rate":   0.0,
                })
    print(f"  CORD: {len(records)} kayit")

    # FATURA - total
    print("FATURA yukleniyor...")
    n_before = len(records)
    fatura = load_from_disk("data/raw/fatura")
    for item in fatura["train"].select(range(2000)):
        parsed = json.loads(fatura_to_donut_json(item))
        total = _safe_float(parsed.get("total"))
        if total and total > 0:
            records.append({
                "subtotal":   total * 0.9,   # subtotal tahmini
                "tax_amount": total * 0.1,
                "total":      total,
                "tax_rate":   0.0,
            })
    print(f"  FATURA: {len(records) - n_before} kayit")

    return records


if __name__ == "__main__":
    records = collect_records()
    print(f"\nToplam kayit: {len(records)}")

    detector = AnomalyDetector()
    detector.fit(records)
    print("Anomali modeli hazir: models/anomaly_detector.pkl")
