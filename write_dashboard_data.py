#!/usr/bin/env python3
"""Pusht Portfolio- und Backtesting-Daten an n8n Webhook zur Speicherung im Container."""
import json, sys, os, urllib.request
sys.path.insert(0, os.path.dirname(__file__))

N8N_BASE = os.environ.get("N8N_BASE_URL", "https://agents.umzwei.de")


def _post_json(path, data):
    """POST JSON an n8n Webhook."""
    url = f"{N8N_BASE}/webhook/{path}"
    payload = json.dumps(data).encode()
    req = urllib.request.Request(url, data=payload, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return result
    except Exception as e:
        print(f"  POST {path} fehlgeschlagen: {e}")
        return None


def push_portfolio():
    try:
        from cfd_portfolio import list_positions, check_positions
        positions = list_positions()
        reports = check_positions(positions) if positions else []
        result = _post_json("stock-update", {"type": "portfolio", "positions": reports})
        print(f"Portfolio: {len(reports)} Positionen gepusht -> {result}")
    except Exception as e:
        print(f"Portfolio-Fehler: {e}")


def push_backtesting():
    try:
        import sqlite3
        from pathlib import Path
        db = Path(__file__).parent / "cfd_backtesting.db"
        if not db.exists():
            return

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row

        total = conn.execute("SELECT COUNT(*) FROM cfd_signals").fetchone()[0]
        resolved = conn.execute("SELECT COUNT(*) FROM cfd_signals WHERE outcome IS NOT NULL").fetchone()[0]
        wins = conn.execute("SELECT COUNT(*) FROM cfd_signals WHERE outcome IN ('tp1','tp2')").fetchone()[0]
        win_rate = round((wins / resolved * 100) if resolved > 0 else 0, 1)
        r_row = conn.execute(
            "SELECT AVG(pnl_r) as a, SUM(pnl_r) as s FROM cfd_signals "
            "WHERE outcome IS NOT NULL AND pnl_r IS NOT NULL"
        ).fetchone()
        avg_r = round(r_row[0] or 0, 2)
        total_r = round(r_row[1] or 0, 2)

        by_direction = [dict(r) for r in conn.execute(
            "SELECT direction, COUNT(*) as cnt, "
            "SUM(CASE WHEN outcome IN ('tp1','tp2') THEN 1 ELSE 0 END) as wins, "
            "AVG(pnl_r) as avg_r, SUM(pnl_r) as total_r "
            "FROM cfd_signals WHERE outcome IS NOT NULL GROUP BY direction")]
        by_market = [dict(r) for r in conn.execute(
            "SELECT market, COUNT(*) as cnt, "
            "SUM(CASE WHEN outcome IN ('tp1','tp2') THEN 1 ELSE 0 END) as wins, "
            "AVG(pnl_r) as avg_r, SUM(pnl_r) as total_r "
            "FROM cfd_signals WHERE outcome IS NOT NULL GROUP BY market ORDER BY cnt DESC")]
        outcomes = [dict(r) for r in conn.execute(
            "SELECT outcome, COUNT(*) as cnt FROM cfd_signals "
            "WHERE outcome IS NOT NULL GROUP BY outcome ORDER BY cnt DESC")]
        by_score_range = [dict(r) for r in conn.execute(
            "SELECT CASE WHEN quality_score>=8 THEN '8.0+' "
            "WHEN quality_score>=7 THEN '7.0-7.9' "
            "WHEN quality_score>=6 THEN '6.0-6.9' "
            "WHEN quality_score>=5 THEN '5.0-5.9' "
            "ELSE '<5.0' END as range, "
            "COUNT(*) as cnt, "
            "SUM(CASE WHEN outcome IN ('tp1','tp2') THEN 1 ELSE 0 END) as wins, "
            "SUM(CASE WHEN outcome IN ('tp1','tp2') THEN 1 ELSE 0 END)*100.0/COUNT(*) as win_pct, "
            "AVG(pnl_r) as avg_r, SUM(pnl_r) as total_r "
            "FROM cfd_signals WHERE outcome IS NOT NULL GROUP BY range ORDER BY range DESC")]
        recent = [dict(r) for r in conn.execute(
            "SELECT ticker, market, direction, quality_score, entry_price, exit_price, "
            "outcome, outcome_day, pnl_r, max_favorable, max_adverse "
            "FROM cfd_signals WHERE outcome IS NOT NULL ORDER BY resolved_at DESC LIMIT 20")]
        conn.close()

        data = {
            "type": "backtesting",
            "total": total, "resolved": resolved, "wins": wins, "win_rate": win_rate,
            "avg_r": avg_r, "total_r": total_r, "by_direction": by_direction,
            "by_market": by_market, "outcomes": outcomes, "by_score_range": by_score_range,
            "recent": recent,
        }
        result = _post_json("stock-update", data)
        print(f"Backtesting: {total} Signale, {resolved} resolved gepusht -> {result}")
    except Exception as e:
        print(f"Backtesting-Fehler: {e}")


if __name__ == "__main__":
    push_portfolio()
    push_backtesting()
