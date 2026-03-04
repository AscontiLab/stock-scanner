# Stock Scanner

Täglicher Aktien-Scanner für kurzfristige Trading-Signale (1–5 Tage) auf Basis technischer Indikatoren.

## Was es macht

- Scannt ~667 Ticker aus NASDAQ 100, S&P 500, DAX 40, Euro Stoxx 50, TecDAX, MDAX und SDAX
- Berechnet Score aus mehreren Indikatoren und filtert Kauf-/Verkaufsignale
- Erstellt zusätzlich CFD-Setups mit ATR-basierten Stop/TP-Levels

## Indikatoren

| Indikator | Zweck |
|-----------|-------|
| RSI | Überkauft / überverkauft |
| MACD | Trendrichtung und Momentum |
| SMA / EMA | Trendstruktur |
| Bollinger Bands | Volatilität und Ausbrüche |
| Volumen | Bestätigung |
| Candlestick-Muster | Umkehrsignale |
| ATR | Positionsgröße und Levels |
| ADX | Trendstärke (CFD-Filter) |

## Signale

**Hauptscan** (Mean Reversion): Score ≥ 3 → Kauf- oder Verkaufsignal

**CFD-Scan** (Trend Following): Score ≥ 4/6 → Long/Short Setup
- ATR-basierte Levels: Stop = 1,5×ATR | TP1 = 1,5×ATR | TP2 = 3×ATR (2:1 R/R)
- Filter: ADX > 25, RSI-Zone, MACD, MA-Struktur, Volumen, kein Gap > 5 %

## Installation

```bash
pip install yfinance pandas numpy
```

## Ausführung

```bash
python3 stock_scanner.py
```

Automatisch Mo–Fr 22:30 UTC via Cron:

```bash
bash run_scanner.sh
```

## Output

```
output/YYYY-MM-DD/
├── trading_signals.html   # HTML-Report mit Kauf-/Verkaufsignalen
└── trading_signals.csv    # Alle Signale als CSV
```

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
