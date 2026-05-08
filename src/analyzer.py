"""
Hibrit analiz motoru:
- Yapisal analizler → report_generator (Python, deterministik)
- Serbest sorular   → Qwen2.5-7B-Instruct (sadece veritabani verisiyle)

Guardrail stratejisi: context kilidi.
Model kendi kafasindan bilgi uretemiyor — sadece ona verdigimiz
veritabani ozeti uzerinden konusabiliyor.
"""
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from src.report_generator import vendor_trend_report

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"

SYSTEM_PROMPT = """Sen bir fatura analiz asistanis. Gorevn yalnizca sana verilen fatura verileri uzerinden analiz yapmak.

Kurallarin:
1. Sadece sana verilen fatura verilerini kullan. Disaridan hicbir bilgi ekleme.
2. Verilen verilerle cevaplanamayan sorular icin: "Bu soruyu yanıtlamak için yeterli fatura verisi bulunmuyor." de.
3. Fatura ve finansla ilgisi olmayan sorulara: "Bu sistem yalnizca fatura analizi icin tasarlanmistir." de.
4. Hic sayi uydurma. Sadece sana verilen rakamlari kullan.
5. Kisa ve net cevap ver."""


class InvoiceAnalyzer:

    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model     = None
        self.tokenizer = None

    def load(self):
        """Modeli bellegea yukle (ilk kullanımda cagrilir)."""
        print(f"[InvoiceAnalyzer] {BASE_MODEL} yukleniyor...")

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        self.tokenizer = AutoTokenizer.from_pretrained(
            BASE_MODEL, trust_remote_code=True
        )
        self.tokenizer.pad_token = self.tokenizer.eos_token

        self.model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
        )
        self.model.eval()
        print("[InvoiceAnalyzer] Hazir.")

    def _generate(self, user_msg: str, context: str,
                  max_new_tokens: int = 300) -> str:
        """
        context: veritabanindan secilmis fatura ozeti.
        Model sadece bu ozet uzerinden konusabilir.
        """
        if self.model is None:
            self.load()

        # Bos context → yanit veremeyiz
        if not context.strip():
            return "Bu soruyu yanıtlamak için yeterli fatura verisi bulunmuyor."

        # Context kilidi: sistem promptu + veri + soru
        system = SYSTEM_PROMPT
        user   = f"Mevcut fatura verileri:\n{context}\n\nSoru: {user_msg}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer(
            text, return_tensors="pt", truncation=True, max_length=1024
        ).to(self.device)

        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                repetition_penalty=1.15,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        generated = output_ids[0][inputs["input_ids"].shape[1]:]
        return self.tokenizer.decode(generated, skip_special_tokens=True).strip()

    # ─── Context uretici ─────────────────────────────────────────────

    def _build_context(self, invoices: list[dict]) -> str:
        """
        Veritabanindan gelen faturalari ozet metin olarak hazirlar.
        Model bu metni gorur, ham SQL satırlarını değil.
        """
        if not invoices:
            return ""

        lines = []
        toplam = sum(float(inv["total"] or 0) for inv in invoices)
        lines.append(f"Toplam {len(invoices)} fatura, toplam tutar: {toplam:,.2f} TL")
        lines.append("")

        # Firma bazli ozet
        from collections import defaultdict
        firma_map = defaultdict(list)
        for inv in invoices:
            firma = inv.get("vendor_name") or "Bilinmeyen"
            firma_map[firma].append(inv)

        for firma, inv_list in sorted(firma_map.items()):
            firma_toplam = sum(float(i["total"] or 0) for i in inv_list)
            lines.append(f"Firma: {firma} — {len(inv_list)} fatura, toplam {firma_toplam:,.2f} TL")
            for inv in sorted(inv_list, key=lambda x: x.get("invoice_date") or ""):
                tarih   = inv.get("invoice_date") or "-"
                tutar   = float(inv.get("total") or 0)
                anomali = ""
                if inv.get("is_anomaly"):
                    skor = inv.get("anomaly_score")
                    skor_str = f", anomali skoru: {skor:.3f}" if skor else ""
                    anomali = f" [ANOMALİ{skor_str}]"
                    # Kural ihlallerini ekle
                    flags_raw = inv.get("rule_flags", "[]")
                    try:
                        import json as _json
                        flags = _json.loads(flags_raw) if isinstance(flags_raw, str) else flags_raw
                        for f in flags:
                            anomali += f"\n    Kural ihlali ({f.get('severity','?')}): {f.get('message','')}"
                    except Exception:
                        pass
                lines.append(f"  {tarih}: {tutar:,.2f} TL{anomali}")

        return "\n".join(lines)

    # ─── Public API ──────────────────────────────────────────────────

    def analyze_vendor_trend(
        self,
        vendor_name: str,
        kategori: str,
        ay_tutar_listesi: list[tuple[str, float]],
    ) -> str:
        """Deterministik Python raporu — hizli, hallucination yok."""
        return vendor_trend_report(vendor_name, kategori, ay_tutar_listesi)

    def analyze_from_db(self, invoices: list[dict]) -> str:
        """Veritabanindan gelen faturalar icin deterministik trend raporu."""
        if not invoices:
            return "Analiz icin yeterli fatura bulunamadi."

        vendor = invoices[0].get("vendor_name", "Bilinmeyen")
        sorted_inv = sorted(invoices, key=lambda x: x.get("invoice_date") or "")
        ay_tutar = [
            (inv.get("invoice_date") or "-", float(inv["total"]))
            for inv in sorted_inv if inv.get("total")
        ]
        if not ay_tutar:
            return "Faturalarda tutar bilgisi bulunamadi."
        return vendor_trend_report(vendor, "genel", ay_tutar)

    def free_question(self, soru: str, invoices: list[dict]) -> str:
        """
        Serbest soru — Qwen 7B kullanilir.
        Context veritabanindan otomatik olusturulur, model disari cikamaz.
        """
        context = self._build_context(invoices)
        return self._generate(soru, context)
