# Stock Scanner

## Ueberblick

Taeglicher Aktien- und CFD-Scanner fuer kurzfristige Trading-Signale. Das System bewertet ein grosses Aktienuniversum anhand technischer Indikatoren, erzeugt HTML/CSV-Reports und fuehrt CFD-Backtesting sowie Portfoliologik.

## Zweck

- Aktien- und CFD-Setups systematisch finden
- Technische Signale anhand konfigurierbarer Regeln bewerten
- Ergebnisse in Reports, Dashboard-Feeds und Backtests ueberfuehren
- Laufende Positionen und historische Signalqualitaet nachhalten

## Bestandteile

- `stock_scanner.py`
  - Hauptscanner fuer Indikatoren, Signale und Reports
  - Fear & Greed Contrarian-Multiplikator auf CFD-Scores
- `scanner_config.yaml`
  - Schwellenwerte und Gewichtungen
- `cfd_backtesting.py`
  - Persistenz und Auswertung historischer CFD-Signale
- `cfd_portfolio.py`
  - Portfolio-bezogene Logik, Telegram-Alert bei Stop/TP-Hit
- `cfd_api.py`
  - API-nahe Hilfslogik rund um CFD-Setups
- `post_to_dashboard.py`
  - Push an n8n oder Dashboard-Ziele
- `telegram_alerts.py`
  - Telegram Bot API: Signal-Alerts, Position-Alerts, Daily Summary
- `run_scanner.sh`
  - Cron-Wrapper mit Logging und Aufraeumen
- `run_resolve.sh`
  - Auto-Resolve Cron (23:00 UTC Mo-Fr): Backtesting + Portfolio-Check
- `dashboard/`
  - FastAPI Live-Dashboard (Port 8091): Signale, Portfolio, Backtesting

## Voraussetzungen

- Python 3.10+
- Pakete fuer Datenanalyse und Marktfeeds, typischerweise:
  - `yfinance`
  - `pandas`
  - `numpy`
  - `pyyaml`
  - `requests`
  - `tqdm`
  - `fastapi`
  - `uvicorn`
  - `jinja2`
  - `pydantic-settings`

## Einrichtung

```bash
cd /home/claude-agent/stock-scanner
pip install yfinance pandas numpy pyyaml tqdm requests fastapi uvicorn jinja2 pydantic-settings
```

## Konfiguration

Die Scannerlogik wird ueber `scanner_config.yaml` gesteuert. Dort liegen unter anderem:

- CFD-Filter
- ATR-Multiplikatoren
- Scoring-Gewichte
- Thresholds
- Backtesting-Parameter

## Nutzung

Manueller Lauf:

```bash
python3 stock_scanner.py
```

Ohne Browser:

```bash
python3 stock_scanner.py --no-open
```

Smoke-Test:

```bash
python3 stock_scanner.py --dry-run
```

Wrapper:

```bash
bash run_scanner.sh
```

## Output

Typische Artefakte:

- `trading_signals.html`
- `trading_signals.csv`
- `cfd_setups.csv`
- `cfd_backtesting.db`
- `cfd_portfolio.json`
- Logs unter `logs/`

## Betriebshinweise

- Der Wrapper ist auf regelmaessige Cron-Laeufe ausgelegt
- Dashboard-Push und E-Mail-Versand sind im Projekt vorgesehen, teils aber bewusst als Fallback oder deaktiviert markiert
- Fuer reproduzierbare Ergebnisse sollten Scanner-Konfiguration und Datenquellen versioniert zusammen betrachtet werden

## Live-Dashboard

FastAPI-App auf Port 8091 mit drei Seiten:

- **Signale** (`/`) — CFD Long/Short + Buy/Sell, Fear & Greed Badge, +Position Button
- **Portfolio** (`/portfolio`) — Aktive Positionen mit P&L, Empfehlung, Schliessen-Button
- **Backtesting** (`/backtesting`) — Win-Rate, Avg R, Outcome-Verteilung, nach Markt/Richtung

Start:
```bash
python3 -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8091
```

## Telegram-Alerts

Push-Nachrichten bei Score >= 7, Stop/TP-Hit und Daily Summary.
Konfiguration in `.env`:
```
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_CHAT_ID=<chat_id>
```

## TODO — Noch zu konfigurieren

- [ ] **Telegram Bot erstellen** via [@BotFather](https://t.me/BotFather) und Token + Chat-ID in `.env` eintragen
- [ ] **systemd Service aktivieren:**
  ```bash
  sudo cp stock-dashboard.service /etc/systemd/system/
  sudo systemctl enable --now stock-dashboard
  ```
- [ ] **Caddy/Reverse Proxy** fuer Subdomain einrichten (z.B. `stocks.umzwei.de`)
- [ ] **Auto-Resolve Cron** eintragen:
  ```bash
  crontab -e
  # 0 23 * * 1-5 /home/claude-agent/stock-scanner/run_resolve.sh
  ```

## Status

Erweiterter Trading-Scanner mit Signalbewertung, Backtesting, Portfoliologik, Live-Dashboard und Telegram-Alerts.
