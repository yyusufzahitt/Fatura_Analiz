"""
Subprocess yöneticisi — Florence-2 için subprocess, chat için Groq API.
"""
import subprocess, json, sys, os, time, base64, io
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent

# Worker Python yorumlayıcıları
FLORENCE_PYTHON = ROOT / ".venv"         / "Scripts" / "python.exe"
QWEN_PYTHON     = ROOT / ".venv_qwen"    / "Scripts" / "python.exe"

# Fallback: aynı venv
if not QWEN_PYTHON.exists():
    QWEN_PYTHON = FLORENCE_PYTHON

FLORENCE_SCRIPT = ROOT / "services" / "florence_worker.py"
QWEN_SCRIPT     = ROOT / "services" / "qwen_worker.py"
LOCK_FILE       = ROOT / ".model_lock"

_proc = None   # aktif subprocess


def _acquire_lock(name: str):
    """Başka bir model çalışıyorsa bekle."""
    for _ in range(60):  # max 60 sn bekle
        if not LOCK_FILE.exists():
            LOCK_FILE.write_text(name)
            return True
        current = LOCK_FILE.read_text().strip()
        if current == name:
            return True
        time.sleep(1)
    return False


def _release_lock():
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _run_worker(python: Path, script: Path, request: dict,
                timeout_load: int = 120, timeout_infer: int = 60) -> dict:
    """Worker subprocess başlat, istek gönder, yanıt al, kapat."""
    global _proc

    proc = subprocess.Popen(
        [str(python), str(script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
    )
    _proc = proc

    try:
        # Model yüklenmesini bekle
        deadline = time.time() + timeout_load
        ready = False
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                # Subprocess erken kapandı — stderr'den gerçek hatayı al
                stderr_out = proc.stderr.read() or ""
                raise RuntimeError(
                    f"Florence subprocess baslatılamadı.\n{stderr_out.strip()}"
                )
            try:
                msg = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            if msg.get("status") == "ready":
                ready = True
                break
            if msg.get("status") == "loading":
                continue

        if not ready:
            stderr_out = proc.stderr.read() or ""
            raise TimeoutError(
                f"Model yükleme zaman aşımı ({timeout_load}s).\n{stderr_out.strip()[:400]}"
            )

        # İstek gönder
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()

        # Yanıt al
        deadline = time.time() + timeout_infer
        while time.time() < deadline:
            if proc.poll() is not None:
                # Subprocess cevap vermeden öldü
                stderr_out = proc.stderr.read() or ""
                raise RuntimeError(
                    f"Florence işlem sırasında çöktü.\n{stderr_out.strip()[:600]}"
                )
            line = proc.stdout.readline()
            if line:
                return json.loads(line.strip())
            time.sleep(0.1)
        raise TimeoutError("Model yanit zaman asimi")

    finally:
        try:
            proc.stdin.write(json.dumps({"action": "exit"}) + "\n")
            proc.stdin.flush()
        except Exception:
            pass
        proc.terminate()
        proc.wait(timeout=10)
        _proc = None
        _release_lock()


def extract_invoice(image: Image.Image) -> dict:
    """Florence-2 ile fatura alanlarını çıkar."""
    if not _acquire_lock("florence"):
        raise RuntimeError("Baska bir model calistirilıyor, lutfen bekleyin.")
    try:
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="JPEG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        result = _run_worker(
            FLORENCE_PYTHON, FLORENCE_SCRIPT,
            {"action": "extract", "image_b64": b64},
            timeout_load=120, timeout_infer=60,
        )
        if result.get("ok"):
            return result["result"]
        raise RuntimeError(result.get("error", "Florence hatasi"))
    finally:
        _release_lock()


def chat_answer(question: str, context: str) -> str:
    """Groq API ile chat sorusunu yanıtla."""
    import requests

    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY bulunamadı. .env dosyasını kontrol edin.")

    system_prompt = """Sen uzman bir mali müşavir ve fatura analiz asistanısın. Verilen fatura verilerini derinlemesine analiz ederek kapsamlı ve değerli içgörüler sun.

Yanıt kuralları:
- Her zaman Türkçe yanıtla.
- Detaylı ve kapsamlı ol — genel sorularda 5-10 madde veya paragraf kullan.
- Rakamları net ve biçimli göster (₺ işareti, binlik nokta ayracı).
- Anomali tespit edilmişse MUTLAKA nedenini ve riskini açıkla.
- İlgili olduğunda önerilerde bulun: ödeme planlaması, risk uyarısı, tasarruf fırsatı.
- Firma, tarih veya ürün bazlı karşılaştırma yap (en yüksek/düşük/ortalama).
- KDV yükü, iskonto oranı, vade analizi gibi mali göstergelere değin.
- Yalnızca verilen fatura verilerindeki bilgileri kullan, asla uydurma.
- Aradığın bilgi yoksa: "Bu bilgi yüklü faturalarda bulunamadı." de."""

    user_content = f"Fatura verileri:\n{context}\n\nSoru: {question}"

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
            "max_tokens": 900,
            "temperature": 0.3,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()
