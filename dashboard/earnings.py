"""Earnings-Kalender: Warnung vor anstehenden Quartalszahlen fuer Portfolio-Positionen."""

import logging
import time
import threading
from datetime import datetime, date

import yfinance as yf

logger = logging.getLogger("earnings")

# In-Memory-Cache mit TTL (6 Stunden)
_earnings_cache: dict = {}  # {ticker: {"date": str, "days_until": int, "ts": float}}
_CACHE_TTL = 6 * 3600  # 6 Stunden
_lock = threading.Lock()


def _fetch_earnings_date(ticker: str) -> dict | None:
    """Earnings-Datum fuer einen Ticker von yfinance abrufen."""
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is None:
            return None

        # yfinance gibt calendar als dict oder DataFrame zurueck
        earnings_date = None

        if isinstance(cal, dict):
            # Moegliche Keys: 'Earnings Date', 'Earnings Average', etc.
            ed = cal.get("Earnings Date")
            if ed:
                # Kann eine Liste sein (Earnings-Fenster)
                if isinstance(ed, list) and len(ed) > 0:
                    earnings_date = ed[0]
                elif isinstance(ed, (datetime, date)):
                    earnings_date = ed
        else:
            # DataFrame-Format (aeltere yfinance-Versionen)
            try:
                if hasattr(cal, "loc") and "Earnings Date" in cal.index:
                    val = cal.loc["Earnings Date"]
                    if hasattr(val, "iloc"):
                        val = val.iloc[0]
                    if isinstance(val, (datetime, date)):
                        earnings_date = val
            except Exception:
                pass

        if earnings_date is None:
            return None

        # In date-Objekt konvertieren
        if isinstance(earnings_date, datetime):
            earnings_date = earnings_date.date()

        today = date.today()
        days_until = (earnings_date - today).days

        return {
            "date": earnings_date.strftime("%d.%m.%Y"),
            "days_until": days_until,
        }

    except Exception as e:
        logger.debug("Earnings-Abfrage fuer %s fehlgeschlagen: %s", ticker, e)
        return None


def get_upcoming_earnings(tickers: list[str], days_ahead: int = 5) -> dict:
    """Gibt Earnings-Daten fuer Ticker zurueck, die in den naechsten N Tagen berichten.

    Returns: {ticker: {"date": "15.04.2026", "days_until": 3}}
    Nur Ticker mit Earnings innerhalb des Zeitfensters werden zurueckgegeben.
    Cache-Eintraege gelten 6 Stunden, fehlgeschlagene Abfragen werden uebersprungen.
    """
    result = {}
    now = time.time()

    for ticker in tickers:
        # Cache pruefen
        with _lock:
            cached = _earnings_cache.get(ticker)
            if cached and (now - cached.get("ts", 0)) < _CACHE_TTL:
                data = cached.get("data")
                if data and 0 <= data["days_until"] <= days_ahead:
                    result[ticker] = data
                continue

        # Nicht im Cache oder abgelaufen — neu abrufen
        data = _fetch_earnings_date(ticker)

        with _lock:
            _earnings_cache[ticker] = {"data": data, "ts": time.time()}

        if data and 0 <= data["days_until"] <= days_ahead:
            result[ticker] = data

    return result


def refresh_earnings_async(tickers: list[str], days_ahead: int = 5) -> None:
    """Startet Earnings-Abfrage im Hintergrund (blockiert nicht den Request)."""
    def _worker():
        try:
            get_upcoming_earnings(tickers, days_ahead)
        except Exception as e:
            logger.error("Async Earnings-Refresh fehlgeschlagen: %s", e)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
