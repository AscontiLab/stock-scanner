#!/usr/bin/env python3
"""
CFD Backtesting-Modul fuer den Stock Scanner.

Speichert jedes CFD-Signal in SQLite, loest nach 1-10 Trading-Tagen auf
(Stop/TP1/TP2 getroffen?) und berechnet P&L in R-Multiples.

DB: cfd_backtesting.db (im Scanner-Verzeichnis)

Verwendung in stock_scanner.py:
    from cfd_backtesting import init_db, log_scan_run, log_cfd_signal, resolve_signals

    init_db()
    run_id = log_scan_run(scan_date, fear_greed_value, ticker_count)
    for signal in cfd_signals:
        log_cfd_signal(run_id, signal, direction)
    resolve_signals()

CLI:
    python3 cfd_backtesting.py summary    # Win-Rate, avg R, nach Markt/Richtung
    python3 cfd_backtesting.py open       # offene Signale
    python3 cfd_backtesting.py resolve    # Ergebnisse abrufen
"""

import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "cfd_backtesting.db"


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA
# ═══════════════════════════════════════════════════════════════════════════════

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cfd_scan_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date       TEXT    NOT NULL,
    scanned_at      TEXT    NOT NULL,
    fear_greed      INTEGER,
    ticker_count    INTEGER,
    long_signals    INTEGER DEFAULT 0,
    short_signals   INTEGER DEFAULT 0,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS cfd_signals (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            INTEGER NOT NULL REFERENCES cfd_scan_runs(id),

    -- Signal-Identifikation
    ticker            TEXT    NOT NULL,
    market            TEXT,
    direction         TEXT    NOT NULL,    -- "long" | "short"

    -- Scoring
    quality_score     REAL    NOT NULL,    -- gewichteter Score (0-10)
    adx               REAL,
    plus_di           REAL,
    minus_di          REAL,
    rsi               REAL,
    vol_ratio         REAL,
    atr_pct           REAL,
    trend_days        INTEGER,            -- Trend-Reife in Tagen
    recent_max_gap    REAL,

    -- Levels
    entry_price       REAL    NOT NULL,
    stop_price        REAL    NOT NULL,
    tp1_price         REAL    NOT NULL,
    tp2_price         REAL    NOT NULL,

    -- Indikator-Snapshot (JSON)
    indicators_json   TEXT,

    -- Resolution (befuellt nach Aufloesung)
    resolved_at       TEXT,
    outcome           TEXT,               -- "stop" | "tp1" | "tp2" | "expired" | NULL
    outcome_day       INTEGER,            -- an welchem Trading-Tag
    exit_price        REAL,
    pnl_r             REAL,               -- P&L in R-Multiples (-1.0, +1.0, +2.67)
    max_favorable     REAL,               -- maximaler Gewinn in R
    max_adverse       REAL                -- maximaler Drawdown in R
);

CREATE INDEX IF NOT EXISTS idx_cfd_signals_ticker    ON cfd_signals(ticker);
CREATE INDEX IF NOT EXISTS idx_cfd_signals_outcome   ON cfd_signals(outcome);
CREATE INDEX IF NOT EXISTS idx_cfd_signals_direction ON cfd_signals(direction);
CREATE INDEX IF NOT EXISTS idx_cfd_signals_date      ON cfd_signals(run_id);
"""


# ═══════════════════════════════════════════════════════════════════════════════
# DB-Initialisierung
# ═══════════════════════════════════════════════════════════════════════════════

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Erstellt Tabellen falls noetig."""
    conn = _get_conn()
    conn.executescript(_SCHEMA)
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════════════════

def log_scan_run(scan_date: str, fear_greed: int = 50, ticker_count: int = 0,
                 long_signals: int = 0, short_signals: int = 0) -> int:
    """Loggt einen Scanner-Lauf, gibt run_id zurueck."""
    conn = _get_conn()
    cur = conn.execute(
        """INSERT INTO cfd_scan_runs (scan_date, scanned_at, fear_greed, ticker_count,
           long_signals, short_signals)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (scan_date, datetime.now().isoformat(), fear_greed, ticker_count,
         long_signals, short_signals),
    )
    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def log_cfd_signal(run_id: int, row: dict, direction: str) -> int:
    """Loggt ein einzelnes CFD-Signal, gibt signal_id zurueck."""
    score_key = f"cfd_{direction}_score"
    quality = row.get("cfd_quality_score", row.get(score_key, 0))

    if direction == "long":
        stop, tp1, tp2 = row["stop_long"], row["tp1_long"], row["tp2_long"]
        trend_days = row.get("trend_long_days", 0)
    else:
        stop, tp1, tp2 = row["stop_short"], row["tp1_short"], row["tp2_short"]
        trend_days = row.get("trend_short_days", 0)

    indicators = {
        "macd": row.get("macd", ""),
        "ma": row.get("ma", ""),
        "bollinger": row.get("bollinger", ""),
        "squeeze": row.get("squeeze", ""),
        "vwap": row.get("vwap", ""),
        "ema9_gt_ema21": direction == "long",
    }

    conn = _get_conn()
    cur = conn.execute(
        """INSERT INTO cfd_signals
           (run_id, ticker, market, direction, quality_score,
            adx, plus_di, minus_di, rsi, vol_ratio, atr_pct,
            trend_days, recent_max_gap,
            entry_price, stop_price, tp1_price, tp2_price,
            indicators_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, row["ticker"], row.get("market", ""),
         direction, quality,
         row.get("adx"), row.get("plus_di"), row.get("minus_di"),
         row.get("rsi"), row.get("vol_ratio"), row.get("atr_pct"),
         trend_days, row.get("recent_max_gap"),
         row["price"], stop, tp1, tp2,
         json.dumps(indicators)),
    )
    signal_id = cur.lastrowid
    conn.commit()
    conn.close()
    return signal_id


# ═══════════════════════════════════════════════════════════════════════════════
# Resolution
# ═══════════════════════════════════════════════════════════════════════════════

def resolve_signals(min_days: int = 1, max_days: int = 10):
    """
    Loest offene Signale auf: prueft per yfinance ob Stop, TP1 oder TP2
    zuerst getroffen wurde.
    """
    import yfinance as yf

    conn = _get_conn()
    open_signals = conn.execute(
        """SELECT s.*, r.scan_date FROM cfd_signals s
           JOIN cfd_scan_runs r ON s.run_id = r.id
           WHERE s.outcome IS NULL"""
    ).fetchall()

    if not open_signals:
        print("Keine offenen Signale zum Aufloesen.")
        conn.close()
        return

    # Nur Signale die alt genug sind
    today = datetime.now().date()
    eligible = []
    for sig in open_signals:
        scan_date = datetime.strptime(sig["scan_date"], "%Y-%m-%d").date()
        days_since = (today - scan_date).days
        if days_since >= min_days:
            eligible.append((sig, scan_date, min(days_since, max_days)))

    if not eligible:
        print(f"Keine Signale aelter als {min_days} Tag(e).")
        conn.close()
        return

    # Batch-Download aller Ticker
    tickers = list(set(sig["ticker"] for sig, _, _ in eligible))
    print(f"Lade Kursdaten fuer {len(tickers)} Ticker ...")

    try:
        data = yf.download(tickers, period=f"{max_days + 5}d", progress=False,
                           group_by="ticker", auto_adjust=True)
    except Exception as e:
        print(f"Download fehlgeschlagen: {e}")
        conn.close()
        return

    resolved_count = 0
    for sig, scan_date, days_avail in eligible:
        ticker = sig["ticker"]
        direction = sig["direction"]
        entry = sig["entry_price"]
        stop = sig["stop_price"]
        tp1 = sig["tp1_price"]
        tp2 = sig["tp2_price"]
        risk = abs(entry - stop)

        if risk == 0:
            continue

        # Kursdaten ab dem Tag NACH dem Scan
        try:
            if len(tickers) == 1:
                ticker_df = data
            else:
                ticker_df = data[ticker]
            if isinstance(ticker_df.columns, type(data.columns)) and hasattr(ticker_df.columns, 'droplevel'):
                try:
                    ticker_df.columns = ticker_df.columns.droplevel(1)
                except Exception:
                    pass

            # Filter: nur Tage nach scan_date
            mask = ticker_df.index.date > scan_date
            post_scan = ticker_df.loc[mask].head(max_days)
        except Exception:
            continue

        if post_scan.empty:
            # Signal zu neu oder keine Daten
            if days_avail > max_days:
                # Expired
                _resolve_signal(conn, sig["id"], "expired", days_avail,
                                float(entry), 0.0, 0.0, 0.0)
                resolved_count += 1
            continue

        outcome = None
        outcome_day = 0
        exit_price = entry
        max_fav = 0.0
        max_adv = 0.0

        for day_idx, (_, day_row) in enumerate(post_scan.iterrows(), 1):
            high_val = float(day_row["High"])
            low_val = float(day_row["Low"])
            close_val = float(day_row["Close"])

            if direction == "long":
                fav = (high_val - entry) / risk
                adv = (entry - low_val) / risk
                max_fav = max(max_fav, fav)
                max_adv = max(max_adv, adv)

                # Stop getroffen?
                if low_val <= stop:
                    outcome = "stop"
                    exit_price = stop
                    outcome_day = day_idx
                    break
                # TP2 getroffen?
                if high_val >= tp2:
                    outcome = "tp2"
                    exit_price = tp2
                    outcome_day = day_idx
                    break
                # TP1 getroffen?
                if high_val >= tp1 and outcome != "tp1":
                    outcome = "tp1"
                    exit_price = tp1
                    outcome_day = day_idx
                    # Weiter pruefen ob TP2 oder Stop noch kommt
            else:  # short
                fav = (entry - low_val) / risk
                adv = (high_val - entry) / risk
                max_fav = max(max_fav, fav)
                max_adv = max(max_adv, adv)

                if high_val >= stop:
                    outcome = "stop"
                    exit_price = stop
                    outcome_day = day_idx
                    break
                if low_val <= tp2:
                    outcome = "tp2"
                    exit_price = tp2
                    outcome_day = day_idx
                    break
                if low_val <= tp1 and outcome != "tp1":
                    outcome = "tp1"
                    exit_price = tp1
                    outcome_day = day_idx

        # Wenn nach max_days kein Ergebnis und genug Tage vergangen
        if outcome is None and days_avail >= max_days:
            outcome = "expired"
            exit_price = float(post_scan["Close"].iloc[-1])
            outcome_day = len(post_scan)

        if outcome is not None:
            if direction == "long":
                pnl_r = (exit_price - entry) / risk
            else:
                pnl_r = (entry - exit_price) / risk

            _resolve_signal(conn, sig["id"], outcome, outcome_day,
                            exit_price, round(pnl_r, 2),
                            round(max_fav, 2), round(max_adv, 2))
            resolved_count += 1

    conn.close()
    print(f"{resolved_count} Signal(e) aufgeloest.")


def _resolve_signal(conn, signal_id, outcome, day, exit_price, pnl_r, max_fav, max_adv):
    conn.execute(
        """UPDATE cfd_signals SET
           resolved_at = ?, outcome = ?, outcome_day = ?,
           exit_price = ?, pnl_r = ?,
           max_favorable = ?, max_adverse = ?
           WHERE id = ?""",
        (datetime.now().isoformat(), outcome, day,
         exit_price, pnl_r, max_fav, max_adv, signal_id),
    )
    conn.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# CLI — Summary / Open / Resolve
# ═══════════════════════════════════════════════════════════════════════════════

def cli_open():
    """Zeigt offene (unaufgeloeste) Signale."""
    init_db()
    conn = _get_conn()
    rows = conn.execute(
        """SELECT s.*, r.scan_date FROM cfd_signals s
           JOIN cfd_scan_runs r ON s.run_id = r.id
           WHERE s.outcome IS NULL
           ORDER BY r.scan_date DESC, s.quality_score DESC"""
    ).fetchall()
    conn.close()

    if not rows:
        print("Keine offenen Signale.")
        return

    print(f"\n{'='*100}")
    print(f"  OFFENE CFD-SIGNALE ({len(rows)})")
    print(f"{'='*100}\n")
    fmt = "{:<12s} {:<8s} {:<6s} {:<6s} {:<6s} {:<6s} {:<10s} {:<10s} {:<10s} {:<10s}"
    print(fmt.format("Datum", "Ticker", "Dir", "Score", "ADX", "RSI",
                      "Entry", "Stop", "TP1", "TP2"))
    print("-" * 86)
    for r in rows:
        print(fmt.format(
            r['scan_date'] or '?',
            r['ticker'],
            r['direction'],
            f"{r['quality_score']:.1f}",
            f"{r['adx'] or 0:.1f}",
            f"{r['rsi'] or 0:.1f}",
            f"{r['entry_price']:.2f}",
            f"{r['stop_price']:.2f}",
            f"{r['tp1_price']:.2f}",
            f"{r['tp2_price']:.2f}",
        ))


def cli_summary():
    """Zeigt Auswertung: Win-Rate, avg R, nach Markt/Richtung."""
    init_db()
    conn = _get_conn()

    # Gesamt-Statistik
    total = conn.execute("SELECT COUNT(*) FROM cfd_signals WHERE outcome IS NOT NULL").fetchone()[0]
    if total == 0:
        print("Noch keine aufgeloesten Signale vorhanden.")
        conn.close()
        return

    stats = conn.execute(
        """SELECT
           COUNT(*) as total,
           SUM(CASE WHEN pnl_r > 0 THEN 1 ELSE 0 END) as wins,
           SUM(CASE WHEN pnl_r <= 0 THEN 1 ELSE 0 END) as losses,
           AVG(pnl_r) as avg_r,
           SUM(pnl_r) as total_r,
           AVG(max_favorable) as avg_mfe,
           AVG(max_adverse) as avg_mae
           FROM cfd_signals WHERE outcome IS NOT NULL"""
    ).fetchone()

    print(f"\n{'='*60}")
    print(f"  CFD BACKTESTING SUMMARY")
    print(f"{'='*60}\n")
    win_rate = (stats["wins"] / stats["total"] * 100) if stats["total"] > 0 else 0
    print(f"  Gesamt:     {stats['total']} Signale")
    print(f"  Gewonnen:   {stats['wins']}  ({win_rate:.1f}%)")
    print(f"  Verloren:   {stats['losses']}")
    print(f"  Avg R:      {stats['avg_r']:.2f}")
    print(f"  Total R:    {stats['total_r']:.2f}")
    print(f"  Avg MFE:    {stats['avg_mfe']:.2f} R")
    print(f"  Avg MAE:    {stats['avg_mae']:.2f} R")

    # Nach Outcome
    print(f"\n  {'Outcome':<10} {'Anzahl':>8} {'Avg R':>8}")
    print(f"  {'-'*28}")
    for row in conn.execute(
        """SELECT outcome, COUNT(*) as cnt, AVG(pnl_r) as avg_r
           FROM cfd_signals WHERE outcome IS NOT NULL
           GROUP BY outcome ORDER BY cnt DESC"""
    ):
        print(f"  {row['outcome']:<10} {row['cnt']:>8} {row['avg_r']:>8.2f}")

    # Nach Richtung
    print(f"\n  {'Richtung':<10} {'Anzahl':>8} {'Win%':>8} {'Avg R':>8}")
    print(f"  {'-'*38}")
    for row in conn.execute(
        """SELECT direction,
           COUNT(*) as cnt,
           SUM(CASE WHEN pnl_r > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_pct,
           AVG(pnl_r) as avg_r
           FROM cfd_signals WHERE outcome IS NOT NULL
           GROUP BY direction"""
    ):
        print(f"  {row['direction']:<10} {row['cnt']:>8} {row['win_pct']:>7.1f}% {row['avg_r']:>8.2f}")

    # Nach Markt
    print(f"\n  {'Markt':<15} {'Anzahl':>8} {'Win%':>8} {'Avg R':>8}")
    print(f"  {'-'*43}")
    for row in conn.execute(
        """SELECT market,
           COUNT(*) as cnt,
           SUM(CASE WHEN pnl_r > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_pct,
           AVG(pnl_r) as avg_r
           FROM cfd_signals WHERE outcome IS NOT NULL
           GROUP BY market ORDER BY cnt DESC"""
    ):
        print(f"  {row['market']:<15} {row['cnt']:>8} {row['win_pct']:>7.1f}% {row['avg_r']:>8.2f}")

    # Letzte 10 aufgeloeste Signale
    print(f"\n  LETZTE 10 AUFGELOESTE SIGNALE:")
    print(f"  {'Datum':<12} {'Ticker':<10} {'Dir':<6} {'Score':>6} {'Outcome':<8} {'R':>6} {'Tag':>4}")
    print(f"  {'-'*56}")
    for row in conn.execute(
        """SELECT s.*, r.scan_date FROM cfd_signals s
           JOIN cfd_scan_runs r ON s.run_id = r.id
           WHERE s.outcome IS NOT NULL
           ORDER BY s.resolved_at DESC LIMIT 10"""
    ):
        print(f"  {row['scan_date']:<12} {row['ticker']:<10} {row['direction']:<6} "
              f"{row['quality_score']:>6.1f} {row['outcome']:<8} "
              f"{row['pnl_r']:>+6.2f} {row['outcome_day']:>4}")

    conn.close()


def cli_resolve():
    """Loest offene Signale per yfinance auf."""
    init_db()
    resolve_signals()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if cmd == "summary":
        cli_summary()
    elif cmd == "open":
        cli_open()
    elif cmd == "resolve":
        cli_resolve()
    else:
        print(f"Unbekannter Befehl: {cmd}")
        print("Verwendung: python3 cfd_backtesting.py [summary|open|resolve]")
