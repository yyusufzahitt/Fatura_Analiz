import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from datasets import load_from_disk
from pathlib import Path
from src.dataset import cord_to_donut_json, sroie_to_donut_json, fatura_to_donut_json

SEP = "-" * 55

# ─── CORD v2 ─────────────────────────────────────────────────
print("=== CORD v2 - cord_to_donut_json ===")
cord = load_from_disk("data/raw/cord")
for i in range(5):
    result = cord_to_donut_json(cord["train"][i])
    parsed = json.loads(result)
    print(f"  [{i}] total={parsed['total']!r:>12}  subtotal={parsed['subtotal']!r:>12}  tax={parsed['tax_amount']!r}")

# Bos vendor_name bekleniyor (CORD makbuz, restoran adi yok)
empty_vendor = sum(
    1 for i in range(len(cord["train"]))
    if not json.loads(cord_to_donut_json(cord["train"][i]))["total"]
)
print(f"  total bos olan ornek sayisi: {empty_vendor} / {len(cord['train'])}")

# ─── SROIE ───────────────────────────────────────────────────
print()
print("=== SROIE - sroie_to_donut_json ===")
ann_dir = Path("data/raw/sroie/data/key")
img_dir = Path("data/raw/sroie/data/img")
ann_files = sorted(ann_dir.glob("*.json"))

for ann_path in ann_files[:5]:
    result = sroie_to_donut_json(ann_path)
    parsed = json.loads(result)
    print(f"  {ann_path.name}: vendor={parsed['vendor_name'][:30]!r}  date={parsed['invoice_date']!r}  total={parsed['total']!r}")

# Gorsel-annotation eslesme orani
matched = sum(
    1 for p in ann_files
    if (img_dir / p.with_suffix(".jpg").name).exists()
)
print(f"  Gorsel-annotation eslesme: {matched} / {len(ann_files)}")

# ─── FATURA ──────────────────────────────────────────────────
print()
print("=== FATURA - fatura_to_donut_json ===")
fatura = load_from_disk("data/raw/fatura")
for i in range(8):
    result = fatura_to_donut_json(fatura["train"][i])
    parsed = json.loads(result)
    print(f"  [{i}] vendor={parsed['vendor_name'][:25]!r:27}  date={parsed['invoice_date']!r:14}  inv_no={parsed['invoice_number']!r:15}  total={parsed['total']!r}")

# Dolu alan orani kontrolu (ilk 200 ornek)
n = 200
counts = {"vendor_name": 0, "invoice_date": 0, "invoice_number": 0, "total": 0}
for i in range(n):
    p = json.loads(fatura_to_donut_json(fatura["train"][i]))
    for k in counts:
        if p[k]:
            counts[k] += 1
print(f"\n  Alan doluluğu (ilk {n} ornek):")
for k, v in counts.items():
    print(f"    {k:>15}: %{100*v//n}")
