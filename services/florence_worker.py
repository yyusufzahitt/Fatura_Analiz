"""
Florence-2 worker — stdin'den JSON alır, stdout'a JSON yazar, çıkar.
Calistir: .venv\Scripts\python services\florence_worker.py
"""
import sys, json, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout = open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)

import torch
from PIL import Image
import base64, io

# Florence'ın "bulamadım" anlamına gelen cevapları
_EMPTY = {
    "", "none", "n/a", "not available", "not found", "not specified",
    "not visible", "unknown", "no", "na", "-", "–", "—", "null",
}


def load_model():
    import glob
    from transformers import AutoProcessor, AutoModelForCausalLM

    # Öncelik: fine-tuned → yerel base → HuggingFace (online)
    def has_weights(path):
        return os.path.isdir(path) and bool(
            glob.glob(os.path.join(path, "*.safetensors")) or
            glob.glob(os.path.join(path, "*.bin"))
        )

    FINETUNED  = "models/florence2_finetuned"
    BEST_MODEL = "models/best_model"        # fine-tuned ağırlıklar burada
    LOCAL_BASE = "models/florence2_base"
    REMOTE_ID  = "microsoft/Florence-2-base-ft"

    if has_weights(FINETUNED):
        model_source = FINETUNED
    elif has_weights(BEST_MODEL):
        model_source = BEST_MODEL
    elif has_weights(LOCAL_BASE):
        model_source = LOCAL_BASE
    else:
        model_source = REMOTE_ID

    # Processor: tokenizer best_model'da eksik olabilir, base'den al
    proc_source = LOCAL_BASE if has_weights(LOCAL_BASE) else REMOTE_ID

    processor = AutoProcessor.from_pretrained(proc_source, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_source,
        trust_remote_code=True,
        attn_implementation="eager",
        torch_dtype=torch.bfloat16,
    ).to("cuda" if torch.cuda.is_available() else "cpu")
    model.eval()
    return model, processor


def ask(model, processor, image, question: str, max_tokens: int = 48) -> str:
    device = next(model.parameters()).device
    prompt = f"<DocVQA>{question}"
    inputs = processor(text=prompt, images=image, return_tensors="pt")
    inputs = {
        k: v.to(device, dtype=torch.bfloat16) if v.dtype == torch.float32
        else v.to(device)
        for k, v in inputs.items()
    }
    with torch.no_grad():
        out = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=max_tokens,
            num_beams=3,
        )
    raw = processor.batch_decode(out, skip_special_tokens=True)[0].strip()
    return "" if raw.lower() in _EMPTY else raw


def extract(model, processor, image_b64: str) -> dict:
    img_bytes = base64.b64decode(image_b64)
    image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

    # (soru, max_new_tokens)
    # Kısa cevaplar: 32 token — tarih, tutar, numara, oran
    # Orta cevaplar: 64 token — isim, yöntem, tip
    # Uzun cevaplar: 96 token — adres, notlar
    questions = {
        # ── Mevcut alanlar ────────────────────────────────────────────────
        "vendor_name":     ("What is the vendor or company name?",                    64),
        "invoice_date":    ("What is the invoice or receipt date?",                   32),
        "invoice_number":  ("What is the invoice number or ID?",                      32),
        "subtotal":        ("What is the subtotal amount before tax?",                32),
        "tax_amount":      ("What is the total tax amount?",                          32),
        "total":           ("What is the total amount payable?",                      32),
        # ── Yeni alanlar ─────────────────────────────────────────────────
        "due_date":        ("What is the due date or payment deadline?",              32),
        "buyer_name":      ("What is the buyer or customer name?",                    64),
        "vendor_vkn":      ("What is the tax identification number or tax ID?",       32),
        "tax_rate":        ("What is the tax rate or VAT percentage?",                32),
        "discount_amount": ("What is the discount or allowance amount?",              32),
        "payment_method":  ("What is the payment method?",                            48),
        "reference_number":("What is the order number or reference number?",          32),
        "invoice_type":    ("What type of document is this?",                         48),
        "vendor_address":  ("What is the vendor or supplier address?",                96),
    }

    result = {}
    for field, (question, max_tok) in questions.items():
        result[field] = ask(model, processor, image, question, max_tok)

    # ── Post-processing: açıkça yanlış değerleri temizle ─────────────────
    def _to_num(v):
        try:
            return float(str(v).replace(",", ".").replace("₺","").replace("%","").strip())
        except Exception:
            return None

    total_val = _to_num(result.get("total"))

    # KDV oranı: 0-50 arası olmalı, para birimi gibi görünüyorsa sil
    tr = _to_num(result.get("tax_rate"))
    if tr is not None and (tr > 50 or tr < 0):
        result["tax_rate"] = ""

    # Sayısal olması gerekmeyen alanlarda tutar varsa sil
    for field in ("payment_method", "invoice_type", "vendor_address", "buyer_name"):
        v = result.get(field, "")
        if v and _to_num(v) is not None:
            result[field] = ""

    # Fatura no tamamen sayısal ve toplam tutarla aynıysa muhtemelen yanlış
    inv_no = result.get("invoice_number", "")
    if inv_no and total_val and _to_num(inv_no) == total_val:
        result["invoice_number"] = ""

    # VKN 10-11 hane olmalı, daha kısa/uzunsa sil
    vkn = str(result.get("vendor_vkn", "")).strip()
    if vkn and (len(vkn) < 10 or len(vkn) > 11 or not vkn.isdigit()):
        result["vendor_vkn"] = ""

    # Tarih alanlarında sayı varsa (örn. 240.00) sil
    for field in ("invoice_date", "due_date"):
        v = result.get(field, "")
        if v and _to_num(v) is not None and "." not in str(v).replace(",","")[:5]:
            result[field] = ""

    # Alıcı = satıcı ise büyük ihtimalle model yanılmış (adisyon)
    if result.get("buyer_name") and result.get("buyer_name") == result.get("vendor_name"):
        result["buyer_name"] = ""

    # KDV oranını hesapla — Florence bulamazsa subtotal'dan türet
    if not result.get("tax_rate"):
        try:
            sub = float(str(result.get("subtotal", "")).replace(",", ".").strip())
            tax = float(str(result.get("tax_amount", "")).replace(",", ".").strip())
            if sub > 0:
                result["tax_rate"] = f"{round(tax / sub * 100, 1)}"
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    result["_source"] = "image"
    return result


if __name__ == "__main__":
    print(json.dumps({"status": "loading"}), flush=True)
    model, processor = load_model()
    print(json.dumps({"status": "ready"}), flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if req.get("action") == "extract":
                result = extract(model, processor, req["image_b64"])
                print(json.dumps({"ok": True, "result": result}), flush=True)
            elif req.get("action") == "exit":
                break
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}), flush=True)
