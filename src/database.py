import sqlite3
import json
from pathlib import Path
from datetime import datetime, date
from typing import Optional

DB_PATH = Path("data/invoices.db")


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Tabloları oluştur (yoksa)."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS invoices (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            filename        TEXT,
            vendor_name     TEXT,
            invoice_date    TEXT,
            invoice_number  TEXT,
            subtotal        REAL,
            tax_amount      REAL,
            total           REAL,
            address         TEXT,
            currency        TEXT DEFAULT 'TRY',
            raw_json        TEXT,
            anomaly_score   REAL,
            is_anomaly      INTEGER DEFAULT 0,
            rule_flags      TEXT,
            extracted_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS line_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id  INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
            description TEXT,
            qty         REAL,
            unit_price  REAL,
            amount      REAL
        );
    """)
    conn.commit()
    conn.close()


def _safe_float(val) -> Optional[float]:
    try:
        return float(str(val).replace(",", ".").replace("$", "").strip())
    except Exception:
        return None


def save_invoice(
    extracted: dict,
    filename: str = "",
    anomaly_result: Optional[dict] = None,
    rule_flags: Optional[list] = None,
) -> int:
    """Çıkarılan faturayı veritabanına kaydeder, invoice id döndürür."""
    init_db()
    conn = get_conn()

    flags_json = json.dumps(
        [{"rule_id": f.rule_id, "severity": f.severity, "message": f.message}
         for f in (rule_flags or [])],
        ensure_ascii=False,
    )

    cursor = conn.execute(
        """
        INSERT INTO invoices
            (filename, vendor_name, invoice_date, invoice_number,
             subtotal, tax_amount, total, address, raw_json,
             anomaly_score, is_anomaly, rule_flags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            filename,
            extracted.get("vendor_name", ""),
            extracted.get("invoice_date", ""),
            extracted.get("invoice_number", ""),
            _safe_float(extracted.get("subtotal")),
            _safe_float(extracted.get("tax_amount")),
            _safe_float(extracted.get("total")),
            extracted.get("address", ""),
            json.dumps(extracted, ensure_ascii=False),
            anomaly_result.get("normalized_score") if anomaly_result else None,
            1 if (anomaly_result or {}).get("is_anomaly") else 0,
            flags_json,
        ),
    )
    invoice_id = cursor.lastrowid

    # Kalem satırları varsa kaydet
    for item in extracted.get("line_items", []):
        conn.execute(
            "INSERT INTO line_items (invoice_id, description, qty, unit_price, amount) VALUES (?,?,?,?,?)",
            (
                invoice_id,
                item.get("desc", item.get("nm", "")),
                _safe_float(item.get("qty", item.get("cnt"))),
                _safe_float(item.get("unit_price", item.get("price"))),
                _safe_float(item.get("amount", item.get("price"))),
            ),
        )

    conn.commit()
    conn.close()
    return invoice_id


def get_all_invoices() -> list[dict]:
    """Tüm faturaları döndürür (yeniden eskiye sıralı)."""
    init_db()
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM invoices ORDER BY extracted_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_invoice(invoice_id: int) -> Optional[dict]:
    init_db()
    conn = get_conn()
    row = conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_invoice(invoice_id: int) -> None:
    init_db()
    conn = get_conn()
    conn.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))
    conn.commit()
    conn.close()


def get_stats() -> dict:
    """Genel istatistikler."""
    init_db()
    conn = get_conn()
    stats = dict(conn.execute("""
        SELECT
            COUNT(*)                                    AS total_count,
            COALESCE(SUM(total), 0)                    AS total_amount,
            COALESCE(AVG(total), 0)                    AS avg_amount,
            COALESCE(MAX(total), 0)                    AS max_amount,
            SUM(CASE WHEN is_anomaly=1 THEN 1 ELSE 0 END) AS anomaly_count
        FROM invoices
    """).fetchone())
    conn.close()
    return stats
