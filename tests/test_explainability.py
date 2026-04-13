import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import post_to_dashboard


def test_normalize_stock_signal_builds_explainability_payload():
    row = {
        "ticker": "NVDA",
        "name": "NVIDIA",
        "market": "NASDAQ",
        "price": "912.4",
        "net_score": "5",
        "ma": "BUY",
        "macd": "BUY",
        "volume": "BUY (1.8x avg)",
        "adx": "26.4",
        "atr_pct": "3.1",
        "trend_long_days": "7",
        "recent_max_gap": "1.2",
        "cfd_long_score": "7.5",
        "fear_greed": 44,
    }

    signal = post_to_dashboard._normalize_stock_signal(row, "2026-03-14", direction="long")

    assert signal["system"] == "stock-scanner"
    assert signal["status"] == "selected"
    assert signal["priority"] == 75
    assert signal["entity"]["side"] == "long"
    assert signal["metrics"]["fear_greed"] == 44
    assert signal["explainability"]["version"] == "v2"
    assert signal["explainability"]["why_now"]
    assert signal["explainability"]["drivers"]
    assert signal["explainability"]["rules_summary"]


def test_write_hub_exports_preserves_other_systems(tmp_path):
    hub_dir = tmp_path / "hub"
    hub_dir.mkdir()
    original_hub_dir = post_to_dashboard.HUB_DIR
    post_to_dashboard.HUB_DIR = hub_dir
    try:
        (hub_dir / "latest_runs.json").write_text(
            '[{"run_id":"sports-1","system":"sports-scanner","generated_at":"2026-03-14T09:00:00Z"}]',
            encoding="utf-8",
        )
        (hub_dir / "latest_signals.json").write_text(
            '[{"signal_id":"sports:a","system":"sports-scanner","title":"Chelsea"}]',
            encoding="utf-8",
        )

        buy = [{"ticker": "NVDA", "name": "NVIDIA", "market": "NASDAQ", "price": "100", "net_score": "5", "ma": "BUY"}]
        post_to_dashboard._write_hub_exports("2026-03-14", {"value": 50, "label": "Neutral"}, buy, [], [], [])

        runs = json.loads((hub_dir / "latest_runs.json").read_text(encoding="utf-8"))
        signals = json.loads((hub_dir / "latest_signals.json").read_text(encoding="utf-8"))

        assert {item["system"] for item in runs} == {"sports-scanner", "stock-scanner"}
        assert {item["system"] for item in signals} == {"sports-scanner", "stock-scanner"}
    finally:
        post_to_dashboard.HUB_DIR = original_hub_dir
