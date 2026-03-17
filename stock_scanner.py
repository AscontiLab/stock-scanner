#!/usr/bin/env python3
"""
Technical Analysis Stock Scanner
Scans NASDAQ 100, S&P 500 and DAX 40 for short-term trading signals (1-5 day horizon).
"""

import argparse
import copy
import logging
import re
import sys
import time
import warnings
import webbrowser
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "cfd": {
        "adx_min": 30, "adx_strong": 40,
        "rsi_long_min": 45, "rsi_long_max": 62,
        "rsi_short_min": 38, "rsi_short_max": 55,
        "atr_pct_min": 1.0, "atr_pct_max": 8.0,
        "trend_maturity_min_days": 3,
        "vol_ratio_min": 1.2, "vol_ratio_bonus": 2.0,
        "max_gap_pct": 5.0,
        "atr_stop_mult": 1.5, "atr_tp1_mult": 1.5, "atr_tp2_mult": 3.0,
        "top_n": 10,
    },
    "scoring": {
        "weights": {
            "adx_di": 2.0, "ma_structure": 1.5, "ema_stack": 1.5,
            "macd": 1.0, "rsi_zone": 1.0, "volume": 0.5, "no_gap": 0.5,
        },
        "bonus": {
            "trend_maturity_days": 5, "trend_maturity_pts": 0.5,
            "vol_ratio_high": 2.0, "vol_ratio_pts": 0.5,
            "adx_strong": 40, "adx_strong_pts": 0.5,
            "squeeze_fire_pts": 0.5,
        },
        "threshold": 5.0, "max_score": 10.0,
    },
    "main_scan": {"min_score": 4, "max_gap_pct": 3.0},
    "backtesting": {
        "db_file": "cfd_backtesting.db", "resolve_after_days": 1,
        "resolve_max_days": 10, "enabled": True,
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
            # Deep-merge: nur vorhandene Sections ueberschreiben
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
# Konstanten
# ---------------------------------------------------------------------------

MIN_AVG_VOLUME = 500_000  # Mindest-Durchschnittsvolumen (20 Tage)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "scan_errors.log"
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.ERROR,
    format="%(asctime)s  %(levelname)s  %(message)s",
)

# ---------------------------------------------------------------------------
# Ticker lists
# ---------------------------------------------------------------------------

NASDAQ100_FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO",
    "COST", "NFLX", "AMD", "ADBE", "ASML", "QCOM", "INTC", "INTU", "AMAT",
    "CSCO", "TXN", "AMGN", "MU", "ISRG", "BKNG", "LRCX", "MDLZ", "REGN",
    "ADI", "PANW", "KLAC", "MRVL", "CDNS", "SNPS", "PYPL", "SBUX", "GILD",
    "ADP", "CTAS", "ORLY", "PCAR", "MNST", "CHTR", "NXPI", "MELI", "FTNT",
    "WDAY", "CPRT", "PAYX", "EXC", "SIRI", "ODFL", "VRSK", "BIIB", "DLTR",
    "DXCM", "ANSS", "FANG", "FAST", "IDXX", "ILMN", "KDP", "KHC", "LCID",
    "LULU", "MAR", "MCHP", "MRNA", "MTCH", "OKTA", "ROST", "TTWO",
    "VRSN", "VRTX", "XEL", "ZS", "ZM", "TEAM", "CRWD", "DDOG", "SNOW",
    "ABNB", "EBAY", "WBA", "CEG", "ON", "GFS", "ENPH", "ALGN", "GEHC",
    "FSLR", "SWKS", "BMRN", "AKAM", "CTSH",
]

SP500_FALLBACK = [
    "JPM", "UNH", "V", "MA", "LLY", "JNJ", "PG", "HD", "MRK", "ABBV",
    "BAC", "KO", "PEP", "WMT", "CVX", "XOM", "CRM", "ACN", "TMO", "MCD",
    "ABT", "ORCL", "NEE", "DHR", "PM", "IBM", "RTX", "CAT", "HON", "GE",
    "T", "VZ", "CMCSA", "MS", "GS", "BLK", "SCHW", "C", "WFC", "AXP",
    "LOW", "SPGI", "DE", "NKE", "AMAT", "MMM", "UPS", "LMT", "MO", "USB",
    "DUK", "SO", "AEP", "SRE", "D", "PCG", "EXC", "ETR", "AWK", "ES",
    "BMY", "AMGN", "GILD", "REGN", "VRTX", "BIIB", "MRNA", "ILMN",
    "ZTS", "IDXX", "A", "BDX", "BAX", "EW", "ISRG", "IQV", "CI", "HUM",
    "CNC", "MOH", "DVA", "HCA", "UHS", "THC", "ELV", "CVS", "WBA", "CAH",
    "MCK", "ABC", "AmerisourceBergen", "PFE", "MDT", "SYK", "BSX", "ZBH",
    "DXCM", "HAL", "SLB", "BKR", "MPC", "VLO", "PSX", "COP", "PXD", "EOG",
    "DVN", "HES", "MRO", "APA", "FANG", "OXY", "WMB", "OKE", "KMI", "ET",
    "FCX", "NEM", "AA", "X", "NUE", "STLD", "CLF", "MP", "ALB", "SQM",
    "AMT", "PLD", "CCI", "EQIX", "PSA", "EXR", "AVB", "EQR", "MAA", "UDR",
]

DAX40_FALLBACK = [
    "ADS.DE", "AIR.DE", "ALV.DE", "BAS.DE", "BAYN.DE", "BEI.DE", "BMW.DE",
    "BNR.DE", "CON.DE", "1COV.DE", "DHER.DE", "DHL.DE", "DTE.DE", "DTG.DE",
    "ENR.DE", "EOAN.DE", "FRE.DE", "HEI.DE", "HEN3.DE", "IFX.DE", "INL.DE",
    "MBG.DE", "MRK.DE", "MTX.DE", "MUV2.DE", "P911.DE", "PAH3.DE", "QIA.DE",
    "RHM.DE", "RWE.DE", "SAP.DE", "SIE.DE", "SHL.DE", "SY1.DE", "VNA.DE",
    "VOW3.DE", "ZAL.DE", "DBK.DE", "DB1.DE", "HFG.DE",
]

EUROSTOXX50_FALLBACK = [
    # France
    "AI.PA", "AIR.PA", "ACA.PA", "BN.PA", "BNP.PA", "DG.PA", "EL.PA",
    "ENGI.PA", "GLE.PA", "KER.PA", "LR.PA", "MC.PA", "OR.PA", "ORA.PA",
    "RMS.PA", "SAF.PA", "SAN.PA", "SGO.PA", "SU.PA", "TTE.PA",
    # Germany
    "ALV.DE", "BAS.DE", "BAYN.DE", "BMW.DE", "DBK.DE", "DTE.DE",
    "MBG.DE", "MUV2.DE", "RWE.DE", "SAP.DE", "SIE.DE", "VOW3.DE",
    # Netherlands
    "ADYEN.AS", "ASML.AS", "INGA.AS", "PHIA.AS", "PRX.AS", "URW.AS",
    # Spain
    "BBVA.MC", "IBE.MC", "ITX.MC", "SAN.MC",
    # Italy
    "ENEL.MI", "ENI.MI", "STLAM.MI",
    # Belgium
    "ABI.BR",
    # Ireland
    "CRG.IR",
    # Finland
    "NOKIA.HE",
]

TECDAX_FALLBACK = [
    "ADTN.DE", "AIXA.DE", "BC8.DE", "COK.DE", "AFX.DE", "DTE.DE",
    "DRW3.DE", "EVT.DE", "FNTN.DE", "GFT.DE", "IFX.DE", "MUM.DE",
    "NEM.DE", "NDX1.DE", "PNE.DE", "QIA.DE", "RAA.DE", "SAP.DE",
    "SIE.DE", "SHL.DE", "WAF.DE", "S92.DE", "SAX.DE", "TMV.DE",
    "SRT3.DE", "EVD.DE",
]

MDAX_FALLBACK = [
    "BOSS.DE", "LHA.DE", "FRA.DE", "G1A.DE", "HOT.DE", "JUN3.DE",
    "KGX.DE", "KBX.DE", "LXS.DE", "LEG.DE", "PSM.DE", "PUM.DE",
    "G24.DE", "TLX.DE", "TKA.DE", "TUI1.DE", "WCH.DE", "EVD.DE",
    "DUE.DE", "FIE.DE", "FPE3.DE", "KRN.DE", "EVK.DE", "GXI.DE",
    "HAG.DE", "DWS.DE", "GYC.DE", "HBH.DE", "PFV.DE", "NOEJ.DE",
]

SDAX_FALLBACK = [
    "AT1.DE", "BFSA.DE", "BVB.DE", "DMP.DE", "ELG.DE", "FTK.DE",
    "HYQ.DE", "JEN.DE", "JST.DE", "OHB.DE", "SIX2.DE", "SZU.DE",
    "TAK.DE", "VBK.DE", "BSL.DE", "BDT.DE", "DEZ.DE", "IIND.DE",
    "KWS.DE", "LPKF.DE", "PHA.DE", "YSN.DE", "STO3.DE", "WUW.DE",
]

# Exchange suffix mapping for EURO STOXX 50 Wikipedia scraping
COUNTRY_TO_SUFFIX = {
    "France": ".PA",
    "Germany": ".DE",
    "Netherlands": ".AS",
    "Spain": ".MC",
    "Italy": ".MI",
    "Belgium": ".BR",
    "Finland": ".HE",
    "Ireland": ".IR",
    "Portugal": ".LS",
    "Austria": ".VI",
}

import io
import json
import urllib.request

from utils import fg_label as _fg_label

TICKER_SOURCES: dict[str, tuple[str, int]] = {}


def _set_source(list_name: str, source: str, count: int) -> None:
    TICKER_SOURCES[list_name] = (source, count)


def filter_valid_tickers(tickers: list, label: str) -> list:
    """
    Entfernt ungültige Ticker (kein valides Symbolformat).
    Erlaubt Buchstaben/Ziffern sowie . und -; muss mit alnum starten.
    """
    pattern = re.compile(r"^[A-Z0-9][A-Z0-9.\-]+$")
    valid = []
    invalid = 0
    for t in tickers:
        t = str(t).strip().upper()
        if not t:
            invalid += 1
            continue
        if pattern.match(t):
            valid.append(t)
        else:
            invalid += 1
    if invalid:
        print(f"  Hinweis: {label} – {invalid} ungültige Ticker entfernt.")
    return valid


def _fetch_html(url: str) -> str | None:
    """Fetch HTML with a browser-like User-Agent to avoid 403 blocks."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except Exception:
        return None


def _safe_read_html(url: str) -> list:
    html = _fetch_html(url)
    if html:
        try:
            return pd.read_html(io.StringIO(html), flavor="lxml")
        except Exception:
            try:
                return pd.read_html(io.StringIO(html))
            except Exception:
                pass
    return []


def get_nasdaq100_tickers() -> list:
    tables = _safe_read_html("https://en.wikipedia.org/wiki/NASDAQ-100")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = t[col].dropna().tolist()
                tickers = [str(x).strip().replace(".", "-") for x in tickers if str(x).strip()]
                if len(tickers) > 50:
                    _set_source("NASDAQ 100", "wiki", len(tickers))
                    return tickers
    _set_source("NASDAQ 100", "fallback", len(NASDAQ100_FALLBACK))
    return NASDAQ100_FALLBACK


def get_sp500_tickers() -> list:
    tables = _safe_read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = t[col].dropna().tolist()
                tickers = [str(x).strip().replace(".", "-") for x in tickers if str(x).strip()]
                if len(tickers) > 400:
                    _set_source("S&P 500", "wiki", len(tickers))
                    return tickers
    _set_source("S&P 500", "fallback", len(SP500_FALLBACK))
    return SP500_FALLBACK


def get_dax40_tickers() -> list:
    tables = _safe_read_html("https://en.wikipedia.org/wiki/DAX")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = t[col].dropna().tolist()
                tickers = [str(x).strip() for x in tickers if str(x).strip()]
                tickers = [x if x.endswith(".DE") else x + ".DE" for x in tickers]
                if len(tickers) >= 30:
                    _set_source("DAX 40", "wiki", len(tickers))
                    return tickers
    _set_source("DAX 40", "fallback", len(DAX40_FALLBACK))
    return DAX40_FALLBACK


def _add_de_suffix(tickers: list) -> list:
    """Add .DE suffix to tickers that have no exchange suffix yet."""
    result = []
    for x in tickers:
        x = str(x).strip()
        if not x:
            continue
        result.append(x if "." in x else x + ".DE")
    return result


def get_eurostoxx50_tickers() -> list:
    tables = _safe_read_html("https://en.wikipedia.org/wiki/Euro_Stoxx_50")
    for t in tables:
        cols_lower = {str(c).lower(): c for c in t.columns}
        ticker_col = next(
            (cols_lower[k] for k in cols_lower if "ticker" in k or "symbol" in k), None
        )
        country_col = next(
            (cols_lower[k] for k in cols_lower if "country" in k), None
        )
        if ticker_col is None:
            continue
        result = []
        for _, row in t.iterrows():
            ticker = str(row[ticker_col]).strip()
            if not ticker or ticker.lower() == "nan":
                continue
            if "." in ticker:
                result.append(ticker)
            elif country_col:
                country = str(row[country_col]).strip()
                suffix = COUNTRY_TO_SUFFIX.get(country, "")
                result.append(ticker + suffix)
            else:
                result.append(ticker)
        if len(result) >= 40:
            _set_source("Euro Stoxx 50", "wiki", len(result))
            return result
    _set_source("Euro Stoxx 50", "fallback", len(EUROSTOXX50_FALLBACK))
    return EUROSTOXX50_FALLBACK


def get_tecdax_tickers() -> list:
    tables = _safe_read_html("https://en.wikipedia.org/wiki/TecDAX")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = _add_de_suffix(t[col].dropna().tolist())
                if len(tickers) >= 20:
                    _set_source("TecDAX", "wiki", len(tickers))
                    return tickers
    _set_source("TecDAX", "fallback", len(TECDAX_FALLBACK))
    return TECDAX_FALLBACK


def get_mdax_tickers() -> list:
    tables = _safe_read_html("https://en.wikipedia.org/wiki/MDAX")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = _add_de_suffix(t[col].dropna().tolist())
                if len(tickers) >= 30:
                    _set_source("MDAX", "wiki", len(tickers))
                    return tickers
    _set_source("MDAX", "fallback", len(MDAX_FALLBACK))
    return MDAX_FALLBACK


def get_sdax_tickers() -> list:
    tables = _safe_read_html("https://en.wikipedia.org/wiki/SDAX")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = _add_de_suffix(t[col].dropna().tolist())
                if len(tickers) >= 50:
                    _set_source("SDAX", "wiki", len(tickers))
                    return tickers
    _set_source("SDAX", "fallback", len(SDAX_FALLBACK))
    return SDAX_FALLBACK


# ---------------------------------------------------------------------------
# Technical indicator helpers
# ---------------------------------------------------------------------------

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_macd(close: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_bollinger(close: pd.Series, period=20, std_dev=2):
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, sma, lower


def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    up_move   = high.diff()
    down_move = -low.diff()
    plus_dm  = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
    ).max(axis=1)
    atr_s    = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_s
    dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx, plus_di, minus_di


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Berechnet Average True Range (ATR)."""
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(period).mean()


def detect_candlestick_patterns(df: pd.DataFrame) -> dict:
    """Detect common candlestick patterns on the last two candles."""
    if len(df) < 3:
        return {"pattern": "none", "bias": 0}

    o, h, l, c = (
        df["Open"].values,
        df["High"].values,
        df["Low"].values,
        df["Close"].values,
    )

    body = abs(c - o)
    candle_range = h - l
    avg_body = np.mean(body[-10:]) if len(body) >= 10 else np.mean(body)

    # Last candle indices
    i = -1
    i2 = -2

    patterns = []

    # Doji
    if candle_range[-1] > 0 and body[i] / candle_range[i] < 0.1:
        patterns.append(("Doji", 0))

    # Hammer (bullish) — small body at top, long lower wick
    lower_wick = min(o[i], c[i]) - l[i]
    upper_wick = h[i] - max(o[i], c[i])
    if lower_wick > 2 * body[i] and upper_wick < body[i] * 0.5 and c[i] > o[i]:
        patterns.append(("Hammer", 1))

    # Shooting Star (bearish)
    if upper_wick > 2 * body[i] and lower_wick < body[i] * 0.5 and c[i] < o[i]:
        patterns.append(("Shooting Star", -1))

    # Bullish Engulfing
    if (
        c[i2] < o[i2]  # prev bearish
        and c[i] > o[i]  # curr bullish
        and o[i] <= c[i2]
        and c[i] >= o[i2]
    ):
        patterns.append(("Bull Engulfing", 1))

    # Bearish Engulfing
    if (
        c[i2] > o[i2]  # prev bullish
        and c[i] < o[i]  # curr bearish
        and o[i] >= c[i2]
        and c[i] <= o[i2]
    ):
        patterns.append(("Bear Engulfing", -1))

    # Morning Star (3-candle, bullish reversal)
    if len(df) >= 3:
        if (
            c[-3] < o[-3]  # first: bearish
            and body[-2] < avg_body * 0.5  # second: small body
            and c[-1] > o[-1]  # third: bullish
            and c[-1] > (o[-3] + c[-3]) / 2
        ):
            patterns.append(("Morning Star", 1))

    # Evening Star (3-candle, bearish reversal)
    if len(df) >= 3:
        if (
            c[-3] > o[-3]
            and body[-2] < avg_body * 0.5
            and c[-1] < o[-1]
            and c[-1] < (o[-3] + c[-3]) / 2
        ):
            patterns.append(("Evening Star", -1))

    if not patterns:
        return {"pattern": "none", "bias": 0}

    # Return dominant pattern
    biases = [b for _, b in patterns]
    dominant_bias = max(biases, key=abs) if biases else 0
    dominant = [p for p, b in patterns if b == dominant_bias]
    return {"pattern": ", ".join(dominant), "bias": dominant_bias}


# ---------------------------------------------------------------------------
# Fear & Greed Index
# ---------------------------------------------------------------------------

def get_fear_greed() -> dict:
    """Holt CNN Fear & Greed Index (0–100). Fallback: neutral."""
    try:
        req = urllib.request.Request(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            value = round(float(data["fear_and_greed"]["score"]))
            return {"value": value, "label": _fg_label(value)}
    except Exception:
        return {"value": 50, "label": "Neutral (Fallback)"}


# ---------------------------------------------------------------------------
# Core analysis function
# ---------------------------------------------------------------------------

def analyze_ticker(ticker: str, market: str) -> dict | None:
    """Download data and compute all signals. Returns result dict or None."""
    try:
        df = yf.download(
            ticker,
            period="90d",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        if df is None or len(df) < 30:
            return None

        # yfinance >= 0.2.x returns MultiIndex columns like ('Close', 'AAPL')
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        df = df.dropna()
        if len(df) < 30:
            return None
    except Exception as exc:
        logging.error("%s: %s", ticker, exc)
        return None

    close = df["Close"]
    volume = df["Volume"]
    open_ = df["Open"]
    high = df["High"]
    low = df["Low"]

    current_price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2])
    pct_change = (current_price - prev_price) / prev_price * 100

    # --- Mindest-Liquidität ---
    avg_vol_20 = float(volume.rolling(20).mean().iloc[-1])
    if avg_vol_20 < MIN_AVG_VOLUME:
        return None

    # --- ATR (wird früh benötigt für Squeeze-Keltner) ---
    atr_series = compute_atr(high, low, close)
    atr_val = float(atr_series.iloc[-1])
    atr_pct = round(atr_val / current_price * 100, 2)

    buy_signals = 0
    sell_signals = 0
    signal_details = {}

    # --- RSI ---
    rsi = compute_rsi(close)
    rsi_val = float(rsi.iloc[-1])
    signal_details["RSI"] = round(rsi_val, 1)
    if rsi_val < 30:
        buy_signals += 1
        signal_details["RSI_signal"] = "BUY"
    elif rsi_val > 70:
        sell_signals += 1
        signal_details["RSI_signal"] = "SELL"
    else:
        signal_details["RSI_signal"] = "neutral"

    # --- MACD ---
    macd_line, signal_line, histogram = compute_macd(close)
    prev_hist = float(histogram.iloc[-2]) if len(histogram) >= 2 else 0
    curr_hist = float(histogram.iloc[-1])
    if prev_hist < 0 and curr_hist > 0:
        buy_signals += 1
        macd_signal = "BUY"
    elif prev_hist > 0 and curr_hist < 0:
        sell_signals += 1
        macd_signal = "SELL"
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

    sma20_val = float(sma20.iloc[-1])
    sma50_val = float(sma50.iloc[-1])
    ema9_val = float(ema9.iloc[-1])
    ema21_val = float(ema21.iloc[-1])
    ema9_prev = float(ema9.iloc[-2])
    ema21_prev = float(ema21.iloc[-2])

    ma_buy = current_price > sma20_val > sma50_val
    ma_sell = current_price < sma20_val < sma50_val
    ema_cross_buy = ema9_prev < ema21_prev and ema9_val > ema21_val
    ema_cross_sell = ema9_prev > ema21_prev and ema9_val < ema21_val

    if ma_buy or ema_cross_buy:
        buy_signals += 1
        ma_signal = "BUY"
    elif ma_sell or ema_cross_sell:
        sell_signals += 1
        ma_signal = "SELL"
    else:
        ma_signal = "neutral"
    signal_details["MA"] = ma_signal

    # --- Bollinger Bands ---
    bb_upper, bb_mid, bb_lower = compute_bollinger(close)
    bb_upper_val = float(bb_upper.iloc[-1])
    bb_lower_val = float(bb_lower.iloc[-1])
    bb_width = float((bb_upper.iloc[-1] - bb_lower.iloc[-1]) / bb_mid.iloc[-1])
    avg_bb_width = float(
        ((bb_upper - bb_lower) / bb_mid).rolling(20).mean().iloc[-1]
    )
    squeeze = not np.isnan(avg_bb_width) and bb_width < avg_bb_width * 0.8

    if current_price < bb_lower_val:
        buy_signals += 1
        bb_signal = "BUY (below lower)"
    elif current_price < bb_lower_val * 1.01 and squeeze:
        buy_signals += 1
        bb_signal = "BUY (squeeze)"
    elif current_price > bb_upper_val:
        sell_signals += 1
        bb_signal = "SELL (above upper)"
    else:
        bb_signal = "neutral"
    signal_details["Bollinger"] = bb_signal

    # --- Volume ---
    curr_vol = float(volume.iloc[-1])
    vol_ratio = curr_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0

    if vol_ratio > 1.5 and pct_change > 0:
        buy_signals += 1
        vol_signal = f"BUY ({vol_ratio:.1f}x avg)"
    elif vol_ratio > 1.5 and pct_change < 0:
        sell_signals += 1
        vol_signal = f"SELL ({vol_ratio:.1f}x avg)"
    else:
        vol_signal = f"neutral ({vol_ratio:.1f}x avg)"
    signal_details["Volume"] = vol_signal

    # --- Candlestick ---
    candle_df = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close}
    )
    candle_result = detect_candlestick_patterns(candle_df)
    if candle_result["bias"] > 0:
        buy_signals += 1
    elif candle_result["bias"] < 0:
        sell_signals += 1
    signal_details["Candlestick"] = candle_result["pattern"] if candle_result["pattern"] != "none" else "neutral"

    # --- VWAP (20-Tages gewichteter Durchschnitt) ---
    typical_price = (high + low + close) / 3
    vol_20 = volume.tail(20)
    tp_20 = typical_price.tail(20)
    vwap_val = float((tp_20 * vol_20).sum() / vol_20.sum()) if float(vol_20.sum()) > 0 else current_price
    if current_price > vwap_val:
        buy_signals += 1
        vwap_signal = f"BUY ({vwap_val:.2f})"
    else:
        sell_signals += 1
        vwap_signal = f"SELL ({vwap_val:.2f})"
    signal_details["VWAP"] = vwap_signal

    # --- Squeeze Momentum (Lazybear-Methode) ---
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
        buy_signals += 1
        sq_signal = f"BUY (mom={squeeze_momentum:.3f})"
    elif not sq_on and squeeze_momentum < 0:
        sell_signals += 1
        sq_signal = f"SELL (mom={squeeze_momentum:.3f})"
    else:
        sq_signal = f"Squeeze {'ON' if sq_on else 'OFF'}"
    signal_details["Squeeze"] = sq_signal

    net_score = buy_signals - sell_signals

    # --- ADX ---
    adx_s, plus_di_s, minus_di_s = compute_adx(high, low, close)
    adx_val      = float(adx_s.iloc[-1])
    plus_di_val  = float(plus_di_s.iloc[-1])
    minus_di_val = float(minus_di_s.iloc[-1])

    # --- Größter Tages-Move der letzten 5 Tage (Gap-Filter) ---
    recent_max_gap = float(close.pct_change().tail(5).abs().max()) * 100

    # --- ATR-Qualitaetsfilter ---
    cfd_atr_ok = CFG["cfd"]["atr_pct_min"] <= atr_pct <= CFG["cfd"]["atr_pct_max"]

    # --- Trend-Reife: Wie viele der letzten N Tage MA-Struktur gehalten ---
    trend_long_days = 0
    trend_short_days = 0
    sma20_arr = sma20.values
    sma50_arr = sma50.values
    close_arr = close.values
    for i in range(max(len(close_arr) - 10, 0), len(close_arr)):
        if close_arr[i] > sma20_arr[i] > sma50_arr[i]:
            trend_long_days += 1
        if close_arr[i] < sma20_arr[i] < sma50_arr[i]:
            trend_short_days += 1

    cfd_cfg = CFG["cfd"]
    w = CFG["scoring"]["weights"]
    bonus = CFG["scoring"]["bonus"]

    # --- CFD Long Score (gewichtet, max 8.0 + 2.0 Bonus) ---
    cfd_long = 0.0
    # ADX + DI-Bestaetigung (2.0)
    if adx_val > cfd_cfg["adx_min"] and plus_di_val > minus_di_val:
        cfd_long += w["adx_di"]
    # MA-Struktur (1.5)
    if current_price > sma20_val > sma50_val:
        cfd_long += w["ma_structure"]
    # EMA-Stack (1.5)
    if ema9_val > ema21_val:
        cfd_long += w["ema_stack"]
    # MACD Histogram (1.0)
    if curr_hist > 0 and curr_hist > prev_hist:
        cfd_long += w["macd"]
    # RSI in Zone (1.0)
    if cfd_cfg["rsi_long_min"] <= rsi_val <= cfd_cfg["rsi_long_max"]:
        cfd_long += w["rsi_zone"]
    # Volume (0.5)
    if vol_ratio >= cfd_cfg["vol_ratio_min"]:
        cfd_long += w["volume"]
    # Kein Gap (0.5)
    if recent_max_gap < cfd_cfg["max_gap_pct"]:
        cfd_long += w["no_gap"]
    # Bonus-Punkte (bis +2.0)
    if trend_long_days >= bonus["trend_maturity_days"]:
        cfd_long += bonus["trend_maturity_pts"]
    if vol_ratio >= bonus["vol_ratio_high"]:
        cfd_long += bonus["vol_ratio_pts"]
    if adx_val > bonus["adx_strong"]:
        cfd_long += bonus["adx_strong_pts"]
    if not sq_on and squeeze_momentum > 0:
        cfd_long += bonus["squeeze_fire_pts"]

    # --- CFD Short Score (gewichtet, max 8.0 + 2.0 Bonus) ---
    cfd_short = 0.0
    if adx_val > cfd_cfg["adx_min"] and minus_di_val > plus_di_val:
        cfd_short += w["adx_di"]
    if current_price < sma20_val < sma50_val:
        cfd_short += w["ma_structure"]
    if ema9_val < ema21_val:
        cfd_short += w["ema_stack"]
    if curr_hist < 0 and curr_hist < prev_hist:
        cfd_short += w["macd"]
    if cfd_cfg["rsi_short_min"] <= rsi_val <= cfd_cfg["rsi_short_max"]:
        cfd_short += w["rsi_zone"]
    if vol_ratio >= cfd_cfg["vol_ratio_min"]:
        cfd_short += w["volume"]
    if recent_max_gap < cfd_cfg["max_gap_pct"]:
        cfd_short += w["no_gap"]
    if trend_short_days >= bonus["trend_maturity_days"]:
        cfd_short += bonus["trend_maturity_pts"]
    if vol_ratio >= bonus["vol_ratio_high"]:
        cfd_short += bonus["vol_ratio_pts"]
    if adx_val > bonus["adx_strong"]:
        cfd_short += bonus["adx_strong_pts"]
    if not sq_on and squeeze_momentum < 0:
        cfd_short += bonus["squeeze_fire_pts"]

    # --- ATR-Gate + Trend-Reife-Filter ---
    if not cfd_atr_ok:
        cfd_long = 0.0
        cfd_short = 0.0
    else:
        if trend_long_days < cfd_cfg["trend_maturity_min_days"]:
            cfd_long = 0.0
        if trend_short_days < cfd_cfg["trend_maturity_min_days"]:
            cfd_short = 0.0

    # --- Exklusive Richtung: nur staerkere Richtung behalten ---
    if cfd_long >= CFG["scoring"]["threshold"] and cfd_short >= CFG["scoring"]["threshold"]:
        if cfd_long > cfd_short:
            cfd_short = 0.0
        elif cfd_short > cfd_long:
            cfd_long = 0.0
        else:
            # Gleichstand: DI entscheidet
            if plus_di_val >= minus_di_val:
                cfd_short = 0.0
            else:
                cfd_long = 0.0

    cfd_long = round(cfd_long, 1)
    cfd_short = round(cfd_short, 1)

    # --- ATR-basierte Stop/Target-Level ---
    atr_stop = cfd_cfg["atr_stop_mult"]
    atr_tp1 = cfd_cfg["atr_tp1_mult"]
    atr_tp2 = cfd_cfg["atr_tp2_mult"]
    stop_long   = round(current_price - atr_stop * atr_val, 2)
    tp1_long    = round(current_price + atr_tp1 * atr_val, 2)
    tp2_long    = round(current_price + atr_tp2 * atr_val, 2)
    stop_short  = round(current_price + atr_stop * atr_val, 2)
    tp1_short   = round(current_price - atr_tp1 * atr_val, 2)
    tp2_short   = round(current_price - atr_tp2 * atr_val, 2)

    # --- RVOL Label ---
    rvol_label = "🔥 Hoch" if vol_ratio > 2.0 else "↑ Erhöht" if vol_ratio > 1.5 else "— Normal"

    # Use ticker as name (avoids extra API call per ticker)
    name = ticker

    return {
        "ticker": ticker,
        "name": name,
        "market": market,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "net_score": net_score,
        "rsi": signal_details.get("RSI", "-"),
        "rsi_signal": signal_details.get("RSI_signal", "-"),
        "macd": signal_details.get("MACD", "-"),
        "ma": signal_details.get("MA", "-"),
        "bollinger": signal_details.get("Bollinger", "-"),
        "volume": signal_details.get("Volume", "-"),
        "candlestick": signal_details.get("Candlestick", "-"),
        "vwap": signal_details.get("VWAP", "-"),
        "squeeze": signal_details.get("Squeeze", "-"),
        "price": round(current_price, 2),
        "pct_change": round(pct_change, 2),
        # CFD-Felder
        "atr": round(atr_val, 3),
        "atr_pct": atr_pct,
        "adx": round(adx_val, 1),
        "plus_di": round(plus_di_val, 1),
        "minus_di": round(minus_di_val, 1),
        "vol_ratio": round(vol_ratio, 2),
        "rvol_label": rvol_label,
        "recent_max_gap": round(recent_max_gap, 1),
        "cfd_long_score": cfd_long,
        "cfd_short_score": cfd_short,
        "cfd_quality_score": max(cfd_long, cfd_short),
        "trend_long_days": trend_long_days,
        "trend_short_days": trend_short_days,
        "stop_long": stop_long,
        "tp1_long": tp1_long,
        "tp2_long": tp2_long,
        "stop_short": stop_short,
        "tp1_short": tp1_short,
        "tp2_short": tp2_short,
    }



# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

SIGNAL_COLORS_BUY = {
    8: "#0b3d20",
    7: "#0b3d20",
    6: "#145a32",
    5: "#1e8449",
    4: "#27ae60",
}
SIGNAL_COLORS_SELL = {
    8: "#4a0f0a",
    7: "#4a0f0a",
    6: "#7b241c",
    5: "#a93226",
    4: "#e74c3c",
}

STRENGTH = {8: "💎 Stark", 7: "💎 Stark", 6: "⭐ Gut", 5: "⭐ Gut", 4: "✓ Ok"}


def score_color(score: int, direction: str) -> str:
    abs_score = abs(score)
    if direction == "buy":
        return SIGNAL_COLORS_BUY.get(min(abs_score, 8), "#eafaf1")
    return SIGNAL_COLORS_SELL.get(min(abs_score, 8), "#fdedec")


def signal_badge(text: str) -> str:
    text_lower = text.lower()
    if "buy" in text_lower or "bull" in text_lower or "hammer" in text_lower or "morning" in text_lower:
        color = "#27ae60"
    elif "sell" in text_lower or "bear" in text_lower or "shooting" in text_lower or "evening" in text_lower:
        color = "#e74c3c"
    else:
        color = "#7f8c8d"
    return (
        f'<span style="background:{color};color:white;padding:2px 6px;'
        f'border-radius:4px;font-size:0.78em;white-space:nowrap">{text}</span>'
    )


def build_row(row: dict, direction: str) -> str:
    score = row["net_score"]
    bg = score_color(score, direction)
    score_text = f"+{score}" if score > 0 else str(score)
    abs_score = abs(score)
    strength = STRENGTH.get(abs_score, "")
    pct = row["pct_change"]
    pct_color = "#27ae60" if pct >= 0 else "#e74c3c"
    pct_str = f'<span style="color:{pct_color}">{pct:+.2f}%</span>'

    cells = [
        f'<td style="font-weight:bold">{row["ticker"]}</td>',
        f'<td>{row["name"]}</td>',
        f'<td>{row["market"]}</td>',
        f'<td style="font-weight:bold;text-align:center">{score_text}</td>',
        f'<td style="text-align:center">{strength}</td>',
        f'<td style="text-align:center">{row["rsi"]}</td>',
        f'<td style="text-align:center">{signal_badge(row["macd"])}</td>',
        f'<td style="text-align:center">{signal_badge(row["ma"])}</td>',
        f'<td style="text-align:center">{signal_badge(row["bollinger"])}</td>',
        f'<td style="text-align:center">{signal_badge(row["volume"])}</td>',
        f'<td style="text-align:center">{signal_badge(row["candlestick"])}</td>',
        f'<td style="text-align:center">{signal_badge(row.get("vwap", "-"))}</td>',
        f'<td style="text-align:center">{signal_badge(row.get("squeeze", "-"))}</td>',
        f'<td style="text-align:right">{row["price"]}</td>',
        f'<td style="text-align:right">{pct_str}</td>',
    ]
    cells_html = "\n".join(cells)
    return f'<tr style="background:{bg}">\n{cells_html}\n</tr>'


TABLE_HEADERS = [
    "Ticker", "Name", "Markt", "Score", "Stärke", "RSI", "MACD",
    "MA-Trend", "Boll. Bands", "Volume", "Candlestick", "VWAP", "Squeeze", "Kurs", "Änderung %",
]


def build_table(rows: list, direction: str, title: str) -> str:
    emoji = "🟢" if direction == "buy" else "🔴"
    header_cells = "".join(
        f'<th style="padding:8px 12px;text-align:left">{h}</th>'
        for h in TABLE_HEADERS
    )
    body_rows = "\n".join(build_row(r, direction) for r in rows)
    return f"""
<h2 style="margin-top:2rem">{emoji} {title} ({len(rows)} Signale)</h2>
<div style="overflow-x:auto">
<table style="width:100%;border-collapse:collapse;font-size:0.88em">
  <thead>
    <tr style="background:#2c3e50;color:white">
      {header_cells}
    </tr>
  </thead>
  <tbody>
    {body_rows}
  </tbody>
</table>
</div>
"""


def build_summary(buy_rows: list, sell_rows: list, scan_time: str) -> str:
    all_rows = buy_rows + sell_rows
    avg_score = (
        round(sum(abs(r["net_score"]) for r in all_rows) / len(all_rows), 2)
        if all_rows
        else 0
    )
    strongest = (
        max(all_rows, key=lambda r: abs(r["net_score"])) if all_rows else None
    )
    strongest_html = ""
    if strongest:
        direction_label = "KAUF" if strongest["net_score"] > 0 else "VERKAUF"
        strongest_html = f"""
        <p><b>Stärkstes Signal:</b>
        {strongest["ticker"]} ({strongest["name"]}) — {direction_label}
        | Score: {strongest["net_score"]}
        | RSI: {strongest["rsi"]}
        | MACD: {strongest["macd"]}
        | MA: {strongest["ma"]}
        | Boll: {strongest["bollinger"]}
        | Vol: {strongest["volume"]}
        | Candle: {strongest["candlestick"]}
        | Kurs: {strongest["price"]}
        | Änderung: {strongest["pct_change"]:+.2f}%
        </p>
        """
    return f"""
<div style="background:#ecf0f1;padding:1.5rem;border-radius:8px;margin-bottom:1.5rem">
  <h2 style="margin-top:0">Zusammenfassung</h2>
  <p>
    <b>Scan-Zeitpunkt:</b> {scan_time} &nbsp;|&nbsp;
    <b>Kaufsignale:</b> <span style="color:#27ae60;font-weight:bold">{len(buy_rows)}</span> &nbsp;|&nbsp;
    <b>Verkaufsignale:</b> <span style="color:#e74c3c;font-weight:bold">{len(sell_rows)}</span> &nbsp;|&nbsp;
    <b>&#216; Score:</b> {avg_score}
  </p>
  {strongest_html}
</div>
"""


CFD_HEADERS = [
    "Ticker", "Markt", "Score", "Richtung", "ADX", "RSI",
    "Einstieg", "Stop (1.5×ATR)", "TP1 (1:1)", "TP2 (2.67:1)",
    "R/R", "ATR%", "Gap 5T", "RVOL", "",
]


def build_cfd_row(row: dict, direction: str) -> str:
    score = row[f"cfd_{direction}_score"]
    if direction == "long":
        stop, tp1, tp2 = row["stop_long"], row["tp1_long"], row["tp2_long"]
        dir_color, dir_label, bg = "#27ae60", "LONG ▲", "#eafaf1"
    else:
        stop, tp1, tp2 = row["stop_short"], row["tp1_short"], row["tp2_short"]
        dir_color, dir_label, bg = "#e74c3c", "SHORT ▼", "#fdedec"

    price  = row["price"]
    risk   = abs(price - stop)
    reward = abs(tp2 - price)
    rr     = reward / risk if risk > 0 else 0

    max_s = CFG["scoring"]["max_score"]
    score_color = "#1e8449" if score >= 7.0 else "#27ae60" if score >= 6.0 else "#d68910" if score >= 5.0 else "#7f8c8d"
    score_display = f"{score:.1f}/{max_s:.0f}"
    gap_html = (
        f'<span style="color:#e74c3c;font-weight:bold">{row["recent_max_gap"]}% ⚠</span>'
        if row["recent_max_gap"] >= 5
        else f'<span style="color:#f39c12">{row["recent_max_gap"]}%</span>'
        if row["recent_max_gap"] >= 3
        else f'{row["recent_max_gap"]}%'
    )
    di_info = f'+DI={row.get("plus_di", "?")}/−DI={row.get("minus_di", "?")}'
    ticker_esc = row["ticker"].replace("'", "\\'")
    cells = "".join([
        f'<td style="font-weight:bold">{row["ticker"]}</td>',
        f'<td style="font-size:0.85em">{row["market"]}</td>',
        f'<td style="text-align:center;font-weight:bold;color:{score_color}">{score_display}</td>',
        f'<td style="text-align:center"><span style="background:{dir_color};color:white;'
        f'padding:2px 8px;border-radius:4px;font-size:0.85em">{dir_label}</span></td>',
        f'<td style="text-align:center" title="{di_info}">{row["adx"]}</td>',
        f'<td style="text-align:center">{row["rsi"]}</td>',
        f'<td style="text-align:right">{price}</td>',
        f'<td style="text-align:right;color:#e74c3c">{stop}</td>',
        f'<td style="text-align:right;color:#27ae60">{tp1}</td>',
        f'<td style="text-align:right;color:#27ae60;font-weight:bold">{tp2}</td>',
        f'<td style="text-align:center;font-weight:bold">{rr:.1f}:1</td>',
        f'<td style="text-align:center">{row["atr_pct"]}%</td>',
        f'<td style="text-align:center">{gap_html}</td>',
        f'<td style="text-align:center">{row.get("rvol_label", "—")}</td>',
        f'<td style="text-align:center">'
        f'<button onclick="addPosition(\'{ticker_esc}\', \'{direction}\')" '
        f'class="btn-add" title="Position übernehmen">+</button></td>',
    ])
    return f'<tr style="background:{bg}">{cells}</tr>'


def build_cfd_table(cfd_long: list, cfd_short: list) -> str:
    header_cells = "".join(
        f'<th style="padding:8px 12px;text-align:left">{h}</th>'
        for h in CFD_HEADERS
    )
    rows = [(r, "long") for r in cfd_long] + [(r, "short") for r in cfd_short]
    rows.sort(key=lambda x: x[0][f"cfd_{x[1]}_score"], reverse=True)
    body = "\n".join(build_cfd_row(r, d) for r, d in rows)
    total_l, total_s = len(cfd_long), len(cfd_short)
    return f"""
<h2 style="margin-top:2rem">⚡ CFD SETUPS &nbsp;
  <span style="color:#27ae60">Long: {total_l}</span> &nbsp;|&nbsp;
  <span style="color:#e74c3c">Short: {total_s}</span>
</h2>
<p style="color:#7f8c8d;font-size:0.83em">
  Gewichteter Score &ge; {CFG["scoring"]["threshold"]:.0f}/{CFG["scoring"]["max_score"]:.0f} &nbsp;|&nbsp;
  ADX+DI (2.0) · MA-Struktur (1.5) · EMA-Stack (1.5) · MACD (1.0) · RSI-Zone (1.0) · Vol (0.5) · Gap (0.5) + Bonus (2.0)
  &nbsp;|&nbsp; Stop = {CFG["cfd"]["atr_stop_mult"]}×ATR &nbsp;|&nbsp; TP2 = {CFG["cfd"]["atr_tp2_mult"]}×ATR
</p>
<div style="overflow-x:auto">
<table style="width:100%;border-collapse:collapse;font-size:0.88em">
  <thead><tr style="background:#1a252f;color:white">{header_cells}</tr></thead>
  <tbody>{body}</tbody>
</table>
</div>
"""


def _fear_greed_badge(fg: dict) -> str:
    value = fg.get("value", 50)
    label = fg.get("label") or _fg_label(value)
    if value <= 20:
        color, bg = "#fff", "#c0392b"
    elif value <= 40:
        color, bg = "#fff", "#e67e22"
    elif value <= 60:
        color, bg = "#fff", "#7f8c8d"
    elif value <= 80:
        color, bg = "#fff", "#27ae60"
    else:
        color, bg = "#fff", "#145a32"
    return (
        f'<span style="background:{bg};color:{color};padding:4px 12px;'
        f'border-radius:6px;font-weight:bold;font-size:1.1em">'
        f'Fear &amp; Greed: {value} — {label}</span>'
    )


def build_portfolio_section(reports: list) -> str:
    """Erstellt die HTML-Sektion 'Meine Positionen' mit Status und Empfehlungen."""
    if not reports:
        return ""

    rows_html = []
    for r in reports:
        if "error" in r:
            rows_html.append(
                f'<tr><td style="font-weight:bold">{r["ticker"]}</td>'
                f'<td colspan="10" style="color:#e74c3c">Fehler: {r["error"]}</td></tr>'
            )
            continue

        # Farben
        dir_color = "#27ae60" if r["direction"] == "long" else "#e74c3c"
        dir_label = r["direction"].upper()
        pnl_color = "#27ae60" if r["pnl_pct"] >= 0 else "#e74c3c"
        pnl_sign = "+" if r["pnl_pct"] >= 0 else ""
        rec_color = r.get("rec_color", "#7f8c8d")

        # Warnungen als Tooltip
        warn_list = r.get("warnings", [])
        warn_tooltip = " | ".join(warn_list) if warn_list else "Keine Warnungen"
        warn_count = len(warn_list)
        warn_badge = (
            f'<span style="color:#27ae60" title="{warn_tooltip}">0</span>'
            if warn_count == 0
            else f'<span style="color:#e67e22" title="{warn_tooltip}">{warn_count}</span>'
            if warn_count <= 2
            else f'<span style="color:#e74c3c;font-weight:bold" title="{warn_tooltip}">{warn_count}</span>'
        )

        # TP1-Hit Badge
        tp1_badge = ' <span style="color:#27ae60;font-size:0.8em">TP1</span>' if r.get("tp1_hit") else ""

        # Indikatoren
        ind = r.get("indicators", {})
        ind_html = ""
        if ind:
            ind_html = (
                f'<span style="font-size:0.75em;color:#7f8c8d">'
                f'ADX {ind.get("adx", "?")} | RSI {ind.get("rsi", "?")} | '
                f'MACD {ind.get("macd_hist", "?")}</span>'
            )

        cells = "".join([
            f'<td style="font-weight:bold">{r["ticker"]}{tp1_badge}</td>',
            f'<td style="text-align:center"><span style="background:{dir_color};color:white;'
            f'padding:2px 8px;border-radius:4px;font-size:0.85em">{dir_label}</span></td>',
            f'<td style="text-align:right">{r["entry_price"]:.2f}</td>',
            f'<td style="text-align:right;font-weight:bold">{r["current_price"]:.2f}</td>',
            f'<td style="text-align:right;color:{pnl_color};font-weight:bold">{pnl_sign}{r["pnl_pct"]:.1f}%</td>',
            f'<td style="text-align:center">{r["days_held"]}d</td>',
            f'<td style="text-align:right;color:#e74c3c">{r["stop_current"]:.2f}</td>',
            f'<td style="text-align:right;color:#27ae60">{r["tp1"]:.2f}</td>',
            f'<td style="text-align:right;color:#27ae60">{r["tp2"]:.2f}</td>',
            f'<td style="text-align:center">{warn_badge}</td>',
            f'<td style="font-weight:bold;color:{rec_color}">{r["recommendation"]}</td>',
        ])
        rows_html.append(f'<tr>{cells}</tr>')

        # Warnungen als Detailzeile
        if warn_list:
            warn_details = " &bull; ".join(warn_list)
            rows_html.append(
                f'<tr style="background:#fef9e7"><td></td>'
                f'<td colspan="10" style="font-size:0.8em;color:#7f8c8d;padding:2px 10px">'
                f'{warn_details}</td></tr>'
            )

    headers = ["Ticker", "Richtung", "Entry", "Aktuell", "P&L", "Tage",
               "Stop", "TP1", "TP2", "Warn.", "Empfehlung"]
    header_cells = "".join(
        f'<th style="padding:8px 12px;text-align:left">{h}</th>' for h in headers
    )

    return f"""
<h2 style="margin-top:2rem;color:#2c3e50">
  Meine CFD-Positionen &nbsp;
  <span style="font-size:0.7em;color:#7f8c8d">({len(reports)} aktiv)</span>
</h2>
<div style="overflow-x:auto">
<table style="width:100%;border-collapse:collapse;font-size:0.88em">
  <thead><tr style="background:#1a252f;color:white">{header_cells}</tr></thead>
  <tbody>{"".join(rows_html)}</tbody>
</table>
</div>
"""


def generate_html(
    buy_rows: list,
    sell_rows: list,
    scan_time: str,
    cfd_long_rows: list | None = None,
    cfd_short_rows: list | None = None,
    fear_greed: dict | None = None,
    position_reports: list | None = None,
) -> str:
    fg_badge = _fear_greed_badge(fear_greed or {"value": 50, "label": "Neutral"})
    summary   = build_summary(buy_rows, sell_rows, scan_time)
    buy_table = build_table(buy_rows, "buy", "KAUFSIGNALE")
    sell_table = build_table(sell_rows, "sell", "VERKAUFSIGNALE")
    cfd_section = build_cfd_table(cfd_long_rows or [], cfd_short_rows or [])
    portfolio_section = build_portfolio_section(position_reports or [])
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Trading Signals — {scan_time}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 2rem; background: #f9f9f9; color: #2c3e50 }}
  h1 {{ color: #2c3e50 }}
  table td, table th {{ border: 1px solid #ddd; padding: 6px 10px }}
  table tr:hover {{ filter: brightness(0.95) }}
  .btn-add {{
    background: #27ae60; color: white; border: none; border-radius: 4px;
    padding: 4px 10px; cursor: pointer; font-weight: bold; font-size: 1em;
  }}
  .btn-add:hover {{ background: #1e8449 }}
  .btn-add:disabled {{ background: #95a5a6; cursor: default }}
</style>
<script>
function addPosition(ticker, direction) {{
  var btn = event.target;
  btn.disabled = true;
  btn.textContent = '...';
  fetch('https://agents.umzwei.de/webhook/cfd-add-position', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ticker: ticker, direction: direction}})
  }})
  .then(function(r) {{ return r.json() }})
  .then(function(d) {{
    btn.textContent = 'OK';
    btn.style.background = '#1e8449';
  }})
  .catch(function(e) {{
    btn.textContent = '!';
    btn.style.background = '#e74c3c';
    btn.disabled = false;
  }});
}}
</script>
</head>
<body>
<h1>📊 Technical Analysis Stock Scanner</h1>
<p style="color:#7f8c8d">Datum: {scan_time} &nbsp;|&nbsp; Signale mit |Score| &ge; 4 &nbsp;|&nbsp; {fg_badge}</p>
{portfolio_section}
{summary}
{buy_table}
{sell_table}
{cfd_section}
<hr>
<p style="color:#aaa;font-size:0.8em">
  Nur technische Analyse — keine Anlageberatung. Kurzfristiger Horizont 1–5 Tage.
</p>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Technical Analysis Stock Scanner")
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Kein automatisches Öffnen des HTML-Reports im Browser.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Keine externen API-Calls; erzeugt leeren Report für Smoke-Check.",
    )
    # CFD-Portfolio-Befehle
    parser.add_argument(
        "--add-position",
        nargs=2,
        metavar=("TICKER", "DIRECTION"),
        help="CFD-Position hinzufügen (z.B. --add-position CVX long)",
    )
    parser.add_argument(
        "--close-position",
        metavar="TICKER",
        help="CFD-Position schliessen (z.B. --close-position CVX)",
    )
    parser.add_argument(
        "--positions",
        action="store_true",
        help="Alle aktiven CFD-Positionen anzeigen.",
    )
    parser.add_argument(
        "--check-positions",
        action="store_true",
        help="Alle Positionen prüfen und Empfehlungen ausgeben.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # ── Portfolio-Befehle (Early Exit) ──────────────────────────────────────
    from cfd_portfolio import (
        add_position, close_position, print_positions, check_positions, list_positions
    )

    if args.add_position:
        ticker, direction = args.add_position
        add_position(ticker, direction)
        return

    if args.close_position:
        close_position(args.close_position)
        return

    if args.positions:
        print_positions()
        return

    if args.check_positions:
        reports = check_positions()
        for r in reports:
            if "error" in r:
                print(f"\n  {r['ticker']}: FEHLER — {r['error']}")
                continue
            pnl_sign = "+" if r["pnl_pct"] >= 0 else ""
            print(f"\n  {r['ticker']} {r['direction'].upper()} | "
                  f"{r['current_price']:.2f} ({pnl_sign}{r['pnl_pct']:.1f}%) | "
                  f"Tag {r['days_held']}")
            print(f"    {r['recommendation']}")
            for w in r.get("warnings", []):
                print(f"      - {w}")
        return

    start_time = time.time()
    scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"  Technical Analysis Stock Scanner")
    print(f"  {scan_time}")
    print(f"{'='*60}\n")

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
        # --- Load tickers ---
        print("Lade Ticker-Listen …")
        nasdaq = filter_valid_tickers(get_nasdaq100_tickers(), "NASDAQ 100")
        sp500 = filter_valid_tickers(get_sp500_tickers(), "S&P 500")
        dax = filter_valid_tickers(get_dax40_tickers(), "DAX 40")
        eurostoxx50 = filter_valid_tickers(get_eurostoxx50_tickers(), "Euro Stoxx 50")
        tecdax = filter_valid_tickers(get_tecdax_tickers(), "TecDAX")
        mdax = filter_valid_tickers(get_mdax_tickers(), "MDAX")
        sdax = filter_valid_tickers(get_sdax_tickers(), "SDAX")

    # Deduplicate while preserving source market label
    all_tickers: list[tuple[str, str]] = []
    seen: set[str] = set()
    for ticker, label in [
        *((t, "NASDAQ 100") for t in nasdaq),
        *((t, "S&P 500") for t in sp500),
        *((t, "DAX 40") for t in dax),
        *((t, "Euro Stoxx 50") for t in eurostoxx50),
        *((t, "TecDAX") for t in tecdax),
        *((t, "MDAX") for t in mdax),
        *((t, "SDAX") for t in sdax),
    ]:
        if ticker not in seen:
            all_tickers.append((ticker, label))
            seen.add(ticker)

    total = len(all_tickers)
    print(
        f"Ticker geladen: NASDAQ 100={len(nasdaq)}, S&P 500={len(sp500)}, "
        f"DAX 40={len(dax)}, Euro Stoxx 50={len(eurostoxx50)}, "
        f"TecDAX={len(tecdax)}, MDAX={len(mdax)}, SDAX={len(sdax)}"
    )
    for list_name in ["NASDAQ 100", "S&P 500", "DAX 40", "Euro Stoxx 50", "TecDAX", "MDAX", "SDAX"]:
        if list_name in TICKER_SOURCES:
            source, cnt = TICKER_SOURCES[list_name]
            print(f"  Quelle {list_name}: {source} ({cnt})")
    print(f"Gesamt eindeutige Ticker: {total}")
    if not args.dry_run:
        estimated_minutes = total * 0.35 / 60
        print(f"Geschätzte Laufzeit: {estimated_minutes:.0f}–{estimated_minutes*1.5:.0f} Minuten\n")

    # Try to use tqdm if available
    try:
        from tqdm import tqdm
        ticker_iter = tqdm(all_tickers, desc="Scanning", unit="ticker")
    except ImportError:
        print("(tqdm nicht installiert — kein Fortschrittsbalken)")
        ticker_iter = all_tickers

    results: list[dict] = []
    BATCH_SIZE = 20
    SLEEP_INTERVAL = 0.1

    for idx, (ticker, market) in enumerate(ticker_iter):
        result = analyze_ticker(ticker, market)
        if result is not None:
            results.append(result)

        # Rate limiting between batches
        if (idx + 1) % BATCH_SIZE == 0:
            time.sleep(SLEEP_INTERVAL)

    # --- Filter and sort (net_score >= 4, Gap <= 3%) ---
    buy_rows = sorted(
        [r for r in results if r["net_score"] >= 4 and r["recent_max_gap"] <= 3.0],
        key=lambda r: r["net_score"],
        reverse=True,
    )
    sell_rows = sorted(
        [r for r in results if r["net_score"] <= -4 and r["recent_max_gap"] <= 3.0],
        key=lambda r: r["net_score"],
    )

    elapsed = time.time() - start_time
    print(f"\nScan abgeschlossen in {elapsed:.0f}s ({elapsed/60:.1f} Min)")
    print(f"Kaufsignale:     {len(buy_rows)}")
    print(f"Verkaufsignale:  {len(sell_rows)}")
    print(f"Fehler geloggt:  {LOG_FILE}\n")

    # --- Terminal summary ---
    print("TOP 5 KAUFSIGNALE:")
    for r in buy_rows[:5]:
        print(f"  {r['ticker']:10s}  Score={r['net_score']:+d}  RSI={r['rsi']}  Kurs={r['price']}  {r['pct_change']:+.2f}%")

    print("\nTOP 5 VERKAUFSIGNALE:")
    for r in sell_rows[:5]:
        print(f"  {r['ticker']:10s}  Score={r['net_score']:+d}  RSI={r['rsi']}  Kurs={r['price']}  {r['pct_change']:+.2f}%")

    # --- Fear & Greed Multiplikator (Contrarian) ---
    fg_value = fear_greed.get("value", 50)
    if fg_value <= 20:
        fg_long_m, fg_short_m = 1.2, 0.8   # Extreme Fear → Long staerker
    elif fg_value <= 40:
        fg_long_m, fg_short_m = 1.1, 0.9
    elif fg_value <= 60:
        fg_long_m, fg_short_m = 1.0, 1.0   # Neutral
    elif fg_value <= 80:
        fg_long_m, fg_short_m = 0.9, 1.1
    else:
        fg_long_m, fg_short_m = 0.8, 1.2   # Extreme Greed → Short staerker

    for r in results:
        r["cfd_long_score_raw"] = r["cfd_long_score"]
        r["cfd_short_score_raw"] = r["cfd_short_score"]
        r["cfd_long_score"] = round(min(r["cfd_long_score"] * fg_long_m, 10.0), 1)
        r["cfd_short_score"] = round(min(r["cfd_short_score"] * fg_short_m, 10.0), 1)

    print(f"\nF&G Multiplikator: Long x{fg_long_m}, Short x{fg_short_m} (F&G={fg_value})")

    # --- CFD Setups filtern (gewichteter Score >= Threshold, Top-N Cap) ---
    cfd_threshold = CFG["scoring"]["threshold"]
    cfd_top_n = CFG["cfd"]["top_n"]
    cfd_long_rows = sorted(
        [r for r in results if r["cfd_long_score"] >= cfd_threshold],
        key=lambda r: r["cfd_long_score"], reverse=True,
    )[:cfd_top_n]
    cfd_short_rows = sorted(
        [r for r in results if r["cfd_short_score"] >= cfd_threshold],
        key=lambda r: r["cfd_short_score"], reverse=True,
    )[:cfd_top_n]
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

    # --- Portfolio-Check (aktive CFD-Positionen) ---
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

    # --- Output-Verzeichnis mit Datum ---
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = Path(__file__).parent / "output" / date_str
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Write HTML ---
    html_path = output_dir / "trading_signals.html"
    html_content = generate_html(
        buy_rows, sell_rows, scan_time, cfd_long_rows, cfd_short_rows,
        fear_greed, position_reports,
    )
    html_path.write_text(html_content, encoding="utf-8")
    Path("trading_signals.html").write_text(html_content, encoding="utf-8")
    print(f"\nHTML-Bericht: {html_path.resolve()}")

    # --- Write CSV ---
    csv_path = output_dir / "trading_signals.csv"
    all_signal_rows = buy_rows + sell_rows
    if all_signal_rows:
        df_signals = pd.DataFrame(all_signal_rows)
        df_signals.to_csv(csv_path, index=False, encoding="utf-8-sig")
        df_signals.to_csv("trading_signals.csv", index=False, encoding="utf-8-sig")
        print(f"CSV-Export:   {csv_path.resolve()}")

    # --- CFD CSV ---
    cfd_all = (
        [{**r, "cfd_direction": "long"}  for r in cfd_long_rows] +
        [{**r, "cfd_direction": "short"} for r in cfd_short_rows]
    )
    if cfd_all:
        cfd_csv = output_dir / "cfd_setups.csv"
        df_cfd = pd.DataFrame(cfd_all)
        df_cfd.to_csv(cfd_csv, index=False, encoding="utf-8-sig")
        df_cfd.to_csv("cfd_setups.csv", index=False, encoding="utf-8-sig")
        print(f"CFD-CSV:      {cfd_csv.resolve()}")

    # --- CFD Backtesting ---
    if CFG["backtesting"]["enabled"] and not args.dry_run:
        try:
            from cfd_backtesting import init_db, log_scan_run, log_cfd_signal, resolve_signals
            init_db()
            run_id = log_scan_run(
                scan_date=date_str,
                fear_greed=fear_greed.get("value", 50),
                ticker_count=total,
                long_signals=len(cfd_long_rows),
                short_signals=len(cfd_short_rows),
            )
            for r in cfd_long_rows:
                log_cfd_signal(run_id, r, "long")
            for r in cfd_short_rows:
                log_cfd_signal(run_id, r, "short")
            print(f"\nBacktesting: {len(cfd_long_rows) + len(cfd_short_rows)} Signale geloggt (Run #{run_id})")
            resolve_signals(
                min_days=CFG["backtesting"]["resolve_after_days"],
                max_days=CFG["backtesting"]["resolve_max_days"],
            )
        except Exception as e:
            print(f"Backtesting-Fehler (nicht kritisch): {e}")

    # --- Dashboard Push ---
    try:
        from post_to_dashboard import post_to_dashboard
        post_to_dashboard(str(output_dir), fear_greed)
    except Exception as e:
        print(f"Dashboard-Push übersprungen: {e}")

    # --- Telegram Alerts ---
    try:
        from telegram_alerts import send_signal_alert, send_daily_summary
        # Alerts fuer starke Signale (Score >= 7)
        alert_count = 0
        for r in cfd_long_rows:
            if r["cfd_long_score"] >= 7.0:
                send_signal_alert(r["ticker"], "long", r["cfd_long_score"],
                                  r["price"], r["stop_long"], r["tp1_long"], r["tp2_long"],
                                  r.get("market", ""))
                alert_count += 1
        for r in cfd_short_rows:
            if r["cfd_short_score"] >= 7.0:
                send_signal_alert(r["ticker"], "short", r["cfd_short_score"],
                                  r["price"], r["stop_short"], r["tp1_short"], r["tp2_short"],
                                  r.get("market", ""))
                alert_count += 1
        # Daily Summary
        top_all = (
            [{**r, "cfd_direction": "long"} for r in cfd_long_rows[:3]] +
            [{**r, "cfd_direction": "short"} for r in cfd_short_rows[:3]]
        )
        send_daily_summary(fear_greed, len(cfd_long_rows), len(cfd_short_rows),
                           top_all, len(positions))
        if alert_count:
            print(f"Telegram: {alert_count} Alerts gesendet")
    except Exception as e:
        print(f"Telegram übersprungen: {e}")

    # --- Open browser (nur interaktiv) ---
    if not args.no_open and sys.stdout.isatty():
        try:
            webbrowser.open(html_path.resolve().as_uri())
        except Exception:
            pass

    print("\nFertig!")


if __name__ == "__main__":
    main()
