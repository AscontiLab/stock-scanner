#!/usr/bin/env python3
"""
Technical Analysis Stock Scanner
Scans NASDAQ 100, S&P 500 and DAX 40 for short-term trading signals (1-5 day horizon).
"""

import yfinance as yf
import pandas as pd
import numpy as np
import time
import logging
import webbrowser
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    filename="scan_errors.log",
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
    "LULU", "MAR", "MCHP", "MRNA", "MTCH", "OKTA", "ROST", "SGEN", "TTWO",
    "VRSN", "VRTX", "XEL", "ZS", "ZM", "TEAM", "CRWD", "DDOG", "SNOW",
    "ABNB", "EBAY", "WBA", "CEG", "ON", "GFS", "ENPH", "ALGN", "GEHC",
    "FSLR", "SWKS", "BMRN", "SPLK", "AKAM", "CTSH",
]

SP500_FALLBACK = [
    "JPM", "UNH", "V", "MA", "LLY", "JNJ", "PG", "HD", "MRK", "ABBV",
    "BAC", "KO", "PEP", "WMT", "CVX", "XOM", "CRM", "ACN", "TMO", "MCD",
    "ABT", "ORCL", "NEE", "DHR", "PM", "IBM", "RTX", "CAT", "HON", "GE",
    "T", "VZ", "CMCSA", "MS", "GS", "BLK", "SCHW", "C", "WFC", "AXP",
    "LOW", "SPGI", "DE", "NKE", "AMAT", "MMM", "UPS", "LMT", "MO", "USB",
    "DUK", "SO", "AEP", "SRE", "D", "PCG", "EXC", "ETR", "AWK", "ES",
    "BMY", "AMGN", "GILD", "REGN", "VRTX", "BIIB", "ALXN", "MRNA", "ILMN",
    "ZTS", "IDXX", "A", "BDX", "BAX", "EW", "ISRG", "IQV", "CI", "HUM",
    "CNC", "MOH", "DVA", "HCA", "UHS", "THC", "ANTM", "CVS", "WBA", "CAH",
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
import urllib.request


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
                    return tickers
    return NASDAQ100_FALLBACK


def get_sp500_tickers() -> list:
    tables = _safe_read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = t[col].dropna().tolist()
                tickers = [str(x).strip().replace(".", "-") for x in tickers if str(x).strip()]
                if len(tickers) > 400:
                    return tickers
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
                    return tickers
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
            return result
    return EUROSTOXX50_FALLBACK


def get_tecdax_tickers() -> list:
    tables = _safe_read_html("https://en.wikipedia.org/wiki/TecDAX")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = _add_de_suffix(t[col].dropna().tolist())
                if len(tickers) >= 20:
                    return tickers
    return TECDAX_FALLBACK


def get_mdax_tickers() -> list:
    tables = _safe_read_html("https://en.wikipedia.org/wiki/MDAX")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = _add_de_suffix(t[col].dropna().tolist())
                if len(tickers) >= 30:
                    return tickers
    return MDAX_FALLBACK


def get_sdax_tickers() -> list:
    tables = _safe_read_html("https://en.wikipedia.org/wiki/SDAX")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = _add_de_suffix(t[col].dropna().tolist())
                if len(tickers) >= 50:
                    return tickers
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

        close = df["Close"]
        volume = df["Volume"]
        open_ = df["Open"]
        high = df["High"]
        low = df["Low"]

        current_price = float(close.iloc[-1])
        prev_price = float(close.iloc[-2])
        pct_change = (current_price - prev_price) / prev_price * 100

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
        squeeze = bb_width < avg_bb_width * 0.8

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
        avg_vol_20 = float(volume.rolling(20).mean().iloc[-1])
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

        net_score = buy_signals - sell_signals

        # --- ATR ---
        tr_s    = pd.concat(
            [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
        ).max(axis=1)
        atr_val = float(tr_s.rolling(14).mean().iloc[-1])
        atr_pct = round(atr_val / current_price * 100, 2)

        # --- ADX ---
        adx_s, plus_di_s, minus_di_s = compute_adx(high, low, close)
        adx_val      = float(adx_s.iloc[-1])
        plus_di_val  = float(plus_di_s.iloc[-1])
        minus_di_val = float(minus_di_s.iloc[-1])

        # --- Größter Tages-Move der letzten 5 Tage (Gap-Filter) ---
        recent_max_gap = float(close.pct_change().tail(5).abs().max()) * 100

        # --- CFD Long Score (6 Kriterien) ---
        cfd_long = 0
        if adx_val > 25:                               cfd_long += 1  # Starker Trend
        if 45 <= rsi_val <= 65:                        cfd_long += 1  # Momentum-Zone
        if curr_hist > 0:                              cfd_long += 1  # MACD bullish
        if current_price > sma20_val > sma50_val:      cfd_long += 1  # MA-Aufwärtstrend
        if vol_ratio >= 1.2:                           cfd_long += 1  # Volumen bestätigt
        if recent_max_gap < 5.0:                       cfd_long += 1  # Kein Spike/Gap

        # --- CFD Short Score (6 Kriterien) ---
        cfd_short = 0
        if adx_val > 25:                               cfd_short += 1
        if 35 <= rsi_val <= 55:                        cfd_short += 1  # Momentum-Zone Short
        if curr_hist < 0:                              cfd_short += 1  # MACD bearish
        if current_price < sma20_val < sma50_val:      cfd_short += 1  # MA-Abwärtstrend
        if vol_ratio >= 1.2:                           cfd_short += 1
        if recent_max_gap < 5.0:                       cfd_short += 1

        # --- ATR-basierte Stop/Target-Level ---
        stop_long   = round(current_price - 1.5 * atr_val, 2)
        tp1_long    = round(current_price + 1.5 * atr_val, 2)
        tp2_long    = round(current_price + 3.0 * atr_val, 2)
        stop_short  = round(current_price + 1.5 * atr_val, 2)
        tp1_short   = round(current_price - 1.5 * atr_val, 2)
        tp2_short   = round(current_price - 3.0 * atr_val, 2)

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
            "price": round(current_price, 2),
            "pct_change": round(pct_change, 2),
            # CFD-Felder
            "atr": round(atr_val, 3),
            "atr_pct": atr_pct,
            "adx": round(adx_val, 1),
            "vol_ratio": round(vol_ratio, 2),
            "recent_max_gap": round(recent_max_gap, 1),
            "cfd_long_score": cfd_long,
            "cfd_short_score": cfd_short,
            "stop_long": stop_long,
            "tp1_long": tp1_long,
            "tp2_long": tp2_long,
            "stop_short": stop_short,
            "tp1_short": tp1_short,
            "tp2_short": tp2_short,
        }

    except Exception as exc:
        logging.error("%s: %s", ticker, exc)
        return None


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

SIGNAL_COLORS_BUY = {
    6: "#145a32",
    5: "#1e8449",
    4: "#27ae60",
    3: "#a9dfbf",
}
SIGNAL_COLORS_SELL = {
    6: "#7b241c",
    5: "#a93226",
    4: "#e74c3c",
    3: "#f5b7b1",
}


def score_color(score: int, direction: str) -> str:
    abs_score = abs(score)
    if direction == "buy":
        return SIGNAL_COLORS_BUY.get(min(abs_score, 6), "#eafaf1")
    return SIGNAL_COLORS_SELL.get(min(abs_score, 6), "#fdedec")


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
    pct = row["pct_change"]
    pct_color = "#27ae60" if pct >= 0 else "#e74c3c"
    pct_str = f'<span style="color:{pct_color}">{pct:+.2f}%</span>'

    cells = [
        f'<td style="font-weight:bold">{row["ticker"]}</td>',
        f'<td>{row["name"]}</td>',
        f'<td>{row["market"]}</td>',
        f'<td style="font-weight:bold;text-align:center">{score_text}</td>',
        f'<td style="text-align:center">{row["rsi"]}</td>',
        f'<td style="text-align:center">{signal_badge(row["macd"])}</td>',
        f'<td style="text-align:center">{signal_badge(row["ma"])}</td>',
        f'<td style="text-align:center">{signal_badge(row["bollinger"])}</td>',
        f'<td style="text-align:center">{signal_badge(row["volume"])}</td>',
        f'<td style="text-align:center">{signal_badge(row["candlestick"])}</td>',
        f'<td style="text-align:right">{row["price"]}</td>',
        f'<td style="text-align:right">{pct_str}</td>',
    ]
    cells_html = "\n".join(cells)
    return f'<tr style="background:{bg}">\n{cells_html}\n</tr>'


TABLE_HEADERS = [
    "Ticker", "Name", "Markt", "Score", "RSI", "MACD",
    "MA-Trend", "Boll. Bands", "Volume", "Candlestick", "Kurs", "Änderung %",
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
    "Einstieg", "Stop (1.5×ATR)", "TP1 (1:1)", "TP2 (2:1)",
    "R/R", "ATR%", "Gap 5T",
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

    score_color = "#1e8449" if score >= 5 else "#d68910" if score >= 4 else "#7f8c8d"
    gap_html = (
        f'<span style="color:#e74c3c;font-weight:bold">{row["recent_max_gap"]}% ⚠</span>'
        if row["recent_max_gap"] >= 5
        else f'<span style="color:#f39c12">{row["recent_max_gap"]}%</span>'
        if row["recent_max_gap"] >= 3
        else f'{row["recent_max_gap"]}%'
    )
    cells = "".join([
        f'<td style="font-weight:bold">{row["ticker"]}</td>',
        f'<td style="font-size:0.85em">{row["market"]}</td>',
        f'<td style="text-align:center;font-weight:bold;color:{score_color}">{score}/6</td>',
        f'<td style="text-align:center"><span style="background:{dir_color};color:white;'
        f'padding:2px 8px;border-radius:4px;font-size:0.85em">{dir_label}</span></td>',
        f'<td style="text-align:center">{row["adx"]}</td>',
        f'<td style="text-align:center">{row["rsi"]}</td>',
        f'<td style="text-align:right">{price}</td>',
        f'<td style="text-align:right;color:#e74c3c">{stop}</td>',
        f'<td style="text-align:right;color:#27ae60">{tp1}</td>',
        f'<td style="text-align:right;color:#27ae60;font-weight:bold">{tp2}</td>',
        f'<td style="text-align:center;font-weight:bold">{rr:.1f}:1</td>',
        f'<td style="text-align:center">{row["atr_pct"]}%</td>',
        f'<td style="text-align:center">{gap_html}</td>',
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
  Score &ge; 4/6 &nbsp;|&nbsp; Kriterien: ADX&gt;25 · RSI-Zone · MACD · MA-Struktur · Volumen · kein Gap &gt;5%
  &nbsp;|&nbsp; Stop = 1.5×ATR &nbsp;|&nbsp; TP2 = 3×ATR (2:1 R/R)
</p>
<div style="overflow-x:auto">
<table style="width:100%;border-collapse:collapse;font-size:0.88em">
  <thead><tr style="background:#1a252f;color:white">{header_cells}</tr></thead>
  <tbody>{body}</tbody>
</table>
</div>
"""


def generate_html(
    buy_rows: list,
    sell_rows: list,
    scan_time: str,
    cfd_long_rows: list | None = None,
    cfd_short_rows: list | None = None,
) -> str:
    summary   = build_summary(buy_rows, sell_rows, scan_time)
    buy_table = build_table(buy_rows, "buy", "KAUFSIGNALE")
    sell_table = build_table(sell_rows, "sell", "VERKAUFSIGNALE")
    cfd_section = build_cfd_table(cfd_long_rows or [], cfd_short_rows or [])
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
</style>
</head>
<body>
<h1>📊 Technical Analysis Stock Scanner</h1>
<p style="color:#7f8c8d">Datum: {scan_time} &nbsp;|&nbsp; Signale mit |Score| &ge; 3</p>
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

def main():
    start_time = time.time()
    scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"  Technical Analysis Stock Scanner")
    print(f"  {scan_time}")
    print(f"{'='*60}\n")

    # --- Load tickers ---
    print("Lade Ticker-Listen …")
    nasdaq = get_nasdaq100_tickers()
    sp500 = get_sp500_tickers()
    dax = get_dax40_tickers()
    eurostoxx50 = get_eurostoxx50_tickers()
    tecdax = get_tecdax_tickers()
    mdax = get_mdax_tickers()
    sdax = get_sdax_tickers()

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
    print(f"Gesamt eindeutige Ticker: {total}")
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

    # --- Filter and sort ---
    buy_rows = sorted(
        [r for r in results if r["net_score"] >= 3],
        key=lambda r: r["net_score"],
        reverse=True,
    )
    sell_rows = sorted(
        [r for r in results if r["net_score"] <= -3],
        key=lambda r: r["net_score"],
    )

    elapsed = time.time() - start_time
    print(f"\nScan abgeschlossen in {elapsed:.0f}s ({elapsed/60:.1f} Min)")
    print(f"Kaufsignale:     {len(buy_rows)}")
    print(f"Verkaufsignale:  {len(sell_rows)}")
    print(f"Fehler geloggt:  scan_errors.log\n")

    # --- Terminal summary ---
    print("TOP 5 KAUFSIGNALE:")
    for r in buy_rows[:5]:
        print(f"  {r['ticker']:10s}  Score={r['net_score']:+d}  RSI={r['rsi']}  Kurs={r['price']}  {r['pct_change']:+.2f}%")

    print("\nTOP 5 VERKAUFSIGNALE:")
    for r in sell_rows[:5]:
        print(f"  {r['ticker']:10s}  Score={r['net_score']:+d}  RSI={r['rsi']}  Kurs={r['price']}  {r['pct_change']:+.2f}%")

    # --- CFD Setups filtern ---
    cfd_long_rows = sorted(
        [r for r in results if r["cfd_long_score"] >= 4],
        key=lambda r: r["cfd_long_score"], reverse=True,
    )
    cfd_short_rows = sorted(
        [r for r in results if r["cfd_short_score"] >= 4],
        key=lambda r: r["cfd_short_score"], reverse=True,
    )
    print(f"\nCFD Long Setups:   {len(cfd_long_rows)}")
    print(f"CFD Short Setups:  {len(cfd_short_rows)}")

    print("\nTOP 5 CFD LONG:")
    for r in cfd_long_rows[:5]:
        print(f"  {r['ticker']:10s}  CFD={r['cfd_long_score']}/6  ADX={r['adx']}  RSI={r['rsi']}  "
              f"Stop={r['stop_long']}  TP2={r['tp2_long']}")

    print("\nTOP 5 CFD SHORT:")
    for r in cfd_short_rows[:5]:
        print(f"  {r['ticker']:10s}  CFD={r['cfd_short_score']}/6  ADX={r['adx']}  RSI={r['rsi']}  "
              f"Stop={r['stop_short']}  TP2={r['tp2_short']}")

    # --- Output-Verzeichnis mit Datum ---
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = Path("output") / date_str
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Write HTML ---
    html_path = output_dir / "trading_signals.html"
    html_content = generate_html(buy_rows, sell_rows, scan_time, cfd_long_rows, cfd_short_rows)
    html_path.write_text(html_content, encoding="utf-8")
    Path("trading_signals.html").write_text(html_content, encoding="utf-8")
    print(f"\nHTML-Bericht: {html_path.resolve()}")

    # --- Write CSV ---
    csv_path = output_dir / "trading_signals.csv"
    all_signal_rows = buy_rows + sell_rows
    if all_signal_rows:
        pd.DataFrame(all_signal_rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
        pd.DataFrame(all_signal_rows).to_csv("trading_signals.csv", index=False, encoding="utf-8-sig")
        print(f"CSV-Export:   {csv_path.resolve()}")

    # --- CFD CSV ---
    cfd_all = (
        [{**r, "cfd_direction": "long"}  for r in cfd_long_rows] +
        [{**r, "cfd_direction": "short"} for r in cfd_short_rows]
    )
    if cfd_all:
        cfd_csv = output_dir / "cfd_setups.csv"
        pd.DataFrame(cfd_all).to_csv(cfd_csv, index=False, encoding="utf-8-sig")
        pd.DataFrame(cfd_all).to_csv("cfd_setups.csv", index=False, encoding="utf-8-sig")
        print(f"CFD-CSV:      {cfd_csv.resolve()}")

    # --- Open browser (nur interaktiv) ---
    try:
        webbrowser.open(html_path.resolve().as_uri())
    except Exception:
        pass

    print("\nFertig!")


if __name__ == "__main__":
    main()
