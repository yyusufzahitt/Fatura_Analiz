import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from src.analyzer import InvoiceAnalyzer

analyzer = InvoiceAnalyzer()

# Sahte veritabani verisi
FATURALAR = [
    {"vendor_name": "AYEDAS A.S.", "invoice_date": "2024-01", "total": 850.0,  "is_anomaly": 0, "anomaly_score": None, "rule_flags": "[]"},
    {"vendor_name": "AYEDAS A.S.", "invoice_date": "2024-02", "total": 920.0,  "is_anomaly": 0, "anomaly_score": None, "rule_flags": "[]"},
    {"vendor_name": "AYEDAS A.S.", "invoice_date": "2024-03", "total": 1105.0, "is_anomaly": 1, "anomaly_score": 0.87,
     "rule_flags": '[{"severity":"error","message":"subtotal + tax_amount = 980.00 but total is 1105.00 (diff=125.00)"},{"severity":"warning","message":"Tax rate 32.5% is outside expected range [0%, 50%]."}]'},
    {"vendor_name": "TURKCELL",    "invoice_date": "2024-01", "total": 450.0,  "is_anomaly": 0, "anomaly_score": None, "rule_flags": "[]"},
    {"vendor_name": "TURKCELL",    "invoice_date": "2024-02", "total": 452.0,  "is_anomaly": 0, "anomaly_score": None, "rule_flags": "[]"},
]

print("=" * 55)
print("TEST 1: Firma trend analizi (Python)")
print("=" * 55)
ayedas = [inv for inv in FATURALAR if inv["vendor_name"] == "AYEDAS A.S."]
print(analyzer.analyze_from_db(ayedas))

print()
print("=" * 55)
print("TEST 2: Serbest soru — ilgili")
print("=" * 55)
print(analyzer.free_question("Bu ay toplam giderim ne kadar?", FATURALAR))

print()
print("=" * 55)
print("TEST 3: Serbest soru — konu disi")
print("=" * 55)
print(analyzer.free_question("Turkiyenin baskenti neresi?", FATURALAR))

print()
print("=" * 55)
print("TEST 4: Serbest soru — firma bazli")
print("=" * 55)
print(analyzer.free_question("AYEDAS faturalarinda anomali var mi?", FATURALAR))
