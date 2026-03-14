#!/usr/bin/env python3
"""
Telegram Bot Alerts fuer den Stock Scanner.

Sendet Push-Nachrichten bei:
- CFD-Signal mit Score >= 7
- Stop/TP-Hit einer Portfolio-Position
- Taegliche Zusammenfassung
"""

import os
import urllib.request
import urllib.parse
import json
from pathlib import Path


def _get_config():
    """Liest Telegram-Config aus .env oder Umgebungsvariablen."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    # Fallback: .env im Scanner-Dir lesen
    if not token or not chat_id:
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k == "TELEGRAM_BOT_TOKEN":
                    token = v
                elif k == "TELEGRAM_CHAT_ID":
                    chat_id = v

    return token, chat_id


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Sendet eine Nachricht via Telegram Bot API. Returns True bei Erfolg."""
    token, chat_id = _get_config()
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Telegram-Fehler: {e}")
        return False


def send_signal_alert(ticker: str, direction: str, score: float,
                      entry: float, stop: float, tp1: float, tp2: float,
                      market: str = "") -> bool:
    """Sendet Alert fuer ein starkes CFD-Signal (Score >= 7)."""
    arrow = "\u2b06" if direction == "long" else "\u2b07"
    text = (
        f"<b>{arrow} CFD {direction.upper()}: {ticker}</b>\n"
        f"Score: <b>{score:.1f}/10</b> | Markt: {market}\n"
        f"Entry: {entry:.2f}\n"
        f"Stop: {stop:.2f} | TP1: {tp1:.2f} | TP2: {tp2:.2f}"
    )
    return send_message(text)


def send_position_alert(ticker: str, direction: str, event: str,
                        price: float, pnl_pct: float) -> bool:
    """Sendet Alert bei Stop/TP-Hit einer Position."""
    if "STOP" in event:
        emoji = "\u26a0\ufe0f"
    elif "TP2" in event:
        emoji = "\U0001f3af"
    elif "TP1" in event:
        emoji = "\u2705"
    else:
        emoji = "\u2139\ufe0f"

    pnl_sign = "+" if pnl_pct >= 0 else ""
    text = (
        f"{emoji} <b>{ticker} {direction.upper()}</b>\n"
        f"{event}\n"
        f"Kurs: {price:.2f} | P&L: {pnl_sign}{pnl_pct:.1f}%"
    )
    return send_message(text)


def send_daily_summary(fear_greed: dict, long_count: int, short_count: int,
                       top_signals: list, position_count: int = 0) -> bool:
    """Sendet taegliche Zusammenfassung nach dem Scan."""
    fg_val = fear_greed.get("value", 50)
    fg_label = fear_greed.get("label", "?")

    lines = [
        f"<b>\U0001f4ca Daily Stock Scanner</b>",
        f"Fear & Greed: <b>{fg_val}</b> ({fg_label})",
        f"CFD Long: {long_count} | Short: {short_count}",
    ]

    if top_signals:
        lines.append("\n<b>Top Signale:</b>")
        for s in top_signals[:5]:
            d = s.get("cfd_direction", "long")
            score_key = "cfd_long_score" if d == "long" else "cfd_short_score"
            score = s.get(score_key, 0)
            arrow = "\u2b06" if d == "long" else "\u2b07"
            lines.append(f"  {arrow} {s['ticker']} {score:.1f}/10")

    if position_count > 0:
        lines.append(f"\nAktive Positionen: {position_count}")

    return send_message("\n".join(lines))
