#!/usr/bin/env python3
"""Sendet Stock-Scanner-Ergebnisse an n8n Dashboard Webhook."""

import csv
import os
import sys
from datetime import datetime

import requests

N8N_WEBHOOK = "https://agents.umzwei.de/webhook/stock-update"


def read_csv_safe(path: str) -> list:
    """Liest CSV und gibt Liste von Dicts zurück."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def to_float(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


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

    cfd_long = [c for c in cfds if c.get("cfd_direction") == "long"][:8]
    cfd_short = [c for c in cfds if c.get("cfd_direction") == "short"][:8]

    payload = {
        "date": date_str,
        "fear_greed": fear_greed,
        "total_signals": len(signals),
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "cfd_long": cfd_long,
        "cfd_short": cfd_short,
    }

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
