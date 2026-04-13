# Stock Scanner

## Ueberblick

Taeglicher Aktien- und CFD-Scanner fuer kurzfristige Trading-Signale. Bewertet 667 Ticker aus 7 Indizes (NASDAQ 100, S&P 500, DAX 40, Euro Stoxx 50, TecDAX, MDAX, SDAX) anhand technischer Indikatoren, generiert CFD-Setups mit gewichtetem Scoring und fuehrt automatisches Backtesting durch.

## Architektur

```
stock_scanner.py (Mo-Fr 22:30 UTC)
  ├── 667 Ticker scannen (yfinance)
  ├── Indikatoren: ADX, RSI, MACD, SMA/EMA, Bollinger, ATR, Volume
  ├── Gewichtetes Scoring (0-10, konfigurierbar, mit lernbasierten Penalties)
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
  ├── Tab Signale: CFD Long/Short Grid, Buy/Sell, F&G Badge, sichtbare Lernregeln pro Setup
  ├── Tab Portfolio: Empfehlung, P&L, Trailing-Stop-Bar
  └── Tab Backtesting: Win-Rate, Score-Analyse, MFE/MAE, Gap-/ATR-Regime und Markt x Richtung
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

Gewichtetes System (max 9 Punkte):

| Indikator | Gewicht |
|-----------|---------|
| ADX + DI-Bestaetigung | 2.0 |
| MA-Struktur (Price > SMA20 > SMA50) | 1.5 |
| EMA-Stack (EMA9 > EMA21) | 1.5 |
| MACD Histogram Momentum | 1.0 |
| RSI in Zone | 1.0 |
| Volumen-Bestaetigung | 0.5 |
| Kein Gap > 5% | 0.5 |
| **Bonus** (Trend >= 5d, Vol >= 2x, Squeeze-Fire) | +1.0 |

Minimum fuer CFD-Signal: **5.0/10**

ATR-Multiplikatoren: Stop = 1.5x, TP1 = 1.5x, TP2 = 2.0x

## Lernschicht / Decision Layer (2026-04-13)

Der Scanner nutzt jetzt nicht nur Backtesting fuer Reporting, sondern spiegelt erste historische Erkenntnisse direkt ins aktuelle CFD-Scoring zurück.

Aktive Regeln:

- **Gap-Penalty**: Setups mit `recent_max_gap >= 4%` werden abgewertet, `>= 6%` deutlich stärker
- **ATR-Regime-Penalty**: hohe Volatilitätsregime (`ATR >= 3%`) werden vorsichtiger bewertet
- **Short-Bias-Penalty**: Short-Setups erhalten einen zusätzlichen Skepsis-Abzug
- **Markt-Adjustments**: schwächere Segmente wie `NASDAQ 100` und `DAX 40` werden gezielt gedämpft

Zusätzlich werden pro CFD-Signal jetzt persistiert:

- `score_components_json` — welche Score-Bausteine/Boni aktiv waren
- `regime_json` — kompaktes Markt-/Volatilitäts-/Gap-Regime

Damit ist aus reinem Backtesting ein erster geschlossener Lernkreislauf geworden: Analyse -> Ergebnis -> Regel -> sichtbarer Einfluss auf neue Setups.

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
- **Signale**: CFD Long/Short nebeneinander, Gradient Score-Bars, Fear & Greed mit Pulsing, +Position Button, Sektor-Heatmap und sichtbare Lernregeln/Rule-Badges pro Setup
- **Portfolio**: Prominente Empfehlungs-Badge (HALTEN/BEOBACHTEN/SCHLIESSEN), Trailing-Stop-Fortschrittsbalken, Gesamt-P&L, aufklappbare Warnungen, Earnings-Banner
- **Backtesting**: Win-Rate, Avg R, Total R, Score-Bereich-Analyse, nach Richtung/Markt, Outcome-Bars, Gap-Regime, ATR-Regime, Markt x Richtung, letzte aufgeloeste Signale

## Sektor-Heatmap (2026-04-09)

- Grid auf der Signale-Seite zeigt Sektor-Performance (avg % Change, RSI, Buy/Sell Ratio)
- Daten via yfinance mit 24h JSON-Cache
- Background-Loading beim ersten Aufruf

## Earnings-Warnung (2026-04-09)

- Orange Banner auf Portfolio- und Stocks-Karten wenn Earnings in den naechsten 5 Tagen anstehen
- 6h In-Memory-Cache
- Nur fuer Portfolio-Aktien, nicht fuer alle gescannten

## Fear & Greed CFD-Filter (2026-04-09)

- Additiver Score-Bonus ±0.5 bei extremem Marktsentiment
- Extreme Fear (<25): Long +0.5, Short -0.5
- Extreme Greed (>75): umgekehrt
- Badge im Dashboard sichtbar

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

`scanner-common` wird als pip-Paket installiert (nicht mehr als lokale Kopie).

## Betriebshinweise

- `run_scanner.sh` nutzt `flock` mit Lock-Datei (`/tmp/stock_scanner.lock`) gegen parallele Laeufe
- `run_resolve.sh` wartet max 30 Minuten auf den Scanner-Lock bevor es startet
- `N8N_BASE_URL` ist per Env-Variable konfigurierbar (Fallback: `agents.umzwei.de`)

## Investment-Portfolio Fallback (2026-04-10)

- Der normale Scanner verwirft illiquide Titel weiterhin fuer **neue Trading-Signale** via `MIN_AVG_VOLUME`
- Fuer gehaltene Aktien im Bereich `/dashboard/stock/stocks` gilt jetzt eine andere Logik:
  - wenn ein Titel nicht in `all_results.csv` auftaucht, wird er fuer die Portfolio-Ansicht direkt nachanalysiert
  - dabei wird der Liquiditaetsfilter bewusst **nicht** erzwungen
- Dadurch erscheinen Bestandswerte wie `VBK.DE` / VERBIO auch dann mit Daten und Warnhinweisen, wenn sie fuer den Signal-Scanner zu illiquide waeren
