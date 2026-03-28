#!/usr/bin/env python3
"""
Technical Analysis Stock Scanner
Scans NASDAQ 100, S&P 500 and DAX 40 for short-term trading signals (1-5 day horizon).
"""

import argparse
import copy
import logging
import sys
import time
import warnings
import webbrowser
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# Preis-Cache: Reduziert yfinance API-Calls um ~80%
try:
    from price_cache import get_prices as cached_get_prices
    _USE_PRICE_CACHE = True
except ImportError:
    _USE_PRICE_CACHE = False

# Modul-Imports (nach Refactoring aufgeteilt)
from indicators.technical import (
    compute_rsi, compute_macd, compute_bollinger, compute_adx, compute_atr,
    detect_candlestick_patterns,
)
from scoring.cfd_scorer import compute_cfd_scores, compute_cfd_levels
from scoring.longterm_scorer import compute_longterm_score
from scoring.fear_greed import get_fear_greed, compute_fg_multiplier
from tickers.sources import (
    TICKER_SOURCES, filter_valid_tickers,
    get_nasdaq100_tickers, get_sp500_tickers, get_dax40_tickers,
    get_eurostoxx50_tickers, get_tecdax_tickers, get_mdax_tickers,
    get_sdax_tickers,
)
from tickers.name_resolver import resolve_name, preload_wiki_names
from reports.html_report import generate_html

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "cfd": {
        "adx_min": 30, "adx_sweet_max": 42, "adx_overripe": 45,
        "rsi_long_min": 45, "rsi_long_max": 62,
        "rsi_short_min": 38, "rsi_short_max": 55,
        "atr_pct_min": 1.0, "atr_pct_max": 8.0,
        "trend_maturity_min_days": 3,
        "vol_ratio_min": 1.2, "vol_ratio_bonus": 2.0,
        "max_gap_pct": 5.0,
        "atr_stop_mult": 1.5, "atr_tp1_mult": 1.5, "atr_tp2_mult": 2.0,
        "top_n": 5,
        "short_score_cap": 7.5,
        "short_resolve_max_days": 5,
    },
    "scoring": {
        "weights": {
            "adx_di": 2.0, "ma_structure": 1.5, "ema_stack": 1.5,
            "macd": 1.0, "rsi_zone": 1.0, "volume": 0.5, "no_gap": 0.5,
        },
        "bonus": {
            "trend_maturity_days": 5, "trend_maturity_pts": 0.5,
            "trend_overripe_days": 15, "trend_overripe_penalty": -0.5,
            "vol_ratio_high": 2.0, "vol_ratio_pts": 0.5,
            "squeeze_fire_pts": 0.5,
            "max_bonus": 1.0,
        },
        "penalty": {
            "adx_overripe_pts": -0.5,
        },
        "threshold": 5.0, "max_score": 9.0,
    },
    "main_scan": {"min_score": 4, "max_gap_pct": 3.0},
    "backtesting": {
        "db_file": "cfd_backtesting.db", "resolve_after_days": 1,
        "resolve_max_days": 7, "enabled": True,
    },
}


def load_config() -> dict:
    """Lade scanner_config.yaml, Fallback auf Defaults."""
    config_path = Path(__file__).parent / "scanner_config.yaml"
    config = copy.deepcopy(_DEFAULT_CONFIG)
    if config_path.exists():
        try:
            import yaml
            with open(config_path, encoding="utf-8") as f:
                user_cfg = yaml.safe_load(f) or {}
            for section, defaults in _DEFAULT_CONFIG.items():
                if section in user_cfg:
                    if isinstance(defaults, dict):
                        merged = dict(defaults)
                        for k, v in user_cfg[section].items():
                            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                                merged[k] = {**merged[k], **v}
                            else:
                                merged[k] = v
                        config[section] = merged
                    else:
                        config[section] = user_cfg[section]
            print("Config geladen: scanner_config.yaml")
        except Exception as e:
            print(f"Config-Fehler, nutze Defaults: {e}")
    else:
        print("Keine scanner_config.yaml gefunden, nutze Defaults.")
    return config


CFG = load_config()

# ---------------------------------------------------------------------------
# Konstanten & Logging
# ---------------------------------------------------------------------------

MIN_AVG_VOLUME = 500_000

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "scan_errors.log"
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.ERROR,
    format="%(asctime)s  %(levelname)s  %(message)s",
)


# ---------------------------------------------------------------------------
# Core analysis function
# ---------------------------------------------------------------------------

def analyze_ticker(ticker: str, market: str) -> dict | None:
    """Download data and compute all signals. Returns result dict or None."""
    try:
        if _USE_PRICE_CACHE:
            df = cached_get_prices(ticker, period="1y")
        else:
            df = yf.download(ticker, period="1y", interval="1d",
                             auto_adjust=True, progress=False)
        if df is None or len(df) < 30:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        df = df.dropna()
        if len(df) < 30:
            return None
    except Exception as exc:
        logging.error("%s: %s", ticker, exc)
        if _USE_PRICE_CACHE:
            try:
                df = yf.download(ticker, period="1y", interval="1d",
                                 auto_adjust=True, progress=False)
                if df is not None and len(df) >= 30:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.droplevel(1)
                    df = df.dropna()
                    if len(df) < 30:
                        return None
                else:
                    return None
            except Exception:
                return None
        else:
            return None

    close, volume, open_, high, low = df["Close"], df["Volume"], df["Open"], df["High"], df["Low"]
    current_price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2])
    pct_change = (current_price - prev_price) / prev_price * 100

    # --- Mindest-Liquiditaet ---
    avg_vol_20 = float(volume.rolling(20).mean().iloc[-1])
    if avg_vol_20 < MIN_AVG_VOLUME:
        return None

    # --- Indikatoren berechnen ---
    atr_series = compute_atr(high, low, close)
    atr_val = float(atr_series.iloc[-1])
    atr_pct = round(atr_val / current_price * 100, 2)

    buy_signals, sell_signals = 0, 0
    signal_details = {}

    # --- RSI ---
    rsi_val = float(compute_rsi(close).iloc[-1])
    signal_details["RSI"] = round(rsi_val, 1)
    if rsi_val < 30:
        buy_signals += 1; signal_details["RSI_signal"] = "BUY"
    elif rsi_val > 70:
        sell_signals += 1; signal_details["RSI_signal"] = "SELL"
    else:
        signal_details["RSI_signal"] = "neutral"

    # --- MACD ---
    _, _, histogram = compute_macd(close)
    prev_hist = float(histogram.iloc[-2]) if len(histogram) >= 2 else 0
    curr_hist = float(histogram.iloc[-1])
    if prev_hist < 0 and curr_hist > 0:
        buy_signals += 1; macd_signal = "BUY"
    elif prev_hist > 0 and curr_hist < 0:
        sell_signals += 1; macd_signal = "SELL"
    elif curr_hist > 0:
        macd_signal = "bullish"
    else:
        macd_signal = "bearish"
    signal_details["MACD"] = macd_signal

    # --- Moving Averages ---
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    sma20_val, sma50_val = float(sma20.iloc[-1]), float(sma50.iloc[-1])
    ema9_val, ema21_val = float(ema9.iloc[-1]), float(ema21.iloc[-1])
    ema9_prev, ema21_prev = float(ema9.iloc[-2]), float(ema21.iloc[-2])

    ma_buy = current_price > sma20_val > sma50_val
    ma_sell = current_price < sma20_val < sma50_val
    ema_cross_buy = ema9_prev < ema21_prev and ema9_val > ema21_val
    ema_cross_sell = ema9_prev > ema21_prev and ema9_val < ema21_val
    if ma_buy or ema_cross_buy:
        buy_signals += 1; ma_signal = "BUY"
    elif ma_sell or ema_cross_sell:
        sell_signals += 1; ma_signal = "SELL"
    else:
        ma_signal = "neutral"
    signal_details["MA"] = ma_signal

    # --- Bollinger Bands ---
    bb_upper, bb_mid, bb_lower = compute_bollinger(close)
    bb_upper_val, bb_lower_val = float(bb_upper.iloc[-1]), float(bb_lower.iloc[-1])
    bb_width = float((bb_upper.iloc[-1] - bb_lower.iloc[-1]) / bb_mid.iloc[-1])
    avg_bb_width = float(((bb_upper - bb_lower) / bb_mid).rolling(20).mean().iloc[-1])
    squeeze = not np.isnan(avg_bb_width) and bb_width < avg_bb_width * 0.8

    if current_price < bb_lower_val:
        buy_signals += 1; bb_signal = "BUY (below lower)"
    elif current_price < bb_lower_val * 1.01 and squeeze:
        buy_signals += 1; bb_signal = "BUY (squeeze)"
    elif current_price > bb_upper_val:
        sell_signals += 1; bb_signal = "SELL (above upper)"
    else:
        bb_signal = "neutral"
    signal_details["Bollinger"] = bb_signal

    # --- Volume ---
    curr_vol = float(volume.iloc[-1])
    vol_ratio = curr_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0
    if vol_ratio > 1.5 and pct_change > 0:
        buy_signals += 1; vol_signal = f"BUY ({vol_ratio:.1f}x avg)"
    elif vol_ratio > 1.5 and pct_change < 0:
        sell_signals += 1; vol_signal = f"SELL ({vol_ratio:.1f}x avg)"
    else:
        vol_signal = f"neutral ({vol_ratio:.1f}x avg)"
    signal_details["Volume"] = vol_signal

    # --- Candlestick ---
    candle_df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close})
    candle_result = detect_candlestick_patterns(candle_df)
    if candle_result["bias"] > 0:
        buy_signals += 1
    elif candle_result["bias"] < 0:
        sell_signals += 1
    signal_details["Candlestick"] = candle_result["pattern"] if candle_result["pattern"] != "none" else "neutral"

    # --- VWAP ---
    typical_price = (high + low + close) / 3
    vol_20, tp_20 = volume.tail(20), typical_price.tail(20)
    vwap_val = float((tp_20 * vol_20).sum() / vol_20.sum()) if float(vol_20.sum()) > 0 else current_price
    if current_price > vwap_val:
        buy_signals += 1; vwap_signal = f"BUY ({vwap_val:.2f})"
    else:
        sell_signals += 1; vwap_signal = f"SELL ({vwap_val:.2f})"
    signal_details["VWAP"] = vwap_signal

    # --- Squeeze Momentum ---
    ema20 = close.ewm(span=20, adjust=False).mean()
    kc_upper = ema20 + 1.5 * atr_series
    kc_lower = ema20 - 1.5 * atr_series
    sq_on = (float(bb_upper.iloc[-1]) < float(kc_upper.iloc[-1])) and \
            (float(bb_lower.iloc[-1]) > float(kc_lower.iloc[-1]))
    highest_high_20 = high.rolling(20).max()
    lowest_low_20 = low.rolling(20).min()
    delta_close = close - ((highest_high_20 + lowest_low_20) / 2 + ema20) / 2
    dc_tail = delta_close.tail(5).values
    squeeze_momentum = 0.0
    if len(dc_tail) == 5 and not np.any(np.isnan(dc_tail)):
        coeffs = np.polyfit(np.arange(5), dc_tail, 1)
        squeeze_momentum = float(np.polyval(coeffs, 4))

    if not sq_on and squeeze_momentum > 0:
        buy_signals += 1; sq_signal = f"BUY (mom={squeeze_momentum:.3f})"
    elif not sq_on and squeeze_momentum < 0:
        sell_signals += 1; sq_signal = f"SELL (mom={squeeze_momentum:.3f})"
    else:
        sq_signal = f"Squeeze {'ON' if sq_on else 'OFF'}"
    signal_details["Squeeze"] = sq_signal

    net_score = buy_signals - sell_signals

    # --- ADX ---
    adx_s, plus_di_s, minus_di_s = compute_adx(high, low, close)
    adx_val = float(adx_s.iloc[-1])
    plus_di_val = float(plus_di_s.iloc[-1])
    minus_di_val = float(minus_di_s.iloc[-1])

    # --- Gap + Trend-Reife ---
    recent_max_gap = float(close.pct_change().tail(5).abs().max()) * 100
    trend_long_days, trend_short_days = 0, 0
    sma20_arr, sma50_arr, close_arr = sma20.values, sma50.values, close.values
    for i in range(max(len(close_arr) - 10, 0), len(close_arr)):
        if close_arr[i] > sma20_arr[i] > sma50_arr[i]:
            trend_long_days += 1
        if close_arr[i] < sma20_arr[i] < sma50_arr[i]:
            trend_short_days += 1

    # --- CFD Scores (ausgelagert in scoring.cfd_scorer) ---
    cfd_long, cfd_short = compute_cfd_scores(
        cfg=CFG, adx_val=adx_val, plus_di_val=plus_di_val, minus_di_val=minus_di_val,
        current_price=current_price, sma20_val=sma20_val, sma50_val=sma50_val,
        ema9_val=ema9_val, ema21_val=ema21_val,
        curr_hist=curr_hist, prev_hist=prev_hist, rsi_val=rsi_val,
        vol_ratio=vol_ratio, recent_max_gap=recent_max_gap, atr_pct=atr_pct,
        trend_long_days=trend_long_days, trend_short_days=trend_short_days,
        sq_on=sq_on, squeeze_momentum=squeeze_momentum,
    )

    # --- ATR-basierte Levels (ausgelagert in scoring.cfd_scorer) ---
    levels = compute_cfd_levels(CFG, current_price, atr_val)

    # --- Langfrist-Investment-Score ---
    longterm = compute_longterm_score(df, current_price)

    # --- RVOL Label ---
    rvol_label = "🔥 Hoch" if vol_ratio > 2.0 else "↑ Erhöht" if vol_ratio > 1.5 else "— Normal"

    return {
        "ticker": ticker, "name": resolve_name(ticker), "market": market,
        "buy_signals": buy_signals, "sell_signals": sell_signals, "net_score": net_score,
        "rsi": signal_details.get("RSI", "-"), "rsi_signal": signal_details.get("RSI_signal", "-"),
        "macd": signal_details.get("MACD", "-"), "ma": signal_details.get("MA", "-"),
        "bollinger": signal_details.get("Bollinger", "-"),
        "volume": signal_details.get("Volume", "-"),
        "candlestick": signal_details.get("Candlestick", "-"),
        "vwap": signal_details.get("VWAP", "-"), "squeeze": signal_details.get("Squeeze", "-"),
        "price": round(current_price, 2), "pct_change": round(pct_change, 2),
        "atr": round(atr_val, 3), "atr_pct": atr_pct,
        "adx": round(adx_val, 1), "plus_di": round(plus_di_val, 1),
        "minus_di": round(minus_di_val, 1), "vol_ratio": round(vol_ratio, 2),
        "rvol_label": rvol_label, "recent_max_gap": round(recent_max_gap, 1),
        "cfd_long_score": cfd_long, "cfd_short_score": cfd_short,
        "cfd_quality_score": max(cfd_long, cfd_short),
        "trend_long_days": trend_long_days, "trend_short_days": trend_short_days,
        **levels,
        "longterm_score": longterm["longterm_score"],
        "longterm_label": longterm["longterm_label"],
        "longterm_details": longterm["longterm_details"],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Technical Analysis Stock Scanner")
    parser.add_argument("--no-open", action="store_true",
                        help="Kein automatisches Öffnen des HTML-Reports im Browser.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Keine externen API-Calls; erzeugt leeren Report für Smoke-Check.")
    parser.add_argument("--add-position", nargs=2, metavar=("TICKER", "DIRECTION"),
                        help="CFD-Position hinzufügen (z.B. --add-position CVX long)")
    parser.add_argument("--close-position", metavar="TICKER",
                        help="CFD-Position schliessen (z.B. --close-position CVX)")
    parser.add_argument("--positions", action="store_true",
                        help="Alle aktiven CFD-Positionen anzeigen.")
    parser.add_argument("--check-positions", action="store_true",
                        help="Alle Positionen prüfen und Empfehlungen ausgeben.")
    parser.add_argument("--add-stock", metavar="TICKER",
                        help="Aktie zum Investment-Portfolio hinzufuegen")
    parser.add_argument("--remove-stock", metavar="TICKER",
                        help="Aktie aus Investment-Portfolio entfernen")
    parser.add_argument("--stocks", action="store_true",
                        help="Alle gehaltenen Aktien anzeigen")
    parser.add_argument("--import-stocks", metavar="TICKERS",
                        help="Batch-Import kommasepariert (z.B. AAPL,MSFT,SAP.DE)")
    return parser.parse_args()


def main():
    args = parse_args()

    # -- Portfolio-Befehle (Early Exit) --
    from cfd_portfolio import (
        add_position, close_position, print_positions, check_positions, list_positions
    )

    if args.add_position:
        add_position(*args.add_position); return
    if args.close_position:
        close_position(args.close_position); return
    if args.positions:
        print_positions(); return
    if args.check_positions:
        reports = check_positions()
        for r in reports:
            if "error" in r:
                print(f"\n  {r['ticker']}: FEHLER — {r['error']}"); continue
            pnl_sign = "+" if r["pnl_pct"] >= 0 else ""
            print(f"\n  {r['ticker']} {r['direction'].upper()} | "
                  f"{r['current_price']:.2f} ({pnl_sign}{r['pnl_pct']:.1f}%) | Tag {r['days_held']}")
            print(f"    {r['recommendation']}")
            for w in r.get("warnings", []):
                print(f"      - {w}")
        return

    # -- Investment-Portfolio-Befehle (Early Exit) --
    from investment_portfolio import (
        add_stock, remove_stock, list_stocks, import_stocks, check_stocks
    )

    if args.add_stock:
        success = add_stock(args.add_stock.upper())
        print(f"{'✓' if success else '✗'} {args.add_stock.upper()}")
        return

    if args.remove_stock:
        success = remove_stock(args.remove_stock.upper())
        print(f"{'✓ Entfernt' if success else '✗ Nicht gefunden'}: {args.remove_stock.upper()}")
        return

    if args.stocks:
        stocks = list_stocks()
        if not stocks:
            print("Keine Aktien im Portfolio.")
        else:
            print(f"\nInvestment-Portfolio ({len(stocks)} Aktien):")
            for s in stocks:
                print(f"  {s['ticker']:10s}  {s.get('market', '')}")
        return

    if args.import_stocks:
        tickers = [t.strip().upper() for t in args.import_stocks.split(",") if t.strip()]
        count = import_stocks(tickers)
        print(f"✓ {count} Aktien importiert (von {len(tickers)} angegeben)")
        return

    start_time = time.time()
    scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}\n  Technical Analysis Stock Scanner\n  {scan_time}\n{'='*60}\n")

    # --- Fear & Greed Index ---
    if args.dry_run:
        fear_greed = {"value": 50, "label": "Neutral (DryRun)"}
    else:
        print("Hole Fear & Greed Index …")
        fear_greed = get_fear_greed()
    print(f"Fear & Greed: {fear_greed['value']} ({fear_greed['label']})\n")

    if args.dry_run:
        print("[DRY-RUN] Keine externen API-Calls. Erzeuge leeren Report …")
        nasdaq = sp500 = dax = eurostoxx50 = tecdax = mdax = sdax = []
    else:
        print("Lade Ticker-Listen …")
        nasdaq = filter_valid_tickers(get_nasdaq100_tickers(), "NASDAQ 100")
        sp500 = filter_valid_tickers(get_sp500_tickers(), "S&P 500")
        dax = filter_valid_tickers(get_dax40_tickers(), "DAX 40")
        eurostoxx50 = filter_valid_tickers(get_eurostoxx50_tickers(), "Euro Stoxx 50")
        tecdax = filter_valid_tickers(get_tecdax_tickers(), "TecDAX")
        mdax = filter_valid_tickers(get_mdax_tickers(), "MDAX")
        sdax = filter_valid_tickers(get_sdax_tickers(), "SDAX")
        preload_wiki_names()

    # Deduplizieren
    all_tickers: list[tuple[str, str]] = []
    seen: set[str] = set()
    for ticker, label in [
        *((t, "NASDAQ 100") for t in nasdaq), *((t, "S&P 500") for t in sp500),
        *((t, "DAX 40") for t in dax), *((t, "Euro Stoxx 50") for t in eurostoxx50),
        *((t, "TecDAX") for t in tecdax), *((t, "MDAX") for t in mdax),
        *((t, "SDAX") for t in sdax),
    ]:
        if ticker not in seen:
            all_tickers.append((ticker, label)); seen.add(ticker)

    total = len(all_tickers)
    print(f"Ticker geladen: NASDAQ 100={len(nasdaq)}, S&P 500={len(sp500)}, "
          f"DAX 40={len(dax)}, Euro Stoxx 50={len(eurostoxx50)}, "
          f"TecDAX={len(tecdax)}, MDAX={len(mdax)}, SDAX={len(sdax)}")
    for list_name in ["NASDAQ 100", "S&P 500", "DAX 40", "Euro Stoxx 50", "TecDAX", "MDAX", "SDAX"]:
        if list_name in TICKER_SOURCES:
            source, cnt = TICKER_SOURCES[list_name]
            print(f"  Quelle {list_name}: {source} ({cnt})")
    print(f"Gesamt eindeutige Ticker: {total}")
    if not args.dry_run:
        est_min = total * 0.35 / 60
        print(f"Geschätzte Laufzeit: {est_min:.0f}–{est_min*1.5:.0f} Minuten\n")

    try:
        from tqdm import tqdm
        ticker_iter = tqdm(all_tickers, desc="Scanning", unit="ticker")
    except ImportError:
        print("(tqdm nicht installiert — kein Fortschrittsbalken)")
        ticker_iter = all_tickers

    results: list[dict] = []
    for idx, (ticker, market) in enumerate(ticker_iter):
        result = analyze_ticker(ticker, market)
        if result is not None:
            results.append(result)
        if (idx + 1) % 20 == 0:
            time.sleep(0.1)

    # --- Langfrist-Signale filtern und sortieren ---
    longterm_rows = sorted(
        [r for r in results if r.get("longterm_score", 0) >= 5.0],
        key=lambda r: r["longterm_score"], reverse=True
    )[:20]

    elapsed = time.time() - start_time
    print(f"\nScan abgeschlossen in {elapsed:.0f}s ({elapsed/60:.1f} Min)")
    print(f"Langfrist-Signale: {len(longterm_rows)}")
    print(f"Fehler geloggt:  {LOG_FILE}\n")

    print("TOP 5 LANGFRIST-INVESTMENTS:")
    for r in longterm_rows[:5]:
        print(f"  {r['name']:25s}  Score={r['longterm_score']:.1f}  {r['longterm_label']}")

    # --- Fear & Greed Multiplikator ---
    fg_value = fear_greed.get("value", 50)
    fg_long_m, fg_short_m = compute_fg_multiplier(fg_value)
    for r in results:
        r["cfd_long_score_raw"] = r["cfd_long_score"]
        r["cfd_short_score_raw"] = r["cfd_short_score"]
        r["cfd_long_score"] = round(min(r["cfd_long_score"] * fg_long_m, 10.0), 1)
        r["cfd_short_score"] = round(min(r["cfd_short_score"] * fg_short_m, 10.0), 1)
    print(f"\nF&G Multiplikator: Long x{fg_long_m}, Short x{fg_short_m} (F&G={fg_value})")

    # --- CFD Setups ---
    cfd_threshold = CFG["scoring"]["threshold"]
    cfd_top_n = CFG["cfd"]["top_n"]
    cfd_long_rows = sorted([r for r in results if r["cfd_long_score"] >= cfd_threshold],
                           key=lambda r: r["cfd_long_score"], reverse=True)[:cfd_top_n]
    cfd_short_rows = sorted([r for r in results if r["cfd_short_score"] >= cfd_threshold],
                            key=lambda r: r["cfd_short_score"], reverse=True)[:cfd_top_n]
    print(f"\nCFD Long Setups:   {len(cfd_long_rows)} (Threshold >= {cfd_threshold}, Top {cfd_top_n})")
    print(f"CFD Short Setups:  {len(cfd_short_rows)}")

    print("\nTOP 5 CFD LONG:")
    for r in cfd_long_rows[:5]:
        print(f"  {r['ticker']:10s}  Score={r['cfd_long_score']:.1f}/10  ADX={r['adx']}  "
              f"+DI={r.get('plus_di','?')}  RSI={r['rsi']}  Stop={r['stop_long']}  TP2={r['tp2_long']}")
    print("\nTOP 5 CFD SHORT:")
    for r in cfd_short_rows[:5]:
        print(f"  {r['ticker']:10s}  Score={r['cfd_short_score']:.1f}/10  ADX={r['adx']}  "
              f"-DI={r.get('minus_di','?')}  RSI={r['rsi']}  Stop={r['stop_short']}  TP2={r['tp2_short']}")

    # --- Portfolio-Check ---
    position_reports = []
    positions = list_positions()
    if positions:
        print(f"\nPrüfe {len(positions)} aktive CFD-Position(en) …")
        position_reports = check_positions(positions)
        for r in position_reports:
            if "error" in r:
                print(f"  {r['ticker']}: FEHLER")
            else:
                pnl_sign = "+" if r["pnl_pct"] >= 0 else ""
                print(f"  {r['ticker']} {r['direction'].upper()} | "
                      f"{pnl_sign}{r['pnl_pct']:.1f}% | {r['recommendation']}")

    # --- Investment-Portfolio-Check ---
    inv_stocks = list_stocks()
    stock_reports = []
    if inv_stocks:
        print(f"\nPrüfe {len(inv_stocks)} Aktie(n) im Investment-Portfolio …")
        stock_reports = check_stocks(inv_stocks, results)
        for r in stock_reports:
            warn_str = f" ⚠ {r['warning_count']} Warnungen" if r['warning_count'] else ""
            print(f"  {r.get('name', r['ticker']):25s}  {r['recommendation']}{warn_str}")

    # --- Output ---
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = Path(__file__).parent / "output" / date_str
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / "trading_signals.html"
    html_content = generate_html(
        longterm_rows, scan_time, cfd_long_rows, cfd_short_rows,
        fear_greed, position_reports, stock_reports, cfg=CFG,
    )
    html_path.write_text(html_content, encoding="utf-8")
    Path("trading_signals.html").write_text(html_content, encoding="utf-8")
    print(f"\nHTML-Bericht: {html_path.resolve()}")

    csv_path = output_dir / "trading_signals.csv"
    if longterm_rows:
        df_signals = pd.DataFrame(longterm_rows)
        df_signals.to_csv(csv_path, index=False, encoding="utf-8-sig")
        df_signals.to_csv("trading_signals.csv", index=False, encoding="utf-8-sig")
        print(f"CSV-Export:   {csv_path.resolve()}")

    # Alle Ergebnisse fuer Portfolio-Check (Dashboard braucht alle Ticker)
    if results:
        df_all = pd.DataFrame(results)
        df_all.to_csv(output_dir / "all_results.csv", index=False, encoding="utf-8-sig")
        df_all.to_csv("all_results.csv", index=False, encoding="utf-8-sig")

    cfd_all = ([{**r, "cfd_direction": "long"} for r in cfd_long_rows] +
               [{**r, "cfd_direction": "short"} for r in cfd_short_rows])
    if cfd_all:
        cfd_csv = output_dir / "cfd_setups.csv"
        df_cfd = pd.DataFrame(cfd_all)
        df_cfd.to_csv(cfd_csv, index=False, encoding="utf-8-sig")
        df_cfd.to_csv("cfd_setups.csv", index=False, encoding="utf-8-sig")
        print(f"CFD-CSV:      {cfd_csv.resolve()}")

    # --- Backtesting ---
    if CFG["backtesting"]["enabled"] and not args.dry_run:
        try:
            from cfd_backtesting import init_db, log_scan_run, log_cfd_signal, resolve_signals
            init_db()
            run_id = log_scan_run(scan_date=date_str, fear_greed=fear_greed.get("value", 50),
                                  ticker_count=total, long_signals=len(cfd_long_rows),
                                  short_signals=len(cfd_short_rows))
            for r in cfd_long_rows:
                log_cfd_signal(run_id, r, "long")
            for r in cfd_short_rows:
                log_cfd_signal(run_id, r, "short")
            print(f"\nBacktesting: {len(cfd_long_rows) + len(cfd_short_rows)} Signale geloggt (Run #{run_id})")
            resolve_signals(min_days=CFG["backtesting"]["resolve_after_days"],
                            max_days=CFG["backtesting"]["resolve_max_days"])
        except Exception as e:
            print(f"Backtesting-Fehler (nicht kritisch): {e}")

    # --- Dashboard Push ---
    try:
        from post_to_dashboard import post_to_dashboard
        post_to_dashboard(str(output_dir), fear_greed)
    except Exception as e:
        print(f"Dashboard-Push übersprungen: {e}")

    # --- Investment-Portfolio Check ---
    stock_reports = []
    try:
        inv_stocks = list_stocks()
        if inv_stocks:
            stock_reports = check_stocks(inv_stocks, results)
            ok_n = sum(1 for r in stock_reports if r.get("warning_count", 0) <= 1)
            watch_n = sum(1 for r in stock_reports if r.get("warning_count", 0) == 2)
            crit_n = sum(1 for r in stock_reports if r.get("warning_count", 0) >= 3)
            print(f"\nInvestment-Portfolio: {len(stock_reports)} Aktien "
                  f"(\u2705 {ok_n} ok | \u26a0 {watch_n} beobachten | \U0001f534 {crit_n} pr\u00fcfen)")
    except Exception as e:
        print(f"Investment-Portfolio-Check \u00fcbersprungen: {e}")

    # --- Telegram Alerts (nur Daily Summary, keine Einzel-Alerts) ---
    try:
        from telegram_alerts import send_daily_summary
        top_all = ([{**r, "cfd_direction": "long"} for r in cfd_long_rows[:3]] +
                   [{**r, "cfd_direction": "short"} for r in cfd_short_rows[:3]])
        send_daily_summary(fear_greed, len(cfd_long_rows), len(cfd_short_rows),
                           top_all, len(positions), stock_reports=stock_reports)
        print("Telegram: Daily Summary gesendet")
    except Exception as e:
        print(f"Telegram \u00fcbersprungen: {e}")

    # --- Investment-Portfolio Telegram Alerts ---
    if stock_reports:
        try:
            from telegram_alerts import send_stock_portfolio_alert
            send_stock_portfolio_alert(stock_reports)
        except Exception as e:
            print(f"Investment-Portfolio Telegram-Alert \u00fcbersprungen: {e}")

    if not args.no_open and sys.stdout.isatty():
        try:
            webbrowser.open(html_path.resolve().as_uri())
        except Exception:
            pass

    print("\nFertig!")


if __name__ == "__main__":
    main()
