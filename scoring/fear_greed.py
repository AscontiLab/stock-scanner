"""
Fear & Greed Index: CNN-Daten abrufen und Multiplikator berechnen.
"""

import json
import sys
import urllib.request

from utils import fg_label as _fg_label

# Realistische Browser-Header: CNN blockt schlanke User-Agents mit HTTP 418.
_FG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_FG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
}


def get_fear_greed() -> dict:
    """
    Holt CNN Fear & Greed Index (0-100).

    Fail-closed: Bei Fehler wird NICHT still ein getarnter "Neutral 50"
    zurueckgegeben (das maskierte den HTTP-418-Block ueber Wochen unbemerkt).
    Stattdessen value=None + laute stderr-Warnung → Contrarian-Bonus wird
    nachgelagert sauber auf 0 gesetzt (kein falscher Tilt).
    """
    try:
        req = urllib.request.Request(_FG_URL, headers=_FG_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        value = round(float(data["fear_and_greed"]["score"]))
        return {"value": value, "label": _fg_label(value), "ok": True}
    except Exception as e:
        sys.stderr.write(
            f"[WARNUNG] Fear&Greed nicht abrufbar ({type(e).__name__}: {e}) "
            f"→ Contrarian-Bonus deaktiviert (KEIN 50-Fallback-Tilt).\n"
        )
        return {"value": None, "label": "UNAVAILABLE", "ok": False}


def compute_fg_multiplier(fg_value: int) -> tuple[float, float]:
    """
    Berechnet Fear & Greed Multiplikatoren (Contrarian-Ansatz).
    DEPRECATED: Wird durch compute_fg_cfd_bonus() ersetzt.

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


def compute_fg_cfd_bonus(fg_value: int) -> dict:
    """
    Berechnet additiven F&G-Bonus fuer CFD-Scores (Contrarian-Ansatz).

    Extreme Fear  (F&G < 25): Long +0.5, Short -0.5, Long-Threshold -0.5
    Extreme Greed (F&G > 75): Short +0.5, Long -0.5, Short-Threshold -0.5
    Normal        (25-75):    keine Anpassung

    Returns:
        Dict mit long_bonus, short_bonus, threshold_long_adj, threshold_short_adj, zone
    """
    if not isinstance(fg_value, (int, float)):
        # F&G nicht verfuegbar (fail-closed): kein Tilt, sichtbar im Output.
        return {
            "long_bonus": 0.0,
            "short_bonus": 0.0,
            "threshold_long_adj": 0.0,
            "threshold_short_adj": 0.0,
            "zone": "UNAVAILABLE",
        }
    if fg_value < 25:
        # Extreme Fear: Contrarian → kaufen (Long bevorzugen)
        return {
            "long_bonus": 0.5,
            "short_bonus": -0.5,
            "threshold_long_adj": -0.5,   # Niedrigerer Threshold fuer Longs
            "threshold_short_adj": 0.0,
            "zone": "Extreme Fear",
        }
    elif fg_value > 75:
        # Extreme Greed: Contrarian → shorten (Short bevorzugen)
        return {
            "long_bonus": -0.5,
            "short_bonus": 0.5,
            "threshold_long_adj": 0.0,
            "threshold_short_adj": -0.5,  # Niedrigerer Threshold fuer Shorts
            "zone": "Extreme Greed",
        }
    else:
        # Neutrale Zone: keine Anpassung
        return {
            "long_bonus": 0.0,
            "short_bonus": 0.0,
            "threshold_long_adj": 0.0,
            "threshold_short_adj": 0.0,
            "zone": "Neutral",
        }
