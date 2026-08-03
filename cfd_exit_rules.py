#!/usr/bin/env python3
"""CFD Exit-Regeln — Signal-Engine Stufe 1 (Exit-Wächter).

Importierbares Modul, aufgerufen am Ende des EOD-Scans (`stock_scanner.py`).
Prüft die OFFENEN realen Revolut-CFD-Positionen (aus dem Trade-History-Store
`revolut_cfd.db` des Unified-Dashboards — NICHT dem alten, leeren
`cfd_portfolio.json`) gegen die frische `cfd_setups.csv` auf die HARTEN Exit-
Trigger aus `CFD_TRADING_RULES.md` §5 und schickt bei einem Pflicht-Trigger
einen Telegram-Alert **„SCHLIESSEN morgen"**. Adressiert die Disziplin-Lücke
aus dem STT-Fall (Score 4,5 + raus aus Setups + Zeit-Stop 13 > 7 — drei ignoriert).

Regelbasiert, KEIN LLM/API (Kosten-Regel).

Pflicht-Trigger (§5):
  - Setup-Erosion: Score < 5,0  ODER  Ticker raus aus cfd_setups.csv
  - Zeit-Stop: ≥ 7 Handelstage seit Entry ohne TP1 (Position noch in voller Größe)
  - Earnings-Gate: nächster Termin ≤ 5 Tage (Gap-Risiko, das kein Stop auffängt)
Warnung (beobachten):
  - MACD dreht gegen die Richtung + Score unter Entry-Schwelle 7,0
    (voller "MACD dreht + Score fällt"-Trigger braucht Entry-Historie -> Stufe 2)
"""

import csv
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCANNER_DIR = Path(__file__).resolve().parent
SETUPS_PATH = SCANNER_DIR / "cfd_setups.csv"
# Trade-History-Store liegt beim Unified-Dashboard (offene Positionen)
REVOLUT_DB = Path(os.environ.get(
    "REVOLUT_DB", "/home/claude-agent/unified-dashboard/revolut_cfd.db"))

SCORE_EXIT = 5.0        # Setup-Erosion unter diesem Score
ENTRY_SCORE = 7.0       # Entry-Schwelle (für MACD-Warnung)
TIME_STOP_DAYS = 7      # Handelstage ohne TP1


def load_setups(path: Path = SETUPS_PATH) -> dict:
    """cfd_setups.csv -> {ticker: row}. Leeres Dict, wenn Datei fehlt."""
    if not Path(path).exists():
        return {}
    with open(path, encoding="utf-8-sig") as f:
        return {row["ticker"].strip().upper(): row for row in csv.DictReader(f)}


def get_open_positions(db_path: Path = REVOLUT_DB) -> list[dict]:
    """Offene reale CFD-Positionen aus revolut_cfd.db (exit_date IS NULL)."""
    if not Path(db_path).exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT symbol, direction, quantity, entry_date, entry_price "
            "FROM revolut_trades WHERE exit_date IS NULL ORDER BY entry_date"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _to_float(val, default=None):
    try:
        return float(str(val).strip())
    except (ValueError, TypeError, AttributeError):
        return default


def trading_days_since(entry_iso: str, today) -> int:
    """Handelstage (Mo–Fr) zwischen Entry-Datum und today (Feiertage ignoriert)."""
    try:
        d = datetime.fromisoformat(str(entry_iso).replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return 0
    days = 0
    while d < today:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days += 1
    return days


def evaluate_position(pos: dict, setups: dict, today) -> dict:
    """Prüft eine offene Position gegen §5. Liefert Trigger + Warnungen."""
    ticker = str(pos["symbol"]).split(":")[0].strip().upper()  # "CVS:CFD" -> "CVS"
    direction = (pos.get("direction") or "long").lower()
    triggers: list[str] = []   # Pflicht -> "SCHLIESSEN morgen"
    warnings: list[str] = []   # beobachten

    row = setups.get(ticker)
    if row is None:
        triggers.append("Setup-Erosion: Ticker raus aus cfd_setups.csv")
    else:
        score_col = "cfd_long_score" if direction == "long" else "cfd_short_score"
        score = _to_float(row.get(score_col))
        if score is not None and score < SCORE_EXIT:
            triggers.append(f"Setup-Erosion: Score {score:.1f} < {SCORE_EXIT:.0f}")

        if str(row.get("earnings_gate", "")).strip().lower() == "true":
            nxt = str(row.get("next_earnings", "")).strip() or "?"
            triggers.append(f"Earnings-Gate: nächster Termin {nxt} (≤5 Tage → Gap-Risiko)")

        macd = str(row.get("macd", "")).strip().lower()
        against = (direction == "long" and macd == "bearish") or \
                  (direction == "short" and macd == "bullish")
        if against and score is not None and score < ENTRY_SCORE:
            warnings.append(f"MACD {macd} gegen {direction} + Score {score:.1f} < {ENTRY_SCORE:.0f}")

    tdays = trading_days_since(pos.get("entry_date"), today)
    if tdays >= TIME_STOP_DAYS:
        triggers.append(f"Zeit-Stop: {tdays} Handelstage seit Entry ohne TP1 (≥{TIME_STOP_DAYS})")

    return {"ticker": ticker, "direction": direction, "pos": pos,
            "triggers": triggers, "warnings": warnings, "trading_days": tdays}


def format_alert(ev: dict) -> str:
    pos = ev["pos"]
    qty = _to_float(pos.get("quantity"), 0) or 0
    entry = _to_float(pos.get("entry_price"), 0) or 0
    lines = [
        f"🚨 <b>SCHLIESSEN morgen — {ev['ticker']} {ev['direction'].upper()}</b>",
        f"{qty:.0f} Stk @ {entry:.2f}",
        "<b>Pflicht-Trigger (§5):</b>",
    ]
    lines += [f"• {t}" for t in ev["triggers"]]
    if ev["warnings"]:
        lines.append("<i>Zusätzlich:</i>")
        lines += [f"• {w}" for w in ev["warnings"]]
    lines.append("Realen Revolut-Stop separat prüfen (steht nicht im Statement).")
    return "\n".join(lines)


def run_exit_check(setups_path: Path = SETUPS_PATH, db_path: Path = REVOLUT_DB,
                   today=None, send: bool = True) -> list[dict]:
    """Kompletter Exit-Check: bewertet alle offenen Positionen und schickt bei
    Pflicht-Triggern einen Telegram-Alert. Gibt die Bewertungen zurück.

    send=False -> nur bewerten (kein Telegram), für Tests/Dry-Run.
    """
    today = today or datetime.now(timezone.utc).date()
    positions = get_open_positions(db_path)
    if not positions:
        return []
    setups = load_setups(setups_path)
    if not setups:
        # Ohne Setups kein verlässlicher Erosions-Check -> nicht blind Alarm schlagen.
        return [{"ticker": str(p["symbol"]).split(":")[0], "direction": p.get("direction"),
                 "pos": p, "triggers": [],
                 "warnings": ["cfd_setups.csv leer/fehlt — Check übersprungen"],
                 "trading_days": 0} for p in positions]

    evals = [evaluate_position(p, setups, today) for p in positions]
    if send:
        from telegram_alerts import send_message
        for ev in evals:
            if ev["triggers"]:
                send_message(format_alert(ev))
    return evals


if __name__ == "__main__":
    # Manueller Dry-Run zum Testen (Produktivpfad = Import aus stock_scanner.py).
    import argparse
    ap = argparse.ArgumentParser(description="CFD Exit-Regeln — manueller Dry-Run")
    ap.add_argument("--setups", type=Path, default=SETUPS_PATH)
    ap.add_argument("--db", type=Path, default=REVOLUT_DB)
    args = ap.parse_args()
    results = run_exit_check(args.setups, args.db, send=False)
    print(f"{len(results)} offene Position(en) geprüft.")
    for ev in results:
        status = "ALERT" if ev["triggers"] else ("warn" if ev["warnings"] else "ok")
        print(f"  {ev['ticker']} {ev['direction']}: {status} — "
              f"{' | '.join(ev['triggers'] + ev['warnings']) or '(nichts)'}")
        if ev["triggers"]:
            print(format_alert(ev))
