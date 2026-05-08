import pathlib, re

p = pathlib.Path(r"c:\Users\yusuf\fatura_analiz\invoice-auditor\.venv\Lib\site-packages\trl\chat_template_utils.py")
content = p.read_text(encoding="utf-8")

# Tum .read_text() cagrilarini .read_text(encoding="utf-8") yap
fixed = re.sub(r'\.read_text\(\)', '.read_text(encoding="utf-8")', content)

if fixed != content:
    p.write_text(fixed, encoding="utf-8")
    count = len(re.findall(r'\.read_text\(\)', content))
    print(f"Duzeltildi: {count} satir guncellendi.")
else:
    print("Degistirilecek satir bulunamadi.")
