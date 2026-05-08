"""
Tamamen Python tabanlı rapor uretici.
Hallucination yok, hizli, deterministik.
Qwen sadece serbest soru icin rezerve edilmistir.
"""
import re
from typing import Optional


def _safe_float(val) -> Optional[float]:
    try:
        return float(str(val).replace(",", ".").replace("TL", "").replace("$", "").strip())
    except Exception:
        return None


def _fmt(t: float) -> str:
    """1234567.89 → 1.234.567,89 TL"""
    return f"{t:,.2f} TL".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(eski: float, yeni: float) -> float:
    if eski == 0:
        return 0.0
    return round((yeni - eski) / eski * 100, 1)


def hesapla(ay_tutar: list[tuple[str, float]]) -> dict:
    tutarlar = [t for _, t in ay_tutar]
    aylar    = [a for a, _ in ay_tutar]
    n        = len(tutarlar)
    ilk, son = tutarlar[0], tutarlar[-1]
    toplam   = sum(tutarlar)
    ort      = toplam / n
    maks     = max(tutarlar)
    mini     = min(tutarlar)
    maks_ay  = aylar[tutarlar.index(maks)]
    mini_ay  = aylar[tutarlar.index(mini)]
    genel_pct = _pct(ilk, son)

    aylik = [
        {"from": aylar[i-1], "to": aylar[i], "pct": _pct(tutarlar[i-1], tutarlar[i])}
        for i in range(1, n)
    ]

    if genel_pct >= 15:
        trend = "artan"
    elif genel_pct <= -10:
        trend = "dusen"
    elif abs(genel_pct) < 5:
        trend = "stabil"
    else:
        trend = "dalgali"

    return {
        "aylar": aylar, "tutarlar": tutarlar, "n": n,
        "ilk": ilk, "son": son, "ilk_ay": aylar[0], "son_ay": aylar[-1],
        "toplam": round(toplam, 2), "ort": round(ort, 2),
        "maks": maks, "maks_ay": maks_ay,
        "mini": mini, "mini_ay": mini_ay,
        "genel_pct": genel_pct, "trend": trend,
        "aylik": aylik,
    }


def vendor_trend_report(firma: str, kategori: str,
                        ay_tutar: list[tuple[str, float]]) -> str:
    if len(ay_tutar) < 2:
        return f"{firma} icin analiz yapabilmek icin en az 2 fatura gereklidir."

    h = hesapla(ay_tutar)
    satirlar = []

    # 1. Giris
    trend_map = {
        "artan":   f"{firma} {kategori} faturalari {h['ilk_ay']}-{h['son_ay']} doneminde artis egilimi gostermistir.",
        "dusen":   f"{firma} {kategori} faturalari {h['ilk_ay']}-{h['son_ay']} doneminde dusus egilimi gostermistir.",
        "stabil":  f"{firma} {kategori} faturalari {h['ilk_ay']}-{h['son_ay']} doneminde stabil seyretmistir.",
        "dalgali": f"{firma} {kategori} faturalari {h['ilk_ay']}-{h['son_ay']} doneminde dalgali bir seyir izlemistir.",
    }
    satirlar.append(trend_map[h["trend"]])

    # 2. Baslangic → bitis
    satirlar.append(
        f"{h['ilk_ay']} ayinda {_fmt(h['ilk'])} olan fatura, "
        f"{h['son_ay']} ayinda {_fmt(h['son'])} seviyesine ulasti."
    )

    # 3. Genel degisim
    yon = "artis" if h["genel_pct"] >= 0 else "dusus"
    satirlar.append(
        f"Donem genelinde toplam degisim %{abs(h['genel_pct'])} {yon} olarak gerceklesti."
    )

    # 4. En buyuk aylik artis
    if h["aylik"]:
        en_buyuk = max(h["aylik"], key=lambda x: x["pct"])
        en_kucuk = min(h["aylik"], key=lambda x: x["pct"])
        if en_buyuk["pct"] >= 5:
            satirlar.append(
                f"En dikkat cekici artis {en_buyuk['from']}-{en_buyuk['to']} "
                f"doneminde %{en_buyuk['pct']} oraninda gerceklesti."
            )
        if en_kucuk["pct"] <= -5:
            satirlar.append(
                f"En belirgin dusus {en_kucuk['from']}-{en_kucuk['to']} "
                f"doneminde %{abs(en_kucuk['pct'])} oraninda yasandi."
            )

    # 5. Tepe ve dip
    if h["maks_ay"] != h["son_ay"]:
        satirlar.append(
            f"Donemin en yuksek faturasi {h['maks_ay']} ayinda {_fmt(h['maks'])} olarak gerceklesti."
        )
    if h["mini_ay"] != h["ilk_ay"]:
        satirlar.append(
            f"En dusuk tutar {h['mini_ay']} ayinda {_fmt(h['mini'])} olarak kaydedildi."
        )

    # 6. Toplam ve ortalama
    satirlar.append(
        f"Incelenen {h['n']} aylik donemde {firma}'ya toplam {_fmt(h['toplam'])} "
        f"odeme yapildi; aylik ortalama {_fmt(h['ort'])} oldu."
    )

    # 7. Yorum
    if h["trend"] == "artan" and h["genel_pct"] >= 20:
        satirlar.append(
            "Bu artis orani dikkat gerektirmektedir. "
            "Fiyat artisi gerekceleri tedarikci firmadan talep edilmesi onerilir."
        )
    elif h["trend"] == "artan" and h["genel_pct"] >= 10:
        satirlar.append("Artis trendi yakindan takip edilmelidir.")
    elif h["trend"] == "dusen":
        satirlar.append("Dusus trendi olumlu; ancak surdurulebilirligi izlenmelidir.")
    elif h["trend"] == "stabil":
        satirlar.append("Stabil seyir butce planlamasi acisindan ongoru saglamaktadir.")

    return "\n".join(satirlar)


def full_summary_report(report: dict) -> str:
    """analysis.full_report() ciktisini okunabilir Turkce metne donusturur."""
    if "error" in report:
        return report["error"]

    satirlar = []
    satirlar.append("=" * 55)
    satirlar.append("GENEL OZET")
    satirlar.append("=" * 55)
    satirlar.append(f"Toplam fatura sayisi  : {report['toplam_fatura']}")
    satirlar.append(f"Toplam tutar          : {_fmt(report['toplam_tutar'])}")
    satirlar.append(f"Ortalama tutar        : {_fmt(report['ortalama_tutar'])}")
    satirlar.append(f"En buyuk fatura       : {_fmt(report['en_buyuk_fatura'])}")
    satirlar.append(f"Anomali tespiti       : {report['anomali_sayisi']} fatura")
    satirlar.append(f"Mukerrer tespiti      : {report['mukerrer_sayisi']} eslesme")
    satirlar.append(f"Firma sayisi          : {report['firma_sayisi']}")

    if report["firma_ozeti"]:
        satirlar.append("")
        satirlar.append("=" * 55)
        satirlar.append("FIRMA BAZLI HARCAMA")
        satirlar.append("=" * 55)
        for v in report["firma_ozeti"]:
            satirlar.append(
                f"  {v['vendor_name'][:35]:<35}  "
                f"{v['count']:>3} fatura  {_fmt(v['total']):>16}"
            )

    if report["aylik_ozet"]:
        satirlar.append("")
        satirlar.append("=" * 55)
        satirlar.append("AYLIK OZET")
        satirlar.append("=" * 55)
        for m in report["aylik_ozet"]:
            satirlar.append(
                f"  {m['period']:<12}  {m['count']:>3} fatura  {_fmt(m['total']):>16}"
            )

    if report["mukerrerler"]:
        satirlar.append("")
        satirlar.append("=" * 55)
        satirlar.append("MUKERRER FATURALAR")
        satirlar.append("=" * 55)
        for d in report["mukerrerler"]:
            satirlar.append(
                f"  ID {d['invoice_id_1']} <-> ID {d['invoice_id_2']}  |  "
                f"{d['vendor_name']}  |  {d['reason']}"
            )

    if report["anomali_faturalar"]:
        satirlar.append("")
        satirlar.append("=" * 55)
        satirlar.append("ANOMALI FATURALAR")
        satirlar.append("=" * 55)
        for a in report["anomali_faturalar"]:
            satirlar.append(f"  ID {a['id']}  {a['vendor']}  ->  {a['total']}")

    return "\n".join(satirlar)
