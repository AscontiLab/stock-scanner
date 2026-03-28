# Plan: Stock Scanner — Langfrist-Investments & Portfolio

## Requirements Summary

1. **Unternehmensnamen statt Tickerkürzel** — Überall wo bisher nur "BG" steht, soll "Bunge Global SA" stehen
2. **Kauf-/Verkaufsignal-Tabellen entfernen** — Ersetzt durch neue "Langfrist-Investments"-Tabelle
3. **Langfrist-Investment-Scoring** — Neues Scoring auf Basis langfristiger Indikatoren (SMA200, Golden Cross, RSI-Zone, Volatilität, 52W-Nähe)
4. **Investment-Portfolio** — Getrennt von CFD. Aktien hinzufügen/entfernen per CLI. Verkaufswarnungen nur für gehaltene Aktien (ähnlich CFD-Gesundheitscheck)

---

## Acceptance Criteria

- [ ] `name`-Spalte zeigt Company Name (z.B. "Apple Inc") statt Ticker in HTML-Report, CSV, Dashboard
- [ ] Alte Buy/Sell-Tabellen (Score ≥4 / ≤-4) sind aus Report und Dashboard entfernt
- [ ] Neue "Langfrist-Investments"-Tabelle zeigt Top-Kandidaten nach Langfrist-Score
- [ ] `--add-stock AAPL` fügt Aktie zum Investment-Portfolio hinzu
- [ ] `--remove-stock AAPL` entfernt Aktie aus Portfolio
- [ ] `--stocks` zeigt alle gehaltenen Aktien
- [ ] Bestehende Aktien können initial per JSON oder CLI-Batch angegeben werden
- [ ] Portfolio-Sektion im Report zeigt nur gehaltene Aktien mit Warn-Ampel
- [ ] Verkaufswarnung wird nur angezeigt wenn ≥2 Warnsignale vorliegen
- [ ] Scanner-Laufzeit steigt um max. 10% (Name-Lookup gecacht)
- [ ] Dashboard (Port 8091) zeigt die neuen Sektionen statt der alten Buy/Sell-Tabs
- [ ] Bestehende CFD-Funktionalität bleibt 100% unverändert

---

## Implementation Steps

### Schritt 1: Company Name Resolver (neue Datei)
**Datei:** `tickers/name_resolver.py` (neu)

- Beim Wikipedia-Scraping in `tickers/sources.py` bereits vorhandene Tabellen haben oft eine "Company"-Spalte → diese gleich mit-extrahieren und als Dict `{ticker: name}` zurückgeben
- Fallback: `yf.Ticker(symbol).info.get("shortName", ticker)` — aber nur 1x pro Ticker, Ergebnis in SQLite-Cache (`name_cache.db`) speichern mit TTL 30 Tage
- Export: `resolve_name(ticker) -> str` und `bulk_resolve(tickers: list) -> dict[str, str]`
- In `stock_scanner.py:342` ändern: `"name": resolve_name(ticker)` statt `"name": ticker`

### Schritt 2: Langfrist-Investment-Scoring (neue Datei)
**Datei:** `scoring/longterm_scorer.py` (neu)

Berechnet einen Langfrist-Score (0–10) basierend auf:

| Indikator | Gewicht | Logik |
|-----------|---------|-------|
| SMA200-Trend | 2.0 | Kurs > SMA200 |
| Golden Cross | 2.0 | SMA50 > SMA200 |
| RSI-Zone | 1.5 | RSI zwischen 40–65 (nicht überkauft, nicht überverkauft) |
| Momentum | 1.5 | MACD-Histogramm > 0 und steigend |
| Volatilität | 1.0 | ATR% im moderaten Bereich (1–4%) |
| 52W-Stärke | 1.0 | Kurs innerhalb 15% vom 52W-Hoch |
| Volumen-Trend | 1.0 | 20d-Volumen-Schnitt > 50d-Volumen-Schnitt |

- Braucht 200 Tage Daten → `yf.download(period="1y")` statt `90d`
- Funktion: `compute_longterm_score(df, current_price) -> float`
- In `analyze_ticker()` aufrufen und als `"longterm_score"` ins Result-Dict einfügen
- Periode in `stock_scanner.py` von `90d` auf `1y` erhöhen (liefert auch alle bisherigen Indikatoren)

### Schritt 3: Investment Portfolio Manager (neue Datei)
**Datei:** `investment_portfolio.py` (neu)

Analog zu `cfd_portfolio.py`, aber einfacher:

```python
# investment_portfolio.json
{
  "stocks": [
    {"ticker": "AAPL", "added_date": "2026-03-28", "market": "NASDAQ 100"},
    {"ticker": "SAP.DE", "added_date": "2026-03-28", "market": "DAX 40"}
  ]
}
```

- `add_stock(ticker, market=None)` — Fügt Aktie hinzu (Duplikat-Check)
- `remove_stock(ticker)` — Entfernt Aktie
- `list_stocks() -> list[dict]` — Alle gehaltenen Aktien
- `check_stocks(stocks, results) -> list[dict]` — Prüft Warnzeichen für jede gehaltene Aktie

**Warnzeichen-Check** (analog CFD `_check_single_position`):
1. Kurs unter SMA200 (langfristiger Trend gebrochen)
2. Death Cross (SMA50 < SMA200)
3. RSI > 75 (stark überkauft)
4. MACD-Histogramm < 0 und fallend
5. ADX < 20 (kein Trend mehr)
6. Volumen-Einbruch (<0.7x Durchschnitt)
7. Kurs >25% unter 52W-Hoch

Empfehlungen:
- 0–1 Warnungen → "HALTEN" (grün)
- 2 Warnungen → "BEOBACHTEN" (orange)
- 3+ Warnungen → "VERKAUF PRÜFEN" (rot)

### Schritt 4: CLI-Erweiterung
**Datei:** `stock_scanner.py` Zeilen 366–380 (parse_args)

Neue Argumente:
- `--add-stock TICKER` — Aktie zum Portfolio hinzufügen
- `--remove-stock TICKER` — Aktie entfernen
- `--stocks` — Alle gehaltenen Aktien auflisten
- `--import-stocks AAPL,SAP.DE,MSFT` — Batch-Import (kommasepariert)

### Schritt 5: HTML-Report anpassen
**Datei:** `reports/html_report.py`

- `generate_html()` Signatur ändern: `buy_rows`/`sell_rows` ersetzen durch `longterm_rows` und `stock_reports`
- `build_table()` für Buy/Sell entfernen → neue `build_longterm_table()`:
  - Spalten: Name, Ticker, Market, Langfrist-Score, Stärke, SMA200, Golden Cross, RSI, Momentum, Volatilität, 52W-Nähe, Kurs, Veränderung
  - Titel: "📈 LANGFRIST-INVESTMENTS (Top 20)"
  - Grüne Farb-Abstufung nach Score
- Neue `build_stock_portfolio_section()`:
  - Titel: "📊 Mein Investment-Portfolio"
  - Spalten: Name, Ticker, Market, Kurs, Veränderung, Warnungen, Empfehlung
  - Warn-Detail-Zeile (wie bei CFD)
  - Nur sichtbar wenn Portfolio nicht leer
- `build_summary()` anpassen: Langfrist-Signale statt Buy/Sell zählen
- Disclaimer-Text anpassen: "Langfristiger Horizont" statt "Kurzfristiger Horizont 1–5 Tage"

### Schritt 6: Main-Flow anpassen
**Datei:** `stock_scanner.py` ab Zeile 460

- `analyze_ticker()` liefert jetzt auch `longterm_score` und `name`
- Download-Periode von `90d` auf `1y` ändern
- Alte Buy/Sell-Filterung (Zeile 476–479) entfernen
- Neue Langfrist-Filterung: `longterm_rows = sorted([r for r in results if r["longterm_score"] >= 6.0], ...)`
- Investment-Portfolio-Check einbauen (analog CFD-Check, Zeile 523–535)
- CSV-Export anpassen: `trading_signals.csv` enthält jetzt Langfrist-Signale statt Buy/Sell
- `generate_html()` mit neuen Parametern aufrufen

### Schritt 7: Dashboard anpassen
**Datei:** `dashboard/routes/signals.py`

- Buy/Sell-Tabs durch Langfrist-Tab ersetzen
- `_load_signals()` liest `trading_signals.csv` jetzt als Langfrist-Signale
- Entferne `buy_rows`/`sell_rows` Filterung (Zeile 67–71)

**Datei:** `dashboard/templates/signals.html`

- Buy/Sell-Abschnitt durch Langfrist-Tabelle ersetzen

**Neue Route:** `dashboard/routes/stocks.py` (neu)

- `GET /stocks` — Investment-Portfolio-Seite (analog `/portfolio` für CFD)
- `POST /api/stocks/add` — Aktie hinzufügen (vom Dashboard aus)
- `POST /api/stocks/remove` — Aktie entfernen
- `GET /api/stocks/check` — Portfolio-Status als JSON

**Datei:** `dashboard/templates/stocks.html` (neu)

- Portfolio-Karten mit Warn-Ampel (ähnlich CFD-Portfolio-Seite)

### Schritt 8: Telegram Alerts anpassen
**Datei:** `telegram_alerts.py`

- Portfolio-Warnungen bei ≥3 Warnzeichen per Telegram senden
- Daily Summary: Langfrist Top-Signale statt Buy/Sell-Count

---

## Risks & Mitigations

| Risiko | Mitigation |
|--------|-----------|
| yfinance `.info` Call ist langsam (~0.5s pro Ticker) | SQLite-Cache mit 30-Tage-TTL; Wikipedia-Scraping als primäre Quelle |
| 1y statt 90d Download erhöht Laufzeit | Price-Cache (`price_cache.py`) fängt das ab — nur fehlende Tage werden nachgeladen |
| yfinance `.info` liefert manchmal None | Fallback auf Ticker-Symbol wenn kein Name verfügbar |
| Bestehende CFD-Logik könnte brechen | CFD bleibt komplett unangetastet — eigene Dateien, eigene JSON, eigene Routen |

---

## Verification Steps

1. `python3 stock_scanner.py --dry-run` — Report wird generiert ohne Fehler
2. `python3 stock_scanner.py --add-stock AAPL` — Aktie erscheint in `investment_portfolio.json`
3. `python3 stock_scanner.py --stocks` — Liste zeigt AAPL
4. `python3 stock_scanner.py --remove-stock AAPL` — Aktie entfernt
5. Voller Scan: HTML-Report enthält "Langfrist-Investments"-Tabelle mit Company Names
6. HTML-Report enthält KEINE Buy/Sell-Tabellen mehr
7. Portfolio-Sektion zeigt Warnungen für gehaltene Aktien
8. Dashboard unter `:8091` zeigt neue Sektionen
9. `--add-position CVX long` und `--check-positions` funktionieren weiterhin (CFD unverändert)
10. CSV enthält `name`-Spalte mit echten Firmennamen

---

## Reihenfolge

```
Schritt 1 (Name Resolver)
    ↓
Schritt 2 (Langfrist Scoring) ←── kann parallel zu 3
    ↓
Schritt 3 (Portfolio Manager) ←── kann parallel zu 2
    ↓
Schritt 4 (CLI)
    ↓
Schritt 5 (HTML Report)
    ↓
Schritt 6 (Main Flow)
    ↓
Schritt 7 (Dashboard)
    ↓
Schritt 8 (Telegram)
```
