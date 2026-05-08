import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from datasets import load_from_disk
from pathlib import Path

# CORD v2
cord = load_from_disk("data/raw/cord")
print("CORD v2:")
print(f"  train : {len(cord['train'])} ornek")
print(f"  test  : {len(cord['test'])} ornek")
print(f"  sutunlar: {cord['train'].column_names}")

print()

# FATURA
try:
    fatura = load_from_disk("data/raw/fatura")
    splits = list(fatura.keys())
    print("FATURA:")
    for s in splits:
        print(f"  {s}: {len(fatura[s])} ornek")
    print(f"  sutunlar: {fatura[splits[0]].column_names}")
except Exception as e:
    print(f"FATURA hata: {e}")

print()

# SROIE
sroie_dir = Path("data/raw/sroie")
img_dirs = list(sroie_dir.rglob("*.jpg")) + list(sroie_dir.rglob("*.png"))
json_files = list(sroie_dir.rglob("*.json"))
print("SROIE:")
print(f"  goruntu sayisi : {len(img_dirs)}")
print(f"  annotation JSON: {len(json_files)}")
