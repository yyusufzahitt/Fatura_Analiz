import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re, json, base64, shutil, tempfile, asyncio
from pathlib import Path
from typing import List
from collections import defaultdict

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from PIL import Image

from src.service_runner import extract_invoice, chat_answer
from src.anomaly import AnomalyDetector
from src.rules import run_rules
from src.database import save_invoice, get_all_invoices, delete_invoice, init_db
from src.xml_parser import parse_ubl_xml

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

detector = AnomalyDetector()
try:
    detector.load()
    ANOMALY_READY = True
except FileNotFoundError:
    ANOMALY_READY = False

init_db()

app = FastAPI(title="Yenibulut Akıllı Fatura", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Helpers ──────────────────────────────────────────────────────────────

def _pdf_to_images(filepath: str) -> list:
    import fitz
    doc = fitz.open(filepath)
    imgs = []
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        imgs.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
    doc.close()
    return imgs


def _score_and_save(inv, fname):
    anm = None
    if ANOMALY_READY and not inv.get("parse_error"):
        try:
            anm = detector.score(inv)
        except Exception:
            pass
    flags = run_rules(inv)
    inv_id = save_invoice(extracted=inv, filename=fname, anomaly_result=anm, rule_flags=flags)
    return anm, flags, inv_id


# Özellik etiketleri:  (Türkçe ad, birim, para mı?)
_FEAT_META = {
    "subtotal":   ("Ara toplam",   "₺", True),
    "tax_amount": ("KDV tutarı",   "₺", True),
    "total":      ("Toplam tutar", "₺", True),
    "tax_rate":   ("KDV oranı",    "%", False),
}


def _anomaly_reasons(inv: dict, score: float) -> list:
    """Isolation Forest'ın gerçek z-skoru verisiyle açıklama üret."""
    if not ANOMALY_READY:
        return [f"Anomali skoru: {score:.2f}/1.00 — model yüklü değil, özellik karşılaştırması yapılamadı"]

    explain_data = detector.explain(inv)
    if not explain_data:
        return [f"Anomali skoru: {score:.2f}/1.00 — karşılaştırma verisi yetersiz"]

    reasons = []
    for item in explain_data:
        z = item["z_score"]
        if abs(z) < 1.0:          # normal sınırda, es geç
            continue

        label, unit, is_money = _FEAT_META.get(item["feature"], (item["feature"], "", False))
        val, mean, std = item["value"], item["mean"], item["std"]

        if is_money:
            val_s  = f"₺{val:,.2f}"
            mean_s = f"₺{mean:,.2f}"
            std_s  = f"₺{std:,.2f}"
        else:
            val_s  = f"%{val:.2f}"
            mean_s = f"%{mean:.2f}"
            std_s  = f"%{std:.2f}"

        if abs(z) >= 4.0:
            seviye = "çok güçlü sapma"
        elif abs(z) >= 2.5:
            seviye = "belirgin sapma"
        else:
            seviye = "dikkat çekici sapma"

        reasons.append(
            f"{label} {val_s} — eğitim ortalaması {mean_s} "
            f"(±{std_s}), normalden {abs(z):.1f}σ {item['direction']} → {seviye}"
        )

    if not reasons:
        reasons.append(
            f"Bireysel özellikler normal görünse de birlikte "
            f"anormal bir dağılım oluşturuyor (skor: {score:.2f}/1.00)"
        )
    return reasons


def _serialize(inv, anm, flags, inv_id, filename):
    clean = {k: v for k, v in inv.items()
             if v is not None and not (isinstance(v, str) and v.startswith("_") and k != "_source")}
    is_anom = bool(anm.get("is_anomaly")) if anm else False
    score   = float(anm.get("normalized_score", 0)) if anm else 0.0
    return {
        "inv_id": inv_id,
        "filename": filename,
        "invoice": clean,
        "anomaly": {
            "is_anomaly": is_anom,
            "score": score,
            "reasons": _anomaly_reasons(inv, score) if is_anom else [],
        },
        "flags": [{"severity": f.severity or "info", "message": f.message} for f in flags],
    }


# ── Routes ───────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/api/analyze")
async def analyze(files: List[UploadFile] = File(...)):
    """SSE akışı: her dosya işlenince sonuç gönderilir."""

    async def generate():
        for f in files:
            fname = f.filename or "fatura"
            ext   = Path(fname).suffix.lower()
            data  = await f.read()
            tmp_path = None
            try:
                # mkstemp: Windows'ta NamedTemporaryFile handle çakışmasını önler
                fd, tmp_path = tempfile.mkstemp(suffix=ext)
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                # Dosya tamamen kapalı — PIL/fitz güvenle açabilir

                if ext == ".xml":
                    inv = await asyncio.to_thread(parse_ubl_xml, tmp_path)
                    anm, flags, inv_id = await asyncio.to_thread(_score_and_save, inv, fname)
                    yield f"data: {json.dumps(_serialize(inv, anm, flags, inv_id, fname), ensure_ascii=False)}\n\n"

                elif ext == ".pdf":
                    pages = await asyncio.to_thread(_pdf_to_images, tmp_path)
                    for i, img in enumerate(pages):
                        pname = f"{fname} — sayfa {i+1}" if len(pages) > 1 else fname
                        inv = await asyncio.to_thread(extract_invoice, img)
                        anm, flags, inv_id = await asyncio.to_thread(_score_and_save, inv, pname)
                        yield f"data: {json.dumps(_serialize(inv, anm, flags, inv_id, pname), ensure_ascii=False)}\n\n"

                else:
                    def _open_and_resize(p):
                        im = Image.open(p).convert("RGB")
                        # WhatsApp/DSLR görüntüleri 3-4K olabilir.
                        # Florence-2 için 1200px yeterli; büyük görüntü
                        # subprocess stdin pipe'ını doldurup [Errno 22] veriyor.
                        MAX_PX = 1200
                        w, h = im.size
                        if w > MAX_PX or h > MAX_PX:
                            ratio = min(MAX_PX / w, MAX_PX / h)
                            im = im.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
                        return im
                    img = await asyncio.to_thread(_open_and_resize, tmp_path)
                    inv = await asyncio.to_thread(extract_invoice, img)
                    anm, flags, inv_id = await asyncio.to_thread(_score_and_save, inv, fname)
                    yield f"data: {json.dumps(_serialize(inv, anm, flags, inv_id, fname), ensure_ascii=False)}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'error': str(e), 'filename': fname}, ensure_ascii=False)}\n\n"
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Chat ─────────────────────────────────────────────────────────────────

_OFFTOPIC = [
    r'\bhava\s*durumu\b', r'\bhava\s+nas[iı]l\b', r'\bfutbol\b',
    r'\b[sş]iir\b', r'\bf[iı]kra\b', r'\bşaka\b', r'\bhaberleri?\b', r'\bmüzik\b',
]
_HINTS = ['fatura', 'fiş', 'kdv', 'vergi', 'ödeme', 'tutar', 'firma',
          'toplam', 'iskonto', 'vade', 'tl', '₺', 'satıcı', 'alıcı']


def _is_offtopic(msg: str) -> bool:
    low = msg.lower()
    if any(h in low for h in _HINTS):
        return False
    return any(re.search(p, low) for p in _OFFTOPIC)


def _detect_last_n(msg: str):
    m = re.search(r'son\s+(\d+)', msg, re.IGNORECASE)
    if m:
        return int(m.group(1))
    if re.search(r'son\s+\S*\s*(fatura|yüklenen|eklenen|eklediğim)', msg, re.IGNORECASE):
        return 1
    return None


def _find_vendor(msg: str, invoices: list):
    vendors = {(i.get("vendor_name") or "").strip() for i in invoices if i.get("vendor_name")}
    for v in sorted(vendors, key=len, reverse=True):   # uzun eşleşme önce
        if v and v.lower() in msg.lower():
            return v
    return None


def _build_context(invoices: list) -> str:
    if not invoices:
        return ""
    toplam     = sum(float(i.get("total") or 0) for i in invoices)
    toplam_kdv = sum(float(i.get("tax_amount") or 0) for i in invoices)
    firma_map  = defaultdict(float)
    for inv in invoices:
        firma_map[inv.get("vendor_name") or "Bilinmeyen"] += float(inv.get("total") or 0)
    en_cok = max(firma_map, key=firma_map.get) if firma_map else "-"
    lines = [
        "GENEL OZET:",
        f"- Fatura sayisi: {len(invoices)}",
        f"- Toplam odeme: {toplam:,.2f} TL",
        f"- Toplam KDV: {toplam_kdv:,.2f} TL",
        f"- En cok odeme: {en_cok}",
        "", "FATURA DETAYLARI:",
    ]
    for i, inv in enumerate(invoices, 1):
        firma     = inv.get("vendor_name")     or "Bilinmeyen"
        tarih     = inv.get("invoice_date")    or "-"
        fatura_no = inv.get("invoice_number")  or ""
        tutar     = float(inv.get("total")     or 0)
        kdv_t     = inv.get("tax_amount")
        kdv_r     = inv.get("tax_rate")
        iskonto   = inv.get("discount_amount")
        alici     = inv.get("buyer_name")      or ""
        vade      = inv.get("due_date")        or ""
        status    = inv.get("status")          or "bekliyor"
        tip       = inv.get("invoice_type")    or ""
        is_anom   = inv.get("is_anomaly")

        lines.append(f"\n{i}. {firma} | {tarih} | {tutar:,.2f} TL{' [ANOMALI]' if is_anom else ''}")
        if fatura_no: lines.append(f"   Fatura No: {fatura_no} | Durum: {status}")
        if tip:       lines.append(f"   Tur: {tip}")
        if alici:     lines.append(f"   Alici: {alici}")
        if kdv_t:
            s = f"{float(kdv_t):,.2f} TL"
            if kdv_r: s += f" (%{kdv_r})"
            lines.append(f"   KDV: {s}")
        if iskonto:   lines.append(f"   Iskonto: {float(iskonto):,.2f} TL")
        if vade:      lines.append(f"   Vade: {vade}")

        # Anomali ise Isolation Forest'ın gerçek z-skoru açıklamasını ekle
        if is_anom and ANOMALY_READY:
            expl = detector.explain(inv)
            satirlar = [
                f"     • {_FEAT_META.get(x['feature'], (x['feature'],'',False))[0]}: "
                f"{'₺' if _FEAT_META.get(x['feature'],('','',True))[2] else '%'}"
                f"{x['value']:,.2f} (ort. "
                f"{'₺' if _FEAT_META.get(x['feature'],('','',True))[2] else '%'}"
                f"{x['mean']:,.2f}, {abs(x['z_score']):.1f}σ {x['direction']})"
                for x in expl if abs(x["z_score"]) >= 1.0
            ]
            if satirlar:
                lines.append("   Anomali nedenleri (istatistiksel z-skoru):")
                lines.extend(satirlar)

    return "\n".join(lines)


class ChatReq(BaseModel):
    message: str
    history: list = []


@app.post("/api/chat")
async def chat(req: ChatReq):
    if not req.message.strip():
        return {"reply": ""}
    if _is_offtopic(req.message):
        return {"reply": "Bu sistem yalnızca fatura analizi içindir."}
    invoices = await asyncio.to_thread(get_all_invoices)
    if not invoices:
        return {"reply": "Henüz hiç fatura yüklenmemiş. Önce fatura yükleyin."}

    # Extracted_at'e göre sırala (en eski → en yeni)
    sorted_invs = sorted(invoices, key=lambda x: x.get("extracted_at") or "")

    # Firma filtresi
    vendor = _find_vendor(req.message, sorted_invs)
    ctx = [i for i in sorted_invs
           if (i.get("vendor_name") or "").strip().lower() == vendor.lower()] if vendor else sorted_invs

    # "Son N fatura" filtresi
    last_n = _detect_last_n(req.message)
    if last_n:
        ctx = ctx[-last_n:]

    context = _build_context(ctx)
    try:
        reply = await asyncio.to_thread(chat_answer, req.message, context)
    except Exception as e:
        reply = f"Yanıt üretilemedi: {e}"
    return {"reply": reply}


# ── Invoices ─────────────────────────────────────────────────────────────

@app.get("/api/invoices")
async def get_invoices():
    rows = await asyncio.to_thread(get_all_invoices)
    return {
        "invoices": rows,
        "stats": {
            "count": len(rows),
            "total_amount": sum(float(r.get("total") or 0) for r in rows),
            "total_tax":    sum(float(r.get("tax_amount") or 0) for r in rows),
            "anomaly_count": sum(1 for r in rows if r.get("is_anomaly")),
        },
    }


@app.delete("/api/invoices/{inv_id}")
async def remove_invoice(inv_id: int):
    try:
        await asyncio.to_thread(delete_invoice, inv_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Document render ───────────────────────────────────────────────────────

@app.post("/api/render")
async def render_document(file: UploadFile = File(...)):
    fname    = file.filename or "doc"
    ext      = Path(fname).suffix.lower()
    content  = await file.read()
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=ext)
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)

        if ext == ".pdf":
            import fitz
            doc   = fitz.open(tmp_path)
            pages = []
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                pages.append(base64.b64encode(pix.tobytes("png")).decode())
            doc.close()
            return {"type": "pdf", "pages": pages}

        elif ext == ".xml":
            from lxml import etree
            _CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
            _CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
            xml_doc = etree.parse(tmp_path)
            root    = xml_doc.getroot()

            # 1. Gömülü PDF ara (GİB e-faturada yaygın)
            for ref in root.findall(f"{{{_CAC}}}AdditionalDocumentReference"):
                dt = ref.find(f"{{{_CBC}}}DocumentType")
                if dt is None or not any(k in (dt.text or "").upper()
                                         for k in ("PDF", "SIGNED", "INVOICE")):
                    continue
                attach = ref.find(f"{{{_CAC}}}Attachment")
                if attach is None: continue
                embed = attach.find(f"{{{_CBC}}}EmbeddedDocumentBinaryObject")
                if embed is None or not embed.text: continue
                try:
                    import fitz
                    pdf_bytes = base64.b64decode(embed.text.strip())
                    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    pages = []
                    for page in doc:
                        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                        pages.append(base64.b64encode(pix.tobytes("png")).decode())
                    doc.close()
                    return {"type": "pdf", "pages": pages}
                except Exception:
                    pass

            # 2. Gömülü XSLT ara
            for ref in root.findall(f"{{{_CAC}}}AdditionalDocumentReference"):
                attach = ref.find(f"{{{_CAC}}}Attachment")
                if attach is None: continue
                embed = attach.find(f"{{{_CBC}}}EmbeddedDocumentBinaryObject")
                if embed is None or not embed.text: continue
                if "xml" not in embed.get("mimeCode", "").lower(): continue
                try:
                    xslt_bytes = base64.b64decode(embed.text.strip())
                    if b"xsl:stylesheet" not in xslt_bytes[:500]: continue
                    xslt_root = etree.fromstring(xslt_bytes)
                    result    = etree.XSLT(xslt_root)(xml_doc)
                    html      = str(result)
                    if html.strip():
                        return {"type": "xml", "html": html}
                except Exception:
                    pass

            # 3. Kendi XSLT şablonumuza düş
            xslt_path = Path(__file__).parent.parent / "templates" / "invoice_view.xslt"
            result    = etree.XSLT(etree.parse(str(xslt_path)))(xml_doc)
            return {"type": "xml", "html": str(result)}

        else:
            raise HTTPException(status_code=400, detail="PDF veya XML yükleyin.")

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
