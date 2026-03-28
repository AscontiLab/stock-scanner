#!/usr/bin/env python3
"""
SQLite-Cache fuer yfinance-Kursdaten.
Spart ~80% der API-Calls, indem bereits geladene Tage aus der DB kommen
und nur fehlende Tage nachgeladen werden.
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parent / "price_cache.db"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Datenbank-Setup
# ---------------------------------------------------------------------------


def _get_connection() -> sqlite3.Connection:
    """Erstellt eine SQLite-Verbindung mit WAL-Modus und busy_timeout."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Legt die Tabelle an, falls sie noch nicht existiert."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_cache (
            ticker     TEXT NOT NULL,
            date       TEXT NOT NULL,
            open       REAL,
            high       REAL,
            low        REAL,
            close      REAL,
            volume     INTEGER,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (ticker, date)
        )
    """)
    # Index fuer schnelle Range-Abfragen
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_price_cache_ticker_date
        ON price_cache (ticker, date)
    """)
    conn.commit()


# Schema beim Import einmalig anlegen
try:
    with _get_connection() as _conn:
        _ensure_schema(_conn)
except Exception as e:
    logger.warning("Cache-Schema konnte nicht angelegt werden: %s", e)


# ---------------------------------------------------------------------------
# Cache-Funktionen
# ---------------------------------------------------------------------------


def get_cached_prices(
    ticker: str, start_date: str, end_date: str
) -> pd.DataFrame | None:
    """
    Liest gecachte Kursdaten fuer einen Ticker im Zeitraum [start_date, end_date].
    Datumsformat: 'YYYY-MM-DD'.
    Gibt DataFrame mit DatetimeIndex zurueck oder None wenn nichts vorhanden.
    """
    try:
        conn = _get_connection()
        query = """
            SELECT date, open, high, low, close, volume
            FROM price_cache
            WHERE ticker = ? AND date >= ? AND date <= ?
            ORDER BY date
        """
        df = pd.read_sql_query(query, conn, params=(ticker, start_date, end_date))
        conn.close()

        if df.empty:
            return None

        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df.index.name = "Date"
        # Spaltennamen gross wie bei yfinance
        df.columns = ["Open", "High", "Low", "Close", "Volume"]
        return df
    except Exception as e:
        logger.warning("Cache-Lesefehler fuer %s: %s", ticker, e)
        return None


def save_prices(ticker: str, df: pd.DataFrame) -> None:
    """
    Speichert einen DataFrame (mit DatetimeIndex) in den Cache.
    Ueberschreibt vorhandene Eintraege per REPLACE.
    """
    if df is None or df.empty:
        return

    try:
        conn = _get_connection()
        now = datetime.now().isoformat()

        # DataFrame vorbereiten — Spaltennamen normalisieren
        save_df = df.copy()
        save_df.columns = [c.lower() for c in save_df.columns]

        rows = []
        for date_idx, row in save_df.iterrows():
            date_str = pd.Timestamp(date_idx).strftime("%Y-%m-%d")
            rows.append((
                ticker,
                date_str,
                float(row.get("open", 0)),
                float(row.get("high", 0)),
                float(row.get("low", 0)),
                float(row.get("close", 0)),
                int(row.get("volume", 0)),
                now,
            ))

        conn.executemany(
            """INSERT OR REPLACE INTO price_cache
               (ticker, date, open, high, low, close, volume, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Cache-Schreibfehler fuer %s: %s", ticker, e)


def _invalidate_today(ticker: str) -> None:
    """Loescht den heutigen Eintrag, damit Intraday-Updates frisch geladen werden."""
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        conn = _get_connection()
        conn.execute(
            "DELETE FROM price_cache WHERE ticker = ? AND date = ?",
            (ticker, today_str),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Cache-Invalidierung fuer %s fehlgeschlagen: %s", ticker, e)


def get_prices(ticker: str, period: str = "90d") -> pd.DataFrame | None:
    """
    Hauptfunktion: Prueft Cache, laedt nur fehlende Tage nach,
    gibt vollstaendigen DataFrame zurueck.

    - Daten vom aktuellen Tag werden immer neu geladen (Intraday-Updates).
    - Fallback auf direkten yf.download() wenn Cache fehlschlaegt.
    """
    # Zeitraum berechnen
    if period.endswith("y"):
        days = int(period.replace("y", "")) * 365
    elif period.endswith("d"):
        days = int(period.replace("d", ""))
    else:
        days = 90
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    # Heutigen Eintrag invalidieren (Intraday-Updates)
    _invalidate_today(ticker)

    # Cache abfragen
    cached_df = get_cached_prices(ticker, start_str, end_str)

    if cached_df is not None and len(cached_df) >= 20:
        # Pruefen ob Daten aktuell genug sind (letzter gecachter Tag)
        last_cached = cached_df.index.max()
        today = pd.Timestamp(end_date.date())
        # Wenn der letzte Boersentag (gestern oder heute) fehlt, nachladen
        gap_days = (today - last_cached).days

        if gap_days <= 1:
            # Cache ist aktuell genug — nur heute nachladen
            logger.debug("%s: Cache-Hit (%d Zeilen)", ticker, len(cached_df))
            # Heutigen Tag nachladen
            try:
                fresh = yf.download(
                    ticker, period="1d", interval="1d",
                    auto_adjust=True, progress=False
                )
                if fresh is not None and not fresh.empty:
                    if isinstance(fresh.columns, pd.MultiIndex):
                        fresh.columns = fresh.columns.droplevel(1)
                    save_prices(ticker, fresh)
                    # Alles zusammenfuegen
                    combined = pd.concat([cached_df, fresh])
                    combined = combined[~combined.index.duplicated(keep="last")]
                    combined.sort_index(inplace=True)
                    return combined
            except Exception:
                pass
            return cached_df

        elif gap_days <= 5:
            # Nur die fehlenden Tage nachladen
            fetch_start = (last_cached + timedelta(days=1)).strftime("%Y-%m-%d")
            try:
                fresh = yf.download(
                    ticker, start=fetch_start, end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
                    interval="1d", auto_adjust=True, progress=False
                )
                if fresh is not None and not fresh.empty:
                    if isinstance(fresh.columns, pd.MultiIndex):
                        fresh.columns = fresh.columns.droplevel(1)
                    save_prices(ticker, fresh)
                    combined = pd.concat([cached_df, fresh])
                    combined = combined[~combined.index.duplicated(keep="last")]
                    combined.sort_index(inplace=True)
                    logger.debug("%s: Cache + %d neue Tage", ticker, len(fresh))
                    return combined
            except Exception:
                pass
            # Fallback: cached data ist besser als nichts
            return cached_df

    # Kein oder zu wenig Cache — komplett laden
    try:
        df = yf.download(
            ticker,
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        # In Cache speichern
        save_prices(ticker, df)
        logger.debug("%s: Komplett geladen und gecacht (%d Zeilen)", ticker, len(df))
        return df
    except Exception as e:
        logger.error("yf.download fehlgeschlagen fuer %s: %s", ticker, e)
        # Letzter Fallback: Cached data zurueckgeben wenn vorhanden
        if cached_df is not None and not cached_df.empty:
            logger.info("%s: Fallback auf Cache-Daten", ticker)
            return cached_df
        return None


def cache_stats() -> dict:
    """Gibt Cache-Statistiken zurueck (Anzahl Ticker, Zeilen, DB-Groesse)."""
    try:
        conn = _get_connection()
        ticker_count = conn.execute(
            "SELECT COUNT(DISTINCT ticker) FROM price_cache"
        ).fetchone()[0]
        row_count = conn.execute(
            "SELECT COUNT(*) FROM price_cache"
        ).fetchone()[0]
        conn.close()

        db_size_mb = DB_PATH.stat().st_size / (1024 * 1024) if DB_PATH.exists() else 0

        return {
            "tickers": ticker_count,
            "rows": row_count,
            "db_size_mb": round(db_size_mb, 2),
        }
    except Exception:
        return {"tickers": 0, "rows": 0, "db_size_mb": 0}


if __name__ == "__main__":
    # Schnelltest
    import sys
    ticker_arg = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(f"Lade Kursdaten fuer {ticker_arg}...")
    result = get_prices(ticker_arg)
    if result is not None:
        print(f"OK: {len(result)} Zeilen")
        print(result.tail(3))
        stats = cache_stats()
        print(f"Cache: {stats['tickers']} Ticker, {stats['rows']} Zeilen, {stats['db_size_mb']} MB")
    else:
        print("FEHLER: Keine Daten erhalten")
