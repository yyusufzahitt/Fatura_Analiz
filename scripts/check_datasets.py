import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from datasets import load_dataset

# 1. AYA - Turkce instruction ornekleri
print("=== AYA Turkce split ===")
try:
    aya = load_dataset("CohereForAI/aya_dataset", split="train")
    tr = aya.filter(lambda x: x["language"] == "Turkish")
    print(f"  Toplam Turkce: {len(tr)} ornek")
    print(f"  Sutunlar: {tr.column_names}")
    for i in range(3):
        print(f"  [{i}] inputs: {tr[i]['inputs'][:80]}")
        print(f"       targets: {tr[i]['targets'][:80]}")
        print()
except Exception as e:
    print(f"  Hata: {e}")

# 2. Alpaca Turkish
print("=== Alpaca Turkish ===")
try:
    alpaca_tr = load_dataset("muhammetali/alpaca-turkish-cleaned", split="train")
    print(f"  Toplam: {len(alpaca_tr)} ornek")
    print(f"  Sutunlar: {alpaca_tr.column_names}")
    for i in range(2):
        print(f"  [{i}] instruction: {alpaca_tr[i]['instruction'][:80]}")
        print(f"       output: {alpaca_tr[i]['output'][:80]}")
        print()
except Exception as e:
    print(f"  Hata: {e}")

# 3. Financial PhraseBank
print("=== Financial PhraseBank ===")
try:
    fpb = load_dataset("financial_phrasebank", "sentences_allagree", split="train", trust_remote_code=True)
    print(f"  Toplam: {len(fpb)} ornek")
    print(f"  Sutunlar: {fpb.column_names}")
    print(f"  Ornek: {fpb[0]}")
except Exception as e:
    print(f"  Hata: {e}")
