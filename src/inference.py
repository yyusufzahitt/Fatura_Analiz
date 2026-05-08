import json
import re
import torch
from pathlib import Path
from PIL import Image
from transformers import DonutProcessor, VisionEncoderDecoderModel

try:
    from pdf2image import convert_from_path
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False


class InvoiceExtractor:
    """Fine-tune edilmiş Donut modeliyle fatura alanı çıkarıcı."""

    def __init__(self, model_dir: str = "models/best_model"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[InvoiceExtractor] Device: {self.device}")

        self.processor = DonutProcessor.from_pretrained(model_dir)
        self.model = VisionEncoderDecoderModel.from_pretrained(model_dir)
        self.model.to(self.device)
        self.model.eval()
        # transformers 5.x: max_length generation_config'te
        self.max_length = getattr(
            self.model.generation_config, "max_length", 512
        )

    def load_image(self, path: str) -> Image.Image:
        """PNG/JPG veya PDF'i PIL Image olarak yükler."""
        path = Path(path)
        if path.suffix.lower() == ".pdf":
            if not PDF_SUPPORT:
                raise RuntimeError("pdf2image kurulu değil. 'pip install pdf2image' çalıştır.")
            pages = convert_from_path(path, dpi=200)
            return pages[0]
        return Image.open(path).convert("RGB")

    def extract(self, image_path: str) -> dict:
        """Fatura görüntüsünden alan dict'i döndürür."""
        image = self.load_image(image_path)
        pixel_values = self.processor(
            image, return_tensors="pt"
        ).pixel_values.to(self.device)
        return self._run_generate(pixel_values)

    def extract_from_pil(self, image: Image.Image) -> dict:
        """PIL Image nesnesinden doğrudan çıkarım yapar (Gradio için)."""
        pixel_values = self.processor(
            image.convert("RGB"), return_tensors="pt"
        ).pixel_values.to(self.device)
        return self._run_generate(pixel_values)

    def _run_generate(self, pixel_values) -> dict:
        task_prompt = "<s_cord-v2>"
        decoder_input_ids = self.processor.tokenizer(
            task_prompt, add_special_tokens=False, return_tensors="pt"
        ).input_ids.to(self.device)

        with torch.no_grad():
            outputs = self.model.generate(
                pixel_values,
                decoder_input_ids=decoder_input_ids,
                max_length=self.max_length,
                pad_token_id=self.processor.tokenizer.pad_token_id,
                eos_token_id=self.processor.tokenizer.eos_token_id,
                use_cache=True,
                num_beams=1,
                bad_words_ids=[[self.processor.tokenizer.unk_token_id]],
                return_dict_in_generate=True,
                repetition_penalty=1.5,      # tekrar döngüsünü önle
                no_repeat_ngram_size=4,      # 4-gram tekrarını engelle
            )

        sequence = self.processor.batch_decode(outputs.sequences)[0]
        sequence = sequence.replace(
            self.processor.tokenizer.eos_token, ""
        ).replace(
            self.processor.tokenizer.pad_token, ""
        )
        sequence = re.sub(r"<.*?>", "", sequence, count=1).strip()

        # Tam JSON parse dene
        try:
            return json.loads(sequence)
        except json.JSONDecodeError:
            pass

        # Kısmi kurtarma: tekrar döngüsü başlamadan önceki geçerli kısmı al
        return self._partial_parse(sequence)

    def _partial_parse(self, raw: str) -> dict:
        """Bozuk JSON'dan key-value çiftlerini ve serbest desenleri kurtarır."""
        result = {}

        # 1. Standart JSON key-value çiftleri
        fields = [
            "vendor_name", "invoice_date", "invoice_number",
            "subtotal", "tax_amount", "total", "address",
        ]
        for field in fields:
            m = re.search(rf'"{field}"\s*:\s*"([^"{{}}\\]*)"', raw)
            if m:
                result[field] = m.group(1).strip()

        # 2. Tarih deseni (örn. 08 Feb-2015, 2019-01-15, 25/12/2018)
        if "invoice_date" not in result:
            m = re.search(
                r'\b(\d{1,2}[-/\s]\w{3,9}[-/\s]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b',
                raw
            )
            if m:
                result["invoice_date"] = m.group(1)

        # 3. Para miktarı — en büyük sayısal değeri total say
        if "total" not in result:
            amounts = re.findall(r'\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?\b', raw)
            if amounts:
                def to_float(s):
                    try:
                        return float(s.replace(",", "").replace(".", "").replace(",", "."))
                    except Exception:
                        return 0.0
                result["total"] = max(amounts, key=to_float)

        # 4. Tırnak içindeki uzun string'i vendor_name say
        if "vendor_name" not in result:
            candidates = re.findall(r'"([A-Z][A-Z0-9 &.,\-]{8,60})"', raw)
            if candidates:
                result["vendor_name"] = candidates[0]

        if result:
            result["_partial"] = True
        else:
            result = {"raw_output": raw[:300], "parse_error": True}

        return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Kullanım: python -m src.inference <görüntü_yolu>")
        sys.exit(1)

    extractor = InvoiceExtractor()
    result = extractor.extract(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
