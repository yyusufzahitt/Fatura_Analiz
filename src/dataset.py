import json
import re
from pathlib import Path
from PIL import Image
from torch.utils.data import Dataset
from transformers import DonutProcessor


# ─── FATURA NER tag eşleşmesi ────────────────────────────────────────
# tag=1  → TOTAL (tutar + para birimi)
# tag=2  → Yazıyla toplam (kullanılmıyor)
# tag=3  → Invoice Date (label + tarih değeri)
# tag=4  → Due Date (kullanılmıyor)
# tag=5  → Buyer bilgisi
# tag=6  → Vendor/Seller adı
# tag=10 → table (yapısal, yoksayılır)
# tag=11 → logo (yapısal, yoksayılır)
# tag=12 → Invoice Number (label + numara değeri)
# tag=13 → Diğer (koşullar, banka, vb.)

_FATURA_TAG_TOTAL          = 1
_FATURA_TAG_DATE           = 3
_FATURA_TAG_BUYER          = 5
_FATURA_TAG_VENDOR         = 6
_FATURA_TAG_INVOICE_NUMBER = 12

# Bu kelimeler tag grubunun içindeki etiket (label) kelimeleridir, değer değil
_LABEL_WORDS = {
    "Invoice", "Date", "Due", "INVOICE", "#", "number", "Number", "TOTAL",
    "Total", "in", "words", "Buyer", "Seller", "Vendor",
}

_DATE_PATTERN = re.compile(
    r"\d{2}[-/]\w{3}[-/]\d{4}|"   # 23-Jan-2002
    r"\d{4}[-/]\d{2}[-/]\d{2}|"   # 2002-01-23
    r"\d{2}[-/]\d{2}[-/]\d{4}"    # 23/01/2002
)

_NUMBER_PATTERN = re.compile(r"^[\d,.\-]+$")


def _extract_by_tag(tokens: list, tags: list, target_tag: int) -> list[str]:
    """Belirtilen tag'e sahip token'ları döndürür."""
    return [t for t, g in zip(tokens, tags) if g == target_tag]


def _find_date(tokens: list) -> str:
    """Token listesi içinden tarih formatına uyan ilk değeri döndürür."""
    for t in tokens:
        if _DATE_PATTERN.match(t):
            return t
    return ""


def _find_amount(tokens: list) -> str:
    """Token listesi içinden ilk sayısal değeri döndürür."""
    for t in tokens:
        if t not in _LABEL_WORDS and _NUMBER_PATTERN.match(t):
            return t
    return ""


def _find_invoice_number(tokens: list) -> str:
    """Invoice Number tag'indeki label kelimelerini atlayıp gerçek numarayı döndürür."""
    for t in tokens:
        if t not in _LABEL_WORDS and len(t) > 2:
            return t
    return ""


def _extract_vendor_name(tokens: list) -> str:
    """tag=6 token'larını birleştirerek vendor adını oluşturur."""
    parts = [t for t in tokens if t not in _LABEL_WORDS]
    return " ".join(parts)


def cord_to_donut_json(sample: dict) -> str:
    """CORD v2 örneğini Donut hedef JSON string'ine çevirir."""
    gt = sample.get("ground_truth", {})
    parsed = json.loads(gt) if isinstance(gt, str) else gt
    gp = parsed.get("gt_parse", parsed)

    # sub_total her örnekte farklı anahtarlar içerebilir
    sub_total = gp.get("sub_total", {})
    if isinstance(sub_total, dict):
        subtotal_price = sub_total.get("subtotal_price", "")
        tax_price = sub_total.get("tax_price", "")
    else:
        subtotal_price = str(sub_total) if sub_total else ""
        tax_price = ""

    # total da dict
    total = gp.get("total", {})
    if isinstance(total, dict):
        total_price = total.get("total_price", "")
    else:
        total_price = str(total) if total else ""

    # vendor_name CORD'da yok; meta'da sadece restoran fişi bilgisi var
    # menu listesindeki ilk nm alanını kullanabiliriz
    menu = gp.get("menu", [])
    vendor_name = ""
    if menu and isinstance(menu, list) and isinstance(menu[0], dict):
        # CORD makbuzlarında restoran adı meta'da geçmiyor; boş bırakıyoruz
        pass

    result = {
        "vendor_name": vendor_name,
        "invoice_date": "",           # CORD'da tarih alanı yok
        "subtotal": subtotal_price,
        "tax_amount": tax_price,
        "total": total_price,
    }
    return json.dumps(result, ensure_ascii=False)


def sroie_to_donut_json(ann_path: Path) -> str:
    """SROIE annotation JSON dosyasını Donut hedef JSON string'ine çevirir.

    Beklenen yol: data/raw/sroie/data/key/<id>.json
    Beklenen format: {"company", "date", "address", "total"}
    """
    with open(ann_path, encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    result = {
        "vendor_name": data.get("company", ""),
        "invoice_date": data.get("date", ""),
        "address": data.get("address", ""),
        "total": data.get("total", ""),
    }
    return json.dumps(result, ensure_ascii=False)


def fatura_to_donut_json(sample: dict) -> str:
    """FATURA NER veri setini Donut hedef JSON string'ine çevirir.

    Veri seti token-level NER etiketleri içerir (annotations alanı yoktur).
    Her token'ın NER tag'i bize alanın ne olduğunu söyler.
    """
    tokens = sample.get("tokens", [])
    tags   = sample.get("ner_tags", [])

    total_tokens   = _extract_by_tag(tokens, tags, _FATURA_TAG_TOTAL)
    date_tokens    = _extract_by_tag(tokens, tags, _FATURA_TAG_DATE)
    vendor_tokens  = _extract_by_tag(tokens, tags, _FATURA_TAG_VENDOR)
    inv_num_tokens = _extract_by_tag(tokens, tags, _FATURA_TAG_INVOICE_NUMBER)

    result = {
        "vendor_name":     _extract_vendor_name(vendor_tokens),
        "invoice_date":    _find_date(date_tokens),
        "invoice_number":  _find_invoice_number(inv_num_tokens),
        "total":           _find_amount(total_tokens),
    }
    return json.dumps(result, ensure_ascii=False)


import torch as _torch


def donut_collate_fn(batch: list[dict]) -> dict:
    """Donut için özel collator — pixel_values + labels tensor'larını birleştirir."""
    pixel_values = _torch.stack([b["pixel_values"] for b in batch])
    labels       = _torch.stack([b["labels"]       for b in batch])
    return {"pixel_values": pixel_values, "labels": labels}


class InvoiceDataset(Dataset):
    """Donut fine-tuning için birleşik dataset sınıfı."""

    def __init__(
        self,
        samples: list,          # [{"image": PIL.Image, "target": str}]
        processor: DonutProcessor,
        max_length: int = 512,
        image_size: tuple = (960, 1280),
    ):
        self.samples = samples
        self.processor = processor
        self.max_length = max_length
        self.image_size = image_size

        self.processor.image_processor.size = {
            "height": image_size[0],
            "width": image_size[1],
        }

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict:
        sample = self.samples[idx]
        image: Image.Image = sample["image"].convert("RGB")
        target: str = sample["target"]

        pixel_values = self.processor(
            image, return_tensors="pt"
        ).pixel_values.squeeze()

        target_seq = self.processor.tokenizer(
            target,
            add_special_tokens=False,
            max_length=self.max_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        ).input_ids.squeeze()

        # Padding token'larını -100 yap — loss hesabında ignore edilir
        labels = target_seq.clone()
        labels[labels == self.processor.tokenizer.pad_token_id] = -100

        return {
            "pixel_values": pixel_values,
            "labels": labels,
            "target_sequence": target,
        }
