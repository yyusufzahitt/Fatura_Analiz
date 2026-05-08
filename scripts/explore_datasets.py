import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from datasets import load_from_disk
from pathlib import Path

SEP = "=" * 60

# ─────────────────────────────────────────────────────────────
# CORD v2
# ─────────────────────────────────────────────────────────────
print(SEP)
print("CORD v2")
print(SEP)

cord = load_from_disk("data/raw/cord")
print(f"Splitler: {list(cord.keys())}")
for split in cord:
    print(f"  {split}: {len(cord[split])} ornek, sutunlar={cord[split].column_names}")

print("\n--- Ornek #0 (train) ---")
sample = cord["train"][0]
print(f"  image tipi : {type(sample['image'])} | mode={sample['image'].mode} | size={sample['image'].size}")
gt_raw = sample["ground_truth"]
print(f"  ground_truth tipi: {type(gt_raw)}")
if isinstance(gt_raw, str):
    gt = json.loads(gt_raw)
else:
    gt = gt_raw
print(f"  ground_truth anahtarlari: {list(gt.keys())}")
print(f"  ground_truth icerigi:")
print(json.dumps(gt, indent=4, ensure_ascii=False))

print("\n--- Ornek #1 (train) - ground_truth ---")
gt2_raw = cord["train"][1]["ground_truth"]
gt2 = json.loads(gt2_raw) if isinstance(gt2_raw, str) else gt2_raw
print(json.dumps(gt2, indent=4, ensure_ascii=False))

# total/sub_total tiplerini kontrol et
print("\n--- ground_truth deger tipleri (ilk 5 ornek) ---")
for i in range(5):
    gt_r = cord["train"][i]["ground_truth"]
    gt_p = json.loads(gt_r) if isinstance(gt_r, str) else gt_r
    gp = gt_p.get("gt_parse", gt_p)
    total_val = gp.get("total", {})
    sub_val   = gp.get("sub_total", {})
    print(f"  [{i}] total tipi={type(total_val).__name__}  sub_total tipi={type(sub_val).__name__}")
    if isinstance(total_val, dict):
        print(f"       total anahtarlari={list(total_val.keys())}")
    if isinstance(sub_val, dict):
        print(f"       sub_total anahtarlari={list(sub_val.keys())}")

# ─────────────────────────────────────────────────────────────
# FATURA
# ─────────────────────────────────────────────────────────────
print()
print(SEP)
print("FATURA (mathieu1256/FATURA2-invoices)")
print(SEP)

fatura = load_from_disk("data/raw/fatura")
print(f"Splitler: {list(fatura.keys())}")
for split in fatura:
    print(f"  {split}: {len(fatura[split])} ornek, sutunlar={fatura[split].column_names}")

print("\n--- Ornek #0 (train) ---")
fs = fatura["train"][0]
for col, val in fs.items():
    if col == "image":
        print(f"  image: mode={val.mode}, size={val.size}")
    elif isinstance(val, list):
        print(f"  {col} (liste, uzunluk={len(val)}): ilk 3 eleman = {val[:3]}")
    else:
        print(f"  {col}: {repr(val)[:120]}")

print("\n--- Ornek #1 (train) ---")
fs2 = fatura["train"][1]
for col, val in fs2.items():
    if col == "image":
        print(f"  image: mode={val.mode}, size={val.size}")
    elif isinstance(val, list):
        print(f"  {col} (liste, uzunluk={len(val)}): ilk 5 eleman = {val[:5]}")
    else:
        print(f"  {col}: {repr(val)[:120]}")

print("\n--- NER tag cesitleri (train, ilk 200 ornek) ---")
all_tags = set()
for i in range(min(200, len(fatura["train"]))):
    all_tags.update(fatura["train"][i].get("ner_tags", []))
print(f"  Benzersiz tag degerleri: {sorted(all_tags)}")

print("\n--- tokens/ner_tags eslesme ornegi (ornek #0) ---")
tokens0  = fs["tokens"]
tags0    = fs["ner_tags"]
for tok, tag in zip(tokens0[:15], tags0[:15]):
    print(f"  {tag:>3}  {tok}")

# ─────────────────────────────────────────────────────────────
# SROIE
# ─────────────────────────────────────────────────────────────
print()
print(SEP)
print("SROIE (ICDAR 2019)")
print(SEP)

sroie_dir = Path("data/raw/sroie")
print(f"Kok klasor: {sroie_dir.resolve()}")
print(f"Alt klasorler: {[d.name for d in sroie_dir.iterdir() if d.is_dir()]}")

# Gorseller
all_imgs = list(sroie_dir.rglob("*.jpg")) + list(sroie_dir.rglob("*.png"))
print(f"\nToplam gorsel: {len(all_imgs)}")
if all_imgs:
    from PIL import Image as PILImage
    img0 = PILImage.open(all_imgs[0])
    print(f"Ornek gorsel: {all_imgs[0].name} | size={img0.size} | mode={img0.mode}")

# JSON annotation dosyalari
all_jsons = list(sroie_dir.rglob("*.json"))
print(f"Toplam JSON annotation: {len(all_jsons)}")

# Hangi klasorlerde var?
json_parents = {}
for jf in all_jsons:
    p = jf.parent.name
    json_parents[p] = json_parents.get(p, 0) + 1
print(f"JSON klasor dagilimi: {json_parents}")

# Ornek annotation oku
if all_jsons:
    print(f"\n--- Ornek annotation: {all_jsons[0].name} ---")
    with open(all_jsons[0], encoding="utf-8") as f:
        content = f.read().strip()
    # JSON mu yoksa diger format mi?
    try:
        data = json.loads(content)
        print(f"  Format: JSON")
        print(f"  Anahtarlar: {list(data.keys())}")
        print(json.dumps(data, indent=4, ensure_ascii=False))
    except json.JSONDecodeError:
        print(f"  Format: duz metin (JSON degil)")
        print(f"  Ilk 5 satir:")
        for line in content.splitlines()[:5]:
            print(f"    {line}")

# task3 key klasorunu bul (gercek annotation orada)
task3_key = sroie_dir / "data" / "key"
task1_img = sroie_dir / "data" / "img"
if not task3_key.exists():
    task3_key = sroie_dir / "task3" / "dev"
    for candidate in [
        sroie_dir / "data" / "key",
        sroie_dir / "task3",
        sroie_dir / "task1_revamp",
    ]:
        if candidate.exists():
            task3_key = candidate
            break

print(f"\n--- task3/key klasoru: {task3_key} ---")
if task3_key.exists():
    key_files = list(task3_key.glob("*.json")) + list(task3_key.glob("*.txt"))
    print(f"  Dosya sayisi: {len(key_files)}")
    if key_files:
        print(f"  Ornek dosya: {key_files[0].name}")
        with open(key_files[0], encoding="utf-8", errors="replace") as f:
            content = f.read().strip()
        try:
            data = json.loads(content)
            print(f"  Anahtarlar: {list(data.keys())}")
            print(json.dumps(data, indent=4, ensure_ascii=False))
        except json.JSONDecodeError:
            for line in content.splitlines()[:8]:
                print(f"    {line}")

# img klasoru
print(f"\n--- img klasoru ---")
for candidate in [sroie_dir / "data" / "img", sroie_dir / "task1" / "train"]:
    if candidate.exists():
        imgs = list(candidate.glob("*.jpg")) + list(candidate.glob("*.png"))
        print(f"  {candidate}: {len(imgs)} gorsel")
