"""
Firmenname-Resolver: Loest Ticker-Symbole zu Firmennamen auf.
Primaerquelle: Wikipedia-Tabellen (gleiche Seiten wie sources.py).
Fallback: yfinance API (langsam, ~0.5s pro Ticker).
Cache: SQLite mit 30-Tage TTL.
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from tickers.sources import _safe_read_html, COUNTRY_TO_SUFFIX

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parents[1] / "name_cache.db"
CACHE_TTL_DAYS = 30

logger = logging.getLogger(__name__)

# In-Memory-Cache fuer schnellen Zugriff innerhalb einer Session
_memory_cache: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Datenbank-Setup
# ---------------------------------------------------------------------------

def _get_connection() -> sqlite3.Connection:
    """Erstellt eine SQLite-Verbindung mit WAL-Modus."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Legt die Tabelle an, falls sie noch nicht existiert."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS company_names (
            ticker     TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
    """)
    conn.commit()


# Schema beim Import einmalig anlegen
try:
    with _get_connection() as _conn:
        _ensure_schema(_conn)
except Exception as e:
    logger.warning("Name-Cache-Schema konnte nicht angelegt werden: %s", e)


# ---------------------------------------------------------------------------
# Cache-Funktionen
# ---------------------------------------------------------------------------

def _get_cached_name(ticker: str) -> str | None:
    """Liest den Firmennamen aus dem Cache, wenn noch gueltig (TTL 30 Tage)."""
    # Zuerst In-Memory-Cache pruefen
    if ticker in _memory_cache:
        return _memory_cache[ticker]

    try:
        conn = _get_connection()
        row = conn.execute(
            "SELECT name, fetched_at FROM company_names WHERE ticker = ?",
            (ticker,)
        ).fetchone()
        conn.close()

        if row is None:
            return None

        name, fetched_at = row
        fetched_dt = datetime.fromisoformat(fetched_at)
        if datetime.now() - fetched_dt > timedelta(days=CACHE_TTL_DAYS):
            return None  # Abgelaufen

        _memory_cache[ticker] = name
        return name
    except Exception as e:
        logger.warning("Cache-Lesefehler fuer %s: %s", ticker, e)
        return None


def _save_to_cache(ticker: str, name: str) -> None:
    """Speichert einen Firmennamen im SQLite-Cache."""
    try:
        conn = _get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO company_names (ticker, name, fetched_at) VALUES (?, ?, ?)",
            (ticker, name, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        _memory_cache[ticker] = name
    except Exception as e:
        logger.warning("Cache-Schreibfehler fuer %s: %s", ticker, e)


def _save_bulk_to_cache(names: dict[str, str]) -> None:
    """Speichert mehrere Firmennamen auf einmal im Cache."""
    if not names:
        return
    try:
        conn = _get_connection()
        now = datetime.now().isoformat()
        rows = [(ticker, name, now) for ticker, name in names.items()]
        conn.executemany(
            "INSERT OR REPLACE INTO company_names (ticker, name, fetched_at) VALUES (?, ?, ?)",
            rows
        )
        conn.commit()
        conn.close()
        _memory_cache.update(names)
    except Exception as e:
        logger.warning("Bulk-Cache-Schreibfehler: %s", e)


# ---------------------------------------------------------------------------
# Wikipedia-Extraktion (Primaerquelle)
# ---------------------------------------------------------------------------

def _extract_name_column(tables: list, name_cols: list[str], ticker_cols: list[str],
                         ticker_transform=None, country_col_name: str | None = None) -> dict[str, str]:
    """
    Generische Extraktion von Ticker->Name aus Wikipedia-Tabellen.
    Sucht nach passenden Spalten fuer Ticker und Name.
    """
    result = {}
    for t in tables:
        cols_lower = {str(c).lower().strip(): c for c in t.columns}

        # Ticker-Spalte finden
        ticker_col = None
        for tc in ticker_cols:
            for k, v in cols_lower.items():
                if tc in k:
                    ticker_col = v
                    break
            if ticker_col is not None:
                break

        # Name-Spalte finden
        name_col = None
        for nc in name_cols:
            for k, v in cols_lower.items():
                if nc in k:
                    name_col = v
                    break
            if name_col is not None:
                break

        if ticker_col is None or name_col is None:
            continue

        # Country-Spalte (optional, fuer Euro Stoxx 50)
        country_col = None
        if country_col_name:
            for k, v in cols_lower.items():
                if country_col_name in k:
                    country_col = v
                    break

        for _, row in t.iterrows():
            ticker = str(row[ticker_col]).strip()
            name = str(row[name_col]).strip()
            if not ticker or ticker.lower() == "nan" or not name or name.lower() == "nan":
                continue

            # Ticker transformieren (z.B. .DE anfuegen)
            if ticker_transform:
                ticker = ticker_transform(ticker, row, country_col)

            if ticker and name:
                result[ticker] = name

    return result


def _transform_nasdaq(ticker: str, row, country_col) -> str:
    """NASDAQ-Ticker: Punkt durch Bindestrich ersetzen (BRK.B -> BRK-B)."""
    return ticker.replace(".", "-")


def _transform_sp500(ticker: str, row, country_col) -> str:
    """S&P 500 Ticker: Punkt durch Bindestrich ersetzen."""
    return ticker.replace(".", "-")


def _transform_de(ticker: str, row, country_col) -> str:
    """Deutsche Indizes: .DE Suffix anfuegen wenn noetig."""
    if "." not in ticker:
        return ticker + ".DE"
    return ticker


def _transform_eurostoxx(ticker: str, row, country_col) -> str:
    """Euro Stoxx 50: Exchange-Suffix basierend auf Land anfuegen."""
    if "." in ticker:
        return ticker
    if country_col is not None:
        country = str(row[country_col]).strip()
        suffix = COUNTRY_TO_SUFFIX.get(country, "")
        return ticker + suffix
    return ticker


def load_wiki_names() -> dict[str, str]:
    """
    Laedt Firmennamen von allen Wikipedia-Indexseiten.
    Gibt ein Dict {ticker: firmenname} zurueck.
    """
    all_names: dict[str, str] = {}

    # --- NASDAQ 100 ---
    try:
        tables = _safe_read_html("https://en.wikipedia.org/wiki/NASDAQ-100")
        names = _extract_name_column(
            tables,
            name_cols=["company", "security"],
            ticker_cols=["ticker", "symbol"],
            ticker_transform=_transform_nasdaq,
        )
        all_names.update(names)
        logger.debug("NASDAQ 100: %d Namen geladen", len(names))
    except Exception as e:
        logger.warning("Wikipedia NASDAQ 100 fehlgeschlagen: %s", e)

    # --- S&P 500 ---
    try:
        tables = _safe_read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        names = _extract_name_column(
            tables,
            name_cols=["security"],
            ticker_cols=["symbol", "ticker"],
            ticker_transform=_transform_sp500,
        )
        all_names.update(names)
        logger.debug("S&P 500: %d Namen geladen", len(names))
    except Exception as e:
        logger.warning("Wikipedia S&P 500 fehlgeschlagen: %s", e)

    # --- DAX 40 ---
    try:
        tables = _safe_read_html("https://en.wikipedia.org/wiki/DAX")
        names = _extract_name_column(
            tables,
            name_cols=["company", "name"],
            ticker_cols=["ticker", "symbol"],
            ticker_transform=_transform_de,
        )
        all_names.update(names)
        logger.debug("DAX 40: %d Namen geladen", len(names))
    except Exception as e:
        logger.warning("Wikipedia DAX 40 fehlgeschlagen: %s", e)

    # --- Euro Stoxx 50 ---
    try:
        tables = _safe_read_html("https://en.wikipedia.org/wiki/Euro_Stoxx_50")
        names = _extract_name_column(
            tables,
            name_cols=["company", "name"],
            ticker_cols=["ticker", "symbol"],
            ticker_transform=_transform_eurostoxx,
            country_col_name="country",
        )
        all_names.update(names)
        logger.debug("Euro Stoxx 50: %d Namen geladen", len(names))
    except Exception as e:
        logger.warning("Wikipedia Euro Stoxx 50 fehlgeschlagen: %s", e)

    # --- TecDAX ---
    try:
        tables = _safe_read_html("https://en.wikipedia.org/wiki/TecDAX")
        names = _extract_name_column(
            tables,
            name_cols=["company", "name"],
            ticker_cols=["ticker", "symbol"],
            ticker_transform=_transform_de,
        )
        all_names.update(names)
        logger.debug("TecDAX: %d Namen geladen", len(names))
    except Exception as e:
        logger.warning("Wikipedia TecDAX fehlgeschlagen: %s", e)

    # --- MDAX ---
    try:
        tables = _safe_read_html("https://en.wikipedia.org/wiki/MDAX")
        names = _extract_name_column(
            tables,
            name_cols=["company", "name"],
            ticker_cols=["ticker", "symbol"],
            ticker_transform=_transform_de,
        )
        all_names.update(names)
        logger.debug("MDAX: %d Namen geladen", len(names))
    except Exception as e:
        logger.warning("Wikipedia MDAX fehlgeschlagen: %s", e)

    # --- SDAX ---
    try:
        tables = _safe_read_html("https://en.wikipedia.org/wiki/SDAX")
        names = _extract_name_column(
            tables,
            name_cols=["company", "name"],
            ticker_cols=["ticker", "symbol"],
            ticker_transform=_transform_de,
        )
        all_names.update(names)
        logger.debug("SDAX: %d Namen geladen", len(names))
    except Exception as e:
        logger.warning("Wikipedia SDAX fehlgeschlagen: %s", e)

    return all_names


# ---------------------------------------------------------------------------
# yfinance Fallback
# ---------------------------------------------------------------------------

def _fetch_name_yfinance(ticker: str) -> str:
    """Holt den Firmennamen via yfinance (langsam, ~0.5s pro Ticker)."""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        name = info.get("shortName") or info.get("longName") or ticker
        return name
    except Exception as e:
        logger.warning("yfinance-Abfrage fuer %s fehlgeschlagen: %s", ticker, e)
        return ticker


# ---------------------------------------------------------------------------
# Oeffentliche API
# ---------------------------------------------------------------------------

def resolve_name(ticker: str) -> str:
    """
    Gibt den Firmennamen fuer einen Ticker zurueck.
    Reihenfolge: Cache -> In-Memory Wiki-Daten -> yfinance -> Ticker als Fallback.
    """
    # 1. Cache pruefen (SQLite + In-Memory)
    cached = _get_cached_name(ticker)
    if cached is not None:
        return cached

    # 2. yfinance als Fallback (Wiki wurde schon beim Preload geladen)
    name = _fetch_name_yfinance(ticker)
    if name and name != ticker:
        _save_to_cache(ticker, name)
    return name


def bulk_resolve(tickers: list[str]) -> dict[str, str]:
    """
    Loest mehrere Ticker auf einmal auf. Effiziente Batch-Operation.
    Nutzt Cache fuer bekannte Ticker, yfinance nur fuer fehlende.
    """
    result: dict[str, str] = {}
    missing: list[str] = []

    # Zuerst alles aus dem Cache holen
    for ticker in tickers:
        cached = _get_cached_name(ticker)
        if cached is not None:
            result[ticker] = cached
        else:
            missing.append(ticker)

    # Fehlende per yfinance nachladen
    if missing:
        logger.info("Lade %d fehlende Firmennamen via yfinance …", len(missing))
        new_names = {}
        for ticker in missing:
            name = _fetch_name_yfinance(ticker)
            result[ticker] = name
            if name != ticker:
                new_names[ticker] = name

        # Alle neuen auf einmal cachen
        _save_bulk_to_cache(new_names)

    return result


def preload_wiki_names() -> int:
    """
    Beim Scanner-Start aufrufen: Laedt Wikipedia-Firmennamen in den Cache.
    Gibt die Anzahl der geladenen Namen zurueck.
    """
    print("Lade Firmennamen von Wikipedia …")
    try:
        wiki_names = load_wiki_names()
        if wiki_names:
            _save_bulk_to_cache(wiki_names)
            print(f"  {len(wiki_names)} Firmennamen gecacht.")
            return len(wiki_names)
        else:
            print("  Keine Wikipedia-Namen geladen (Netzwerkfehler?).")
            return 0
    except Exception as e:
        logger.warning("Wikipedia-Preload fehlgeschlagen: %s", e)
        print(f"  Wikipedia-Preload fehlgeschlagen: {e}")
        return 0
