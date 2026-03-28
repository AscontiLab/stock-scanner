#!/usr/bin/env python3
"""
Sendet den täglichen Trading-Report per E-Mail (Gmail SMTP).
Liest Credentials aus ~/.stock_scanner_credentials

Nutzt scanner_common fuer Credentials und E-Mail-Versand.
"""

import re
import sys
from datetime import datetime
from pathlib import Path

# --- Neue zentrale Imports aus scanner_common ---
from scanner_common import load_credentials, require_keys
from scanner_common import send_report as _send_report_generic


# ── DEPRECATED: Alte lokale Funktionen ──────────────────────────────────────
# Die folgenden Funktionen sind deprecated und werden aus scanner_common importiert.
# Bitte scanner_common.load_credentials / scanner_common.require_keys nutzen.

# def load_credentials() -> dict:
#     """DEPRECATED — nutze scanner_common.load_credentials()"""
#     ...

# def require_keys(creds, keys) -> bool:
#     """DEPRECATED — nutze scanner_common.require_keys()"""
#     ...
# ────────────────────────────────────────────────────────────────────────────


def build_subject(html_path: Path) -> str:
    date_str = datetime.now().strftime("%d.%m.%Y")
    # Kaufsignale/Verkaufsignale aus HTML zählen
    try:
        content = html_path.read_text(encoding="utf-8")
        buy_match  = re.search(r"Kaufsignale.*?bold\">(\d+)<", content)
        sell_match = re.search(r"Verkaufsignale.*?bold\">(\d+)<", content)
        buy_count  = buy_match.group(1)  if buy_match  else "?"
        sell_count = sell_match.group(1) if sell_match else "?"
        return f"📊 Trading Scanner {date_str} — Kauf: {buy_count} | Verkauf: {sell_count}"
    except Exception:
        return f"📊 Trading Scanner Report {date_str}"


def send_report(html_path: Path, csv_path: Path | None = None):
    """Sendet den Stock-Scanner-Report via scanner_common."""
    subject = build_subject(html_path)
    html_content = html_path.read_text(encoding="utf-8")

    if not _send_report_generic(
        subject=subject,
        html_body=html_content,
        csv_attachments=csv_path,
        sender_name="Stock Scanner",
    ):
        sys.exit(1)


if __name__ == "__main__":
    base = Path(__file__).parent
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Datums-Ordner bevorzugen, sonst Hauptordner
    dated_dir = base / "output" / date_str
    html = dated_dir / "trading_signals.html"
    csv  = dated_dir / "trading_signals.csv"

    if not html.exists():
        html = base / "trading_signals.html"
        csv  = base / "trading_signals.csv"

    if not html.exists():
        print("Fehler: Kein HTML-Report gefunden.", file=sys.stderr)
        sys.exit(1)

    send_report(html, csv if csv.exists() else None)
