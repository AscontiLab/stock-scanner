# Stock Scanner

Taeglicher Aktien-Scanner fuer kurzfristige Trading-Signale (1-5 Tage Horizont) auf Basis technischer Indikatoren. Scannt ~667 Ticker aus 7 Indizes, bewertet sie anhand von 9 Indikatoren und generiert Kauf-/Verkaufsignale sowie CFD-Setups mit ATR-basierten Levels.

---

## Ueberblick

```
                    ┌─────────────────────┐
                    │   stock_scanner.py   │
                    │                      │
  Ticker-Listen ───>│  1. Ticker laden     │
  (Wikipedia,       │  2. yfinance-Daten   │
   Fallback)        │  3. Indikatoren      │
                    │  4. Scoring           │
                    │  5. CFD-Filter        │
                    │  6. HTML/CSV erzeugen │
                    └──────┬──────┬────────┘
                           │      │
              ┌────────────┘      └────────────┐
              v                                v
     ┌─────────────────┐            ┌────────────────────┐
     │  send_report.py │            │ post_to_dashboard.py│
     │  (Gmail SMTP)   │            │ (n8n Webhook)       │
     └─────────────────┘            └────────────────────┘
              │                                │
              v                                v
        E-Mail-Report                 n8n Stock Dashboard
                                  (agents.umzwei.de)

     ┌──────────────────┐
     │ cfd_backtesting.py│
     │ (SQLite Tracking) │
     └──────────────────┘
```

---

## Indizes und Ticker

| Index | Quelle | ca. Ticker |
|-------|--------|------------|
| NASDAQ 100 | Wikipedia / Fallback | 100 |
| S&P 500 | Wikipedia / Fallback | 500 |
| DAX 40 | Wikipedia / Fallback | 40 |
| Euro Stoxx 50 | Wikipedia / Fallback | 50 |
| TecDAX | Wikipedia / Fallback | 30 |
| MDAX | Wikipedia / Fallback | 50 |
| SDAX | Wikipedia / Fallback | 70 |

Ticker werden dedupliziert (ein Ticker kann in mehreren Indizes vorkommen). Nur Ticker mit einem 20-Tage-Durchschnittsvolumen >= 500.000 werden analysiert.

---

## Indikatoren

### Hauptscan (Mean Reversion, 9 Indikatoren)

| Indikator | Buy-Signal | Sell-Signal |
|-----------|------------|-------------|
| **RSI (14)** | < 30 (ueberverkauft) | > 70 (ueberkauft) |
| **MACD (12/26/9)** | Histogram kreuzt ueber 0 | Histogram kreuzt unter 0 |
| **SMA 20/50 + EMA 9/21** | Price > SMA20 > SMA50 oder EMA-Cross | Price < SMA20 < SMA50 oder EMA-Cross |
| **Bollinger Bands (20,2)** | Price < unteres Band (+ Squeeze) | Price > oberes Band |
| **Volumen** | Ratio > 1.5x bei positiver Aenderung | Ratio > 1.5x bei negativer Aenderung |
| **Candlestick-Muster** | Hammer, Morning Star, Engulfing (bullish) | Shooting Star, Evening Star, Engulfing (bearish) |
| **VWAP (20 Tage)** | Price > VWAP | Price < VWAP |
| **Squeeze Momentum** | Squeeze loest sich bullish auf | Squeeze loest sich bearish auf |
| **Fear & Greed Index** | CNN Fear & Greed (Kontextinfo im Report) | — |

**Scoring:** Jeder Indikator gibt +1 (Buy) oder -1 (Sell). Net Score = Buy - Sell. Signal bei |Score| >= 4.

### CFD-Scan (Trend Following, gewichtetes Scoring)

Der CFD-Scan verwendet ein separates gewichtetes Scoring-System mit strengeren Filtern:

| Kriterium | Gewicht | Beschreibung |
|-----------|---------|--------------|
| **ADX + DI-Bestaetigung** | 2.0 | ADX > 30 UND +DI > -DI (Long) bzw. -DI > +DI (Short) |
| **MA-Struktur** | 1.5 | Price > SMA20 > SMA50 (Long) bzw. umgekehrt (Short) |
| **EMA 9/21 Stack** | 1.5 | EMA9 > EMA21 (Long) bzw. EMA9 < EMA21 (Short) |
| **MACD Histogram** | 1.0 | Positiv und steigend (Long) bzw. negativ und fallend (Short) |
| **RSI in Zone** | 1.0 | 45-62 (Long) bzw. 38-55 (Short) |
| **Volume Ratio** | 0.5 | >= 1.2x Durchschnitt |
| **Kein Gap > 5%** | 0.5 | Max. Tages-Move der letzten 5 Tage < 5% |

**Basis-Score: max. 8.0**

Zusaetzlich gibt es **Bonus-Punkte** (bis +2.0):

| Bonus | Punkte | Bedingung |
|-------|--------|-----------|
| Trend-Reife | +0.5 | MA-Struktur >= 5 Tage gehalten |
| Hohes Volumen | +0.5 | Volume Ratio >= 2.0x |
| Starker ADX | +0.5 | ADX > 40 |
| Squeeze-Fire | +0.5 | Squeeze loest sich in Trendrichtung auf |

**Gesamt-Score: max. 10.0** — Signal bei Score >= 5.0

### CFD-Qualitaetsfilter

Zusaetzlich zum Score-Threshold muessen CFD-Signale folgende Filter bestehen:

| Filter | Beschreibung | Zweck |
|--------|--------------|-------|
| **+DI/-DI Richtung** | Long nur bei +DI > -DI, Short nur bei -DI > +DI | Verhindert Signale gegen die Trendrichtung |
| **Exklusive Richtung** | Wenn Long UND Short >= Threshold: nur staerkere behalten | Verhindert widersprüchliche Signale |
| **Trend-Reife** | MA-Struktur muss min. 3 Tage gehalten haben | Filtert One-Day-Spikes |
| **ATR-Qualitaet** | ATR% muss zwischen 1.0% und 8.0% liegen | Zu enge Stops (< 1%) und extrem volatile Werte (> 8%) raus |
| **Top-N Cap** | Max. 10 Long + 10 Short Signale | Fokus auf die besten Setups |

### ATR-basierte Stop/Target-Levels

| Level | Berechnung | R/R |
|-------|-----------|-----|
| **Stop Loss** | Entry +/- 1.5 x ATR | — |
| **Take Profit 1** | Entry +/- 1.5 x ATR | 1:1 |
| **Take Profit 2** | Entry +/- 4.0 x ATR | 2.67:1 |

Alle Multiplikatoren sind in `scanner_config.yaml` konfigurierbar.

---

## Dateien

```
stock-scanner/
├── stock_scanner.py        # Hauptscript: Scan, Analyse, HTML/CSV-Generierung
├── scanner_config.yaml     # Konfiguration: alle Schwellenwerte und Gewichte
├── cfd_backtesting.py      # CFD-Backtesting: SQLite-Tracking + CLI
├── post_to_dashboard.py    # n8n Dashboard-Push (Webhook)
├── send_report.py          # E-Mail-Versand (Gmail SMTP)
├── run_scanner.sh          # Cron-Wrapper-Script
├── .gitignore
├── README.md
├── output/                 # (generiert) Tages-Output
│   └── YYYY-MM-DD/
│       ├── trading_signals.html
│       ├── trading_signals.csv
│       └── cfd_setups.csv
├── logs/                   # (generiert) Log-Dateien
│   └── scanner_YYYY-MM-DD.log
└── cfd_backtesting.db      # (generiert) SQLite Backtesting-DB
```

---

## Installation

### Voraussetzungen

- Python 3.10+
- pip-Pakete:

```bash
pip install yfinance pandas numpy pyyaml tqdm requests
```

(`tqdm` ist optional — ohne wird kein Fortschrittsbalken angezeigt.)

### Gmail-Credentials

Fuer den E-Mail-Versand: Datei `~/.stock_scanner_credentials` anlegen (chmod 600):

```
GMAIL_USER=maikstephan.lab@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
GMAIL_RECIPIENT=empfaenger@example.com
```

Das App-Passwort wird in den Google-Account-Einstellungen unter "Sicherheit > App-Passwoerter" erstellt.

---

## Ausfuehrung

### Manuell

```bash
# Vollstaendiger Scan (oeffnet HTML im Browser)
python3 stock_scanner.py

# Scan ohne Browser-Oeffnung (fuer Server / SSH)
python3 stock_scanner.py --no-open

# Smoke-Test ohne API-Calls (prueft Syntax + Config)
python3 stock_scanner.py --dry-run
```

### Automatisch (Cron)

Der Scanner laeuft automatisch Mo-Fr um 22:30 UTC (23:30 MEZ, nach US-Boersenschluss):

```bash
# Crontab-Eintrag:
30 22 * * 1-5 /home/claude-agent/stock-scanner/run_scanner.sh
```

`run_scanner.sh` uebernimmt:
1. Scanner ausfuehren mit Logging
2. E-Mail-Report senden (bei Erfolg)
3. Alte Logs (> 30 Tage) aufraumen

### E-Mail manuell senden

```bash
python3 send_report.py
```

Sucht automatisch den HTML-Report im aktuellen Tages-Ordner (`output/YYYY-MM-DD/`) und haengt die CSV als Anhang an.

---

## Konfiguration (`scanner_config.yaml`)

Alle Schwellenwerte sind in einer YAML-Datei externalisiert. Wenn die Datei fehlt, greift der Scanner auf eingebaute Defaults zurueck.

### Struktur

```yaml
cfd:
  adx_min: 30              # Mindest-ADX fuer CFD-Signal
  adx_strong: 40           # Bonus ab ADX > 40
  rsi_long_min: 45         # RSI-Zone Long (Minimum)
  rsi_long_max: 62         # RSI-Zone Long (Maximum)
  rsi_short_min: 38        # RSI-Zone Short
  rsi_short_max: 55
  atr_pct_min: 1.0         # ATR-Gate: Minimum (% vom Kurs)
  atr_pct_max: 8.0         # ATR-Gate: Maximum
  trend_maturity_min_days: 3  # Min. Tage MA-Struktur
  vol_ratio_min: 1.2       # Mindest-Volumen-Ratio
  atr_stop_mult: 1.5       # Stop-Loss = Entry +/- X * ATR
  atr_tp1_mult: 1.5        # Take Profit 1
  atr_tp2_mult: 4.0        # Take Profit 2
  top_n: 10                # Max. Signale pro Richtung

scoring:
  weights:                 # Gewichte fuer CFD-Score (max 8.0)
    adx_di: 2.0
    ma_structure: 1.5
    ema_stack: 1.5
    macd: 1.0
    rsi_zone: 1.0
    volume: 0.5
    no_gap: 0.5
  bonus:                   # Bonus-Punkte (max +2.0)
    trend_maturity_days: 5
    trend_maturity_pts: 0.5
    vol_ratio_high: 2.0
    vol_ratio_pts: 0.5
    adx_strong: 40
    adx_strong_pts: 0.5
    squeeze_fire_pts: 0.5
  threshold: 5.0           # Mindest-Score fuer CFD-Signal
  max_score: 10.0

main_scan:
  min_score: 4             # |net_score| >= 4 fuer Hauptsignal
  max_gap_pct: 3.0

backtesting:
  db_file: "cfd_backtesting.db"
  resolve_after_days: 1    # Frueheste Aufloesung
  resolve_max_days: 10     # Spaeteste Aufloesung
  enabled: true
```

---

## CFD Backtesting

Das Backtesting-Modul trackt jedes CFD-Signal in einer SQLite-Datenbank und loest es spaeter automatisch auf.

### Wie es funktioniert

1. **Logging:** Bei jedem Scanner-Lauf werden alle CFD-Signale (Ticker, Richtung, Score, Entry/Stop/TP-Levels, Indikator-Snapshot) in die DB geschrieben.
2. **Resolution:** Nach 1-10 Trading-Tagen wird per yfinance geprueft, welches Level zuerst getroffen wurde:
   - **Stop** getroffen → pnl_r = -1.0 R
   - **TP1** getroffen → pnl_r = +1.0 R
   - **TP2** getroffen → pnl_r = +2.67 R
   - **Expired** (nach 10 Tagen kein Level) → pnl_r berechnet aus Schlusskurs
3. **Analyse:** Win-Rate, durchschnittlicher R-Wert, Aufschluesselung nach Markt und Richtung.

### CLI-Befehle

```bash
# Zusammenfassung: Win-Rate, Avg R, Total R, nach Markt/Richtung
python3 cfd_backtesting.py summary

# Offene (noch nicht aufgeloeste) Signale anzeigen
python3 cfd_backtesting.py open

# Offene Signale per yfinance aufloesen
python3 cfd_backtesting.py resolve
```

### Beispiel-Ausgabe `summary`

```
  CFD BACKTESTING SUMMARY

  Gesamt:     42 Signale
  Gewonnen:   23  (54.8%)
  Verloren:   19
  Avg R:      +0.34
  Total R:    +14.28
  Avg MFE:    1.82 R
  Avg MAE:    0.67 R

  Richtung     Anzahl    Win%     Avg R
  long             28   57.1%    +0.41
  short            14   50.0%    +0.21

  Markt           Anzahl    Win%     Avg R
  S&P 500             18   55.6%    +0.38
  NASDAQ 100          12   58.3%    +0.45
  DAX 40               8   50.0%    +0.15
```

### DB-Schema

**`cfd_scan_runs`** — ein Eintrag pro Scanner-Lauf:
- `scan_date`, `fear_greed`, `ticker_count`, `long_signals`, `short_signals`

**`cfd_signals`** — ein Eintrag pro CFD-Signal:
- Identifikation: `ticker`, `market`, `direction`
- Scoring: `quality_score`, `adx`, `plus_di`, `minus_di`, `rsi`, `vol_ratio`
- Levels: `entry_price`, `stop_price`, `tp1_price`, `tp2_price`
- Resolution: `outcome` (stop/tp1/tp2/expired), `pnl_r`, `max_favorable`, `max_adverse`

---

## n8n Dashboard

Der Scanner pusht Ergebnisse automatisch an ein n8n-Dashboard.

| Workflow | ID | Endpoint |
|----------|-----|---------|
| Stock – Empfang | `gzG58s6HkDnqT34L` | `POST /webhook/stock-update` |
| Stock – Dashboard | `Y4DA5bzf1FMF3JnS` | `GET /webhook/stock-dashboard` |

### Ablauf

1. `stock_scanner.py` ruft am Ende `post_to_dashboard.py` auf
2. JSON-Payload (Top-10 Buy/Sell, Top-10 CFD Long/Short, Fear & Greed) wird an n8n gesendet
3. n8n "Empfang"-Workflow speichert Daten als JSON-Datei
4. n8n "Dashboard"-Workflow generiert live eine HTML-Seite aus der gespeicherten JSON

### Dashboard-Ansicht

Dark-Theme mit Gold-Akzenten, zeigt:
- Fear & Greed Index Badge
- Kaufsignale (Top 10) mit Score, RSI, MACD, Kurs
- Verkaufsignale (Top 10)
- CFD Setups mit gewichtetem Score, ADX, Entry/Stop/TP2, RVOL

---

## Output-Formate

### HTML-Report (`trading_signals.html`)

Vollstaendiger Report mit:
- Zusammenfassung (Anzahl Signale, staerkstes Signal, Durchschnitts-Score)
- Kaufsignal-Tabelle (sortiert nach Score)
- Verkaufsignal-Tabelle
- CFD-Setup-Tabelle mit Score, Richtung, Levels, R/R, ATR%, Gap, RVOL

### CSV-Export (`trading_signals.csv`)

Alle Signale als flache CSV mit allen Indikator-Werten. Geeignet fuer Import in Excel oder weitere Analyse.

### CFD-CSV (`cfd_setups.csv`)

Nur CFD-Signale mit Richtung, Score, Entry/Stop/TP-Levels und allen Filterkriterien.

---

## Architektur-Entscheidungen

### Zwei Scan-Strategien in einem Script

| | Hauptscan | CFD-Scan |
|---|-----------|----------|
| **Strategie** | Mean Reversion | Trend Following |
| **Scoring** | Einfach (+-1 pro Indikator) | Gewichtet (0-10, mit Bonus) |
| **Horizont** | 1-5 Tage | 1-10 Tage |
| **Filter** | Score >= 4, Gap <= 3% | Score >= 5.0, DI-Bestaetigung, Trend-Reife, ATR-Gate |
| **Output** | Kauf-/Verkaufsignale | Long/Short mit Entry/Stop/TP |

Beide nutzen dieselben yfinance-Daten und Indikator-Berechnungen — es wird nur einmal pro Ticker heruntergeladen.

### Config externalisiert

Alle Schwellenwerte in `scanner_config.yaml`, damit Anpassungen ohne Code-Aenderung moeglich sind. Fallback auf eingebaute Defaults, falls die Datei fehlt.

### Backtesting als separates Modul

`cfd_backtesting.py` ist bewusst ein eigenstaendiges Modul (nicht Teil von `stock_scanner.py`), damit es unabhaengig testbar ist und per CLI verwendet werden kann. Die Integration in den Scanner ist minimal (~10 Zeilen in `main()`).

---

## Typischer Workflow

```
22:30 UTC  ─── Cron startet run_scanner.sh
                │
                ├── stock_scanner.py laeuft (~4-6 Min)
                │   ├── Ticker laden (Wikipedia / Fallback)
                │   ├── ~667 Ticker analysieren (yfinance)
                │   ├── Signale filtern + CFD-Setups
                │   ├── HTML/CSV erzeugen
                │   ├── Backtesting: Signale loggen + alte aufloesen
                │   └── Dashboard-Push an n8n
                │
                └── send_report.py sendet E-Mail
                    └── HTML als Body, CSV als Anhang

Naechster Tag:
    python3 cfd_backtesting.py resolve   # Ergebnisse pruefen
    python3 cfd_backtesting.py summary   # Statistik anschauen
```

---

## Fehlerbehandlung

- **yfinance-Fehler** (Netzwerk, ungueltige Ticker): werden geloggt in `logs/scan_errors.log`, Ticker wird uebersprungen
- **Config-Fehler** (YAML-Syntax): Fallback auf eingebaute Defaults, Warnung im Terminal
- **Dashboard-Push-Fehler**: wird abgefangen, Scanner laeuft weiter
- **Backtesting-Fehler**: wird abgefangen ("nicht kritisch"), Scanner laeuft weiter
- **E-Mail-Fehler**: wird von `run_scanner.sh` geloggt, Exit-Code bleibt 0 vom Scanner

---

## Lizenz

Privates Projekt — nicht zur oeffentlichen Nutzung bestimmt.
