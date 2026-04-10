#!/usr/bin/env python3
"""
Investment-Portfolio-Manager fuer langfristige Aktienbestaende.

Verwaltet eine einfache Liste gehaltener Aktien (ohne Einstiegspreise/P&L)
und prueft Warnzeichen anhand der Scan-Ergebnisse.

Verwendung:
    python3 stock_scanner.py --add-stock AAPL
    python3 stock_scanner.py --remove-stock AAPL
    python3 stock_scanner.py --stocks
    python3 stock_scanner.py --import-stocks AAPL,MSFT,SAP.DE
"""

import fcntl
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

PORTFOLIO_PATH = Path(__file__).parent / "investment_portfolio.json"

_EMPTY_PORTFOLIO = {"stocks": []}


@contextmanager
def _portfolio_lock():
    """File-Lock fuer Portfolio-JSON (verhindert Race Conditions)."""
    lock_path = PORTFOLIO_PATH.with_suffix(".lock")
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


def _load_portfolio() -> dict:
    """Laedt das Portfolio aus der JSON-Datei."""
    if not PORTFOLIO_PATH.exists():
        return _EMPTY_PORTFOLIO.copy()
    try:
        data = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
        if "stocks" not in data:
            data["stocks"] = []
        return data
    except Exception:
        return _EMPTY_PORTFOLIO.copy()


def _save_portfolio(data: dict) -> None:
    """Speichert das Portfolio in die JSON-Datei."""
    PORTFOLIO_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_stock(ticker: str, market: str = "") -> bool:
    """Fuegt Aktie zum Portfolio hinzu. Gibt False zurueck bei Duplikat."""
    ticker = ticker.upper()
    with _portfolio_lock():
        portfolio = _load_portfolio()

        # Duplikat-Check
        for s in portfolio["stocks"]:
            if s["ticker"] == ticker:
                return False

        today = datetime.now().strftime("%Y-%m-%d")
        portfolio["stocks"].append({
            "ticker": ticker,
            "market": market,
            "added_date": today,
        })
        _save_portfolio(portfolio)
    return True


def remove_stock(ticker: str) -> bool:
    """Entfernt Aktie aus Portfolio. Gibt False zurueck wenn nicht gefunden."""
    ticker = ticker.upper()
    with _portfolio_lock():
        portfolio = _load_portfolio()
        before = len(portfolio["stocks"])
        portfolio["stocks"] = [
            s for s in portfolio["stocks"] if s["ticker"] != ticker
        ]
        after = len(portfolio["stocks"])
        if before > after:
            _save_portfolio(portfolio)
            return True
    return False


def list_stocks() -> list[dict]:
    """Gibt alle gehaltenen Aktien zurueck."""
    return _load_portfolio().get("stocks", [])


def import_stocks(tickers: list[str]) -> int:
    """Batch-Import. Gibt Anzahl neu hinzugefuegter Aktien zurueck."""
    count = 0
    with _portfolio_lock():
        portfolio = _load_portfolio()
        existing = {s["ticker"] for s in portfolio["stocks"]}
        today = datetime.now().strftime("%Y-%m-%d")

        for t in tickers:
            t = t.upper().strip()
            if t and t not in existing:
                portfolio["stocks"].append({
                    "ticker": t,
                    "market": "",
                    "added_date": today,
                })
                existing.add(t)
                count += 1

        if count > 0:
            _save_portfolio(portfolio)
    return count


def check_stocks(stocks: list[dict], scan_results: list[dict]) -> list[dict]:
    """
    Prueft Warnzeichen fuer jede gehaltene Aktie anhand der Scan-Ergebnisse.

    Args:
        stocks: Liste aus list_stocks()
        scan_results: Vollstaendige Scan-Ergebnisse aus analyze_ticker()

    Returns:
        Liste mit Reports pro Aktie inkl. Warnungen und Empfehlung.
    """
    # Scan-Ergebnisse nach Ticker indizieren (BOM-sichere Key-Bereinigung)
    def _clean(d):
        return {k.lstrip("\ufeff"): v for k, v in d.items()}
    scan_results = [_clean(r) for r in scan_results if r]
    result_map = {r["ticker"]: r for r in scan_results if "ticker" in r}

    def _portfolio_result(stock: dict) -> dict | None:
        """Fallback fuer gehaltene Aktien, die wegen Scanner-Filtern nicht im CSV gelandet sind."""
        try:
            from stock_scanner import analyze_ticker
            return analyze_ticker(stock["ticker"], stock.get("market", ""), enforce_liquidity=False)
        except Exception:
            return None

    reports = []
    for stock in stocks:
        ticker = stock["ticker"]
        result = result_map.get(ticker)

        if result is None:
            result = _portfolio_result(stock)

        # Aktie im Portfolio aber nicht gescannt -> ueberspringe mit Hinweis
        if result is None:
            reports.append({
                "ticker": ticker,
                "market": stock.get("market", ""),
                "price": None,
                "pct_change": None,
                "warnings": ["Keine Scan-Daten verfuegbar"],
                "warning_count": 0,
                "recommendation": "KEINE DATEN",
                "rec_color": "gray",
                "longterm_score": None,
                "longterm_label": None,
                "details": {},
            })
            continue

        # Longterm-Details aus dem Scan-Ergebnis (ggf. JSON-String aus CSV)
        lt_details = result.get("longterm_details", {})
        if isinstance(lt_details, str):
            import json as _json
            try:
                lt_details = _json.loads(lt_details.replace("'", '"'))
            except Exception:
                lt_details = {}

        warnings = []

        # 1. SMA200 gebrochen
        sma200_status = lt_details.get("sma200", "neutral")
        if sma200_status == "SELL":
            warnings.append("SMA200 unterschritten")

        # 2. Death Cross (SMA50 < SMA200)
        golden_cross = lt_details.get("golden_cross", "neutral")
        if golden_cross == "SELL":
            warnings.append("Death Cross (SMA50 < SMA200)")

        # 3. RSI ueberkauft (>75)
        rsi_val = result.get("rsi", "-")
        if isinstance(rsi_val, (int, float)) and rsi_val > 75:
            warnings.append(f"RSI ueberkauft ({rsi_val:.0f})")

        # 4. MACD negativ & fallend
        momentum = lt_details.get("momentum", "neutral")
        if momentum == "bearish":
            warnings.append("MACD negativ (Momentum bearish)")

        # 5. Kein Trend (ADX < 20)
        adx_val = result.get("adx", 0)
        if isinstance(adx_val, (int, float)) and adx_val < 20:
            warnings.append(f"Kein Trend (ADX {adx_val:.0f})")

        # 6. Volumen-Einbruch
        volume_trend = lt_details.get("volume_trend", "neutral")
        if volume_trend == "SELL":
            warnings.append("Volumen-Einbruch (Akkumulation ruecklaeufig)")

        # 7. Weit vom 52W-Hoch (>25%)
        week52_str = lt_details.get("week52", "+0.0%")
        try:
            pct_from_high = float(week52_str.replace("%", "").replace("+", ""))
            if pct_from_high < -25:
                warnings.append(f"Weit vom 52W-Hoch ({week52_str})")
        except (ValueError, AttributeError):
            pass

        # Empfehlung ableiten
        n_warn = len(warnings)
        if n_warn <= 1:
            recommendation = "HALTEN \u2014 Alles im gr\u00fcnen Bereich"
            rec_color = "green"
        elif n_warn == 2:
            recommendation = "BEOBACHTEN \u2014 Leichte Schw\u00e4che"
            rec_color = "orange"
        else:
            recommendation = "VERKAUF PR\u00dcFEN \u2014 Mehrere Warnsignale"
            rec_color = "red"

        reports.append({
            "ticker": ticker,
            "name": result.get("name", ticker),
            "market": result.get("market", stock.get("market", "")),
            "price": result.get("price"),
            "pct_change": result.get("pct_change"),
            "warnings": warnings,
            "warning_count": n_warn,
            "recommendation": recommendation,
            "rec_color": rec_color,
            "longterm_score": result.get("longterm_score"),
            "longterm_label": result.get("longterm_label"),
            "details": lt_details,
        })

    return reports


# ═══════════════════════════════════════════════════════════════════════════════
# CLI (Standalone-Ausfuehrung)
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        stocks = list_stocks()
        if not stocks:
            print("Keine Aktien im Portfolio.")
        else:
            print(f"\nInvestment-Portfolio ({len(stocks)} Aktien):")
            for s in stocks:
                print(f"  {s['ticker']:10s}  {s.get('market', '')}")
    elif sys.argv[1] == "add" and len(sys.argv) >= 3:
        ok = add_stock(sys.argv[2])
        print(f"{'Hinzugefuegt' if ok else 'Bereits vorhanden'}: {sys.argv[2].upper()}")
    elif sys.argv[1] == "remove" and len(sys.argv) >= 3:
        ok = remove_stock(sys.argv[2])
        print(f"{'Entfernt' if ok else 'Nicht gefunden'}: {sys.argv[2].upper()}")
    elif sys.argv[1] == "import" and len(sys.argv) >= 3:
        tickers = [t.strip().upper() for t in sys.argv[2].split(",") if t.strip()]
        count = import_stocks(tickers)
        print(f"{count} Aktien importiert (von {len(tickers)} angegeben)")
    else:
        print("Verwendung: python3 investment_portfolio.py [add TICKER|remove TICKER|import T1,T2,...]")
