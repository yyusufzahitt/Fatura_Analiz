import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from src.analyzer import InvoiceAnalyzer

analyzer = InvoiceAnalyzer("models/qwen_best")

# Test 1 — artan trend
print("=" * 55)
print("TEST 1: Artan trend (elektrik)")
print("=" * 55)
sonuc = analyzer.analyze_vendor_trend(
    vendor_name="AYEDAS A.S.",
    kategori="elektrik",
    ay_tutar_listesi=[
        ("Ocak", 850.0),
        ("Subat", 920.0),
        ("Mart", 1105.0),
    ]
)
print(sonuc)

# Test 2 — stabil trend
print()
print("=" * 55)
print("TEST 2: Stabil trend (internet)")
print("=" * 55)
sonuc2 = analyzer.analyze_vendor_trend(
    vendor_name="TURKCELL",
    kategori="telefon/internet",
    ay_tutar_listesi=[
        ("Ocak", 450.0),
        ("Subat", 452.0),
        ("Mart", 448.0),
        ("Nisan", 451.0),
    ]
)
print(sonuc2)

# Test 3 — serbest soru
print()
print("=" * 55)
print("TEST 3: Serbest soru")
print("=" * 55)
sonuc3 = analyzer.free_question(
    soru="Bu firmaya yapilan odemeler normal mi, dikkat etmem gereken bir durum var mi?",
    context="Firma: AYEDAS A.S. | Ocak: 850 TL | Subat: 920 TL | Mart: 1105 TL | Toplam: 2875 TL"
)
print(sonuc3)
