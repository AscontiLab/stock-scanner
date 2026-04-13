#!/usr/bin/env python3
"""Sendet Stock-Scanner-Ergebnisse an n8n Dashboard Webhook."""

import json
import os
import sys
import ast
from datetime import datetime, timezone
from pathlib import Path

import requests

from utils import safe_float as to_float
from utils import safe_int as to_int
from utils import read_csv as read_csv_safe

_N8N_BASE = os.environ.get("N8N_BASE_URL", "https://agents.umzwei.de")
N8N_WEBHOOK = f"{_N8N_BASE}/webhook/stock-update"
HUB_DIR = Path(__file__).resolve().parent.parent / "hub"


def _status_from_signal(signal: dict, direction: str | None = None) -> str:
    if direction:
        return "selected"
    score = to_int(signal.get("net_score"))
    if score >= 4 or score <= -4:
        return "selected"
    return "candidate"


def _stock_priority(signal: dict, direction: str | None = None) -> int:
    if direction == "long":
        return min(100, int(round(to_float(signal.get("cfd_long_score")) * 10)))
    if direction == "short":
        return min(100, int(round(to_float(signal.get("cfd_short_score")) * 10)))
    return min(100, max(0, 50 + to_int(signal.get("net_score")) * 8))


def _stock_explainability(signal: dict, direction: str | None = None) -> dict:
    if direction == "long":
        side = "long"
        score_val = to_float(signal.get("cfd_long_score"))
        stop = signal.get("stop_long")
        tp1 = signal.get("tp1_long")
        tp2 = signal.get("tp2_long")
    elif direction == "short":
        side = "short"
        score_val = to_float(signal.get("cfd_short_score"))
        stop = signal.get("stop_short")
        tp1 = signal.get("tp1_short")
        tp2 = signal.get("tp2_short")
    else:
        side = "buy" if to_int(signal.get("net_score")) >= 0 else "sell"
        score_val = abs(to_int(signal.get("net_score")))
        stop = tp1 = tp2 = None

    why_now = []
    confidence_reason = []
    risk_flags = []
    invalidators = []
    drivers = []
    learning_flags = []
    rules_summary = []

    raw_components = signal.get(f"cfd_{side}_components", {}) if side in ("long", "short") else {}
    raw_penalties = signal.get(f"cfd_{side}_penalties", {}) if side in ("long", "short") else {}

    if isinstance(raw_components, str):
        try:
            raw_components = json.loads(raw_components)
        except Exception:
            try:
                raw_components = ast.literal_eval(raw_components)
            except Exception:
                raw_components = {}
    if isinstance(raw_penalties, str):
        try:
            raw_penalties = json.loads(raw_penalties)
        except Exception:
            try:
                raw_penalties = ast.literal_eval(raw_penalties)
            except Exception:
                raw_penalties = {}

    if signal.get("ma") and signal.get("ma") != "neutral":
        why_now.append(f"MA-Struktur ist aktuell {signal.get('ma')}.")
        drivers.append({"label": "MA Structure", "direction": "positive", "value": signal.get("ma"), "weight": 0.20})
    if signal.get("macd") and signal.get("macd") not in ("neutral", "bearish", "bullish"):
        why_now.append(f"MACD zeigt {signal.get('macd')}.")
        drivers.append({"label": "MACD", "direction": "positive", "value": signal.get("macd"), "weight": 0.15})
    if signal.get("volume"):
        confidence_reason.append(f"Volumen-Signal: {signal.get('volume')}.")
        drivers.append({"label": "Volume", "direction": "positive", "value": signal.get("volume"), "weight": 0.10})
    if signal.get("adx"):
        confidence_reason.append(f"ADX liegt bei {to_float(signal.get('adx')):.1f}.")
    if signal.get("rsi_signal") and signal.get("rsi_signal") != "neutral":
        why_now.append(f"RSI ist aktuell {signal.get('rsi_signal')}.")
    if signal.get("recent_max_gap") and to_float(signal.get("recent_max_gap")) > 3.0:
        risk_flags.append(f"Der letzte Max-Gap liegt bei {to_float(signal.get('recent_max_gap')):.1f}% und ist erhoeht.")
    if signal.get("atr_pct"):
        risk_flags.append(f"ATR liegt bei {to_float(signal.get('atr_pct')):.1f}% und erhoeht die Schwankung.")
    if signal.get("trend_long_days") and side in ("long", "buy"):
        confidence_reason.append(f"Trendstruktur haelt seit {to_int(signal.get('trend_long_days'))} Tagen.")
    if signal.get("trend_short_days") and side == "short":
        confidence_reason.append(f"Short-Trendstruktur haelt seit {to_int(signal.get('trend_short_days'))} Tagen.")

    if raw_penalties.get("gap_hard"):
        learning_flags.append({
            "code": "gap_hard",
            "label": "Gap > 6%",
            "impact": raw_penalties["gap_hard"],
            "kind": "penalty",
        })
        rules_summary.append("Hartes Gap-Filter aktiv")
    elif raw_penalties.get("gap_soft"):
        learning_flags.append({
            "code": "gap_soft",
            "label": "Gap 4-6%",
            "impact": raw_penalties["gap_soft"],
            "kind": "penalty",
        })
        rules_summary.append("Gap-Regime dämpft den Score")

    if raw_penalties.get("atr_high"):
        learning_flags.append({
            "code": "atr_high",
            "label": "ATR >= 3%",
            "impact": raw_penalties["atr_high"],
            "kind": "penalty",
        })
        rules_summary.append("Hohes ATR-Regime vorsichtiger bewertet")

    if raw_penalties.get("short_bias"):
        learning_flags.append({
            "code": "short_bias",
            "label": "Short-Bias",
            "impact": raw_penalties["short_bias"],
            "kind": "penalty",
        })
        rules_summary.append("Shorts werden historisch skeptischer bewertet")

    market_adj = raw_penalties.get("market_adjustment", 0)
    if market_adj:
        learning_flags.append({
            "code": "market_adjustment",
            "label": f"Marktfilter {signal.get('market', '?')}",
            "impact": market_adj,
            "kind": "penalty" if market_adj < 0 else "bonus",
        })
        rules_summary.append(f"Marktfilter fuer {signal.get('market', '?')} aktiv")

    if raw_components.get("bonus_trend_maturity"):
        learning_flags.append({
            "code": "trend_maturity_bonus",
            "label": "Trend-Reife",
            "impact": raw_components["bonus_trend_maturity"],
            "kind": "bonus",
        })

    if raw_components.get("bonus_squeeze_fire"):
        learning_flags.append({
            "code": "squeeze_fire_bonus",
            "label": "Squeeze Fire",
            "impact": raw_components["bonus_squeeze_fire"],
            "kind": "bonus",
        })

    if stop is not None:
        invalidators.append(f"Setup verliert seine Gueltigkeit unter/ueber dem Stop-Level {stop}.")
    if tp1 is not None and tp2 is not None:
        invalidators.append(f"Trade-Management orientiert sich an TP1 {tp1} und TP2 {tp2}.")
    invalidators.append("Gesamtmarkt-Regime oder Momentum kippt gegen die aktuelle Richtung.")

    if not why_now:
        why_now.append("Mehrere technische Treiber liefern gleichzeitig ein aktives Signal.")
    if not confidence_reason:
        confidence_reason.append("Der Score wird aus technischen Faktoren, Trendfiltern und Volumenbestaetigung abgeleitet.")
    if not risk_flags:
        risk_flags.append("Schnelle Marktregimewechsel koennen das Setup trotz gutem Score entwerten.")
    if not rules_summary:
        rules_summary.append("Keine datenbasierten Sonderregeln aktiv; Basisscore ohne starke Dämpfer.")

    title_side = "Long" if side == "long" else "Short" if side == "short" else "Buy" if side == "buy" else "Sell"
    return {
        "summary": f"{signal.get('ticker', '?')} zeigt ein {title_side}-Setup mit Score {score_val:.1f}.",
        "rules_summary": rules_summary,
        "why_now": why_now,
        "model_basis": [
            "Technische Faktoren: RSI, MACD, MA-Struktur, Bollinger, Volumen, Candlestick, VWAP, Squeeze",
            "CFD-Score kombiniert Trend-, Momentum- und Volatilitaetsfilter" if direction else "Net-Score basiert auf aggregierten technischen Signalen",
        ],
        "confidence_reason": confidence_reason,
        "risk_flags": risk_flags,
        "invalidators": invalidators,
        "drivers": drivers,
        "learning_flags": learning_flags,
        "version": "v2",
    }


def _stock_signal_id(signal: dict, date_str: str, direction: str | None = None) -> str:
    kind = direction or ("buy" if to_int(signal.get("net_score")) >= 0 else "sell")
    return f"stock:{signal.get('ticker', 'unknown')}:{kind}:{date_str}"


def _normalize_stock_signal(signal: dict, date_str: str, direction: str | None = None) -> dict:
    side = direction or ("buy" if to_int(signal.get("net_score")) >= 0 else "sell")
    title_side = "Long Setup" if side == "long" else "Short Setup" if side == "short" else "Buy Signal" if side == "buy" else "Sell Signal"
    metrics = {
        "price": round(to_float(signal.get("price")), 2),
        "net_score": to_int(signal.get("net_score")),
        "cfd_quality_score": round(
            to_float(signal.get("cfd_long_score") if side == "long" else signal.get("cfd_short_score") if side == "short" else signal.get("cfd_quality_score")),
            2,
        ),
        "adx": round(to_float(signal.get("adx")), 1),
        "vol_ratio": round(to_float(signal.get("vol_ratio")), 2),
        "atr_pct": round(to_float(signal.get("atr_pct")), 2),
        "fear_greed": signal.get("fear_greed"),
    }
    explainability = _stock_explainability(signal, direction)
    return {
        "signal_id": _stock_signal_id(signal, date_str, direction),
        "run_id": f"stock-{date_str}",
        "system": "stock-scanner",
        "category": "stock_setup",
        "status": _status_from_signal(signal, direction),
        "priority": _stock_priority(signal, direction),
        "title": f"{signal.get('ticker', '?')} {title_side}",
        "subtitle": f"{signal.get('market', 'Unbekannt')} | Kurs {to_float(signal.get('price')):.2f}",
        "entity": {
            "primary": signal.get("ticker"),
            "secondary": signal.get("name") or signal.get("ticker"),
            "market": "equity",
            "side": side,
            "universe": signal.get("market"),
        },
        "timing": {
            "event_time": f"{date_str}T00:00:00Z",
            "expires_at": f"{date_str}T23:59:59Z",
        },
        "reason": " | ".join(explainability.get("rules_summary", [])[:2]),
        "metrics": metrics,
        "explainability": explainability,
    }


def _upsert_hub_records(path: Path, records: list[dict], key_field: str, system_name: str) -> None:
    existing = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing = [r for r in existing if r.get("system") != system_name]
    merged = existing + records
    merged.sort(key=lambda r: (r.get("generated_at") or r.get("run_id") or r.get(key_field) or ""), reverse=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_hub_exports(date_str: str, fear_greed: dict, buy_signals: list, sell_signals: list, cfd_long: list, cfd_short: list) -> None:
    HUB_DIR.mkdir(parents=True, exist_ok=True)
    run_payload = {
        "run_id": f"stock-{date_str}",
        "system": "stock-scanner",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "ok",
        "summary": {
            "total_candidates": len(buy_signals) + len(sell_signals) + len(cfd_long) + len(cfd_short),
            "selected_count": len(cfd_long) + len(cfd_short),
            "watch_count": len(buy_signals) + len(sell_signals),
            "warnings_count": sum(1 for row in cfd_long + cfd_short if to_float(row.get("recent_max_gap")) > 3.0),
        },
    }
    normalized = []
    for row in buy_signals:
        row = {**row, "fear_greed": fear_greed.get("value")}
        normalized.append(_normalize_stock_signal(row, date_str))
    for row in sell_signals:
        row = {**row, "fear_greed": fear_greed.get("value")}
        normalized.append(_normalize_stock_signal(row, date_str))
    for row in cfd_long:
        row = {**row, "fear_greed": fear_greed.get("value")}
        normalized.append(_normalize_stock_signal(row, date_str, direction="long"))
    for row in cfd_short:
        row = {**row, "fear_greed": fear_greed.get("value")}
        normalized.append(_normalize_stock_signal(row, date_str, direction="short"))
    _upsert_hub_records(HUB_DIR / "latest_runs.json", [run_payload], "run_id", "stock-scanner")
    _upsert_hub_records(HUB_DIR / "latest_signals.json", normalized, "signal_id", "stock-scanner")


def post_to_dashboard(output_dir: str, fear_greed: dict) -> None:
    """Liest CSVs und postet JSON an n8n."""
    date_str = datetime.now().strftime("%Y-%m-%d")

    signals = read_csv_safe(f"{output_dir}/trading_signals.csv")
    cfds = read_csv_safe(f"{output_dir}/cfd_setups.csv")

    buy_signals = sorted(
        [s for s in signals if to_float(s.get("net_score", 0)) > 0],
        key=lambda s: to_float(s.get("net_score", 0)),
        reverse=True,
    )[:10]
    sell_signals = sorted(
        [s for s in signals if to_float(s.get("net_score", 0)) < 0],
        key=lambda s: to_float(s.get("net_score", 0)),
    )[:10]

    cfd_long = [c for c in cfds if c.get("cfd_direction") == "long"][:10]
    cfd_short = [c for c in cfds if c.get("cfd_direction") == "short"][:10]

    # cfd_quality_score als Float sicherstellen
    for c in cfd_long + cfd_short:
        if "cfd_quality_score" not in c:
            # Backward-Compat: altes Format (int Score /7)
            direction = c.get("cfd_direction", "long")
            score_key = f"cfd_{direction}_score"
            c["cfd_quality_score"] = to_float(c.get(score_key, 0))

    payload = {
        "date": date_str,
        "fear_greed": fear_greed,
        "total_signals": len(signals),
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "cfd_long": cfd_long,
        "cfd_short": cfd_short,
        "score_format": "weighted",  # Signal an Dashboard: neues Float-Format
    }

    _write_hub_exports(date_str, fear_greed, buy_signals, sell_signals, cfd_long, cfd_short)

    try:
        resp = requests.post(N8N_WEBHOOK, json=payload, timeout=10)
        print(
            f"Dashboard-Push: HTTP {resp.status_code} "
            f"({len(buy_signals)} Kauf, {len(sell_signals)} Verkauf, "
            f"{len(cfd_long)} CFD Long, {len(cfd_short)} CFD Short)"
        )
    except Exception as e:
        print(f"Dashboard-Push fehlgeschlagen: {e}")


if __name__ == "__main__":
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = sys.argv[1] if len(sys.argv) > 1 else f"output/{date_str}"
    fear_greed = {"value": 50, "label": "Neutral"}
    post_to_dashboard(output_dir, fear_greed)
