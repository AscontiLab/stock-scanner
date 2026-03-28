#!/usr/bin/env python3
"""
Telegram Bot Alerts fuer den Stock Scanner.

Sendet Push-Nachrichten bei:
- CFD-Signal mit Score >= 7
- Stop/TP-Hit einer Portfolio-Position
- Taegliche Zusammenfassung

Nutzt scanner_common.telegram fuer den eigentlichen Versand.
"""

import os
from pathlib import Path

# --- Neue zentrale Imports aus scanner_common ---
from scanner_common.telegram import send_message as _send_message_common
from scanner_common.credentials import load_credentials


# ── DEPRECATED: Alte lokale _get_config / urllib-basierte send_message ───────
# Die Basis-Funktionen sind jetzt in scanner_common.telegram.
# Die scanner-spezifischen Alerts (send_signal_alert etc.) bleiben hier.
# ────────────────────────────────────────────────────────────────────────────


def _get_config():
    """Liest Telegram-Config aus Credentials-Datei oder Umgebungsvariablen.

    Primaer: AscontiLab Bot Token, Fallback: alter TELEGRAM_BOT_TOKEN.
    """
    # Primaer aus Umgebungsvariablen
    token = os.environ.get("ASCONTILAB_BOT_TOKEN", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("ASCONTILAB_CHAT_ID", "") or os.environ.get("TELEGRAM_CHAT_ID", "")

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
                if k == "ASCONTILAB_BOT_TOKEN":
                    token = token or v
                elif k == "ASCONTILAB_CHAT_ID":
                    chat_id = chat_id or v
                elif k == "TELEGRAM_BOT_TOKEN":
                    token = token or v
                elif k == "TELEGRAM_CHAT_ID":
                    chat_id = chat_id or v

    # Fallback: zentrale Credentials-Datei
    if not token or not chat_id:
        creds = load_credentials()
        token = token or creds.get("ASCONTILAB_BOT_TOKEN", "") or creds.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = chat_id or creds.get("ASCONTILAB_CHAT_ID", "") or creds.get("TELEGRAM_CHAT_ID", "")

    return token, chat_id


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Sendet eine Nachricht via Telegram Bot API. Returns True bei Erfolg."""
    token, chat_id = _get_config()
    if not token or not chat_id:
        return False
    return _send_message_common(text, token, chat_id, parse_mode=parse_mode)


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


def send_stock_portfolio_alert(stock_reports: list) -> bool:
    """Sendet Telegram-Alert wenn gehaltene Aktien 2+ Warnungen haben.

    Nur Aktien mit warning_count >= 2 werden gemeldet.
    Bei 2 Warnungen: BEOBACHTEN, bei 3+: VERKAUF PRUEFEN.
    """
    if not stock_reports:
        return False

    # Nur Aktien mit mindestens 2 Warnungen
    critical = [r for r in stock_reports if r.get("warning_count", 0) >= 2]
    if not critical:
        return False

    lines = ["<b>\U0001f4ca Investment-Portfolio Warnung</b>"]

    for r in critical:
        n_warn = r.get("warning_count", 0)
        ticker = r.get("ticker", "?")
        name = r.get("name", ticker)
        price = r.get("price")
        pct = r.get("pct_change")

        # Emoji und Empfehlung je nach Schwere
        if n_warn >= 3:
            emoji = "\U0001f534"  # Roter Kreis
            label = "VERKAUF PR\u00dcFEN"
        else:
            emoji = "\u26a0\ufe0f"  # Warnzeichen
            label = "BEOBACHTEN"

        lines.append(f"\n{emoji} <b>{name} ({ticker})</b>")
        lines.append(f"  Empfehlung: {label}")

        # Kurs-Zeile (nur wenn vorhanden)
        if price is not None:
            pct_str = f" ({pct:+.1f}%)" if pct is not None else ""
            lines.append(f"  Kurs: {price:.2f}{pct_str}")

        # Warnungen auflisten
        warnings = r.get("warnings", [])
        if warnings:
            lines.append("  Warnungen:")
            for w in warnings:
                lines.append(f"  \u2022 {w}")

    try:
        return send_message("\n".join(lines))
    except Exception as e:
        print(f"Investment-Portfolio Telegram-Alert fehlgeschlagen: {e}")
        return False


def send_daily_summary(fear_greed: dict, long_count: int, short_count: int,
                       top_signals: list, position_count: int = 0,
                       stock_reports: list = None) -> bool:
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

    # Investment-Portfolio Zusammenfassung
    if stock_reports:
        total = len(stock_reports)
        ok_count = sum(1 for r in stock_reports if r.get("warning_count", 0) <= 1)
        watch_count = sum(1 for r in stock_reports if r.get("warning_count", 0) == 2)
        critical_count = sum(1 for r in stock_reports if r.get("warning_count", 0) >= 3)
        lines.append(f"\n\U0001f4ca Investment-Portfolio: {total} Aktien")
        lines.append(f"  \u2705 {ok_count} ok | \u26a0\ufe0f {watch_count} beobachten | \U0001f534 {critical_count} pr\u00fcfen")

    return send_message("\n".join(lines))
