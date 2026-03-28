"""Signale-Seite: CFD Long/Short + Langfrist-Investments."""

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from dashboard.config import settings
from utils import safe_float as _safe_float
from utils import safe_int as _safe_int
from utils import read_csv as _read_csv
from utils import fg_label

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

SCANNER_DIR = settings.SCANNER_DIR


def _get_scan_timestamp() -> str:
    """Findet den Zeitstempel des letzten Scans."""
    # Suche neuestes Output-Verzeichnis
    output_dir = SCANNER_DIR / "output"
    if not output_dir.exists():
        return "Kein Scan gefunden"
    dirs = sorted([d for d in output_dir.iterdir() if d.is_dir()], reverse=True)
    if dirs:
        return dirs[0].name
    return "Kein Scan gefunden"


def _get_fear_greed() -> dict:
    """Liest F&G aus dem letzten Scan-Log oder holt ihn frisch."""
    # Versuche aus der letzten cfd_setups.csv den F&G-Wert zu ermitteln
    # Fallback: direkt abrufen
    try:
        import sqlite3
        db_path = SCANNER_DIR / "cfd_backtesting.db"
        if db_path.exists():
            with sqlite3.connect(str(db_path)) as conn:
                cur = conn.cursor()
                cur.execute("SELECT fear_greed FROM cfd_scan_runs ORDER BY id DESC LIMIT 1")
                row = cur.fetchone()
            if row:
                val = int(row[0])
                return {"value": val, "label": fg_label(val)}
    except Exception:
        pass
    return {"value": 50, "label": "Neutral (Fallback)"}


def _load_signals() -> dict:
    """Laedt alle Signal-Daten fuer die Anzeige."""
    # CFD Setups (Root-Level-Kopie)
    cfd_rows = _read_csv(SCANNER_DIR / "cfd_setups.csv")
    cfd_long = [r for r in cfd_rows if r.get("cfd_direction") == "long"]
    cfd_short = [r for r in cfd_rows if r.get("cfd_direction") == "short"]

    # Sortieren nach Score
    cfd_long.sort(key=lambda r: _safe_float(r.get("cfd_long_score")), reverse=True)
    cfd_short.sort(key=lambda r: _safe_float(r.get("cfd_short_score")), reverse=True)

    # Langfrist-Signale statt Buy/Sell
    all_rows = _read_csv(SCANNER_DIR / "trading_signals.csv")
    longterm_rows = sorted(
        all_rows,
        key=lambda r: _safe_float(r.get("longterm_score")),
        reverse=True,
    )[:20]

    fear_greed = _get_fear_greed()
    scan_time = _get_scan_timestamp()

    return {
        "cfd_long": cfd_long,
        "cfd_short": cfd_short,
        "longterm_rows": longterm_rows,
        "fear_greed": fear_greed,
        "scan_time": scan_time,
    }


@router.get("/", response_class=HTMLResponse)
async def signals_page(request: Request):
    data = _load_signals()
    return templates.TemplateResponse("signals.html", {"request": request, **data})


@router.get("/api/signals")
async def signals_json():
    return _load_signals()
