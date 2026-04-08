# Stock Scanner

## Ueberblick

Taeglicher Aktien- und CFD-Scanner fuer kurzfristige Trading-Signale. Bewertet 667 Ticker aus 7 Indizes (NASDAQ 100, S&P 500, DAX 40, Euro Stoxx 50, TecDAX, MDAX, SDAX) anhand technischer Indikatoren, generiert CFD-Setups mit gewichtetem Scoring und fuehrt automatisches Backtesting durch.

## Architektur

```
stock_scanner.py (Mo-Fr 22:30 UTC)
  ├── 667 Ticker scannen (yfinance)
  ├── Indikatoren: ADX, RSI, MACD, SMA/EMA, Bollinger, ATR, Volume
  ├── Gewichtetes Scoring (0-10, konfigurierbar)
  ├── CFD-Setups: Stop/TP1/TP2 via ATR-Multiplikatoren
  ├── Output: CSV + HTML nach output/YYYY-MM-DD/
  ├── Backtesting-DB: cfd_backtesting.db
  └── Push an n8n Dashboard: /webhook/stock-update

run_resolve.sh (Mo-Fr 23:00 UTC)
  ├── cfd_backtesting.py resolve (Signale aufloesen)
  ├── cfd_portfolio.py check (Stop/TP pruefen, Trailing Stop)
  ├── write_dashboard_data.py (Portfolio + BT an n8n pushen)
  └── Telegram Summary

n8n Dashboard: /webhook/stock-dashboard
  ├── Tab Signale: CFD Long/Short Grid, Buy/Sell, F&G Badge
  ├── Tab Portfolio: Empfehlung, P&L, Trailing-Stop-Bar
  └── Tab Backtesting: Win-Rate, Score-Analyse, MFE/MAE
```

## Dateien

| Datei | Zweck |
|-------|-------|
| `stock_scanner.py` | Hauptscanner: Indikatoren, Scoring, Reports |
| `scanner_config.yaml` | Schwellenwerte, Gewichtungen, ATR-Multiplikatoren |
| `cfd_backtesting.py` | Signal-Tracking, Resolve via yfinance, historischer Import |
| `cfd_portfolio.py` | Aktive Positionen, Trend-Health-Check, Empfehlungen |
| `write_dashboard_data.py` | Portfolio + Backtesting an n8n pushen |
| `post_to_dashboard.py` | Signal-Daten an n8n pushen |
| `telegram_alerts.py` | Telegram: Signal-Alerts, Position-Alerts, Summary |
| `run_scanner.sh` | Cron-Wrapper: Scanner + Dashboard-Push |
| `run_resolve.sh` | Cron-Wrapper: Resolve + Portfolio-Check + Dashboard-Push |
| `cfd_api.py` | REST-API fuer CFD-Operationen |
| `investment_portfolio.py` | Investment-Portfolio Verwaltung |
| `price_cache.py` | Kurs-Cache fuer schnellere Abfragen |
| `utils.py` | Hilfsfunktionen (CSV, Labels, Formatter) |
| `send_report.py` | E-Mail-Versand des HTML-Reports |
| `check_portfolio_json.py` | Portfolio-JSON Validierung |
| `check_stocks_json.py` | Stocks-JSON Validierung |
| `backup_db.sh` | Datenbank-Backup Script |
| `dashboard/` | FastAPI Dashboard (Port 8091, systemd) |

## Scoring

Gewichtetes System (max 10 Punkte):

| Indikator | Gewicht |
|-----------|---------|
| ADX + DI-Bestaetigung | 2.0 |
| MA-Struktur (Price > SMA20 > SMA50) | 1.5 |
| EMA-Stack (EMA9 > EMA21) | 1.5 |
| MACD Histogram Momentum | 1.0 |
| RSI in Zone | 1.0 |
| Volumen-Bestaetigung | 0.5 |
| Kein Gap > 5% | 0.5 |
| **Bonus** (Trend >= 5d, Vol >= 2x, ADX > 40, Squeeze) | +2.0 |

Minimum fuer CFD-Signal: **5.0/10**

ATR-Multiplikatoren: Stop = 1.5x, TP1 = 1.5x, TP2 = 3.0x

## Cron-Schedule

```
30 22 * * 1-5  run_scanner.sh    # Scanner nach US-Marktschluss
 0 23 * * 1-5  run_resolve.sh    # Resolve + Portfolio-Check + Dashboard
```

## Nutzung

```bash
# Manueller Scan
python3 stock_scanner.py
python3 stock_scanner.py --no-open    # ohne Browser
python3 stock_scanner.py --dry-run    # Smoke-Test

# Backtesting
python3 cfd_backtesting.py summary    # Auswertung
python3 cfd_backtesting.py open       # offene Signale
python3 cfd_backtesting.py resolve    # Signale aufloesen
python3 cfd_backtesting.py import     # historische CSVs importieren

# Portfolio
python3 cfd_portfolio.py check        # Positionen pruefen
python3 cfd_portfolio.py add CVX long # Position hinzufuegen
python3 cfd_portfolio.py close CVX    # Position schliessen

# Dashboard-Daten aktualisieren
python3 write_dashboard_data.py       # Portfolio + BT an n8n pushen
```

## Dashboard

Erreichbar unter `https://agents.umzwei.de/webhook/stock-dashboard`

Drei Tabs:
- **Signale**: CFD Long/Short nebeneinander, Gradient Score-Bars, Fear & Greed mit Pulsing, +Position Button
- **Portfolio**: Prominente Empfehlungs-Badge (HALTEN/BEOBACHTEN/SCHLIESSEN), Trailing-Stop-Fortschrittsbalken, Gesamt-P&L, aufklappbare Warnungen
- **Backtesting**: Win-Rate, Avg R, Total R, Score-Bereich-Analyse, nach Richtung/Markt, Outcome-Bars, letzte aufgeloeste Signale

FastAPI-Dashboard laeuft zusaetzlich auf Port 8091 (systemd Service `stock-dashboard`).

## Telegram

Push-Nachrichten bei Score >= 7, Stop/TP-Hit und Daily Summary.

```
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_CHAT_ID=<chat_id>
```

In `.env` konfigurieren.

## Voraussetzungen

Python 3.10+, Pakete: `yfinance`, `pandas`, `numpy`, `pyyaml`, `tqdm`, `requests`, `fastapi`, `uvicorn`, `jinja2`, `pydantic-settings`
