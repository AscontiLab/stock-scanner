"""
Fear & Greed Index: CNN-Daten abrufen und Multiplikator berechnen.
"""

import json
import urllib.request

from utils import fg_label as _fg_label


def get_fear_greed() -> dict:
    """Holt CNN Fear & Greed Index (0-100). Fallback: neutral."""
    try:
        req = urllib.request.Request(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            value = round(float(data["fear_and_greed"]["score"]))
            return {"value": value, "label": _fg_label(value)}
    except Exception:
        return {"value": 50, "label": "Neutral (Fallback)"}


def compute_fg_multiplier(fg_value: int) -> tuple[float, float]:
    """
    Berechnet Fear & Greed Multiplikatoren (Contrarian-Ansatz).

    Returns:
        (fg_long_multiplier, fg_short_multiplier)
    """
    if fg_value <= 20:
        return 1.2, 0.8   # Extreme Fear -> Long staerker
    elif fg_value <= 40:
        return 1.1, 0.9
    elif fg_value <= 60:
        return 1.0, 1.0   # Neutral
    elif fg_value <= 80:
        return 0.9, 1.1
    else:
        return 0.8, 1.2   # Extreme Greed -> Short staerker
