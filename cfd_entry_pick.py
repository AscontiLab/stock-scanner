#!/usr/bin/env python3
"""CFD Entry-Empfehlung — Signal-Engine Stufe 2 (genau EIN Trade).

Importierbares Modul, aufgerufen am Ende des EOD-Scans (`stock_scanner.py`).
Wendet die STRENGEN Regeln aus `CFD_TRADING_RULES.md` (§2 Filter, §3 Frische +
Entry-Zone, §4 Sizing, §6 Fee-Gate) auf die frischen `cfd_setups.csv`-Kandidaten
an, einigt sich sweetspot-gerankt auf GENAU EINEN und schickt per Telegram:
„MORGEN KAUFEN: TICKER long — Entry-Zone X–Y, Stop Z, TP1/TP2" — oder „kein Trade
morgen" + Grund. Nur wenn KEINE Position offen ist (1-Positions-Regel §4).

Regelbasiert, KEIN LLM/API (Kosten-Regel). Ergänzt den Exit-Wächter
(`cfd_exit_rules.py`) — zusammen = geschlossener Regel-Loop (Entry + Exit).
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

SCANNER_DIR = Path(__file__).resolve().parent
SETUPS_PATH = SCANNER_DIR / "cfd_setups.csv"
OUTPUT_DIR = SCANNER_DIR / "output"   # dated Historie für Frische-Check

# --- Schwellen (CFD_TRADING_RULES.md; hier zentral tunebar) ---
SCORE_MIN = 7.0
SWEET_SCORE = (7.0, 7.9)     # Backtest-Sweetspot schlägt 8+
ADX_MIN, ADX_MAX = 30.0, 42.0
ADX_SWEET = 37.0             # Zentrum 35–39 (76 % Win)
RSI_LONG = (45.0, 68.0)
RSI_SHORT = (38.0, 55.0)
GAP_MAX = 4.0
ATR_PCT_MIN, ATR_PCT_MAX = 1.0, 3.0
FRESH_MAX_DAY = 2            # nur Tag 1 oder 2
ENTRY_ZONE_ATR = 0.5        # Limit-Zone = Preis ± 0,5×ATR
STOP_DIST_MAX_PCT = 4.0     # §4: Stop-Distanz ≤ 4 %
# Fee-Gate (§6)
FEE_BASE_PCT = 0.50         # 0,25 % je Seite
FEE_PER_DAY_PCT = 0.02
HOLD_DAYS_ASSUMED = 7       # bis Zeit-Stop
FEE_GATE_MULT = 3.0
TP1_ATR_MULT = 1.5


def _f(val, default=None):
    try:
        return float(str(val).strip())
    except (ValueError, TypeError, AttributeError):
        return default


def load_setups(path: Path = SETUPS_PATH) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def fee_gate(atr_pct: float) -> tuple[bool, float, float]:
    """TP1 % (= 1,5×ATR%) muss ≥ 3× Round-Trip-Kosten % sein."""
    tp1_pct = TP1_ATR_MULT * atr_pct
    cost_pct = FEE_BASE_PCT + FEE_PER_DAY_PCT * HOLD_DAYS_ASSUMED
    return tp1_pct >= FEE_GATE_MULT * cost_pct, tp1_pct, cost_pct


def freshness_day(ticker: str, direction: str, output_dir: Path, today) -> int:
    """Wie oft steht der Ticker in Folge (inkl. heute) in cfd_setups.csv für die
    Richtung? Tag 1 = gestern NICHT drin. Zählt aufeinanderfolgende Vortage."""
    score_col = "cfd_long_score" if direction == "long" else "cfd_short_score"
    if not Path(output_dir).is_dir():
        return 1  # keine Historie -> als frisch behandeln
    prior = sorted((d.name for d in Path(output_dir).iterdir()
                    if d.is_dir() and d.name < str(today)), reverse=True)
    consec = 0
    for dname in prior:
        csv_path = Path(output_dir) / dname / "cfd_setups.csv"
        if not csv_path.exists():
            break
        present = any(
            r.get("ticker", "").strip().upper() == ticker
            and (_f(r.get(score_col)) or 0) >= SCORE_MIN
            for r in load_setups(csv_path))
        if present:
            consec += 1
        else:
            break
    return consec + 1


def check_candidate(row: dict, direction: str, output_dir: Path, today) -> dict:
    """Prüft eine Kandidatenzeile gegen ALLE harten Filter. Liefert pass + Gründe."""
    ticker = row.get("ticker", "").strip().upper()
    score = _f(row.get("cfd_long_score" if direction == "long" else "cfd_short_score"))
    adx = _f(row.get("adx"))
    rsi = _f(row.get("rsi"))
    gap = _f(row.get("recent_max_gap"))
    atr_pct = _f(row.get("atr_pct"))
    price = _f(row.get("price"))
    stop = _f(row.get("stop_long" if direction == "long" else "stop_short"))

    fails = []
    if score is None or score < SCORE_MIN:
        fails.append(f"Score {score} < {SCORE_MIN}")
    if adx is None or not (ADX_MIN <= adx <= ADX_MAX):
        fails.append(f"ADX {adx} außerhalb {ADX_MIN:.0f}–{ADX_MAX:.0f}")
    rsi_lo, rsi_hi = RSI_LONG if direction == "long" else RSI_SHORT
    if rsi is None or not (rsi_lo <= rsi <= rsi_hi):
        fails.append(f"RSI {rsi} außerhalb {rsi_lo:.0f}–{rsi_hi:.0f}")
    if gap is not None and gap >= GAP_MAX:
        fails.append(f"Gap {gap} ≥ {GAP_MAX}")
    if atr_pct is None or not (ATR_PCT_MIN <= atr_pct <= ATR_PCT_MAX):
        fails.append(f"ATR% {atr_pct} außerhalb {ATR_PCT_MIN}–{ATR_PCT_MAX}")
    if str(row.get("earnings_gate", "")).strip().lower() == "true":
        fails.append(f"Earnings ≤5 Tage ({row.get('next_earnings','?')})")

    day = freshness_day(ticker, direction, output_dir, today)
    if day > FRESH_MAX_DAY:
        fails.append(f"Frische Tag {day} (> {FRESH_MAX_DAY})")

    ok_fee, tp1_pct, cost_pct = (False, None, None)
    if atr_pct is not None:
        ok_fee, tp1_pct, cost_pct = fee_gate(atr_pct)
        if not ok_fee:
            fails.append(f"Fee-Gate: TP1 {tp1_pct:.1f}% < {FEE_GATE_MULT*cost_pct:.1f}%")

    # Stop-Distanz ≤ 4 % (§4)
    stop_dist_pct = None
    if price and stop:
        stop_dist_pct = abs(price - stop) / price * 100
        if stop_dist_pct > STOP_DIST_MAX_PCT:
            fails.append(f"Stop-Distanz {stop_dist_pct:.1f}% > {STOP_DIST_MAX_PCT}%")

    return {"ticker": ticker, "direction": direction, "row": row, "fails": fails,
            "passes": not fails, "score": score, "adx": adx, "rsi": rsi,
            "atr_pct": atr_pct, "price": price, "stop": stop, "day": day,
            "tp1_pct": tp1_pct, "cost_pct": cost_pct, "stop_dist_pct": stop_dist_pct}


def fit_score(cand: dict) -> float:
    """Sweetspot-Ranking (höher = besser). Long-Bias + Score 7–7,9 + ADX≈37."""
    s = 3.0 if cand["direction"] == "long" else 0.0
    score = cand["score"] or 0
    s += 2.0 if SWEET_SCORE[0] <= score <= SWEET_SCORE[1] else 1.0
    if cand["adx"] is not None:
        s += max(0.0, 2.0 - abs(cand["adx"] - ADX_SWEET) / 5.0)
    s += score * 0.1  # Tie-Break
    return s


def pick_entry(setups: list[dict], output_dir: Path = OUTPUT_DIR,
               today=None, has_open: bool = False) -> dict:
    """Einigt sich auf genau EINEN Trade oder liefert Grund für 'kein Trade'."""
    today = today or datetime.now(timezone.utc).date()
    if has_open:
        return {"pick": None, "reason": "Position offen — kein neuer Entry (1-Positions-Regel)."}

    cands = [check_candidate(r, "long", output_dir, today) for r in setups] + \
            [check_candidate(r, "short", output_dir, today) for r in setups]
    survivors = [c for c in cands if c["passes"]]
    if not survivors:
        # Warum? Top-3 Kandidaten (nach Score) mit ihren Fehlgründen zeigen.
        ranked = sorted([c for c in cands if c["score"]],
                        key=lambda c: -(c["score"] or 0))[:3]
        why = "; ".join(f"{c['ticker']} {c['direction']}: {', '.join(c['fails'])}"
                        for c in ranked) or "keine Kandidaten ≥ Score 7"
        return {"pick": None, "reason": f"kein Setup passiert die Filter — {why}"}

    best = max(survivors, key=fit_score)
    return {"pick": best, "reason": None, "n_survivors": len(survivors)}


def format_recommendation(res: dict) -> str:
    if res["pick"] is None:
        return f"🚫 <b>Kein Trade morgen</b>\n{res['reason']}"
    c = res["pick"]
    price, atr_pct = c["price"], c["atr_pct"]
    atr_abs = price * atr_pct / 100 if price and atr_pct else 0
    lo = price - ENTRY_ZONE_ATR * atr_abs
    hi = price + ENTRY_ZONE_ATR * atr_abs
    r = c["row"]
    tp1 = _f(r.get("tp1_long" if c["direction"] == "long" else "tp1_short"))
    tp2 = _f(r.get("tp2_long" if c["direction"] == "long" else "tp2_short"))
    lines = [
        f"📈 <b>MORGEN: {c['ticker']} {c['direction'].upper()}</b>  (1 Position)",
        f"Score {c['score']:.1f} | ADX {c['adx']:.0f} | RSI {c['rsi']:.0f} | ATR% {atr_pct:.1f} | Frische Tag {c['day']}",
        f"<b>Entry-Zone (Limit): {lo:.2f} – {hi:.2f}</b>",
        f"<b>Stop: {c['stop']:.2f}</b> (−{c['stop_dist_pct']:.1f}%)"
        + (f" | TP1: {tp1:.2f}" if tp1 else "")
        + (f" | TP2: {tp2:.2f}" if tp2 else ""),
        f"Fee-Gate ✓ (TP1 {c['tp1_pct']:.1f}% ≥ {FEE_GATE_MULT*c['cost_pct']:.1f}%)",
        "Stop SOFORT als echte Order bei Revolut setzen; nur nachziehen, nie lockern.",
    ]
    return "\n".join(lines)


def run_entry_pick(setups_path: Path = SETUPS_PATH, output_dir: Path = OUTPUT_DIR,
                   revolut_db: Path = None, today=None, send: bool = True) -> dict:
    """Kompletter Entry-Pick + Telegram. send=False -> nur berechnen (Tests)."""
    setups = load_setups(setups_path)
    has_open = False
    try:
        from cfd_exit_rules import get_open_positions, REVOLUT_DB
        has_open = bool(get_open_positions(revolut_db or REVOLUT_DB))
    except Exception:
        pass
    res = pick_entry(setups, output_dir, today, has_open)
    if send:
        from telegram_alerts import send_message
        send_message(format_recommendation(res))
    return res


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="CFD Entry-Empfehlung — manueller Dry-Run")
    ap.add_argument("--setups", type=Path, default=SETUPS_PATH)
    args = ap.parse_args()
    res = run_entry_pick(args.setups, send=False)
    print(format_recommendation(res).replace("<b>", "").replace("</b>", ""))
