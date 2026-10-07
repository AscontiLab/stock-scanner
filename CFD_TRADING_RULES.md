# CFD-Swing-Handelssystem — Regelwerk v1

> Status: **verbindlich** (abgenommen 2026-05-19). Lehrgeld-Konto Revolut (~US$366).
> Stil: Swing (Tage), Basis = EOD-Scan `cfd_setups.csv`. Quelle der Schwellen:
> `scanner_config.yaml` (backtest-optimiert auf 119 aufgelöste Signale).

## 0 · Philosophie

Das Konto ist **zu klein für echtes Risk-Management** — das ist die Lektion, nicht der
Mangel. Positionsgröße ist nicht steuerbar (1 Position bindet ~92 % Kapital; 1 %
Risiko < Commission). Steuerbar sind **Selektivität, Entry-Timing, Exit-Disziplin,
Fee-Bewusstsein**. Bewertet wird der *Prozess*, nicht das Ergebnis.

## 1 · Signalquelle

`cfd_setups.csv` aus dem EOD-Scan (Mo–Fr 22:30 UTC). System listet Top 5 long +
Top 5 short ab Score 5,0. Es wird **nur eine strengere Teilmenge** gehandelt.

## 2 · Kandidaten-Filter (strenger als System-Default)

| Kriterium | Regel | Begründung |
|---|---|---|
| Score | **≥ 7,0** | Backtest-Sweetspot 7–7,9 (schlägt 8+) |
| ADX | **30–42** | 76 % Win bei 35–39; > 45 überreif → skip |
| RSI | long 45–62 / short 38–55 | `scanner_config.yaml` |
| Richtung | **Long bevorzugt** | Shorts schwächer (Bias −0,4, Cap 7,5) |
| Gap | < 4 % | ab 4 % kippt die Performance |
| **Earnings** | nächster Termin **> 5 Kalendertage** entfernt | Swing über Earnings = Gap-Risiko, das kein Stop auffängt. Scanner setzt `earnings_gate`/`next_earnings` automatisch (yfinance) für Setup-Ticker |

## 3 · Entry — „nicht zu spät"

**a) Setup-Frische:** Entry nur, wenn der Ticker **Tag 1 oder 2** in
`cfd_setups.csv` für diese Richtung steht (Historie: `output/<DATUM>/cfd_setups.csv`).
Ab Tag 3+ in Folge → Trend gelaufen → **skip**.

**b) Entry-Zone, kein Market-Buy:** Limit-Order in
`[Setup-Preis − 0,5×ATR … Setup-Preis + 0,5×ATR]`.
Liegt der Kurs am Folgetag schon **> Setup-Preis + 1×ATR** → R/R kaputt → **skip**.

> STT-Gegenprobe: Setup 05.05. @ 148,68, ATR 3,84 → Zone ≈ 146,8–150,6.
> Kauf 06.05. @ 151,04 = +0,4 über Zone → grenzwertig „schon leicht spät".

## 4 · Sizing

Echtes %-Risk nicht möglich → Ersatz-Steuerung über Setup-Auswahl:
- **Stop-Distanz ≤ 4 % vom Entry** (max. Verlust ≈ 15 $ ≈ 4 % Konto)
- **ATR% 1–3 %** (verschärft von 1–8 %)
- **Immer nur 1 Position gleichzeitig**

## 5 · Stop & Exit — hart/automatisch

Initial-Stop = `stop_long/short` aus CSV (1,5×ATR), als **echte Stop-Order in
Revolut**, sofort bei Entry. Stop **nur nachziehen, nie lockern.**

| Regel | Auslöser |
|---|---|
| **Break-even** | +1,0×ATR im Plus → Stop auf Entry |
| **TP1** (1,5×ATR) | 50 % schließen + Reststop auf Entry |
| **TP2** (2,0×ATR) | Rest schließen |
| **Setup-Erosion** | Score < 5,0 **ODER** raus aus `cfd_setups.csv` **ODER** MACD dreht + Score fällt |
| **Zeit-Stop** | 7 Handelstage ohne TP1 → schließen |

**Verbindlichkeit:** Setup-Erosion und Zeit-Stop erzeugen einen **Pflicht-Alert
„SCHLIESSEN morgen" — keine Ermessensentscheidung.** Das ist exakt die Disziplin,
die im STT-Fall fehlte (Score 4,5 + raus seit 12.05. + Zeit-Stop 13 > 7 Tage —
drei Trigger ignoriert, weil keine Regel existierte).

## 6 · Fee-Gate (Pflichtrechnung vor jedem Entry)

Kein Pauschalwert mehr — echtes Revolut-CFD-Kostenmodell:

```
Round-Trip-Kosten % = 0,50 %                      (Commission: 0,25 % je Seite)
                     + 0,02 % × Haltetage         (Overnight-Finanzierung¹)
                     ( Fr→Mo zählt 3 Overnight-Tage )

¹ instrumentabhängig (Referenzzins ± Spread). 0,02 %/Tag = empirischer
  Richtwert aus dem realen STT-Statement (0,30 $/Tag auf ~1.661 $).
```

**Regel:** `erwartetes TP1 in %` (= 1,5×ATR ÷ Entry) muss **≥ 3 × Round-Trip-Kosten %**
sein. Sonst ist der Trade vor Einstieg negativ erwartbar → **skip**.

> STT-Gegenprobe: TP1 = 1,5×3,84 ÷ 151 = **3,8 %**. Haltedauer-Annahme bis
> Zeit-Stop (7 Tage): 0,50 % + 0,02 %×7 ≈ **0,64 %** (real wurden es 13 Tage
> → ~0,73 %). 3,8 / 0,64 ≈ **5,9×** → Gate **ok**. STT scheiterte nicht hier,
> sondern am fehlenden Exit — das Fee-Gate hätte den Trade korrekt zugelassen.

**Konsequenz fürs Mini-Konto:** Je länger der Hold, desto höher die Gate-Hürde.
Ein Setup mit knappem TP1 *und* erwartet langer Haltedauer fällt durch — genau
richtig, denn dort frisst die Friction die Edge.

## 7 · Trade-Journal & Wöchentlicher Review

Pro Trade festhalten: Entry-Datum/Kurs · Setup-Tag (Frische) · Score@Entry ·
Stop · Exit-Datum/Kurs · **welcher Exit-Trigger** · PnL netto ·
**Regel befolgt? J/N**. (Deckt zugleich den fehlenden Closed-Trades-Log ab.)

Wöchentlich **nicht das Geld bewerten**, sondern: Wie oft Regel verletzt?
- 0 Verletzungen + Verlust → System-Tuning prüfen
- Verletzungen → Disziplin-Problem

---

## Tägliche Checkliste

**ENTRY (nach EOD-Scan, Ausführung am Folgetag per Limit):**
1. Score ≥ 7,0? ADX 30–42? RSI in Zone? Gap < 4 %?
2. `earnings_gate` = false / nächster Earnings-Termin > 5 Tage?
3. Setup Tag 1 oder 2 (nicht älter)?
4. Kurs in Entry-Zone (≤ Setup-Preis + 1×ATR)?
5. Stop-Distanz ≤ 4 %? ATR% 1–3 %?
6. Fee-Gate: TP1-% ≥ 3× (0,50 % + 0,02 %×Haltetage)?
7. Keine andere Position offen?
→ Nur wenn **alle** ✓: Limit-Order + Stop-Order setzen.

**EXIT (täglich prüfen, solange Position offen):**
1. Score < 5,0 oder raus aus `cfd_setups.csv`? → **SCHLIESSEN morgen**
2. 7 Handelstage ohne TP1? → **SCHLIESSEN morgen**
3. +1×ATR erreicht? → Stop auf Break-even
4. TP1 erreicht? → 50 % zu, Reststop auf Entry

---
*v1 · 2026-05-19 · nächster Schritt (separat): Signal-Engine + Revolut-PDF-Import
+ Closed-Trades-Log, die dieses Regelwerk automatisiert.*
