"""Gemeinsame Hilfsfunktionen fuer Stock Scanner Module."""

import csv
from pathlib import Path


def safe_float(val, default=0.0):
    """Konvertiert zu float, gibt default bei Fehler zurueck."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_int(val, default=0):
    """Konvertiert zu int (via float), gibt default bei Fehler zurueck."""
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def read_csv(path) -> list[dict]:
    """Liest CSV-Datei und gibt Liste von Dicts zurueck."""
    p = Path(path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def fg_label(value: int) -> str:
    """Gibt das Fear & Greed Label fuer einen Wert (0-100) zurueck."""
    if value <= 20:
        return "Extreme Angst"
    elif value <= 40:
        return "Angst"
    elif value <= 60:
        return "Neutral"
    elif value <= 80:
        return "Gier"
    else:
        return "Extreme Gier"
