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
- `scanner_config.yaml`
  - Schwellenwerte und Gewichtungen
- `cfd_backtesting.py`
  - Persistenz und Auswertung historischer CFD-Signale
- `cfd_portfolio.py`
  - Portfolio-bezogene Logik
- `cfd_api.py`
  - API-nahe Hilfslogik rund um CFD-Setups
- `post_to_dashboard.py`
  - Push an n8n oder Dashboard-Ziele
- `run_scanner.sh`
  - Cron-Wrapper mit Logging und Aufraeumen

## Voraussetzungen

- Python 3.10+
- Pakete fuer Datenanalyse und Marktfeeds, typischerweise:
  - `yfinance`
  - `pandas`
  - `numpy`
  - `pyyaml`
  - `requests`
  - `tqdm`

## Einrichtung

```bash
cd /home/claude-agent/stock-scanner
pip install yfinance pandas numpy pyyaml tqdm requests
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

## Status

Erweiterter Trading-Scanner mit Signalbewertung, Backtesting und Portfoliologik.
