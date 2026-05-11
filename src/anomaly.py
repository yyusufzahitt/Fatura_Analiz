import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


class AnomalyDetector:
    """Fatura sayısal alanları üzerinde Isolation Forest anomali tespiti."""

    FEATURES = ["subtotal", "tax_amount", "total", "tax_rate"]
    MODEL_PATH = Path("models/anomaly_detector.pkl")
    SCALER_PATH = Path("models/anomaly_scaler.pkl")

    def __init__(self):
        self.model = None
        self.scaler = None

    def _safe_float(self, val) -> float:
        try:
            return float(str(val).replace(",", ".").replace("$", "").strip())
        except Exception:
            return 0.0

    def _build_dataframe(self, records: list[dict]) -> pd.DataFrame:
        rows = []
        for r in records:
            subtotal   = self._safe_float(r.get("subtotal", 0))
            tax_amount = self._safe_float(r.get("tax_amount", 0))
            total      = self._safe_float(r.get("total", 0))
            tax_rate   = (tax_amount / subtotal) if subtotal > 0 else 0.0
            rows.append([subtotal, tax_amount, total, tax_rate])
        return pd.DataFrame(rows, columns=self.FEATURES)

    def fit(self, records: list[dict]) -> None:
        """Tarihsel fatura kayıtlarından anomali modeli eğit.

        records: [{"subtotal": 100.0, "tax_amount": 8.0, "total": 108.0, ...}]
        """
        df = self._build_dataframe(records)

        self.scaler = StandardScaler()
        X = self.scaler.fit_transform(df.values)

        self.model = IsolationForest(
            n_estimators=200,
            contamination=0.05,
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(X)

        self.MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, self.MODEL_PATH)
        joblib.dump(self.scaler, self.SCALER_PATH)
        print(f"[AnomalyDetector] Eğitildi: {len(records)} kayıt üzerinde.")

    def load(self) -> None:
        """Daha önce kaydedilmiş modeli yükler."""
        if not self.MODEL_PATH.exists() or not self.SCALER_PATH.exists():
            raise FileNotFoundError(
                "Anomali modeli bulunamadı. Önce fit() çalıştırın "
                "veya train.py'den sonra anomaly_detector.fit() çağırın."
            )
        self.model = joblib.load(self.MODEL_PATH)
        self.scaler = joblib.load(self.SCALER_PATH)

    def is_ready(self) -> bool:
        return self.model is not None and self.scaler is not None

    def explain(self, invoice: dict) -> list[dict]:
        """Her özelliğin anomaliye katkısını z-skoru ile döndürür.

        Scaler'ın mean_ ve scale_ değerleri eğitim verisi dağılımını tutar.
        z = (değer - ortalama) / std  →  kaç standart sapma uzakta?
        """
        if not self.is_ready():
            return []

        subtotal   = self._safe_float(invoice.get("subtotal", 0))
        tax_amount = self._safe_float(invoice.get("tax_amount", 0))
        total      = self._safe_float(invoice.get("total", 0))
        tax_rate   = (tax_amount / subtotal) if subtotal > 0 else 0.0

        vals  = [subtotal, tax_amount, total, tax_rate]
        means = self.scaler.mean_.tolist()
        stds  = self.scaler.scale_.tolist()

        results = []
        for feat, val, mean, std in zip(self.FEATURES, vals, means, stds):
            if std < 1e-9:
                continue
            z = (val - mean) / std
            results.append({
                "feature":   feat,
                "value":     round(val,  4),
                "mean":      round(mean, 4),
                "std":       round(std,  4),
                "z_score":   round(z,    2),
                "direction": "yüksek" if z > 0 else "düşük",
            })

        results.sort(key=lambda x: abs(x["z_score"]), reverse=True)
        return results

    def score(self, invoice: dict) -> dict:
        """Tek fatura için anomali skoru ve karar döndürür.

        Dönüş: {"anomaly_score": float, "is_anomaly": bool, "normalized_score": float}
        """
        if not self.is_ready():
            raise RuntimeError("Model yüklü değil. Önce load() veya fit() çağırın.")

        subtotal   = self._safe_float(invoice.get("subtotal", 0))
        tax_amount = self._safe_float(invoice.get("tax_amount", 0))
        total      = self._safe_float(invoice.get("total", 0))
        tax_rate   = (tax_amount / subtotal) if subtotal > 0 else 0.0

        row = [[subtotal, tax_amount, total, tax_rate]]
        X = self.scaler.transform(row)

        # score_samples: negatif değer → daha anomali
        raw_score = float(self.model.score_samples(X)[0])
        decision  = int(self.model.predict(X)[0])  # -1 = anomali, 1 = normal

        # 0–1 aralığına normalize et (yüksek = daha anomali)
        normalized = max(0.0, min(1.0, (-raw_score + 0.5) * 2))

        return {
            "anomaly_score": raw_score,
            "normalized_score": normalized,
            "is_anomaly": decision == -1,
        }
