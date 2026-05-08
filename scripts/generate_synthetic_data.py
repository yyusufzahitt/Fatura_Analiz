"""
Fatura analizi icin sentetik egitim verisi uretir.
Calistir: python scripts/generate_synthetic_data.py
Cikti: data/synthetic/invoice_analysis_train.jsonl
"""
import sys, io, json, random
from pathlib import Path
from datetime import date, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
random.seed(42)

OUT_PATH = Path("data/synthetic")
OUT_PATH.mkdir(parents=True, exist_ok=True)

# ─── Sabit listeler ──────────────────────────────────────────────────

FIRMALAR = [
    "AYEDAŞ A.Ş.", "BAŞKENT EDAŞ", "ENERJİSA", "TOROSLAR EDAŞ",
    "İSTANBUL SU", "ANKARA SU İDARESİ", "İZMİR SU", "BURSA SU",
    "TURKCELL", "VODAFONE TÜRKİYE", "TÜRK TELEKOM", "SUPERONLINE",
    "İGDAŞ", "BAĞCILAR DOĞALGAZ", "GAZDAŞ", "AKSA DOĞALGAZ",
    "AMAZON TÜRKİYE", "TRENDYOL TEDARİK", "N11 B2B", "HEPSİBURADA",
    "ABC TEMİZLİK HİZM.", "XYZ KURYE LOJİSTİK", "DELTA GÜVENLİK",
    "METRO TOPTAN", "MAKRO MARKET", "ÇAĞRIOĞLU KIRTASIYE",
]

KATEGORİLER = {
    "AYEDAŞ A.Ş.":          "elektrik",
    "BAŞKENT EDAŞ":         "elektrik",
    "ENERJİSA":             "elektrik",
    "TOROSLAR EDAŞ":        "elektrik",
    "İSTANBUL SU":          "su",
    "ANKARA SU İDARESİ":    "su",
    "İZMİR SU":             "su",
    "BURSA SU":             "su",
    "TURKCELL":             "telefon/internet",
    "VODAFONE TÜRKİYE":     "telefon/internet",
    "TÜRK TELEKOM":         "telefon/internet",
    "SUPERONLINE":          "telefon/internet",
    "İGDAŞ":                "doğalgaz",
    "BAĞCILAR DOĞALGAZ":    "doğalgaz",
    "GAZDAŞ":               "doğalgaz",
    "AKSA DOĞALGAZ":        "doğalgaz",
    "AMAZON TÜRKİYE":       "e-ticaret/tedarik",
    "TRENDYOL TEDARİK":     "e-ticaret/tedarik",
    "N11 B2B":              "e-ticaret/tedarik",
    "HEPSİBURADA":          "e-ticaret/tedarik",
    "ABC TEMİZLİK HİZM.":   "hizmet",
    "XYZ KURYE LOJİSTİK":   "lojistik",
    "DELTA GÜVENLİK":       "hizmet",
    "METRO TOPTAN":         "market/tedarik",
    "MAKRO MARKET":         "market/tedarik",
    "ÇAĞRIOĞLU KIRTASIYE":  "kırtasiye",
}

AYLAR = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
]

# ─── Yardımcı fonksiyonlar ───────────────────────────────────────────

def uret_tutarlar(n_ay: int, baslangic: float, trend: str) -> list[float]:
    """Belirli trende gore aylik tutarlar uret."""
    tutarlar = [baslangic]
    for _ in range(n_ay - 1):
        if trend == "artan":
            degisim = random.uniform(0.03, 0.25)
        elif trend == "dusen":
            degisim = -random.uniform(0.03, 0.20)
        elif trend == "stabil":
            degisim = random.uniform(-0.04, 0.04)
        else:  # dalgali
            degisim = random.uniform(-0.20, 0.30)
        yeni = tutarlar[-1] * (1 + degisim)
        yeni = max(10.0, yeni)
        tutarlar.append(round(yeni, 2))
    return tutarlar


def yuzde_degisim(eski: float, yeni: float) -> float:
    if eski == 0:
        return 0.0
    return round((yeni - eski) / eski * 100, 1)


def trend_tespit(tutarlar: list[float]) -> str:
    ilk = tutarlar[0]
    son = tutarlar[-1]
    pct = yuzde_degisim(ilk, son)
    if pct >= 15:
        return "artan"
    elif pct <= -10:
        return "dusen"
    elif abs(pct) < 5:
        return "stabil"
    else:
        return "dalgali"


def format_tutar(t: float) -> str:
    return f"{t:,.2f} TL".replace(",", "X").replace(".", ",").replace("X", ".")


# ─── Analiz metni uretici ────────────────────────────────────────────

def analiz_yaz(firma: str, kategori: str, ay_isimleri: list[str],
               tutarlar: list[float]) -> str:
    n = len(tutarlar)
    ilk = tutarlar[0]
    son = tutarlar[-1]
    maks = max(tutarlar)
    maks_ay = ay_isimleri[tutarlar.index(maks)]
    mini = min(tutarlar)
    mini_ay = ay_isimleri[tutarlar.index(mini)]
    toplam = sum(tutarlar)
    ort = toplam / n
    genel_pct = yuzde_degisim(ilk, son)
    trend = trend_tespit(tutarlar)

    # Aylik degisimler
    degisimler = []
    for i in range(1, n):
        pct = yuzde_degisim(tutarlar[i-1], tutarlar[i])
        degisimler.append((ay_isimleri[i-1], ay_isimleri[i], pct))

    # En buyuk tek aylik artis
    en_buyuk = max(degisimler, key=lambda x: x[2])
    en_kucuk = min(degisimler, key=lambda x: x[2])

    # Template secimi
    satirlar = []

    # 1. Giris cumlesi
    giris_sablonlar = {
        "artan": [
            f"{firma} adlı firmaya ait {kategori} faturaları {ay_isimleri[0]}-{ay_isimleri[-1]} döneminde sürekli artış eğilimi göstermiştir.",
            f"{ay_isimleri[0]}'dan {ay_isimleri[-1]}'a kadar {firma} {kategori} giderlerinde belirgin bir yükseliş gözlemlenmektedir.",
        ],
        "dusen": [
            f"{firma} {kategori} faturaları {ay_isimleri[0]}-{ay_isimleri[-1]} döneminde genel olarak azalma göstermiştir.",
            f"İncelenen dönemde {firma}'ya ödenen {kategori} tutarları düşüş eğilimindedir.",
        ],
        "stabil": [
            f"{firma} {kategori} faturaları {ay_isimleri[0]}-{ay_isimleri[-1]} döneminde oldukça stabil seyretmiştir.",
            f"İncelenen {n} aylık dönemde {firma} {kategori} giderleri büyük dalgalanma göstermemiştir.",
        ],
        "dalgali": [
            f"{firma} {kategori} faturaları {ay_isimleri[0]}-{ay_isimleri[-1]} döneminde dalgalı bir seyir izlemiştir.",
            f"{firma}'ya ait {kategori} ödemeleri incelenen dönemde tutarsız bir görünüm sergilemiştir.",
        ],
    }
    satirlar.append(random.choice(giris_sablonlar[trend]))

    # 2. Tutar ozeti
    satirlar.append(
        f"{ay_isimleri[0]} ayında {format_tutar(ilk)} olan fatura tutarı, "
        f"{ay_isimleri[-1]} ayında {format_tutar(son)} seviyesine ulaşmıştır."
    )

    # 3. Genel degisim
    if abs(genel_pct) >= 1:
        yon = "artmış" if genel_pct > 0 else "azalmış"
        satirlar.append(
            f"Bu dönemde toplam değişim %{abs(genel_pct):.1f} oranında {yon}tır."
        )

    # 4. En buyuk tek aylik degisim
    if abs(en_buyuk[2]) >= 5:
        satirlar.append(
            f"En dikkat çekici artış {en_buyuk[0]}-{en_buyuk[1]} döneminde "
            f"%{en_buyuk[2]:.1f} oranında gerçekleşmiştir."
        )
    if en_kucuk[2] < -5:
        satirlar.append(
            f"En belirgin düşüş ise {en_kucuk[0]}-{en_kucuk[1]} arasında "
            f"%{abs(en_kucuk[2]):.1f} oranında yaşanmıştır."
        )

    # 5. Tepe ve dip
    if maks_ay != ay_isimleri[-1]:
        satirlar.append(
            f"Dönemin en yüksek faturası {maks_ay} ayında {format_tutar(maks)} olarak gerçekleşmiştir."
        )
    if mini_ay != ay_isimleri[0]:
        satirlar.append(
            f"En düşük tutar ise {mini_ay} ayında {format_tutar(mini)} olarak kaydedilmiştir."
        )

    # 6. Toplam ve ortalama
    satirlar.append(
        f"Dönem genelinde {firma}'ya toplam {format_tutar(toplam)} ödeme yapılmış, "
        f"aylık ortalama {format_tutar(ort)} olmuştur."
    )

    # 7. Yorum / oneri
    if trend == "artan" and genel_pct >= 20:
        satirlar.append(
            f"Bu artış oranı dikkat gerektirmektedir. "
            f"Fiyat artışı gerekçelerinin tedarikçiden talep edilmesi önerilir."
        )
    elif trend == "artan" and genel_pct >= 10:
        satirlar.append("Artış trendi yakından takip edilmelidir.")
    elif trend == "dusen":
        satirlar.append("Düşüş trendi olumlu olmakla birlikte sürdürülebilirliği izlenmelidir.")
    elif trend == "stabil":
        satirlar.append("Stabil seyir, bütçe planlaması açısından öngörülebilir bir yapı sunmaktadır.")

    return " ".join(satirlar)


# ─── Ana uretim dongusu ──────────────────────────────────────────────

def ornek_uret() -> dict:
    firma = random.choice(FIRMALAR)
    kategori = KATEGORİLER.get(firma, "genel")
    n_ay = random.choice([3, 4, 5, 6])
    baslangic_ay_idx = random.randint(0, 12 - n_ay)
    ay_isimleri = AYLAR[baslangic_ay_idx: baslangic_ay_idx + n_ay]
    yil = random.choice([2023, 2024])
    trend = random.choice(["artan", "artan", "dusen", "stabil", "dalgali"])  # artana agirlik
    baslangic = random.uniform(150, 5000)
    tutarlar = uret_tutarlar(n_ay, baslangic, trend)

    # Tablo satiri
    tablo = "\n".join(
        f"  {ay}: {format_tutar(t)}"
        for ay, t in zip(ay_isimleri, tutarlar)
    )

    # Girdi: sistem promptu + veri
    girdi = (
        f"Aşağıdaki fatura verilerini analiz et ve Türkçe rapor yaz.\n\n"
        f"Firma: {firma}\n"
        f"Kategori: {kategori}\n"
        f"Yıl: {yil}\n"
        f"Aylık fatura tutarları:\n{tablo}"
    )

    # Cikti: analiz metni
    cikti = analiz_yaz(firma, kategori, ay_isimleri, tutarlar)

    return {
        "instruction": girdi,
        "output": cikti,
        "firma": firma,
        "kategori": kategori,
        "trend": trend,
        "n_ay": n_ay,
    }


def main(n: int = 1000):
    print(f"{n} adet sentetik ornek uretiliyor...")
    ornekler = [ornek_uret() for _ in range(n)]

    out_file = OUT_PATH / "invoice_analysis_train.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for ornek in ornekler:
            f.write(json.dumps(ornek, ensure_ascii=False) + "\n")

    print(f"Kaydedildi: {out_file}")
    print(f"Toplam: {len(ornekler)} ornek")

    # Ornekten goster
    print("\n--- Ornek #0 ---")
    print("GIRDI:")
    print(ornekler[0]["instruction"])
    print("\nCIKTI:")
    print(ornekler[0]["output"])
    print("\n--- Ornek #1 ---")
    print("GIRDI:")
    print(ornekler[1]["instruction"])
    print("\nCIKTI:")
    print(ornekler[1]["output"])

    # Trend dagilimi
    from collections import Counter
    trend_dist = Counter(o["trend"] for o in ornekler)
    print(f"\nTrend dagilimi: {dict(trend_dist)}")


if __name__ == "__main__":
    main(1000)
