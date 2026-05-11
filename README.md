# Yenibulut Akıllı Fatura

Türkçe fatura analiz sistemi. Görsel, PDF ve XML (UBL-TR e-fatura) formatındaki faturaları otomatik olarak analiz eder.

## Özellikler

- **Çoklu format desteği** — PNG/JPG, PDF, XML (GİB UBL-TR e-fatura)
- **Alan çıkarımı** — Florence-2 (fine-tuned) ile 15 fatura alanı
- **Anomali tespiti** — Isolation Forest ile istatistiksel anormallik tespiti ve z-skoru açıklaması
- **10 kural motoru** — KDV tutarsızlığı, geçersiz tarih, anormal iskonto vb.
- **AI sohbet** — Groq API (Llama 3.3 70B) ile Türkçe fatura analizi
- **XML görüntüleyici** — GİB XSLT ile resmi e-fatura render'ı
- **SSE akışı** — Faturalar işlenirken teker teker görünür

## Teknoloji

| Katman | Teknoloji |
|---|---|
| Görsel OCR | Florence-2 (microsoft/Florence-2-base-ft, fine-tuned) |
| XML parser | Python xml.etree — UBL-TR |
| PDF render | PyMuPDF (Poppler gerektirmez) |
| AI sohbet | Groq API — llama-3.3-70b-versatile |
| Anomali | Isolation Forest (scikit-learn) |
| Backend | FastAPI + uvicorn |
| Frontend | Vanilla HTML/CSS/JS (SSE) |
| Veritabanı | SQLite |

## Kurulum

### Gereksinimler
- Python 3.11+
- NVIDIA GPU (CUDA) — Florence-2 için önerilir, CPU'da da çalışır
- [Groq API key](https://console.groq.com) (ücretsiz)

### Adımlar

```bash
# 1. Sanal ortam oluştur
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

# 2. Bağımlılıkları kur
pip install -r requirements.txt

# 3. flash_attn stub (Windows — Florence-2 import hatası önler)
echo "" > .venv/Lib/site-packages/flash_attn/__init__.py

# 4. Ortam değişkeni
cp .env.example .env
# .env içine GROQ_API_KEY ekle

# 5. Florence-2 modelini indir (ilk çalıştırmada otomatik)
python -c "from transformers import AutoProcessor, AutoModelForCausalLM; AutoProcessor.from_pretrained('microsoft/Florence-2-base-ft', trust_remote_code=True); AutoModelForCausalLM.from_pretrained('microsoft/Florence-2-base-ft', trust_remote_code=True)"

# 6. Uygulamayı başlat
python app/main.py
# → http://127.0.0.1:8000
```

### .env dosyası

```
GROQ_API_KEY=gsk_...
```

## Proje Yapısı

```
invoice-auditor/
├── app/
│   ├── main.py              # FastAPI backend
│   └── static/
│       └── index.html       # SPA frontend
├── services/
│   └── florence_worker.py   # Florence-2 subprocess worker
├── src/
│   ├── service_runner.py    # Subprocess yöneticisi + Groq chat
│   ├── database.py          # SQLite CRUD
│   ├── xml_parser.py        # UBL-TR XML parser
│   ├── anomaly.py           # Isolation Forest + explain()
│   ├── rules.py             # 10 kural motoru
│   └── __init__.py
├── scripts/
│   ├── train_anomaly.py     # Anomali modeli eğitimi
│   └── generate_synthetic_data.py
├── templates/
│   └── invoice_view.xslt    # Fallback XSLT (GİB görünümü)
├── models/                  # git-ignored
│   ├── best_model/          # Fine-tuned Florence-2
│   ├── florence2_base/      # Base model (fallback)
│   ├── anomaly_detector.pkl
│   └── anomaly_scaler.pkl
├── data/
│   └── invoices.db          # SQLite (runtime, git-ignored)
├── .env                     # git-ignored
├── requirements.txt
└── README.md
```

## API Endpoints

| Method | Path | Açıklama |
|---|---|---|
| GET | `/` | Web arayüzü |
| POST | `/api/analyze` | SSE — dosya analizi |
| POST | `/api/chat` | Groq AI sohbet |
| GET | `/api/invoices` | Tüm faturalar + istatistik |
| DELETE | `/api/invoices/{id}` | Fatura sil |
| POST | `/api/render` | PDF/XML belge görüntüle |

## Anomali Tespiti

Isolation Forest, 4 sayısal özelliği analiz eder: `subtotal`, `tax_amount`, `total`, `tax_rate`.

Anomali tespit edildiğinde z-skoru açıklaması üretilir:
```
Toplam tutar: ₺1,000,000 (ortalama ₺12,480, normalden 8.3σ yüksek)
```

## Anomali Modeli Yeniden Eğitimi

```bash
python scripts/train_anomaly.py
```

## Notlar

- Florence-2 subprocess ile çalışır (`transformers==4.41.2` gerektirir)
- Windows'ta `flash_attn` stub gereklidir
- Model önceliği: `models/best_model` → `models/florence2_base` → HuggingFace cache
