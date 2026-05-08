import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from datasets import load_from_disk

fatura = load_from_disk("data/raw/fatura")
train = fatura["train"]

# Dataset features icinde label map var mi?
print("=== DATASET FEATURES ===")
print(train.features)

print()

# Tag -> token eslesme dagilimi (ilk 500 ornek)
from collections import defaultdict
tag_to_tokens = defaultdict(list)

for i in range(min(500, len(train))):
    sample = train[i]
    for token, tag in zip(sample["tokens"], sample["ner_tags"]):
        tag_to_tokens[tag].append(token)

print("=== TAG -> ORNEK TOKENLAR ===")
for tag in sorted(tag_to_tokens.keys()):
    ornek = list(dict.fromkeys(tag_to_tokens[tag]))[:12]  # ilk 12 benzersiz token
    print(f"  tag={tag:>2}: {ornek}")

print()

# Ornek bir faturayi tam goster (token + tag + bbox)
print("=== ORNEK FATURA #2 (tam token listesi) ===")
sample = train[2]
print(f"id: {sample['id']}, goruntu boyutu: {sample['image'].size}")
print(f"{'TAG':>4}  TOKEN")
print("-" * 40)
for tok, tag, bbox in zip(sample["tokens"], sample["ner_tags"], sample["bboxes"]):
    print(f"  {tag:>2}  {tok}")
