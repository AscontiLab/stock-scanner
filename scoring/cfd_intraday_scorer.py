"""
CFD Intraday Scorer — vereinfachte Score-Funktion auf 15m-Basis.

Unterschied zu cfd_scorer.py:
- Keine tagesbasierten Trendzähler (trend_long_days / trend_short_days)
  → Trend-Reife-Gate und Trend-Bonus entfallen
- Sonst identische Gewichtung und Schwellen aus scanner_config.yaml (cfd: + scoring:)
- ATR-Gate, RSI-Zonen, MA-Struktur, EMA-Stack, MACD-Histogram, Volume, Gap gelten unverändert
- Gleiche Exklusiv-Logik (nur stärkere Richtung behalten)
"""


def compute_cfd_intraday_scores(
    cfg: dict,
    market: str,
    adx_val: float,
    plus_di_val: float,
    minus_di_val: float,
    current_price: float,
    sma20_val: float,
    sma50_val: float,
    ema9_val: float,
    ema21_val: float,
    curr_hist: float,
    prev_hist: float,
    rsi_val: float,
    vol_ratio: float,
    recent_max_gap: float,
    atr_pct: float,
) -> tuple[float, float, dict]:
    """
    Berechnet CFD Long/Short-Scores auf Basis von 15m-Bars.

    Gibt (long, short, metadata) zurück. Scores sind auf eine Dezimalstelle gerundet.
    """
    cfd_cfg_base = cfg["cfd"]
    intraday_overrides = cfd_cfg_base.get("intraday", {})
    # Intraday-Werte ueberschreiben die Tagesdefaults wo gesetzt
    cfd_cfg = {**cfd_cfg_base, **intraday_overrides}

    w = cfg["scoring"]["weights"]
    bonus = cfg["scoring"]["bonus"]
    penalty = cfg["scoring"].get("penalty", {})
    market_cfg = cfg["scoring"].get("market_adjustments", {})

    long_components: dict[str, float] = {}
    short_components: dict[str, float] = {}
    long_penalties: dict[str, float] = {}
    short_penalties: dict[str, float] = {}

    cfd_atr_ok = cfd_cfg["atr_pct_min"] <= atr_pct <= cfd_cfg["atr_pct_max"]

    # --- Long ---
    cfd_long = 0.0
    if adx_val > cfd_cfg["adx_min"] and plus_di_val > minus_di_val:
        cfd_long += w["adx_di"]
        long_components["adx_di"] = w["adx_di"]
    if current_price > sma20_val > sma50_val:
        cfd_long += w["ma_structure"]
        long_components["ma_structure"] = w["ma_structure"]
    if ema9_val > ema21_val:
        cfd_long += w["ema_stack"]
        long_components["ema_stack"] = w["ema_stack"]
    if curr_hist > 0 and curr_hist > prev_hist:
        cfd_long += w["macd"]
        long_components["macd"] = w["macd"]
    if cfd_cfg["rsi_long_min"] <= rsi_val <= cfd_cfg["rsi_long_max"]:
        cfd_long += w["rsi_zone"]
        long_components["rsi_zone"] = w["rsi_zone"]
    if vol_ratio >= cfd_cfg["vol_ratio_min"]:
        cfd_long += w["volume"]
        long_components["volume"] = w["volume"]
    if recent_max_gap < cfd_cfg["max_gap_pct"]:
        cfd_long += w["no_gap"]
        long_components["no_gap"] = w["no_gap"]

    long_bonus = 0.0
    if vol_ratio >= bonus["vol_ratio_high"]:
        long_bonus += bonus["vol_ratio_pts"]
        long_components["bonus_high_volume"] = bonus["vol_ratio_pts"]
    cfd_long += min(long_bonus, bonus.get("max_bonus", 1.0))

    if adx_val > cfd_cfg.get("adx_overripe", 99):
        val = penalty.get("adx_overripe_pts", 0)
        cfd_long += val
        long_penalties["adx_overripe"] = val
    if recent_max_gap >= penalty.get("gap_hard_pct", 999):
        val = penalty.get("gap_hard_pts", 0)
        cfd_long += val
        long_penalties["gap_hard"] = val
    elif recent_max_gap >= penalty.get("gap_soft_pct", 999):
        val = penalty.get("gap_soft_pts", 0)
        cfd_long += val
        long_penalties["gap_soft"] = val
    if atr_pct >= penalty.get("atr_high_pct", 999):
        val = penalty.get("atr_high_pts", 0)
        cfd_long += val
        long_penalties["atr_high"] = val
    market_long_adj = market_cfg.get("long", {}).get(market, 0.0)
    if market_long_adj:
        cfd_long += market_long_adj
        long_penalties["market_adjustment"] = market_long_adj

    # --- Short ---
    cfd_short = 0.0
    if adx_val > cfd_cfg["adx_min"] and minus_di_val > plus_di_val:
        cfd_short += w["adx_di"]
        short_components["adx_di"] = w["adx_di"]
    if current_price < sma20_val < sma50_val:
        cfd_short += w["ma_structure"]
        short_components["ma_structure"] = w["ma_structure"]
    if ema9_val < ema21_val:
        cfd_short += w["ema_stack"]
        short_components["ema_stack"] = w["ema_stack"]
    if curr_hist < 0 and curr_hist < prev_hist:
        cfd_short += w["macd"]
        short_components["macd"] = w["macd"]
    if cfd_cfg["rsi_short_min"] <= rsi_val <= cfd_cfg["rsi_short_max"]:
        cfd_short += w["rsi_zone"]
        short_components["rsi_zone"] = w["rsi_zone"]
    if vol_ratio >= cfd_cfg["vol_ratio_min"]:
        cfd_short += w["volume"]
        short_components["volume"] = w["volume"]
    if recent_max_gap < cfd_cfg["max_gap_pct"]:
        cfd_short += w["no_gap"]
        short_components["no_gap"] = w["no_gap"]

    short_bonus = 0.0
    if vol_ratio >= bonus["vol_ratio_high"]:
        short_bonus += bonus["vol_ratio_pts"]
        short_components["bonus_high_volume"] = bonus["vol_ratio_pts"]
    cfd_short += min(short_bonus, bonus.get("max_bonus", 1.0))

    if adx_val > cfd_cfg.get("adx_overripe", 99):
        val = penalty.get("adx_overripe_pts", 0)
        cfd_short += val
        short_penalties["adx_overripe"] = val
    if recent_max_gap >= penalty.get("gap_hard_pct", 999):
        val = penalty.get("gap_hard_pts", 0)
        cfd_short += val
        short_penalties["gap_hard"] = val
    elif recent_max_gap >= penalty.get("gap_soft_pct", 999):
        val = penalty.get("gap_soft_pts", 0)
        cfd_short += val
        short_penalties["gap_soft"] = val
    if atr_pct >= penalty.get("atr_high_pct", 999):
        val = penalty.get("atr_high_pts", 0)
        cfd_short += val
        short_penalties["atr_high"] = val
    short_bias = penalty.get("short_bias_pts", 0)
    if short_bias:
        cfd_short += short_bias
        short_penalties["short_bias"] = short_bias
    market_short_adj = market_cfg.get("short", {}).get(market, 0.0)
    if market_short_adj:
        cfd_short += market_short_adj
        short_penalties["market_adjustment"] = market_short_adj

    short_cap = cfd_cfg.get("short_score_cap", 99)
    if cfd_short > short_cap:
        cfd_short = short_cap

    if not cfd_atr_ok:
        cfd_long = 0.0
        cfd_short = 0.0
        long_penalties["atr_gate"] = "blocked"
        short_penalties["atr_gate"] = "blocked"

    threshold = cfg["scoring"]["threshold"]
    if cfd_long >= threshold and cfd_short >= threshold:
        if cfd_long > cfd_short:
            cfd_short = 0.0
            short_penalties["exclusive_direction"] = "blocked_by_long"
        elif cfd_short > cfd_long:
            cfd_long = 0.0
            long_penalties["exclusive_direction"] = "blocked_by_short"
        else:
            if plus_di_val >= minus_di_val:
                cfd_short = 0.0
                short_penalties["exclusive_direction"] = "blocked_by_di"
            else:
                cfd_long = 0.0
                long_penalties["exclusive_direction"] = "blocked_by_di"

    metadata = {
        "long": {"components": long_components, "penalties": long_penalties},
        "short": {"components": short_components, "penalties": short_penalties},
    }
    return round(cfd_long, 1), round(cfd_short, 1), metadata
