import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import gradio as gr
from PIL import Image

from src.inference import InvoiceExtractor
from src.anomaly import AnomalyDetector
from src.rules import run_rules
from src.database import save_invoice, get_all_invoices, delete_invoice, init_db
from src.analysis import full_report, vendor_detail

# Qwen 7B analiz modeli — lazy load (ilk kullanımda yukler)
try:
    from src.analyzer import InvoiceAnalyzer
    analyzer = InvoiceAnalyzer()
    QWEN_READY = True
except Exception as e:
    analyzer = None
    QWEN_READY = False
    print(f"[warn] Qwen modeli yapilandirilamadi: {e}")

# ─── Modeller ────────────────────────────────────────────────────────
print("Donut modeli yukleniyor...")
extractor = InvoiceExtractor("models/best_model")

detector = AnomalyDetector()
try:
    detector.load()
    ANOMALY_READY = True
    print("Anomali modeli hazir.")
except FileNotFoundError:
    ANOMALY_READY = False
    print("[warn] Anomali modeli bulunamadi.")

init_db()


# ─── Tab 1: Fatura Yukle & Analiz ────────────────────────────────────

def analyze_and_save(image: Image.Image, filename: str) -> tuple[str, str, str, str]:
    if image is None:
        return "Goruntu yuklenmedi.", "", "", ""

    invoice = extractor.extract_from_pil(image)
    extracted_json = json.dumps(invoice, indent=2, ensure_ascii=False)

    # Anomali
    anomaly_result = None
    if ANOMALY_READY and not invoice.get("parse_error"):
        try:
            anomaly_result = detector.score(invoice)
            normalized  = anomaly_result["normalized_score"]
            is_anomaly  = anomaly_result["is_anomaly"]
            partial_note = " (kismi veri)" if invoice.get("_partial") else ""
            anomaly_text = (
                f"Anomaly Score : {normalized:.3f}{partial_note}\n"
                f"Decision      : {'ANOMALY DETECTED' if is_anomaly else 'NORMAL'}\n"
                f"Raw Score     : {anomaly_result['anomaly_score']:.4f}"
            )
        except Exception as e:
            anomaly_text = f"Skor hesaplanamadi: {e}"
    else:
        anomaly_text = "Parse hatasi — anomali skoru hesaplanamadi."

    # Kural motoru
    flags = run_rules(invoice)
    if not flags:
        rules_text = "OK - Tum kurallar gecti."
    else:
        lines = []
        for f in flags:
            icon = {"error": "[HATA]", "warning": "[UYARI]", "info": "[BILGI]"}.get(f.severity, "[-]")
            lines.append(f"{icon} {f.rule_id}: {f.message}")
        rules_text = "\n".join(lines)

    # Veritabani kayit
    fname = filename.strip() if filename.strip() else "yuklenen_fatura"
    inv_id = save_invoice(
        extracted=invoice,
        filename=fname,
        anomaly_result=anomaly_result,
        rule_flags=flags,
    )
    save_msg = f"Fatura kaydedildi (ID: {inv_id})"

    return extracted_json, anomaly_text, rules_text, save_msg


# ─── Tab 2: Fatura Gecmisi ───────────────────────────────────────────

def load_history() -> str:
    invoices = get_all_invoices()
    if not invoices:
        return "Henuz hic fatura yuklenmemis."

    lines = [f"{'ID':>4}  {'Firma':<30}  {'Tarih':<12}  {'Tutar':>10}  {'Anomali'}"]
    lines.append("-" * 75)
    for inv in invoices:
        vendor  = (inv.get("vendor_name") or "?")[:30]
        date_   = inv.get("invoice_date") or "-"
        total   = f"{inv['total']:.2f}" if inv.get("total") else "-"
        anomaly = "EVET" if inv.get("is_anomaly") else "hayir"
        lines.append(f"{inv['id']:>4}  {vendor:<30}  {date_:<12}  {total:>10}  {anomaly}")

    return "\n".join(lines)


def delete_by_id(inv_id_str: str) -> str:
    try:
        inv_id = int(inv_id_str.strip())
        delete_invoice(inv_id)
        return f"Fatura {inv_id} silindi."
    except Exception as e:
        return f"Hata: {e}"


# ─── Tab 3: Analiz ───────────────────────────────────────────────────

def run_full_analysis() -> str:
    report = full_report()
    if "error" in report:
        return report["error"]

    lines = []
    lines.append("=" * 55)
    lines.append("GENEL OZET")
    lines.append("=" * 55)
    lines.append(f"Toplam fatura sayisi  : {report['toplam_fatura']}")
    lines.append(f"Toplam tutar          : {report['toplam_tutar']:,.2f}")
    lines.append(f"Ortalama tutar        : {report['ortalama_tutar']:,.2f}")
    lines.append(f"En buyuk fatura       : {report['en_buyuk_fatura']:,.2f}")
    lines.append(f"Anomali tespiti       : {report['anomali_sayisi']} fatura")
    lines.append(f"Mukerrer tespiti      : {report['mukerrer_sayisi']} eslesme")
    lines.append(f"Firma sayisi          : {report['firma_sayisi']}")

    lines.append("")
    lines.append("=" * 55)
    lines.append("FIRMA BAZLI HARCAMA (buyukten kucuge)")
    lines.append("=" * 55)
    for v in report["firma_ozeti"]:
        lines.append(f"  {v['vendor_name'][:35]:<35}  {v['count']:>3} fatura  {v['total']:>12,.2f}")

    lines.append("")
    lines.append("=" * 55)
    lines.append("AYLIK OZET")
    lines.append("=" * 55)
    for m in report["aylik_ozet"]:
        lines.append(f"  {m['period']:<10}  {m['count']:>3} fatura  {m['total']:>12,.2f}")

    if report["mukerrerler"]:
        lines.append("")
        lines.append("=" * 55)
        lines.append("MUKERRER FATURALAR")
        lines.append("=" * 55)
        for d in report["mukerrerler"]:
            lines.append(
                f"  ID {d['invoice_id_1']} <-> ID {d['invoice_id_2']}  |  "
                f"{d['vendor_name']}  |  {d['total']}  |  {d['reason']}"
            )

    if report["anomali_faturalar"]:
        lines.append("")
        lines.append("=" * 55)
        lines.append("ANOMALI TESPIT EDILEN FATURALAR")
        lines.append("=" * 55)
        for a in report["anomali_faturalar"]:
            lines.append(f"  ID {a['id']}  {a['vendor']}  ->  {a['total']}")

    return "\n".join(lines)


def run_vendor_analysis(vendor_name: str) -> str:
    if not vendor_name.strip():
        return "Lutfen bir firma adi girin."
    invoices = get_all_invoices()
    detail = vendor_detail(invoices, vendor_name.strip())
    if detail["count"] == 0:
        return f"'{vendor_name}' adli firma bulunamadi."

    lines = []
    lines.append(f"Firma        : {detail['vendor_name']}")
    lines.append(f"Fatura sayisi: {detail['count']}")
    lines.append(f"Toplam tutar : {detail['total']:,.2f}")
    lines.append(f"Ortalama     : {detail['avg']:,.2f}")
    lines.append(f"En kucuk     : {detail['min']:,.2f}")
    lines.append(f"En buyuk     : {detail['max']:,.2f}")
    lines.append("")
    lines.append("Fatura detaylari:")
    lines.append("-" * 50)
    for inv in detail["invoices"]:
        total = f"{inv['total']:.2f}" if inv.get("total") else "-"
        lines.append(
            f"  ID {inv['id']:>4}  {inv.get('invoice_date', '-'):<12}  "
            f"{total:>10}  {'[ANOMALI]' if inv.get('is_anomaly') else ''}"
        )
    return "\n".join(lines)


# ─── Arayuz ──────────────────────────────────────────────────────────

with gr.Blocks(title="Invoice Auditor VQA") as demo:

    gr.Markdown("## Invoice Auditor VQA\nFatura analiz ve denetim sistemi")

    with gr.Tabs():

        # ── Sekme 1: Yukle ──────────────────────────────────────────
        with gr.Tab("Fatura Yukle"):
            gr.Markdown("Fatura gorselini yukleyin. Sistem alanlari cikarir, anomali ve kural denetimi yapar, veritabanina kaydeder.")
            with gr.Row():
                with gr.Column(scale=1):
                    img_input  = gr.Image(type="pil", label="Fatura (PNG / JPG)")
                    fname_input = gr.Textbox(label="Dosya adi (opsiyonel)", placeholder="ornek_fatura_ocak.jpg")
                    submit_btn = gr.Button("Analiz Et ve Kaydet", variant="primary")
                with gr.Column(scale=2):
                    json_out    = gr.Code(label="Cikarilan Alanlar", language="json", lines=12)
                    anomaly_out = gr.Textbox(label="Anomali Tespiti", lines=4)
                    rules_out   = gr.Textbox(label="Kural Denetim Raporu", lines=5)
                    save_out    = gr.Textbox(label="Kayit Durumu", lines=1)

            submit_btn.click(
                fn=analyze_and_save,
                inputs=[img_input, fname_input],
                outputs=[json_out, anomaly_out, rules_out, save_out],
            )

        # ── Sekme 2: Gecmis ─────────────────────────────────────────
        with gr.Tab("Fatura Gecmisi"):
            gr.Markdown("Yuklenmis tum faturalarin listesi.")
            refresh_btn = gr.Button("Listeyi Yenile", variant="secondary")
            history_out = gr.Textbox(label="Fatura Listesi", lines=20, max_lines=40)
            with gr.Row():
                del_input = gr.Textbox(label="Silinecek Fatura ID", placeholder="5")
                del_btn   = gr.Button("Sil", variant="stop")
                del_out   = gr.Textbox(label="Silme Sonucu", lines=1)

            refresh_btn.click(fn=load_history, outputs=history_out)
            del_btn.click(fn=delete_by_id, inputs=del_input, outputs=del_out)

        # ── Sekme 3: Analiz ─────────────────────────────────────────
        with gr.Tab("Coklu Fatura Analizi"):
            gr.Markdown("Tum faturalar uzerinde firma, donem ve mukerrer analizi.")

            analysis_btn = gr.Button("Tam Rapor Olustur", variant="primary")
            analysis_out = gr.Textbox(label="Analiz Raporu", lines=30, max_lines=60)

            gr.Markdown("---")
            gr.Markdown("**Firma Bazli Detay**")
            with gr.Row():
                vendor_input = gr.Textbox(label="Firma Adi", placeholder="ABC Ltd.")
                vendor_btn   = gr.Button("Firma Analizi")
            vendor_out = gr.Textbox(label="Firma Detayi", lines=15)

            analysis_btn.click(fn=run_full_analysis, outputs=analysis_out)
            vendor_btn.click(fn=run_vendor_analysis, inputs=vendor_input, outputs=vendor_out)


        # ── Sekme 4: YZ Analiz (Qwen) ───────────────────────────────────
        with gr.Tab("YZ Analiz (Qwen)"):
            if not QWEN_READY:
                gr.Markdown("""
                > **Qwen modeli henuz hazir degil.**
                > Donut egitimi bittikten sonra asagidaki komutu calistirin:
                > ```
                > python -m src.train_qwen
                > ```
                > Egitim tamamlaninca bu sekme aktif olacak.
                """)
            else:
                gr.Markdown("""
                Firma adini girin — Qwen veritabanindaki faturalari analiz edip
                Turkce rapor uretir. Ya da serbest soru sorabilirsiniz.
                """)

                with gr.Tab("Firma Trend Analizi"):
                    qwen_vendor_input = gr.Textbox(
                        label="Firma Adi",
                        placeholder="AYEDAS A.S."
                    )
                    qwen_vendor_btn = gr.Button("Yapay Zeka ile Analiz Et", variant="primary")
                    qwen_vendor_out = gr.Textbox(label="YZ Analiz Raporu", lines=15)

                with gr.Tab("Serbest Soru"):
                    gr.Markdown("Soru sorabilirsiniz. Model sadece veritabanındaki fatura verileriyle yanıt verir.")
                    qwen_context = gr.Textbox(
                        label="Firma filtresi (opsiyonel — bos birakinca tum faturalar kullanilir)",
                        placeholder="AYEDAS",
                    )
                    qwen_soru = gr.Textbox(
                        label="Sorunuz",
                        placeholder="Bu ay toplam giderim ne kadar?"
                    )
                    qwen_soru_btn = gr.Button("Sor", variant="primary")
                    qwen_soru_out = gr.Textbox(label="YZ Yaniti", lines=10)

                def qwen_vendor_analiz(vendor_name: str) -> str:
                    if not vendor_name.strip():
                        return "Lutfen firma adi girin."
                    invoices = get_all_invoices()
                    filtered = [
                        inv for inv in invoices
                        if (inv.get("vendor_name") or "").strip().lower()
                        == vendor_name.strip().lower()
                    ]
                    if not filtered:
                        return f"'{vendor_name}' icin kayitli fatura bulunamadi."
                    return analyzer.analyze_from_db(filtered)

                def qwen_soru_yanit(firma_filtre: str, soru: str) -> str:
                    if not soru.strip():
                        return "Lutfen bir soru girin."
                    invoices = get_all_invoices()
                    # Firma filtresi varsa sadece o firmanin faturalari
                    if firma_filtre.strip():
                        invoices = [
                            inv for inv in invoices
                            if firma_filtre.strip().lower() in
                            (inv.get("vendor_name") or "").lower()
                        ]
                    return analyzer.free_question(soru, invoices)

                qwen_vendor_btn.click(
                    fn=qwen_vendor_analiz,
                    inputs=qwen_vendor_input,
                    outputs=qwen_vendor_out,
                )
                qwen_soru_btn.click(
                    fn=qwen_soru_yanit,
                    inputs=[qwen_context, qwen_soru],
                    outputs=qwen_soru_out,
                )


if __name__ == "__main__":
    demo.launch(server_port=7860, share=False, show_error=True)
