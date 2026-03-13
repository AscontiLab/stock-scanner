#!/usr/bin/env python3
"""
CFD-Portfolio-Tracker für den Stock Scanner.

Speichert aktive CFD-Positionen in einer JSON-Datei und prüft
täglich den Status jeder Position mit Empfehlung: HALTEN / SCHLIESSEN / etc.

Verwendung:
    python3 stock_scanner.py --add-position AAPL long
    python3 stock_scanner.py --close-position AAPL
    python3 stock_scanner.py --positions
"""

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

PORTFOLIO_PATH = Path(__file__).parent / "cfd_portfolio.json"

_EMPTY_PORTFOLIO = {"positions": []}


def load_portfolio() -> dict:
    """Lädt das Portfolio aus der JSON-Datei."""
    if not PORTFOLIO_PATH.exists():
        return _EMPTY_PORTFOLIO.copy()
    try:
        data = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
        if "positions" not in data:
            data["positions"] = []
        return data
    except Exception:
        return _EMPTY_PORTFOLIO.copy()


def save_portfolio(data: dict) -> None:
    """Speichert das Portfolio in die JSON-Datei."""
    PORTFOLIO_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_position(
    ticker: str,
    direction: str,
    entry_price: float | None = None,
    stop: float | None = None,
    tp1: float | None = None,
    tp2: float | None = None,
    atr: float | None = None,
    score: float | None = None,
    market: str = "",
) -> dict:
    """
    Fügt eine Position zum Portfolio hinzu.

    Wenn entry_price/stop/tp1/tp2 nicht angegeben werden,
    wird versucht, sie aus der letzten cfd_setups.csv zu lesen
    oder live per yfinance zu berechnen.
    """
    direction = direction.lower()
    if direction not in ("long", "short"):
        raise ValueError(f"Richtung muss 'long' oder 'short' sein, nicht '{direction}'")

    portfolio = load_portfolio()

    # Duplikat-Check
    for p in portfolio["positions"]:
        if p["ticker"] == ticker.upper() and p["direction"] == direction:
            print(f"Position {ticker.upper()} {direction} existiert bereits.")
            return p

    # Auto-Fill aus CSV oder Live-Daten
    if entry_price is None or stop is None:
        entry_price, stop, tp1, tp2, atr, score, market = _lookup_levels(
            ticker, direction
        )

    today = datetime.now().strftime("%Y-%m-%d")
    pos_id = f"{ticker.upper()}_{direction}_{today}"

    position = {
        "id": pos_id,
        "ticker": ticker.upper(),
        "direction": direction,
        "entry_price": round(entry_price, 2),
        "entry_date": today,
        "stop_original": round(stop, 2),
        "stop_current": round(stop, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "tp1_hit": False,
        "tp1_hit_date": None,
        "atr_at_entry": round(atr, 3) if atr else None,
        "score_at_entry": round(score, 1) if score else None,
        "market": market,
        "highest_since_entry": round(entry_price, 2),
        "lowest_since_entry": round(entry_price, 2),
    }

    portfolio["positions"].append(position)
    save_portfolio(portfolio)
    print(f"Position hinzugefügt: {ticker.upper()} {direction.upper()} "
          f"@ {entry_price:.2f} | Stop {stop:.2f} | TP1 {tp1:.2f} | TP2 {tp2:.2f}")
    return position


def _lookup_levels(ticker: str, direction: str) -> tuple:
    """Versucht Levels aus CSV zu lesen, sonst live berechnen."""
    ticker = ticker.upper()
    csv_path = Path(__file__).parent / "cfd_setups.csv"

    # 1. Aus letztem CSV lesen
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path)
            match = df[(df["ticker"] == ticker) & (df["cfd_direction"] == direction)]
            if not match.empty:
                row = match.iloc[0]
                return (
                    float(row["price"]),
                    float(row[f"stop_{direction}"]),
                    float(row[f"tp1_{direction}"]),
                    float(row[f"tp2_{direction}"]),
                    float(row["atr"]),
                    float(row[f"cfd_{direction}_score"]),
                    str(row.get("market", "")),
                )
        except Exception:
            pass

    # 2. Live berechnen
    print(f"  Lade Live-Daten für {ticker} …")
    data = yf.download(ticker, period="90d", progress=False)
    if data.empty:
        raise ValueError(f"Keine Daten für {ticker}")

    close = data["Close"].squeeze()
    high = data["High"].squeeze()
    low = data["Low"].squeeze()
    current = float(close.iloc[-1])

    # ATR(14) berechnen
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr_val = float(tr.rolling(14).mean().iloc[-1])

    if direction == "long":
        stop = round(current - 1.5 * atr_val, 2)
        tp1 = round(current + 1.5 * atr_val, 2)
        tp2 = round(current + 4.0 * atr_val, 2)
    else:
        stop = round(current + 1.5 * atr_val, 2)
        tp1 = round(current - 1.5 * atr_val, 2)
        tp2 = round(current - 4.0 * atr_val, 2)

    return current, stop, tp1, tp2, atr_val, None, ""


def close_position(ticker: str, direction: str | None = None) -> bool:
    """Entfernt eine Position aus dem Portfolio."""
    ticker = ticker.upper()
    portfolio = load_portfolio()
    before = len(portfolio["positions"])
    portfolio["positions"] = [
        p for p in portfolio["positions"]
        if not (p["ticker"] == ticker and (direction is None or p["direction"] == direction))
    ]
    after = len(portfolio["positions"])
    if before > after:
        save_portfolio(portfolio)
        print(f"Position geschlossen: {ticker}" +
              (f" {direction}" if direction else ""))
        return True
    print(f"Keine offene Position für {ticker} gefunden.")
    return False


def list_positions() -> list[dict]:
    """Gibt alle aktiven Positionen zurück."""
    return load_portfolio().get("positions", [])


# ═══════════════════════════════════════════════════════════════════════════════
# TÄGLICHE POSITIONS-PRÜFUNG
# ═══════════════════════════════════════════════════════════════════════════════

def check_positions(positions: list | None = None) -> list[dict]:
    """
    Prüft alle aktiven Positionen und generiert Empfehlungen.

    Returns:
        Liste von Positions-Reports mit Empfehlung und Indikatoren.
    """
    if positions is None:
        positions = list_positions()

    if not positions:
        return []

    reports = []
    portfolio = load_portfolio()

    for pos in positions:
        try:
            report = _check_single_position(pos)
            reports.append(report)
            # Position im Portfolio aktualisieren (Stop-Trailing etc.)
            _update_position_in_portfolio(portfolio, pos)
        except Exception as e:
            print(f"  Fehler bei {pos['ticker']}: {e}")
            reports.append({
                "ticker": pos["ticker"],
                "direction": pos["direction"],
                "error": str(e),
                "recommendation": "FEHLER",
                "rec_color": "#7f8c8d",
            })

    save_portfolio(portfolio)
    return reports


def _check_single_position(pos: dict) -> dict:
    """Prüft eine einzelne Position gegen aktuelle Marktdaten."""
    ticker = pos["ticker"]
    direction = pos["direction"]
    entry = pos["entry_price"]
    stop_current = pos["stop_current"]
    tp1 = pos["tp1"]
    tp2 = pos["tp2"]

    print(f"  Prüfe {ticker} {direction.upper()} …")

    # Daten laden
    data = yf.download(ticker, period="90d", progress=False)
    if data.empty:
        raise ValueError(f"Keine Daten für {ticker}")

    close = data["Close"].squeeze()
    high = data["High"].squeeze()
    low = data["Low"].squeeze()
    volume = data["Volume"].squeeze()
    current = float(close.iloc[-1])

    # Tage seit Entry
    entry_date = datetime.strptime(pos["entry_date"], "%Y-%m-%d")
    days_held = (datetime.now() - entry_date).days

    # P&L berechnen
    if direction == "long":
        pnl_pct = (current - entry) / entry * 100
        pnl_abs = current - entry
    else:
        pnl_pct = (entry - current) / entry * 100
        pnl_abs = entry - current

    # Höchstkurs / Tiefstkurs seit Entry tracken
    entry_idx = None
    dates = close.index
    for i, d in enumerate(dates):
        if d.strftime("%Y-%m-%d") >= pos["entry_date"]:
            entry_idx = i
            break
    if entry_idx is not None:
        since_entry = close.iloc[entry_idx:]
        highest = float(since_entry.max())
        lowest = float(since_entry.min())
        pos["highest_since_entry"] = round(max(highest, pos.get("highest_since_entry", highest)), 2)
        pos["lowest_since_entry"] = round(min(lowest, pos.get("lowest_since_entry", lowest)), 2)

    # ── LEVEL-CHECKS ──────────────────────────────────────────────────────
    if direction == "long":
        stop_hit = current <= stop_current
        tp1_reached = current >= tp1 and not pos["tp1_hit"]
        tp2_reached = current >= tp2
    else:
        stop_hit = current >= stop_current
        tp1_reached = current <= tp1 and not pos["tp1_hit"]
        tp2_reached = current <= tp2

    # TP1-Hit markieren & Stop auf Break-Even
    if tp1_reached:
        pos["tp1_hit"] = True
        pos["tp1_hit_date"] = datetime.now().strftime("%Y-%m-%d")
        pos["stop_current"] = entry  # Break-Even
        stop_current = entry

    # Trailing Stop (nach TP1-Hit): 1.5x ATR unter Höchstkurs (Long)
    if pos["tp1_hit"] and pos.get("atr_at_entry"):
        atr = pos["atr_at_entry"]
        if direction == "long":
            trail_stop = round(pos["highest_since_entry"] - 1.5 * atr, 2)
            if trail_stop > stop_current:
                pos["stop_current"] = trail_stop
                stop_current = trail_stop
        else:
            trail_stop = round(pos["lowest_since_entry"] + 1.5 * atr, 2)
            if trail_stop < stop_current:
                pos["stop_current"] = trail_stop
                stop_current = trail_stop

    # ── SOFORT-EMPFEHLUNGEN ───────────────────────────────────────────────
    if stop_hit:
        return _build_report(pos, current, pnl_pct, pnl_abs, days_held,
                             "STOP GETROFFEN", "#c0392b", ["Kurs hat den Stop erreicht."],
                             auto_close=True)

    if tp2_reached:
        return _build_report(pos, current, pnl_pct, pnl_abs, days_held,
                             "TP2 ERREICHT — SCHLIESSEN", "#145a32",
                             ["Kursziel 2 erreicht. Position schliessen!"],
                             auto_close=True)

    if tp1_reached:
        return _build_report(pos, current, pnl_pct, pnl_abs, days_held,
                             "TP1 ERREICHT — Teilgewinn", "#d4ac0d",
                             ["TP1 erreicht. Teilgewinn mitnehmen, Stop auf Break-Even."])

    # ── TREND-HEALTH-CHECK ────────────────────────────────────────────────
    warnings = []

    # SMA20, SMA50
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma20_val = float(sma20.iloc[-1])
    sma50_val = float(sma50.iloc[-1])

    # EMA9, EMA21
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema9_val = float(ema9.iloc[-1])
    ema21_val = float(ema21.iloc[-1])

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - 100 / (1 + rs)
    rsi_val = float(rsi.iloc[-1])

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - macd_signal
    curr_hist = float(hist.iloc[-1])
    prev_hist = float(hist.iloc[-2]) if len(hist) > 1 else 0

    # ADX
    from stock_scanner import compute_adx
    adx_s, plus_di_s, minus_di_s = compute_adx(high, low, close)
    adx_val = float(adx_s.iloc[-1])
    plus_di = float(plus_di_s.iloc[-1])
    minus_di = float(minus_di_s.iloc[-1])

    # Volume Ratio
    vol_avg = float(volume.rolling(20).mean().iloc[-1])
    vol_current = float(volume.iloc[-1])
    vol_ratio = vol_current / vol_avg if vol_avg > 0 else 1.0

    if direction == "long":
        # MA-Struktur gebrochen?
        if not (current > sma20_val > sma50_val):
            warnings.append("MA-Struktur gebrochen (Kurs < SMA20 oder SMA20 < SMA50)")
        # EMA-Cross?
        if ema9_val < ema21_val:
            warnings.append("EMA9 unter EMA21 — bearisher Cross")
        # MACD dreht?
        if curr_hist < 0 or (curr_hist < prev_hist and curr_hist > 0):
            warnings.append(f"MACD-Momentum nachlassend (Hist: {curr_hist:.3f})")
        # RSI überkauft?
        if rsi_val > 75:
            warnings.append(f"RSI überkauft ({rsi_val:.0f})")
        # ADX schwach oder DI-Wechsel?
        if adx_val < 20:
            warnings.append(f"ADX schwach ({adx_val:.0f}) — kein Trend")
        elif minus_di > plus_di:
            warnings.append(f"DI-Wechsel: -DI ({minus_di:.0f}) > +DI ({plus_di:.0f})")
    else:  # short
        if not (current < sma20_val < sma50_val):
            warnings.append("MA-Struktur gebrochen (Kurs > SMA20 oder SMA20 > SMA50)")
        if ema9_val > ema21_val:
            warnings.append("EMA9 über EMA21 — bullisher Cross")
        if curr_hist > 0 or (curr_hist > prev_hist and curr_hist < 0):
            warnings.append(f"MACD-Momentum nachlassend (Hist: {curr_hist:.3f})")
        if rsi_val < 25:
            warnings.append(f"RSI überverkauft ({rsi_val:.0f})")
        if adx_val < 20:
            warnings.append(f"ADX schwach ({adx_val:.0f}) — kein Trend")
        elif plus_di > minus_di:
            warnings.append(f"DI-Wechsel: +DI ({plus_di:.0f}) > -DI ({minus_di:.0f})")

    # Volumen-Warnung
    if vol_ratio < 0.8:
        warnings.append(f"Volumen niedrig ({vol_ratio:.1f}x Durchschnitt)")

    # ── EMPFEHLUNG ABLEITEN ───────────────────────────────────────────────
    n_warn = len(warnings)
    if n_warn == 0:
        rec = "HALTEN — Trend intakt"
        rec_color = "#2980b9"
    elif n_warn == 1:
        rec = "HALTEN — leichte Schwäche"
        rec_color = "#2980b9"
    elif n_warn == 2:
        rec = "BEOBACHTEN — Trend-Warnung"
        rec_color = "#e67e22"
    else:
        rec = "SCHLIESSEN — Trend gebrochen"
        rec_color = "#c0392b"

    return _build_report(
        pos, current, pnl_pct, pnl_abs, days_held, rec, rec_color, warnings,
        indicators={
            "adx": round(adx_val, 1),
            "plus_di": round(plus_di, 1),
            "minus_di": round(minus_di, 1),
            "rsi": round(rsi_val, 1),
            "macd_hist": round(curr_hist, 3),
            "ema9": round(ema9_val, 2),
            "ema21": round(ema21_val, 2),
            "sma20": round(sma20_val, 2),
            "sma50": round(sma50_val, 2),
            "vol_ratio": round(vol_ratio, 2),
        },
    )


def _build_report(
    pos: dict, current: float, pnl_pct: float, pnl_abs: float,
    days_held: int, recommendation: str, rec_color: str,
    warnings: list, indicators: dict | None = None,
    auto_close: bool = False,
) -> dict:
    """Erstellt den Report-Dict für eine Position."""
    return {
        "ticker": pos["ticker"],
        "direction": pos["direction"],
        "market": pos.get("market", ""),
        "entry_price": pos["entry_price"],
        "entry_date": pos["entry_date"],
        "current_price": round(current, 2),
        "pnl_pct": round(pnl_pct, 2),
        "pnl_abs": round(pnl_abs, 2),
        "days_held": days_held,
        "stop_original": pos["stop_original"],
        "stop_current": pos["stop_current"],
        "tp1": pos["tp1"],
        "tp2": pos["tp2"],
        "tp1_hit": pos["tp1_hit"],
        "highest_since_entry": pos.get("highest_since_entry"),
        "lowest_since_entry": pos.get("lowest_since_entry"),
        "recommendation": recommendation,
        "rec_color": rec_color,
        "warnings": warnings,
        "indicators": indicators or {},
        "auto_close": auto_close,
    }


def _update_position_in_portfolio(portfolio: dict, pos: dict) -> None:
    """Aktualisiert eine Position im Portfolio-Dict (Stop-Trailing, TP1-Hit)."""
    for p in portfolio["positions"]:
        if p["id"] == pos["id"]:
            p["stop_current"] = pos["stop_current"]
            p["tp1_hit"] = pos["tp1_hit"]
            p["tp1_hit_date"] = pos.get("tp1_hit_date")
            p["highest_since_entry"] = pos.get("highest_since_entry", p.get("highest_since_entry"))
            p["lowest_since_entry"] = pos.get("lowest_since_entry", p.get("lowest_since_entry"))
            break


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def print_positions():
    """Gibt aktive Positionen formatiert aus."""
    positions = list_positions()
    if not positions:
        print("Keine aktiven Positionen.")
        return

    print(f"\n{'='*60}")
    print(f"  Aktive CFD-Positionen: {len(positions)}")
    print(f"{'='*60}")
    for p in positions:
        tp1_mark = " [TP1 ✓]" if p["tp1_hit"] else ""
        print(f"  {p['ticker']:8s} {p['direction'].upper():5s} @ {p['entry_price']:>8.2f}"
              f"  | Stop {p['stop_current']:>8.2f} | TP1 {p['tp1']:>8.2f} "
              f"| TP2 {p['tp2']:>8.2f}{tp1_mark}")
        print(f"           Entry: {p['entry_date']} | Markt: {p.get('market', '?')}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print_positions()
    elif sys.argv[1] == "check":
        reports = check_positions()
        for r in reports:
            pnl_sign = "+" if r["pnl_pct"] >= 0 else ""
            print(f"\n  {r['ticker']} {r['direction'].upper()} | "
                  f"{r['current_price']:.2f} ({pnl_sign}{r['pnl_pct']:.1f}%) | "
                  f"Tag {r['days_held']}")
            print(f"    → {r['recommendation']}")
            for w in r.get("warnings", []):
                print(f"      ⚠ {w}")
    elif sys.argv[1] == "add" and len(sys.argv) >= 4:
        add_position(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "close" and len(sys.argv) >= 3:
        close_position(sys.argv[2])
    else:
        print("Verwendung: python3 cfd_portfolio.py [check|add TICKER DIR|close TICKER]")
