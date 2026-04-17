#!/usr/bin/env python3
"""
CFD Intraday Scanner — laeuft alle 15 min waehrend Handelszeiten.

Watchlist = offene Positionen + Top-N Tickers vom letzten Vorabend-Scan + manuelle Watchlist.
Pro Ticker: 15m-Bars holen, Indikatoren berechnen, Long/Short-Score, Position-Check, Alerts.
Output: dashboard/data/cfd_intraday.json (vom Dashboard gepollt) + Telegram-Alerts.

Alerts:
- Position-Hit (Stop/TP1/TP2): immer feuern, kein Cooldown
- Score-Drift bei offener Position (entry_score - current_score >= 3.0): max 1x/Tag/Position
- Neues Setup (max(long, short) >= 7.0) auf nicht-Position-Tickern: max 1x/4h/Ticker

Kein Auto-Close von Positionen — Maik handelt manuell beim Broker.
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

from indicators.technical import compute_adx, compute_atr, compute_macd, compute_rsi
from scoring.cfd_intraday_scorer import compute_cfd_intraday_scores
from cfd_portfolio import load_portfolio, save_portfolio, _portfolio_lock
import telegram_alerts

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "scanner_config.yaml"
WATCHLIST_PATH = SCRIPT_DIR / "cfd_watchlist.json"
SETUPS_CSV_PATH = SCRIPT_DIR / "cfd_setups.csv"
DASHBOARD_DATA_DIR = SCRIPT_DIR / "dashboard" / "data"
DASHBOARD_JSON_PATH = DASHBOARD_DATA_DIR / "cfd_intraday.json"
STATE_PATH = DASHBOARD_DATA_DIR / "cfd_intraday_state.json"

# Trading hours in UTC. Sommer/Winterzeit ignoriert (kleine Toleranz an Markträndern).
MARKET_HOURS_UTC = {
    "DAX 40":        (7, 0, 15, 30),
    "MDAX":          (7, 0, 15, 30),
    "SDAX":          (7, 0, 15, 30),
    "TecDAX":        (7, 0, 15, 30),
    "Euro Stoxx 50": (7, 0, 15, 30),
    "S&P 500":       (13, 30, 20, 0),
    "NASDAQ 100":    (13, 30, 20, 0),
}

ATR_TRAIL_MULT = 1.5
TOP_N_FROM_SETUPS = 20
SETUP_ALERT_COOLDOWN_HOURS = 4
DRIFT_ALERT_THRESHOLD = 3.0
SCORE_ALERT_MIN = 7.0
MIN_BARS_FOR_SCORE = 30


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def load_watchlist() -> list[dict]:
    """
    Vereinigt Tickers aus Watchlist-Quellen. Position > Setup > Manual bei Konflikt.
    Returns liste mit {ticker, market, source, daily_direction}.

    daily_direction: "long" | "short" | None — aus cfd_setups.csv (cfd_direction-Feld),
    nur gesetzt wenn der Daily-Score in dieser Richtung >= threshold (5.0) ist.
    Wird zum Counter-Trend-Filter genutzt.
    """
    by_ticker: dict[str, dict] = {}

    if WATCHLIST_PATH.exists():
        try:
            data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
            for entry in data.get("tickers", []):
                t = entry.get("ticker")
                if t:
                    by_ticker[t] = {
                        "ticker": t,
                        "market": entry.get("market", ""),
                        "source": "manual",
                        "daily_direction": None,
                    }
        except Exception as e:
            print(f"Warnung: cfd_watchlist.json: {e}", file=sys.stderr)

    if SETUPS_CSV_PATH.exists():
        try:
            with SETUPS_CSV_PATH.open("r", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))

            def best_score(r):
                try:
                    return max(float(r.get("cfd_long_score") or 0),
                               float(r.get("cfd_short_score") or 0))
                except ValueError:
                    return 0.0

            rows.sort(key=best_score, reverse=True)
            for r in rows[:TOP_N_FROM_SETUPS]:
                t = r.get("ticker")
                if not t or t in by_ticker:
                    continue
                # Daily-Direction nur als verbindlich nehmen, wenn der entsprechende Score >= 5
                direction = (r.get("cfd_direction") or "").strip().lower()
                try:
                    score_in_dir = float(
                        r.get(f"cfd_{direction}_score") or 0
                    ) if direction in ("long", "short") else 0.0
                except ValueError:
                    score_in_dir = 0.0
                daily_direction = direction if score_in_dir >= 5.0 and direction in ("long", "short") else None

                by_ticker[t] = {
                    "ticker": t,
                    "market": r.get("market", ""),
                    "source": "setup",
                    "daily_direction": daily_direction,
                }
        except Exception as e:
            print(f"Warnung: cfd_setups.csv: {e}", file=sys.stderr)

    portfolio = load_portfolio()
    for pos in portfolio.get("positions", []):
        t = pos.get("ticker")
        if t:
            existing_dir = by_ticker.get(t, {}).get("daily_direction")
            by_ticker[t] = {
                "ticker": t,
                "market": pos.get("market", ""),
                "source": "position",
                "daily_direction": existing_dir,
            }

    return list(by_ticker.values())


def is_market_open(market: str, now_utc: datetime) -> bool:
    """True wenn der Markt aktuell handeln sollte (UTC, Mo-Fr, ohne SoZ-Korrektur)."""
    if now_utc.weekday() >= 5:
        return False
    hours = MARKET_HOURS_UTC.get(market, (7, 0, 15, 30))
    sh, sm, eh, em = hours
    start = now_utc.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = now_utc.replace(hour=eh, minute=em, second=0, microsecond=0)
    return start <= now_utc <= end


def fetch_15m_bars(tickers: list[str]) -> dict:
    """Bulk-download 15m-Bars (5d). Returns {ticker: dataframe}."""
    if not tickers:
        return {}
    df = yf.download(
        tickers=" ".join(tickers),
        period="5d",
        interval="15m",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    out = {}
    if df is None or df.empty:
        return out
    # group_by='ticker' liefert immer MultiIndex (auch bei 1 Ticker)
    for t in tickers:
        try:
            if isinstance(df.columns, pd.MultiIndex):
                sub = df[t].dropna()
            else:
                sub = df.dropna()
            if not sub.empty:
                out[t] = sub
        except (KeyError, TypeError):
            pass
    return out


def compute_indicators_from_df(df: pd.DataFrame) -> dict:
    """Berechnet alle Score-Inputs aus 15m-OHLCV."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    sma20 = close.rolling(20).mean().iloc[-1]
    sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else float("nan")
    ema9 = close.ewm(span=9, adjust=False).mean().iloc[-1]
    ema21 = close.ewm(span=21, adjust=False).mean().iloc[-1]

    _, _, hist = compute_macd(close)
    curr_hist = float(hist.iloc[-1]) if len(hist) > 0 else 0.0
    prev_hist = float(hist.iloc[-2]) if len(hist) > 1 else 0.0

    rsi = compute_rsi(close)
    rsi_val = float(rsi.iloc[-1]) if len(rsi) > 0 and pd.notna(rsi.iloc[-1]) else 50.0

    adx_s, plus_di_s, minus_di_s = compute_adx(high, low, close)
    adx_val = float(adx_s.iloc[-1]) if len(adx_s) > 0 and pd.notna(adx_s.iloc[-1]) else 0.0
    plus_di = float(plus_di_s.iloc[-1]) if len(plus_di_s) > 0 and pd.notna(plus_di_s.iloc[-1]) else 0.0
    minus_di = float(minus_di_s.iloc[-1]) if len(minus_di_s) > 0 and pd.notna(minus_di_s.iloc[-1]) else 0.0

    atr_s = compute_atr(high, low, close)
    atr_val = float(atr_s.iloc[-1]) if len(atr_s) > 0 and pd.notna(atr_s.iloc[-1]) else 0.0
    current_price = float(close.iloc[-1])
    atr_pct = (atr_val / current_price * 100.0) if current_price > 0 else 0.0

    vol_avg = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else float(volume.mean())
    vol_current = float(volume.iloc[-1])
    vol_ratio = vol_current / vol_avg if vol_avg and vol_avg > 0 else 1.0

    if len(close) >= 2:
        opens = df["Open"].iloc[-20:]
        prev_closes = close.shift(1).iloc[-20:]
        gaps = ((opens - prev_closes).abs() / prev_closes * 100.0).dropna()
        recent_max_gap = float(gaps.max()) if len(gaps) > 0 else 0.0
    else:
        recent_max_gap = 0.0

    return {
        "current_price": current_price,
        "sma20_val": float(sma20) if pd.notna(sma20) else current_price,
        "sma50_val": float(sma50) if pd.notna(sma50) else current_price,
        "ema9_val": float(ema9) if pd.notna(ema9) else current_price,
        "ema21_val": float(ema21) if pd.notna(ema21) else current_price,
        "curr_hist": curr_hist,
        "prev_hist": prev_hist,
        "rsi_val": rsi_val,
        "adx_val": adx_val,
        "plus_di_val": plus_di,
        "minus_di_val": minus_di,
        "atr_val": atr_val,
        "atr_pct": atr_pct,
        "vol_ratio": vol_ratio,
        "recent_max_gap": recent_max_gap,
        "bar_time": str(df.index[-1]) if len(df.index) > 0 else None,
    }


def check_position_intraday(pos: dict, current_price: float) -> dict | None:
    """
    Stop/TP-Check auf intraday-Basis. Mutiert pos in-place fuer Trailing-Updates.
    Returns None wenn kein Event, sonst Event-Dict.
    """
    direction = pos["direction"]
    entry = pos["entry_price"]
    stop_current = pos["stop_current"]
    tp1 = pos["tp1"]
    tp2 = pos["tp2"]

    if direction == "long":
        prev_high = pos.get("highest_since_entry", current_price)
        pos["highest_since_entry"] = round(max(prev_high, current_price), 2)
        pnl_pct = (current_price - entry) / entry * 100
        stop_hit = current_price <= stop_current
        tp1_reached = current_price >= tp1 and not pos.get("tp1_hit", False)
        tp2_reached = current_price >= tp2
    else:
        prev_low = pos.get("lowest_since_entry", current_price)
        pos["lowest_since_entry"] = round(min(prev_low, current_price), 2)
        pnl_pct = (entry - current_price) / entry * 100
        stop_hit = current_price >= stop_current
        tp1_reached = current_price <= tp1 and not pos.get("tp1_hit", False)
        tp2_reached = current_price <= tp2

    if stop_hit:
        return {"event": "STOP GETROFFEN (intraday)", "pnl_pct": pnl_pct, "price": current_price}
    if tp2_reached:
        return {"event": "TP2 ERREICHT (intraday)", "pnl_pct": pnl_pct, "price": current_price}
    if tp1_reached:
        pos["tp1_hit"] = True
        pos["tp1_hit_date"] = datetime.utcnow().strftime("%Y-%m-%d")
        pos["stop_current"] = entry
        return {"event": "TP1 ERREICHT (intraday)", "pnl_pct": pnl_pct, "price": current_price}

    if pos.get("tp1_hit") and pos.get("atr_at_entry"):
        atr = pos["atr_at_entry"]
        if direction == "long":
            trail = round(pos["highest_since_entry"] - ATR_TRAIL_MULT * atr, 2)
            if trail > pos["stop_current"]:
                pos["stop_current"] = trail
        else:
            trail = round(pos["lowest_since_entry"] + ATR_TRAIL_MULT * atr, 2)
            if trail < pos["stop_current"]:
                pos["stop_current"] = trail

    return None


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_alerts": {}}


def save_state(state: dict) -> None:
    DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def cooldown_passed(state: dict, key: str, hours: float) -> bool:
    last = state.get("last_alerts", {}).get(key)
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True
    return (datetime.utcnow() - last_dt) >= timedelta(hours=hours)


def mark_alert(state: dict, key: str) -> None:
    state.setdefault("last_alerts", {})[key] = datetime.utcnow().isoformat()


def write_dashboard_json(rows: list[dict]) -> None:
    DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "rows": rows,
    }
    tmp = DASHBOARD_JSON_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DASHBOARD_JSON_PATH)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Keine Alerts senden, kein State/Portfolio schreiben.")
    parser.add_argument("--force", action="store_true",
                        help="Trading-Hours-Filter ignorieren.")
    args = parser.parse_args()

    cfg = load_config()
    now_utc = datetime.utcnow()

    watchlist = load_watchlist()
    if not watchlist:
        print("Watchlist leer — exit.")
        write_dashboard_json([])
        return 0

    if args.force:
        active = watchlist
    else:
        active = [w for w in watchlist if is_market_open(w["market"], now_utc)]

    if not active:
        print(f"[{now_utc.isoformat()}] Kein Markt offen — exit.")
        return 0

    print(f"[{now_utc.isoformat()}] Aktive Tickers ({len(active)}): "
          f"{[w['ticker'] for w in active]}")

    bars = fetch_15m_bars([w["ticker"] for w in active])
    if not bars:
        print("Keine Bars geladen — exit.")
        return 1

    portfolio = load_portfolio()
    open_positions = {p["ticker"]: p for p in portfolio.get("positions", [])}
    state = load_state()

    rows = []
    portfolio_dirty = False

    for w in active:
        ticker, market = w["ticker"], w["market"]
        df = bars.get(ticker)
        if df is None or len(df) < MIN_BARS_FOR_SCORE:
            n = 0 if df is None else len(df)
            print(f"  {ticker}: zu wenig Bars ({n}) — skip")
            continue

        try:
            ind = compute_indicators_from_df(df)
        except Exception as e:
            print(f"  {ticker}: Indikatoren fehlgeschlagen: {e}")
            continue

        long_score, short_score, _ = compute_cfd_intraday_scores(
            cfg=cfg,
            market=market,
            adx_val=ind["adx_val"],
            plus_di_val=ind["plus_di_val"],
            minus_di_val=ind["minus_di_val"],
            current_price=ind["current_price"],
            sma20_val=ind["sma20_val"],
            sma50_val=ind["sma50_val"],
            ema9_val=ind["ema9_val"],
            ema21_val=ind["ema21_val"],
            curr_hist=ind["curr_hist"],
            prev_hist=ind["prev_hist"],
            rsi_val=ind["rsi_val"],
            vol_ratio=ind["vol_ratio"],
            recent_max_gap=ind["recent_max_gap"],
            atr_pct=ind["atr_pct"],
        )

        row = {
            "ticker": ticker,
            "market": market,
            "source": w["source"],
            "daily_direction": w.get("daily_direction"),
            "current_price": round(ind["current_price"], 2),
            "long_score": long_score,
            "short_score": short_score,
            "adx": round(ind["adx_val"], 1),
            "rsi": round(ind["rsi_val"], 1),
            "atr_pct": round(ind["atr_pct"], 2),
            "vol_ratio": round(ind["vol_ratio"], 2),
            "bar_time": ind["bar_time"],
        }

        pos = open_positions.get(ticker)
        if pos:
            event = check_position_intraday(pos, ind["current_price"])
            row["position"] = {
                "direction": pos["direction"],
                "entry": pos["entry_price"],
                "stop_current": pos["stop_current"],
                "tp1": pos["tp1"],
                "tp2": pos["tp2"],
                "tp1_hit": pos.get("tp1_hit", False),
            }
            if event:
                portfolio_dirty = True
                row["event"] = event["event"]
                row["pnl_pct"] = round(event["pnl_pct"], 2)
                if not args.dry_run:
                    telegram_alerts.send_position_alert(
                        ticker, pos["direction"], event["event"],
                        event["price"], event["pnl_pct"],
                    )

            entry_score = pos.get("score_at_entry", 0) or 0
            current_dir_score = long_score if pos["direction"] == "long" else short_score
            drift = round(entry_score - current_dir_score, 1)
            row["entry_score"] = entry_score
            row["drift"] = drift
            if drift >= DRIFT_ALERT_THRESHOLD:
                key = f"{ticker}_drift_{datetime.utcnow().strftime('%Y-%m-%d')}"
                if cooldown_passed(state, key, hours=24) and not args.dry_run:
                    telegram_alerts.send_message(
                        f"\u26a0\ufe0f <b>Score-Drift {ticker} {pos['direction'].upper()}</b>\n"
                        f"Entry-Score (daily): {entry_score:.1f} \u2192 jetzt (15m): {current_dir_score:.1f}\n"
                        f"Drift: {drift:.1f} Punkte\n"
                        f"Kurs: {ind['current_price']:.2f} \u2014 Position pruefen."
                    )
                    mark_alert(state, key)
        else:
            best = max(long_score, short_score)
            if best >= SCORE_ALERT_MIN:
                direction = "long" if long_score >= short_score else "short"
                daily_dir = w.get("daily_direction")
                # Counter-Trend-Filter: wenn daily_direction bekannt UND nicht gleich intraday-Richtung → skip
                if daily_dir and daily_dir != direction:
                    row["counter_trend"] = True
                    print(f"  {ticker}: {direction} setup (15m {best:.1f}) gegen daily {daily_dir} → Alert geblockt.")
                else:
                    key = f"{ticker}_{direction}_setup"
                    if cooldown_passed(state, key, hours=SETUP_ALERT_COOLDOWN_HOURS) and not args.dry_run:
                        telegram_alerts.send_message(
                            f"\U0001f50e <b>Intraday-Setup {ticker} {direction.upper()}</b>\n"
                            f"Score: <b>{best:.1f}/10</b> auf 15m | Markt: {market}\n"
                            f"Kurs: {ind['current_price']:.2f} | ADX: {ind['adx_val']:.0f} | RSI: {ind['rsi_val']:.0f}\n"
                            f"(Quelle: {w['source']}{', daily ' + daily_dir if daily_dir else ''})"
                        )
                        mark_alert(state, key)

        rows.append(row)

    if portfolio_dirty and not args.dry_run:
        with _portfolio_lock():
            save_portfolio(portfolio)

    write_dashboard_json(rows)
    if not args.dry_run:
        save_state(state)

    print(f"[{datetime.utcnow().isoformat()}] Done. {len(rows)} Tickers gescannt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
