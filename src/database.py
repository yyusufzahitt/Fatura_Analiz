import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path("data/invoices.db")


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Tabloları oluştur, mevcut DB'yi migrate et."""
    conn = get_conn()
    conn.executescript("""
        -- ── Ana fatura tablosu ──────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS invoices (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,

            -- Kimlik & belge
            filename         TEXT,
            source_type      TEXT DEFAULT 'image',   -- image / pdf / xml
            invoice_number   TEXT,
            invoice_date     TEXT,
            due_date         TEXT,
            reference_number TEXT,
            invoice_type     TEXT,                   -- e-Fatura / e-Arşiv / normal
            currency         TEXT DEFAULT 'TRY',

            -- Satıcı
            vendor_name      TEXT,
            vendor_vkn       TEXT,
            vendor_address   TEXT,

            -- Alıcı
            buyer_name       TEXT,
            buyer_vkn        TEXT,
            buyer_address    TEXT,

            -- Tutarlar
            subtotal         REAL,
            discount_amount  REAL,
            tax_amount       REAL,
            tax_rate         REAL,
            total            REAL,

            -- Ödeme
            payment_method   TEXT,

            -- İş akışı (kullanıcı yönetir)
            status           TEXT DEFAULT 'bekliyor',  -- bekliyor / ödendi / iptal
            category         TEXT,
            notes            TEXT,

            -- Sistem
            raw_json         TEXT,
            anomaly_score    REAL,
            is_anomaly       INTEGER DEFAULT 0,
            rule_flags       TEXT,
            extracted_at     TEXT DEFAULT (datetime('now'))
        );

        -- ── Kalem satırları ─────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS line_items (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id    INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
            description   TEXT,
            qty           REAL,
            unit          TEXT,
            unit_price    REAL,
            discount_rate REAL,
            tax_rate      REAL,
            tax_amount    REAL,
            amount        REAL,
            product_code  TEXT
        );

        -- ── Çoklu KDV oranı tablosu (%1, %8, %18, %20 ayrı ayrı) ──────
        CREATE TABLE IF NOT EXISTS invoice_taxes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
            tax_rate   REAL,
            tax_base   REAL,
            tax_amount REAL
        );
    """)
    conn.commit()
    _migrate(conn)
    conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Eski DB'ye yeni sütunlar ekle — varsa sessizce geç."""
    new_cols = [
        # invoices
        ("invoices", "source_type",      "TEXT DEFAULT 'image'"),
        ("invoices", "due_date",         "TEXT"),
        ("invoices", "reference_number", "TEXT"),
        ("invoices", "invoice_type",     "TEXT"),
        ("invoices", "vendor_vkn",       "TEXT"),
        ("invoices", "vendor_address",   "TEXT"),
        ("invoices", "buyer_name",       "TEXT"),
        ("invoices", "buyer_vkn",        "TEXT"),
        ("invoices", "buyer_address",    "TEXT"),
        ("invoices", "discount_amount",  "REAL"),
        ("invoices", "tax_rate",         "REAL"),
        ("invoices", "payment_method",   "TEXT"),
        ("invoices", "status",           "TEXT DEFAULT 'bekliyor'"),
        ("invoices", "category",         "TEXT"),
        ("invoices", "notes",            "TEXT"),
        # line_items
        ("line_items", "unit",           "TEXT"),
        ("line_items", "discount_rate",  "REAL"),
        ("line_items", "tax_rate",       "REAL"),
        ("line_items", "tax_amount",     "REAL"),
        ("line_items", "product_code",   "TEXT"),
    ]
    for table, col, dtype in new_cols:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError:
            pass  # sütun zaten var
    conn.commit()


# ─── Yardımcı ─────────────────────────────────────────────────────────────────

def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(str(val).replace(",", ".").replace("₺", "")
                              .replace("TL", "").replace("$", "")
                              .replace("%", "").strip())
    except Exception:
        return None


# ─── Kaydetme ─────────────────────────────────────────────────────────────────

def save_invoice(
    extracted: dict,
    filename:  str = "",
    anomaly_result: Optional[dict] = None,
    rule_flags:     Optional[list] = None,
) -> int:
    """Faturayı ve ilişkili tüm kayıtları veritabanına yazar."""
    init_db()
    conn = get_conn()

    flags_json = json.dumps(
        [{"rule_id": f.rule_id, "severity": f.severity, "message": f.message}
         for f in (rule_flags or [])],
        ensure_ascii=False,
    )

    # KDV oranını hesapla (yoksa)
    tax_rate = _safe_float(extracted.get("tax_rate"))
    if tax_rate is None:
        sub = _safe_float(extracted.get("subtotal"))
        tax = _safe_float(extracted.get("tax_amount"))
        if sub and tax and sub > 0:
            tax_rate = round(tax / sub * 100, 2)

    cursor = conn.execute(
        """
        INSERT INTO invoices (
            filename, source_type,
            invoice_number, invoice_date, due_date, reference_number, invoice_type, currency,
            vendor_name, vendor_vkn, vendor_address,
            buyer_name,  buyer_vkn,  buyer_address,
            subtotal, discount_amount, tax_amount, tax_rate, total,
            payment_method,
            status, category, notes,
            raw_json, anomaly_score, is_anomaly, rule_flags
        ) VALUES (
            ?,?,  ?,?,?,?,?,?,  ?,?,?,  ?,?,?,  ?,?,?,?,?,  ?,  ?,?,?,  ?,?,?,?
        )
        """,
        (
            filename,
            extracted.get("_source", "image"),
            extracted.get("invoice_number", ""),
            extracted.get("invoice_date", ""),
            extracted.get("due_date", ""),
            extracted.get("reference_number", ""),
            extracted.get("invoice_type", ""),
            extracted.get("currency", "TRY"),
            extracted.get("vendor_name", ""),
            extracted.get("vendor_vkn", ""),
            extracted.get("vendor_address", extracted.get("address", "")),
            extracted.get("buyer_name", ""),
            extracted.get("buyer_vkn", ""),
            extracted.get("buyer_address", ""),
            _safe_float(extracted.get("subtotal")),
            _safe_float(extracted.get("discount_amount")),
            _safe_float(extracted.get("tax_amount")),
            tax_rate,
            _safe_float(extracted.get("total")),
            extracted.get("payment_method", ""),
            extracted.get("status", "bekliyor"),
            extracted.get("category", ""),
            extracted.get("notes", ""),
            json.dumps(extracted, ensure_ascii=False),
            anomaly_result.get("normalized_score") if anomaly_result else None,
            1 if (anomaly_result or {}).get("is_anomaly") else 0,
            flags_json,
        ),
    )
    invoice_id = cursor.lastrowid

    # ── Kalem satırları ──────────────────────────────────────────────────────
    for item in extracted.get("line_items", []):
        conn.execute(
            """INSERT INTO line_items
               (invoice_id, description, qty, unit, unit_price,
                discount_rate, tax_rate, tax_amount, amount, product_code)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                invoice_id,
                item.get("description", item.get("desc", item.get("nm", ""))),
                _safe_float(item.get("qty",  item.get("cnt"))),
                item.get("unit", ""),
                _safe_float(item.get("unit_price", item.get("price"))),
                _safe_float(item.get("discount_rate")),
                _safe_float(item.get("tax_rate")),
                _safe_float(item.get("tax_amount")),
                _safe_float(item.get("amount")),
                item.get("product_code", ""),
            ),
        )

    # ── Çoklu KDV satırları (XML'den gelir) ─────────────────────────────────
    for tax in extracted.get("tax_lines", []):
        conn.execute(
            "INSERT INTO invoice_taxes (invoice_id, tax_rate, tax_base, tax_amount) VALUES (?,?,?,?)",
            (
                invoice_id,
                _safe_float(tax.get("tax_rate")),
                _safe_float(tax.get("tax_base")),
                _safe_float(tax.get("tax_amount")),
            ),
        )

    conn.commit()
    conn.close()
    return invoice_id


# ─── Okuma ────────────────────────────────────────────────────────────────────

def get_all_invoices() -> list[dict]:
    init_db()
    conn = get_conn()
    rows = conn.execute("SELECT * FROM invoices ORDER BY extracted_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_invoice(invoice_id: int) -> Optional[dict]:
    init_db()
    conn = get_conn()
    row = conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_line_items(invoice_id: int) -> list[dict]:
    init_db()
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM line_items WHERE invoice_id=? ORDER BY id", (invoice_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_invoice_taxes(invoice_id: int) -> list[dict]:
    init_db()
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM invoice_taxes WHERE invoice_id=? ORDER BY tax_rate", (invoice_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Güncelleme ───────────────────────────────────────────────────────────────

def update_invoice_status(invoice_id: int, status: str) -> None:
    init_db()
    conn = get_conn()
    conn.execute("UPDATE invoices SET status=? WHERE id=?", (status, invoice_id))
    conn.commit()
    conn.close()


def update_invoice_notes(invoice_id: int, notes: str) -> None:
    init_db()
    conn = get_conn()
    conn.execute("UPDATE invoices SET notes=? WHERE id=?", (notes, invoice_id))
    conn.commit()
    conn.close()


def update_invoice_category(invoice_id: int, category: str) -> None:
    init_db()
    conn = get_conn()
    conn.execute("UPDATE invoices SET category=? WHERE id=?", (category, invoice_id))
    conn.commit()
    conn.close()


# ─── Silme ────────────────────────────────────────────────────────────────────

def delete_invoice(invoice_id: int) -> None:
    init_db()
    conn = get_conn()
    conn.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))
    conn.commit()
    conn.close()


# ─── İstatistik ───────────────────────────────────────────────────────────────

def get_stats() -> dict:
    init_db()
    conn = get_conn()
    stats = dict(conn.execute("""
        SELECT
            COUNT(*)                                       AS total_count,
            COALESCE(SUM(total),  0)                       AS total_amount,
            COALESCE(AVG(total),  0)                       AS avg_amount,
            COALESCE(MAX(total),  0)                       AS max_amount,
            SUM(CASE WHEN is_anomaly=1 THEN 1 ELSE 0 END) AS anomaly_count,
            SUM(CASE WHEN status='bekliyor' THEN 1 ELSE 0 END) AS pending_count,
            COALESCE(SUM(tax_amount), 0)                   AS total_tax
        FROM invoices
    """).fetchone())
    conn.close()
    return stats
