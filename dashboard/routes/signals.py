"""Signale-Seite: CFD Long/Short + Langfrist-Investments + Sektor-Heatmap."""

import json
import logging
import time
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

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

SCANNER_DIR = settings.SCANNER_DIR
SECTOR_CACHE_PATH = Path(__file__).parent.parent / "data" / "sector_cache.json"
# Sektor-Cache ist 24h gueltig
SECTOR_CACHE_TTL = 86400


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


def _load_sector_cache() -> dict:
    """Laedt den Sektor-Cache aus JSON. Gibt leeres Dict zurueck wenn nicht vorhanden."""
    if SECTOR_CACHE_PATH.exists():
        try:
            with open(SECTOR_CACHE_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_sector_cache(cache: dict) -> None:
    """Speichert den Sektor-Cache als JSON."""
    SECTOR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SECTOR_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def _compute_sector_heatmap() -> list[dict]:
    """Berechnet Sektor-Performance aus den neuesten Scan-Daten.

    Liest all_results.csv, ermittelt Sektoren via yfinance (mit Cache),
    und gruppiert die Daten nach Sektoren.
    """
    # Neuestes Output-Verzeichnis finden
    output_dir = SCANNER_DIR / "output"
    if not output_dir.exists():
        return []
    dirs = sorted([d for d in output_dir.iterdir() if d.is_dir()], reverse=True)
    if not dirs:
        return []

    csv_path = dirs[0] / "all_results.csv"
    if not csv_path.exists():
        return []

    rows = _read_csv(csv_path)
    if not rows:
        return []

    # Sektor-Cache laden und pruefen ob er aktuell ist
    cache = _load_sector_cache()
    cache_ts = cache.get("_timestamp", 0)
    cache_stale = (time.time() - cache_ts) > SECTOR_CACHE_TTL
    cache_mapping = cache.get("sectors", {})

    # Ticker ohne Sektor-Info sammeln
    tickers_to_lookup = []
    if cache_stale:
        # Bei abgelaufenem Cache alle Ticker pruefen
        tickers_to_lookup = [r["ticker"] for r in rows if r.get("ticker")]
    else:
        # Nur neue Ticker nachschlagen
        tickers_to_lookup = [
            r["ticker"] for r in rows
            if r.get("ticker") and r["ticker"] not in cache_mapping
        ]

    # Fehlende Sektoren via yfinance abrufen (im Background wenn viele fehlen)
    if tickers_to_lookup:
        if len(tickers_to_lookup) > 20:
            # Zu viele Ticker — im Background-Thread laden, Seite nicht blockieren
            import threading
            def _bg_fetch():
                try:
                    import yfinance as yf
                    for t in tickers_to_lookup:
                        try:
                            info = yf.Ticker(t).info
                            cache_mapping[t] = info.get("sector", "Unbekannt")
                        except Exception:
                            cache_mapping[t] = "Unbekannt"
                    _save_sector_cache({"_timestamp": time.time(), "sectors": cache_mapping})
                except Exception:
                    pass
            threading.Thread(target=_bg_fetch, daemon=True).start()
            # Mit vorhandenen Cache-Daten weiterarbeiten (oder leer)
            if not cache_mapping:
                return []
        else:
            try:
                import yfinance as yf
                for ticker in tickers_to_lookup:
                    try:
                        info = yf.Ticker(ticker).info
                        sector = info.get("sector", "Unbekannt")
                        cache_mapping[ticker] = sector
                    except Exception:
                        cache_mapping[ticker] = "Unbekannt"
            except ImportError:
                logger.warning("yfinance nicht installiert — Sektor-Daten nicht verfuegbar")
                return []
            _save_sector_cache({"_timestamp": time.time(), "sectors": cache_mapping})

    # Daten nach Sektoren gruppieren
    sector_data: dict[str, dict] = {}
    for row in rows:
        ticker = row.get("ticker", "")
        sector = cache_mapping.get(ticker, "Unbekannt")
        if sector not in sector_data:
            sector_data[sector] = {
                "sector": sector,
                "pct_changes": [],
                "rsi_values": [],
                "buy_count": 0,
                "sell_count": 0,
                "count": 0,
            }

        sd = sector_data[sector]
        sd["count"] += 1

        pct = _safe_float(row.get("pct_change", "0"))
        sd["pct_changes"].append(pct)

        rsi = _safe_float(row.get("rsi", "0"))
        if rsi > 0:
            sd["rsi_values"].append(rsi)

        buy_sig = _safe_int(row.get("buy_signals", "0"))
        sell_sig = _safe_int(row.get("sell_signals", "0"))
        if buy_sig > sell_sig:
            sd["buy_count"] += 1
        elif sell_sig > buy_sig:
            sd["sell_count"] += 1

    # Ergebnis-Liste aufbauen
    result = []
    for sector, sd in sector_data.items():
        avg_pct = sum(sd["pct_changes"]) / len(sd["pct_changes"]) if sd["pct_changes"] else 0
        avg_rsi = sum(sd["rsi_values"]) / len(sd["rsi_values"]) if sd["rsi_values"] else 0
        total_signals = sd["buy_count"] + sd["sell_count"]
        buy_ratio = (sd["buy_count"] / total_signals * 100) if total_signals > 0 else 50

        result.append({
            "sector": sector,
            "avg_pct_change": round(avg_pct, 2),
            "avg_rsi": round(avg_rsi, 1),
            "count": sd["count"],
            "buy_count": sd["buy_count"],
            "sell_count": sd["sell_count"],
            "buy_ratio": round(buy_ratio, 0),
        })

    # Sortieren nach durchschnittlicher Kursaenderung (beste oben)
    result.sort(key=lambda x: x["avg_pct_change"], reverse=True)
    return result


def _load_signals() -> dict:
    """Laedt alle Signal-Daten fuer die Anzeige."""
    def _parse_jsonish(value):
        if isinstance(value, dict):
            return value
        if not value:
            return {}
        try:
            return json.loads(value)
        except Exception:
            return {}

    def _annotate_learning(row: dict, direction: str) -> dict:
        penalties = _parse_jsonish(row.get(f"cfd_{direction}_penalties"))
        components = _parse_jsonish(row.get(f"cfd_{direction}_components"))
        flags: list[dict] = []
        summary: list[str] = []

        if penalties.get("gap_hard"):
            flags.append({"label": "Gap > 6%", "kind": "penalty"})
            summary.append("Hartes Gap-Filter aktiv")
        elif penalties.get("gap_soft"):
            flags.append({"label": "Gap 4-6%", "kind": "penalty"})
            summary.append("Gap-Regime dämpft den Score")

        if penalties.get("atr_high"):
            flags.append({"label": "ATR >= 3%", "kind": "penalty"})
            summary.append("Hohes ATR-Regime vorsichtiger")

        market_adj = _safe_float(penalties.get("market_adjustment"))
        if market_adj:
            flags.append({
                "label": f"Marktfilter {row.get('market', '')}".strip(),
                "kind": "bonus" if market_adj > 0 else "penalty",
            })
            summary.append(f"Marktfilter für {row.get('market', '?')} aktiv")

        if penalties.get("short_bias"):
            flags.append({"label": "Short-Bias", "kind": "penalty"})
            summary.append("Shorts werden skeptischer bewertet")

        if components.get("bonus_trend_maturity"):
            flags.append({"label": "Trend-Reife", "kind": "bonus"})
        if components.get("bonus_squeeze_fire"):
            flags.append({"label": "Squeeze Fire", "kind": "bonus"})

        row["learning_flags"] = flags[:4]
        row["learning_summary"] = " | ".join(summary[:2]) if summary else "Basisscore ohne starke Sonderregeln"
        return row

    # CFD Setups (Root-Level-Kopie)
    cfd_rows = _read_csv(SCANNER_DIR / "cfd_setups.csv")
    cfd_long = [r for r in cfd_rows if r.get("cfd_direction") == "long"]
    cfd_short = [r for r in cfd_rows if r.get("cfd_direction") == "short"]

    # Sortieren nach Score
    cfd_long.sort(key=lambda r: _safe_float(r.get("cfd_long_score")), reverse=True)
    cfd_short.sort(key=lambda r: _safe_float(r.get("cfd_short_score")), reverse=True)
    cfd_long = [_annotate_learning(r, "long") for r in cfd_long]
    cfd_short = [_annotate_learning(r, "short") for r in cfd_short]

    # Langfrist-Signale statt Buy/Sell
    all_rows = _read_csv(SCANNER_DIR / "trading_signals.csv")
    longterm_rows = sorted(
        all_rows,
        key=lambda r: _safe_float(r.get("longterm_score")),
        reverse=True,
    )[:20]

    fear_greed = _get_fear_greed()
    scan_time = _get_scan_timestamp()

    # Sektor-Heatmap berechnen
    try:
        sector_heatmap = _compute_sector_heatmap()
    except Exception as e:
        logger.error("Sektor-Heatmap Fehler: %s", e)
        sector_heatmap = []

    return {
        "cfd_long": cfd_long,
        "cfd_short": cfd_short,
        "longterm_rows": longterm_rows,
        "fear_greed": fear_greed,
        "scan_time": scan_time,
        "sector_heatmap": sector_heatmap,
    }


@router.get("/", response_class=HTMLResponse)
async def signals_page(request: Request):
    data = _load_signals()
    return templates.TemplateResponse("signals.html", {"request": request, **data})


@router.get("/api/signals")
async def signals_json():
    return _load_signals()
