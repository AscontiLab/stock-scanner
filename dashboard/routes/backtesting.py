"""Backtesting-Statistiken aus der SQLite-Datenbank."""

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from dashboard.config import settings

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

DB_PATH = settings.SCANNER_DIR / "cfd_backtesting.db"


def _query(sql: str, params=()) -> list[dict]:
    """Fuehrt SQL-Query aus und gibt Liste von Dicts zurueck."""
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    return rows


def _get_stats() -> dict:
    """Berechnet alle Backtesting-Statistiken."""
    if not DB_PATH.exists():
        return {"total": 0, "resolved": 0, "open": 0}

    # Gesamt-Stats
    total_row = _query("SELECT COUNT(*) as cnt FROM cfd_signals")
    total = total_row[0]["cnt"] if total_row else 0

    resolved_row = _query("SELECT COUNT(*) as cnt FROM cfd_signals WHERE outcome IS NOT NULL")
    resolved = resolved_row[0]["cnt"] if resolved_row else 0

    open_count = total - resolved

    # Win-Rate (TP1 oder TP2 = Win)
    wins_row = _query(
        "SELECT COUNT(*) as cnt FROM cfd_signals WHERE outcome IN ('tp1', 'tp2')"
    )
    wins = wins_row[0]["cnt"] if wins_row else 0
    win_rate = (wins / resolved * 100) if resolved > 0 else 0

    # Avg R und Total R
    r_row = _query(
        "SELECT AVG(pnl_r) as avg_r, SUM(pnl_r) as total_r "
        "FROM cfd_signals WHERE outcome IS NOT NULL AND pnl_r IS NOT NULL"
    )
    avg_r = r_row[0]["avg_r"] if r_row and r_row[0]["avg_r"] else 0
    total_r = r_row[0]["total_r"] if r_row and r_row[0]["total_r"] else 0

    # Nach Richtung
    by_direction = _query(
        "SELECT direction, COUNT(*) as cnt, "
        "SUM(CASE WHEN outcome IN ('tp1','tp2') THEN 1 ELSE 0 END) as wins, "
        "AVG(pnl_r) as avg_r, SUM(pnl_r) as total_r "
        "FROM cfd_signals WHERE outcome IS NOT NULL "
        "GROUP BY direction"
    )

    # Nach Markt
    by_market = _query(
        "SELECT market, COUNT(*) as cnt, "
        "SUM(CASE WHEN outcome IN ('tp1','tp2') THEN 1 ELSE 0 END) as wins, "
        "AVG(pnl_r) as avg_r, SUM(pnl_r) as total_r "
        "FROM cfd_signals WHERE outcome IS NOT NULL "
        "GROUP BY market ORDER BY cnt DESC"
    )

    # Outcome-Verteilung
    outcomes = _query(
        "SELECT outcome, COUNT(*) as cnt FROM cfd_signals "
        "WHERE outcome IS NOT NULL GROUP BY outcome ORDER BY cnt DESC"
    )

    # Nach Score-Bereich
    by_score_range = _query(
        """SELECT
            CASE
                WHEN quality_score >= 8 THEN '8.0+'
                WHEN quality_score >= 7 THEN '7.0-7.9'
                WHEN quality_score >= 6 THEN '6.0-6.9'
                WHEN quality_score >= 5 THEN '5.0-5.9'
                ELSE '<5.0'
            END as range_label,
            COUNT(*) as cnt,
            SUM(CASE WHEN outcome IN ('tp1','tp2') THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome IN ('tp1','tp2') THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_pct,
            AVG(pnl_r) as avg_r,
            SUM(pnl_r) as total_r
        FROM cfd_signals WHERE outcome IS NOT NULL
        GROUP BY range_label
        ORDER BY range_label DESC"""
    )
    # Rename key for template
    for row in by_score_range:
        row["range"] = row.pop("range_label")

    by_gap_bucket = _query(
        """SELECT
            CASE
                WHEN recent_max_gap < 2 THEN '<2%'
                WHEN recent_max_gap < 4 THEN '2-3.9%'
                WHEN recent_max_gap < 6 THEN '4-5.9%'
                ELSE '6%+'
            END as bucket,
            COUNT(*) as cnt,
            SUM(CASE WHEN outcome IN ('tp1','tp2') THEN 1 ELSE 0 END) as wins,
            AVG(pnl_r) as avg_r
        FROM cfd_signals WHERE outcome IS NOT NULL
        GROUP BY bucket
        ORDER BY CASE bucket
            WHEN '<2%' THEN 1
            WHEN '2-3.9%' THEN 2
            WHEN '4-5.9%' THEN 3
            ELSE 4
        END"""
    )

    by_atr_bucket = _query(
        """SELECT
            CASE
                WHEN atr_pct < 1 THEN '<1%'
                WHEN atr_pct < 2 THEN '1-1.9%'
                WHEN atr_pct < 3 THEN '2-2.9%'
                ELSE '3%+'
            END as bucket,
            COUNT(*) as cnt,
            SUM(CASE WHEN outcome IN ('tp1','tp2') THEN 1 ELSE 0 END) as wins,
            AVG(pnl_r) as avg_r
        FROM cfd_signals WHERE outcome IS NOT NULL
        GROUP BY bucket
        ORDER BY CASE bucket
            WHEN '<1%' THEN 1
            WHEN '1-1.9%' THEN 2
            WHEN '2-2.9%' THEN 3
            ELSE 4
        END"""
    )

    by_market_direction = _query(
        """SELECT market, direction, COUNT(*) as cnt,
            SUM(CASE WHEN outcome IN ('tp1','tp2') THEN 1 ELSE 0 END) as wins,
            AVG(pnl_r) as avg_r, SUM(pnl_r) as total_r
        FROM cfd_signals
        WHERE outcome IS NOT NULL
        GROUP BY market, direction
        ORDER BY market ASC, direction ASC"""
    )

    # Letzte 20 aufgeloeste Signale
    recent = _query(
        "SELECT ticker, market, direction, quality_score, entry_price, "
        "exit_price, outcome, outcome_day, pnl_r, max_favorable, max_adverse, resolved_at "
        "FROM cfd_signals WHERE outcome IS NOT NULL "
        "ORDER BY resolved_at DESC LIMIT 20"
    )

    return {
        "total": total,
        "resolved": resolved,
        "open": open_count,
        "wins": wins,
        "win_rate": round(win_rate, 1),
        "avg_r": round(avg_r, 2),
        "total_r": round(total_r, 2),
        "by_direction": by_direction,
        "by_market": by_market,
        "by_score_range": by_score_range,
        "by_gap_bucket": by_gap_bucket,
        "by_atr_bucket": by_atr_bucket,
        "by_market_direction": by_market_direction,
        "outcomes": outcomes,
        "recent": recent,
    }


@router.get("/backtesting", response_class=HTMLResponse)
async def backtesting_page(request: Request):
    stats = _get_stats()
    return templates.TemplateResponse("backtesting.html", {"request": request, **stats})


@router.get("/api/backtesting")
async def backtesting_json():
    return _get_stats()
