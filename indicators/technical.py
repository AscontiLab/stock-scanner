"""
Technische Indikatoren: RSI, MACD, SMA/EMA, Bollinger, ADX, ATR, Candlestick-Patterns.
"""

import numpy as np
import pandas as pd


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Berechnet den Relative Strength Index (RSI)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_macd(close: pd.Series, fast=12, slow=26, signal=9):
    """Berechnet MACD Line, Signal Line und Histogram."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_bollinger(close: pd.Series, period=20, std_dev=2):
    """Berechnet Bollinger Baender (Upper, Mid, Lower)."""
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, sma, lower


def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    """Berechnet ADX, +DI und -DI."""
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
    """Erkennt haeufige Candlestick-Patterns auf den letzten zwei Kerzen."""
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

    # Hammer (bullish) — kleiner Body oben, langer unterer Docht
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

    # Morning Star (3-Kerzen, bullish reversal)
    if len(df) >= 3:
        if (
            c[-3] < o[-3]  # first: bearish
            and body[-2] < avg_body * 0.5  # second: small body
            and c[-1] > o[-1]  # third: bullish
            and c[-1] > (o[-3] + c[-3]) / 2
        ):
            patterns.append(("Morning Star", 1))

    # Evening Star (3-Kerzen, bearish reversal)
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

    # Dominantes Pattern zurueckgeben
    biases = [b for _, b in patterns]
    dominant_bias = max(biases, key=abs) if biases else 0
    dominant = [p for p, b in patterns if b == dominant_bias]
    return {"pattern": ", ".join(dominant), "bias": dominant_bias}
