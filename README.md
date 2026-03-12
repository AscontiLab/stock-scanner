# Stock Scanner

Taeglicher Aktien-Scanner fuer kurzfristige Trading-Signale (1-5 Tage) auf Basis technischer Indikatoren.

## Was es macht

- Scannt ~667 Ticker aus NASDAQ 100, S&P 500, DAX 40, Euro Stoxx 50, TecDAX, MDAX und SDAX
- Berechnet Score aus mehreren Indikatoren und filtert Kauf-/Verkaufsignale
- Erstellt CFD-Setups mit gewichtetem Quality-Score und ATR-basierten Stop/TP-Levels
- Trackt CFD-Signale in SQLite-Backtesting-DB mit automatischer Aufloesung

## Indikatoren

| Indikator | Zweck |
|-----------|-------|
| RSI | Ueberkauft / ueberverkauft |
| MACD | Trendrichtung und Momentum |
| SMA / EMA | Trendstruktur |
| Bollinger Bands | Volatilitaet und Ausbrueche |
| Volumen | Bestaetigung |
| Candlestick-Muster | Umkehrsignale |
| ATR | Positionsgroesse und Levels |
| ADX + DI | Trendstaerke und -richtung (CFD-Filter) |

## Signale

**Hauptscan** (Mean Reversion): Score >= 4 -> Kauf- oder Verkaufsignal

**CFD-Scan** (Trend Following): Gewichteter Score >= 5.0/10.0

Scoring-Gewichte:
| Kriterium | Gewicht |
|-----------|---------|
| ADX + DI-Bestaetigung | 2.0 |
| MA-Struktur | 1.5 |
| EMA9/21 Stack | 1.5 |
| MACD Histogram | 1.0 |
| RSI in Zone | 1.0 |
| Volume Ratio | 0.5 |
| Kein Gap >5% | 0.5 |
| **Bonus** (Trend-Reife, Vol, ADX>40, Squeeze) | bis +2.0 |

Filter:
- +DI/-DI Richtungsbestaetigung
- Exklusive Richtung (kein Long + Short gleichzeitig)
- Trend-Reife >= 3 Tage (MA-Struktur gehalten)
- ATR-Qualitaet: 1.0% - 8.0% vom Kurs
- RSI-Zonen: Long 45-62, Short 38-55
- Top-N Cap: max 10 Long + 10 Short

ATR-Levels: Stop = 1.5xATR | TP1 = 1.5xATR | TP2 = 4.0xATR (2.67:1 R/R)

## Konfiguration

Alle Schwellenwerte in `scanner_config.yaml`. Fallback auf Defaults wenn Datei fehlt.

## Installation

```bash
pip install yfinance pandas numpy pyyaml
```

## Ausfuehrung

```bash
python3 stock_scanner.py              # Vollstaendiger Scan
python3 stock_scanner.py --no-open    # Ohne Browser oeffnen
python3 stock_scanner.py --dry-run    # Smoke-Test ohne API-Calls
```

Automatisch Mo-Fr 22:30 UTC via Cron:

```bash
bash run_scanner.sh
```

## CFD Backtesting

```bash
python3 cfd_backtesting.py summary    # Win-Rate, avg R, nach Markt/Richtung
python3 cfd_backtesting.py open       # Offene Signale anzeigen
python3 cfd_backtesting.py resolve    # Ergebnisse per yfinance aufloesen
```

## Output

```
output/YYYY-MM-DD/
├── trading_signals.html   # HTML-Report mit Kauf-/Verkaufsignalen
├── trading_signals.csv    # Alle Signale als CSV
└── cfd_setups.csv         # CFD-Setups mit Quality-Score
```

## Dashboard

- POST-Empfang: `https://agents.umzwei.de/webhook/stock-update`
- Dashboard-Ansicht: `https://agents.umzwei.de/webhook/stock-dashboard`

## Report per E-Mail

Credentials in `~/.stock_scanner_credentials`:

```
GMAIL_USER=...
GMAIL_APP_PASSWORD=...
GMAIL_RECIPIENT=...
```

```bash
python3 send_report.py
```
