"""
Langfrist-Investment-Score: Bewertet Aktien fuer Buy-and-Hold-Eignung (0-10).
"""

import pandas as pd

from indicators.technical import compute_rsi, compute_macd, compute_atr


def compute_longterm_score(df: pd.DataFrame, current_price: float) -> dict:
    """
    Berechnet einen Langfrist-Score (0-10) fuer Investment-Eignung.

    Args:
        df: DataFrame mit Spalten Close, High, Low, Volume (ideal min 200 Zeilen)
        current_price: Aktueller Schlusskurs

    Returns:
        dict mit keys:
            longterm_score: float (0-10)
            longterm_details: dict mit Einzel-Indikator-Ergebnissen
            longterm_label: str (Label je nach Score)
    """
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
    n = len(df)

    score = 0.0
    details = {}

    # --- SMA200 Trend (max 2.0) ---
    sma200_pts = 0.0
    if n >= 200:
        sma200 = float(close.rolling(200).mean().iloc[-1])
        pct_above_sma200 = (current_price - sma200) / sma200 * 100
        if pct_above_sma200 > 2.0:
            sma200_pts = 2.0
            details["sma200"] = "BUY"
        elif pct_above_sma200 > 0:
            sma200_pts = 1.0
            details["sma200"] = "neutral"
        else:
            sma200_pts = 0.0
            details["sma200"] = "SELL"
    else:
        # Nicht genug Daten fuer SMA200
        details["sma200"] = "neutral"
    score += sma200_pts

    # --- Golden Cross: SMA50 vs SMA200 (max 2.0) ---
    golden_pts = 0.0
    if n >= 200:
        sma50_val = float(close.rolling(50).mean().iloc[-1])
        sma200_val = float(close.rolling(200).mean().iloc[-1])
        if sma50_val > sma200_val:
            golden_pts = 2.0
            details["golden_cross"] = "BUY"
        else:
            # SMA50 naehert sich SMA200 von unten (innerhalb 2%)?
            gap_pct = (sma200_val - sma50_val) / sma200_val * 100
            if gap_pct <= 2.0:
                golden_pts = 1.0
                details["golden_cross"] = "neutral"
            else:
                golden_pts = 0.0
                details["golden_cross"] = "SELL"
    elif n >= 50:
        # Nur SMA50 verfuegbar, kein Vergleich moeglich
        details["golden_cross"] = "neutral"
    else:
        details["golden_cross"] = "neutral"
    score += golden_pts

    # --- RSI Zone (max 1.5) ---
    rsi_pts = 0.0
    rsi_val = float(compute_rsi(close).iloc[-1])
    if 40 <= rsi_val <= 65:
        rsi_pts = 1.5
    elif (30 <= rsi_val < 40) or (65 < rsi_val <= 75):
        rsi_pts = 0.75
    else:
        rsi_pts = 0.0
    details["rsi_zone"] = str(round(rsi_val, 1))
    score += rsi_pts

    # --- Momentum: MACD Histogram (max 1.5) ---
    momentum_pts = 0.0
    _, _, histogram = compute_macd(close)
    curr_hist = float(histogram.iloc[-1])
    prev_hist = float(histogram.iloc[-2]) if len(histogram) >= 2 else 0.0
    if curr_hist > 0 and curr_hist > prev_hist:
        momentum_pts = 1.5
        details["momentum"] = "BUY"
    elif curr_hist > 0:
        momentum_pts = 0.75
        details["momentum"] = "neutral"
    else:
        momentum_pts = 0.0
        details["momentum"] = "bearish"
    score += momentum_pts

    # --- Volatilitaet: ATR% (max 1.0) ---
    vol_pts = 0.0
    atr_val = float(compute_atr(high, low, close).iloc[-1])
    atr_pct = atr_val / current_price * 100 if current_price > 0 else 0.0
    if 1.0 <= atr_pct <= 3.0:
        vol_pts = 1.0
    elif 3.0 < atr_pct <= 5.0:
        vol_pts = 0.5
    else:
        vol_pts = 0.0
    details["volatility"] = f"{atr_pct:.1f}%"
    score += vol_pts

    # --- 52-Wochen-Staerke (max 1.0) ---
    w52_pts = 0.0
    # 252 Handelstage ~ 1 Jahr, nutze verfuegbare Daten
    lookback = min(n, 252)
    week52_high = float(high.tail(lookback).max())
    if week52_high > 0:
        pct_from_high = (current_price - week52_high) / week52_high * 100
    else:
        pct_from_high = 0.0
    if pct_from_high >= -10:
        w52_pts = 1.0
    elif pct_from_high >= -20:
        w52_pts = 0.5
    else:
        w52_pts = 0.0
    details["week52"] = f"{pct_from_high:+.1f}%"
    score += w52_pts

    # --- Volume Trend: Akkumulation (max 1.0) ---
    vt_pts = 0.0
    if n >= 50:
        avg_vol_20 = float(volume.rolling(20).mean().iloc[-1])
        avg_vol_50 = float(volume.rolling(50).mean().iloc[-1])
        if avg_vol_50 > 0:
            vol_ratio = avg_vol_20 / avg_vol_50
            if vol_ratio > 1.05:
                vt_pts = 1.0
                details["volume_trend"] = "BUY"
            elif vol_ratio >= 0.95:
                vt_pts = 0.5
                details["volume_trend"] = "neutral"
            else:
                vt_pts = 0.0
                details["volume_trend"] = "SELL"
        else:
            details["volume_trend"] = "neutral"
    else:
        # Nicht genug Daten fuer 50-Tage-Durchschnitt
        if n >= 20:
            avg_vol_20 = float(volume.rolling(20).mean().iloc[-1])
            avg_vol_10 = float(volume.rolling(10).mean().iloc[-1])
            if avg_vol_20 > 0 and avg_vol_10 / avg_vol_20 > 1.05:
                vt_pts = 1.0
                details["volume_trend"] = "BUY"
            else:
                details["volume_trend"] = "neutral"
        else:
            details["volume_trend"] = "neutral"
    score += vt_pts

    # --- Score runden ---
    score = round(score, 1)

    # --- Label vergeben ---
    if score >= 8.0:
        label = "\U0001f48e Top-Investment"
    elif score >= 6.5:
        label = "\u2b50 Stark"
    elif score >= 5.0:
        label = "\u2713 Solide"
    else:
        label = "\u2014 Neutral"

    return {
        "longterm_score": score,
        "longterm_details": details,
        "longterm_label": label,
    }
