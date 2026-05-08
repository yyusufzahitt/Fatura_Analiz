"""
Veri setlerini indirir: CORD v2, FATURA, SROIE.
Calistir: python scripts/download_datasets.py
"""
import subprocess
import sys
import io
from pathlib import Path

# Windows terminal encoding sorununu coz
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    from datasets import load_dataset
except ImportError:
    print("datasets kutuphanesi bulunamadi. 'pip install datasets' calistirin.")
    sys.exit(1)

BASE = Path("data/raw")


def _has_content(path: Path) -> bool:
    return path.exists() and any(path.iterdir())


def download_cord():
    print("--- CORD v2 indiriliyor ---")
    dst = BASE / "cord"
    if _has_content(dst):
        print(f"  Zaten mevcut: {dst}")
        return
    ds = load_dataset("naver-clova-ix/cord-v2")
    ds.save_to_disk(str(dst))
    print(f"  CORD v2: {len(ds['train'])} train, {len(ds['test'])} test -> {dst}")


def download_fatura():
    print("--- FATURA indiriliyor (~4GB, bekleyin) ---")
    dst = BASE / "fatura"
    if _has_content(dst):
        print(f"  Zaten mevcut: {dst}")
        return
    ds = load_dataset("mathieu1256/FATURA2-invoices")
    ds.save_to_disk(str(dst))
    total = sum(len(ds[s]) for s in ds)
    print(f"  FATURA: {total} goruntu -> {dst}")


def download_sroie():
    print("--- SROIE indiriliyor ---")
    dst = BASE / "sroie"
    if _has_content(dst):
        print(f"  Zaten mevcut: {dst}")
        return
    result = subprocess.run(
        ["git", "clone", "https://github.com/zzzDavid/ICDAR-2019-SROIE.git", str(dst)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  [hata] SROIE clone basarisiz:\n{result.stderr}")
    else:
        print(f"  SROIE -> {dst}")


if __name__ == "__main__":
    BASE.mkdir(parents=True, exist_ok=True)
    download_cord()
    download_sroie()
    download_fatura()
    print("\nTum veri setleri hazir.")
