#!/usr/bin/env python3
"""
Sendet den täglichen Trading-Report per E-Mail (Gmail SMTP).
Liest Credentials aus ~/.stock_scanner_credentials
"""

import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path


def load_credentials() -> dict:
    cred_file = Path.home() / ".stock_scanner_credentials"
    creds = {}
    if not cred_file.exists():
        print(f"Fehler: Credentials-Datei fehlt: {cred_file}", file=sys.stderr)
        return {}
    with open(cred_file) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                creds[key.strip()] = val.strip()
    return creds


def require_keys(creds: dict, keys: list[str]) -> bool:
    missing = [k for k in keys if not creds.get(k)]
    if missing:
        print(f"Fehler: Fehlende Credentials: {', '.join(missing)}", file=sys.stderr)
        return False
    return True


def build_subject(html_path: Path) -> str:
    date_str = datetime.now().strftime("%d.%m.%Y")
    # Kaufsignale/Verkaufsignale aus HTML zählen
    try:
        content = html_path.read_text(encoding="utf-8")
        import re
        buy_match  = re.search(r"Kaufsignale.*?bold\">(\d+)<", content)
        sell_match = re.search(r"Verkaufsignale.*?bold\">(\d+)<", content)
        buy_count  = buy_match.group(1)  if buy_match  else "?"
        sell_count = sell_match.group(1) if sell_match else "?"
        return f"📊 Trading Scanner {date_str} — Kauf: {buy_count} | Verkauf: {sell_count}"
    except Exception:
        return f"📊 Trading Scanner Report {date_str}"


def send_report(html_path: Path, csv_path: Path | None = None):
    creds = load_credentials()
    if not require_keys(creds, ["GMAIL_USER", "GMAIL_APP_PASSWORD", "GMAIL_RECIPIENT"]):
        sys.exit(1)
    user      = creds["GMAIL_USER"]
    password  = creds["GMAIL_APP_PASSWORD"]
    recipient = creds["GMAIL_RECIPIENT"]

    subject = build_subject(html_path)
    html_content = html_path.read_text(encoding="utf-8")

    msg = MIMEMultipart("mixed")
    msg["From"]    = f"Stock Scanner <{user}>"
    msg["To"]      = recipient
    msg["Subject"] = subject

    # HTML als E-Mail-Body
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    # CSV als Anhang (falls vorhanden)
    if csv_path and csv_path.exists():
        with open(csv_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={csv_path.name}",
        )
        msg.attach(part)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(user, password)
        server.sendmail(user, recipient, msg.as_string())

    print(f"E-Mail gesendet an {recipient}: {subject}")


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
