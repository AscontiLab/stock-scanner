"""
HTML-Report-Generierung: Tabellen, Badges, Zusammenfassung, CFD-Sektion.
"""

from utils import fg_label as _fg_label


# ---------------------------------------------------------------------------
# Farb-Mappings
# ---------------------------------------------------------------------------

LONGTERM_HEADERS = [
    "Name", "Ticker", "Market", "Score", "Stärke", "SMA200", "Golden Cross",
    "RSI", "Momentum", "Volatilität", "52W", "Vol-Trend", "Kurs", "% Änderung",
]

CFD_HEADERS = [
    "Ticker", "Markt", "Score", "Richtung", "ADX", "RSI",
    "Einstieg", "Stop (1.5×ATR)", "TP1 (1:1)", "TP2 (2.67:1)",
    "R/R", "ATR%", "Gap 5T", "RVOL", "",
]


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def longterm_score_color(score: float) -> str:
    """Gibt Hintergrundfarbe basierend auf Langfrist-Score zurueck (gruen-Gradient)."""
    if score >= 8.0:
        return "#0b3d20"
    elif score >= 7.0:
        return "#145a32"
    elif score >= 6.0:
        return "#1e8449"
    elif score >= 5.0:
        return "#27ae60"
    return "#eafaf1"


def longterm_score_class(score: float) -> str:
    """CSS-Klasse fuer Langfrist-Score (analog CFD-Scores)."""
    if score >= 8.0:
        return "c-score-best"
    elif score >= 6.5:
        return "c-score-good"
    elif score >= 5.0:
        return "c-score-mid"
    return "c-muted"


def signal_badge(text: str) -> str:
    """Erzeugt ein farbiges HTML-Badge fuer ein Signal."""
    text_lower = text.lower()
    if "buy" in text_lower or "bull" in text_lower or "hammer" in text_lower or "morning" in text_lower:
        cls = "badge badge-buy"
    elif "sell" in text_lower or "bear" in text_lower or "shooting" in text_lower or "evening" in text_lower:
        cls = "badge badge-sell"
    else:
        cls = "badge badge-neutral"
    return f'<span class="{cls}">{text}</span>'


# ---------------------------------------------------------------------------
# Zeilen-Builder
# ---------------------------------------------------------------------------

def build_longterm_row(row: dict) -> str:
    """Baut eine HTML-Tabellenzeile fuer ein Langfrist-Signal."""
    score = row.get("longterm_score", 0)
    label = row.get("longterm_label", "—")
    details = row.get("longterm_details", {})
    bg = longterm_score_color(score)
    score_cls = longterm_score_class(score)
    score_display = f"{score:.1f}/10"

    pct = row.get("pct_change", 0)
    pct_color = "#27ae60" if pct >= 0 else "#e74c3c"
    pct_str = f'<span style="color:{pct_color}">{pct:+.2f}%</span>'

    cells = "".join([
        f'<td class="bold">{row.get("name", row["ticker"])}</td>',
        f'<td class="sm c-muted">{row["ticker"]}</td>',
        f'<td>{row.get("market", "")}</td>',
        f'<td class="tc bold {score_cls}">{score_display}</td>',
        f'<td class="tc">{label}</td>',
        f'<td class="tc">{signal_badge(details.get("sma200", "neutral"))}</td>',
        f'<td class="tc">{signal_badge(details.get("golden_cross", "neutral"))}</td>',
        f'<td class="tc">{details.get("rsi_zone", "-")}</td>',
        f'<td class="tc">{signal_badge(details.get("momentum", "neutral"))}</td>',
        f'<td class="tc">{details.get("volatility", "-")}</td>',
        f'<td class="tc">{details.get("week52", "-")}</td>',
        f'<td class="tc">{signal_badge(details.get("volume_trend", "neutral"))}</td>',
        f'<td class="tr">{row.get("price", "-")}</td>',
        f'<td class="tr">{pct_str}</td>',
    ])
    return f'<tr style="background:{bg}">{cells}</tr>'


def build_longterm_table(rows: list) -> str:
    """Baut die Langfrist-Investments-Tabelle (Top 20)."""
    header_cells = "".join(
        f'<th scope="col">{h}</th>'
        for h in LONGTERM_HEADERS
    )
    body_rows = "\n".join(build_longterm_row(r) for r in rows[:20])
    return f"""
<h2 class="section-title">📈 LANGFRIST-INVESTMENTS ({len(rows)} Signale)</h2>
<div class="table-wrap">
<table>
  <thead>
    <tr class="hdr">
      {header_cells}
    </tr>
  </thead>
  <tbody>
    {body_rows}
  </tbody>
</table>
</div>
"""


def build_summary(longterm_rows: list, scan_time: str) -> str:
    """Baut die Zusammenfassungs-Sektion."""
    avg_score = (
        round(sum(r.get("longterm_score", 0) for r in longterm_rows) / len(longterm_rows), 1)
        if longterm_rows
        else 0
    )
    strongest = (
        max(longterm_rows, key=lambda r: r.get("longterm_score", 0))
        if longterm_rows
        else None
    )
    strongest_html = ""
    if strongest:
        details = strongest.get("longterm_details", {})
        strongest_html = f"""
        <p><b>Staerkstes Signal:</b>
        {strongest["ticker"]} ({strongest.get("name", "")}) — {strongest.get("longterm_label", "")}
        | Score: {strongest.get("longterm_score", 0):.1f}
        | SMA200: {details.get("sma200", "-")}
        | Momentum: {details.get("momentum", "-")}
        | RSI: {details.get("rsi_zone", "-")}
        | 52W: {details.get("week52", "-")}
        | Kurs: {strongest.get("price", "-")}
        | Aenderung: {strongest.get("pct_change", 0):+.2f}%
        </p>
        """
    return f"""
<div class="summary">
  <h2>Zusammenfassung</h2>
  <p>
    <b>Scan-Zeitpunkt:</b> {scan_time} &nbsp;|&nbsp;
    <b>Langfrist-Signale:</b> <span class="c-green bold">{len(longterm_rows)}</span> &nbsp;|&nbsp;
    <b>&#216; Score:</b> {avg_score}
  </p>
  {strongest_html}
</div>
"""


# ---------------------------------------------------------------------------
# CFD-Sektion
# ---------------------------------------------------------------------------

def build_cfd_row(row: dict, direction: str, cfg: dict) -> str:
    """Baut eine CFD-Tabellenzeile."""
    score = row[f"cfd_{direction}_score"]
    if direction == "long":
        stop, tp1, tp2 = row["stop_long"], row["tp1_long"], row["tp2_long"]
        pill_cls, dir_label, bg = "pill pill-long", "LONG ▲", "#eafaf1"
    else:
        stop, tp1, tp2 = row["stop_short"], row["tp1_short"], row["tp2_short"]
        pill_cls, dir_label, bg = "pill pill-short", "SHORT ▼", "#fdedec"

    price  = row["price"]
    risk   = abs(price - stop)
    reward = abs(tp2 - price)
    rr     = reward / risk if risk > 0 else 0

    max_s = cfg["scoring"]["max_score"]
    score_cls = "c-score-best" if score >= 7.0 else "c-score-good" if score >= 6.0 else "c-score-mid" if score >= 5.0 else "c-muted"
    score_display = f"{score:.1f}/{max_s:.0f}"
    gap_html = (
        f'<span class="c-red bold">{row["recent_max_gap"]}% ⚠</span>'
        if row["recent_max_gap"] >= 5
        else f'<span class="c-warn">{row["recent_max_gap"]}%</span>'
        if row["recent_max_gap"] >= 3
        else f'{row["recent_max_gap"]}%'
    )
    di_info = f'+DI={row.get("plus_di", "?")}/−DI={row.get("minus_di", "?")}'
    ticker_esc = row["ticker"].replace("'", "\\'")
    cells = "".join([
        f'<td class="bold">{row["ticker"]}</td>',
        f'<td class="sm">{row["market"]}</td>',
        f'<td class="tc bold {score_cls}">{score_display}</td>',
        f'<td class="tc"><span class="{pill_cls}">{dir_label}</span></td>',
        f'<td class="tc" title="{di_info}">{row["adx"]}</td>',
        f'<td class="tc">{row["rsi"]}</td>',
        f'<td class="tr">{price}</td>',
        f'<td class="tr c-red">{stop}</td>',
        f'<td class="tr c-green">{tp1}</td>',
        f'<td class="tr c-green bold">{tp2}</td>',
        f'<td class="tc bold">{rr:.1f}:1</td>',
        f'<td class="tc">{row["atr_pct"]}%</td>',
        f'<td class="tc">{gap_html}</td>',
        f'<td class="tc">{row.get("rvol_label", "—")}</td>',
        f'<td class="tc">'
        f'<button onclick="addPosition(\'{ticker_esc}\', \'{direction}\')" '
        f'class="btn-add" title="Position übernehmen">+</button></td>',
    ])
    return f'<tr style="background:{bg}">{cells}</tr>'


def build_cfd_table(cfd_long: list, cfd_short: list, cfg: dict) -> str:
    """Baut die komplette CFD-Setups-Tabelle."""
    header_cells = "".join(
        f'<th scope="col">{h}</th>'
        for h in CFD_HEADERS
    )
    rows = [(r, "long") for r in cfd_long] + [(r, "short") for r in cfd_short]
    rows.sort(key=lambda x: x[0][f"cfd_{x[1]}_score"], reverse=True)
    body = "\n".join(build_cfd_row(r, d, cfg) for r, d in rows)
    total_l, total_s = len(cfd_long), len(cfd_short)
    return f"""
<h2 class="section-title">⚡ CFD SETUPS &nbsp;
  <span class="c-green">Long: {total_l}</span> &nbsp;|&nbsp;
  <span class="c-red">Short: {total_s}</span>
</h2>
<p class="c-muted" style="font-size:0.83em">
  Gewichteter Score &ge; {cfg["scoring"]["threshold"]:.0f}/{cfg["scoring"]["max_score"]:.0f} &nbsp;|&nbsp;
  ADX+DI (2.0) · MA-Struktur (1.5) · EMA-Stack (1.5) · MACD (1.0) · RSI-Zone (1.0) · Vol (0.5) · Gap (0.5) + Bonus (max 1.0) · Penalties (ADX>45, Trend>15d) · Short-Cap 7.5 · TP2=2.0×ATR
  &nbsp;|&nbsp; Stop = {cfg["cfd"]["atr_stop_mult"]}×ATR &nbsp;|&nbsp; TP2 = {cfg["cfd"]["atr_tp2_mult"]}×ATR
</p>
<div class="table-wrap">
<table>
  <thead><tr class="hdr-dark">{header_cells}</tr></thead>
  <tbody>{body}</tbody>
</table>
</div>
"""


# ---------------------------------------------------------------------------
# Fear & Greed Badge
# ---------------------------------------------------------------------------

def _fear_greed_badge(fg: dict) -> str:
    """Erzeugt ein HTML-Badge fuer den Fear & Greed Index."""
    value = fg.get("value", 50)
    label = fg.get("label") or _fg_label(value)
    if value <= 20:
        color, bg = "#fff", "#c0392b"
    elif value <= 40:
        color, bg = "#fff", "#e67e22"
    elif value <= 60:
        color, bg = "#fff", "#7f8c8d"
    elif value <= 80:
        color, bg = "#fff", "#1a7a3a"
    else:
        color, bg = "#fff", "#145a32"
    return (
        f'<span style="background:{bg};color:{color};padding:4px 12px;'
        f'border-radius:6px;font-weight:bold;font-size:1.1em">'
        f'Fear &amp; Greed: {value} — {label}</span>'
    )


# ---------------------------------------------------------------------------
# Portfolio-Sektion
# ---------------------------------------------------------------------------

def build_portfolio_section(reports: list) -> str:
    """Erstellt die HTML-Sektion 'Meine Positionen' mit Status und Empfehlungen."""
    if not reports:
        return ""

    rows_html = []
    for r in reports:
        if "error" in r:
            rows_html.append(
                f'<tr><td class="bold">{r["ticker"]}</td>'
                f'<td colspan="10" class="c-red">Fehler: {r["error"]}</td></tr>'
            )
            continue

        # Farben
        pill_cls = "pill pill-long" if r["direction"] == "long" else "pill pill-short"
        dir_label = r["direction"].upper()
        pnl_cls = "c-green" if r["pnl_pct"] >= 0 else "c-red"
        pnl_sign = "+" if r["pnl_pct"] >= 0 else ""
        rec_color = r.get("rec_color", "#7f8c8d")

        # Warnungen als Tooltip
        warn_list = r.get("warnings", [])
        warn_tooltip = " | ".join(warn_list) if warn_list else "Keine Warnungen"
        warn_count = len(warn_list)
        warn_badge = (
            f'<span class="c-green" title="{warn_tooltip}">0</span>'
            if warn_count == 0
            else f'<span class="c-warn" title="{warn_tooltip}">{warn_count}</span>'
            if warn_count <= 2
            else f'<span class="c-red bold" title="{warn_tooltip}">{warn_count}</span>'
        )

        # TP1-Hit Badge
        tp1_badge = ' <span class="c-green" style="font-size:0.8em">TP1</span>' if r.get("tp1_hit") else ""

        # Indikatoren
        ind = r.get("indicators", {})
        ind_html = ""
        if ind:
            ind_html = (
                f'<span class="c-muted" style="font-size:0.75em">'
                f'ADX {ind.get("adx", "?")} | RSI {ind.get("rsi", "?")} | '
                f'MACD {ind.get("macd_hist", "?")}</span>'
            )

        cells = "".join([
            f'<td class="bold">{r["ticker"]}{tp1_badge}</td>',
            f'<td class="tc"><span class="{pill_cls}">{dir_label}</span></td>',
            f'<td class="tr">{r["entry_price"]:.2f}</td>',
            f'<td class="tr bold">{r["current_price"]:.2f}</td>',
            f'<td class="tr {pnl_cls} bold">{pnl_sign}{r["pnl_pct"]:.1f}%</td>',
            f'<td class="tc">{r["days_held"]}d</td>',
            f'<td class="tr c-red">{r["stop_current"]:.2f}</td>',
            f'<td class="tr c-green">{r["tp1"]:.2f}</td>',
            f'<td class="tr c-green">{r["tp2"]:.2f}</td>',
            f'<td class="tc">{warn_badge}</td>',
            f'<td class="bold" style="color:{rec_color}">{r["recommendation"]}</td>',
        ])
        rows_html.append(f'<tr>{cells}</tr>')

        # Warnungen als Detailzeile
        if warn_list:
            warn_details = " &bull; ".join(warn_list)
            rows_html.append(
                f'<tr class="warn-row"><td></td>'
                f'<td colspan="10">'
                f'{warn_details}</td></tr>'
            )

    headers = ["Ticker", "Richtung", "Entry", "Aktuell", "P&L", "Tage",
               "Stop", "TP1", "TP2", "Warn.", "Empfehlung"]
    header_cells = "".join(
        f'<th scope="col">{h}</th>' for h in headers
    )

    return f"""
<h2 class="section-title" style="color:#2c3e50">
  Meine CFD-Positionen &nbsp;
  <span class="c-muted" style="font-size:0.7em">({len(reports)} aktiv)</span>
</h2>
<div class="table-wrap">
<table>
  <thead><tr class="hdr-dark">{header_cells}</tr></thead>
  <tbody>{"".join(rows_html)}</tbody>
</table>
</div>
"""


# ---------------------------------------------------------------------------
# Investment-Portfolio-Sektion
# ---------------------------------------------------------------------------

def build_stock_portfolio_section(stock_reports: list) -> str:
    """Erstellt die HTML-Sektion 'Mein Investment-Portfolio' mit Warnungen und Empfehlungen."""
    if not stock_reports:
        return ""

    rows_html = []
    for r in stock_reports:
        # Preis und Aenderung
        price = r.get("price")
        price_str = f"{price}" if price is not None else "—"
        pct = r.get("pct_change")
        if pct is not None:
            pct_color = "#27ae60" if pct >= 0 else "#e74c3c"
            pct_str = f'<span style="color:{pct_color}">{pct:+.2f}%</span>'
        else:
            pct_str = "—"

        # Langfrist-Score
        lt_score = r.get("longterm_score")
        if lt_score is not None:
            score_cls = longterm_score_class(lt_score)
            score_str = f'<span class="{score_cls} bold">{lt_score:.1f}/10</span>'
        else:
            score_str = "—"

        # Warnungen-Badge
        warn_list = r.get("warnings", [])
        warn_count = r.get("warning_count", len(warn_list))
        warn_tooltip = " | ".join(warn_list) if warn_list else "Keine Warnungen"
        if warn_count <= 1:
            warn_badge = f'<span class="c-green" title="{warn_tooltip}">{warn_count}</span>'
        elif warn_count == 2:
            warn_badge = f'<span class="c-warn" title="{warn_tooltip}">{warn_count}</span>'
        else:
            warn_badge = f'<span class="c-red bold" title="{warn_tooltip}">{warn_count}</span>'

        # Empfehlung
        rec_color = r.get("rec_color", "#7f8c8d")
        recommendation = r.get("recommendation", "—")

        cells = "".join([
            f'<td class="bold">{r.get("name", r["ticker"])}</td>',
            f'<td class="sm">{r["ticker"]}</td>',
            f'<td>{r.get("market", "")}</td>',
            f'<td class="tr">{price_str}</td>',
            f'<td class="tr">{pct_str}</td>',
            f'<td class="tc">{score_str}</td>',
            f'<td class="tc">{warn_badge}</td>',
            f'<td class="bold" style="color:{rec_color}">{recommendation}</td>',
        ])
        rows_html.append(f'<tr>{cells}</tr>')

        # Warnungen als Detailzeile (analog CFD-Portfolio)
        if warn_list:
            warn_details = " &bull; ".join(warn_list)
            rows_html.append(
                f'<tr class="warn-row"><td></td>'
                f'<td colspan="7">'
                f'{warn_details}</td></tr>'
            )

    headers = ["Name", "Ticker", "Market", "Kurs", "% Änderung",
               "Langfrist-Score", "Warn.", "Empfehlung"]
    header_cells = "".join(
        f'<th scope="col">{h}</th>' for h in headers
    )

    return f"""
<h2 class="section-title" style="color:#2c3e50">
  Mein Investment-Portfolio &nbsp;
  <span class="c-muted" style="font-size:0.7em">({len(stock_reports)} Aktien)</span>
</h2>
<div class="table-wrap">
<table>
  <thead><tr class="hdr-dark">{header_cells}</tr></thead>
  <tbody>{"".join(rows_html)}</tbody>
</table>
</div>
"""


# ---------------------------------------------------------------------------
# Haupt-Funktion: Kompletten HTML-Report generieren
# ---------------------------------------------------------------------------

def generate_html(
    longterm_rows: list,
    scan_time: str,
    cfd_long_rows: list | None = None,
    cfd_short_rows: list | None = None,
    fear_greed: dict | None = None,
    position_reports: list | None = None,
    stock_reports: list | None = None,
    cfg: dict | None = None,
) -> str:
    """Generiert den kompletten HTML-Report."""
    # Fallback-Config fuer CFD-Tabelle (wird von main uebergeben)
    if cfg is None:
        cfg = {
            "scoring": {"threshold": 5.0, "max_score": 9.0},
            "cfd": {"atr_stop_mult": 1.5, "atr_tp2_mult": 2.0},
        }

    fg_badge = _fear_greed_badge(fear_greed or {"value": 50, "label": "Neutral"})
    summary = build_summary(longterm_rows, scan_time)
    longterm_table = build_longterm_table(longterm_rows)
    cfd_section = build_cfd_table(cfd_long_rows or [], cfd_short_rows or [], cfg)
    portfolio_section = build_portfolio_section(position_reports or [])
    stock_portfolio_section = build_stock_portfolio_section(stock_reports or [])
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading Signals — {scan_time}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 2rem; background: #f9f9f9; color: #2c3e50 }}
  h1 {{ color: #2c3e50 }}
  /* Tabellen-Grundlagen */
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88em }}
  table td, table th {{ border: 1px solid #ddd; padding: 6px 10px }}
  table tr:hover {{ filter: brightness(0.95) }}
  /* Header-Zeile */
  .hdr {{ background: #2c3e50; color: white }}
  .hdr-dark {{ background: #1a252f; color: white }}
  .hdr th {{ padding: 8px 12px; text-align: left }}
  /* Zell-Ausrichtung */
  .tc {{ text-align: center }}
  .tr {{ text-align: right }}
  .bold {{ font-weight: bold }}
  .sm {{ font-size: 0.85em }}
  .xs {{ font-size: 0.78em }}
  /* Signal-Badge */
  .badge {{ color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.78em; white-space: nowrap }}
  .badge-buy {{ background: #27ae60 }}
  .badge-sell {{ background: #e74c3c }}
  .badge-neutral {{ background: #7f8c8d }}
  /* Richtungs-Pillen */
  .pill {{ color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.85em }}
  .pill-long {{ background: #1a7a3a }}
  .pill-short {{ background: #c0392b }}
  /* Farben */
  .c-green {{ color: #27ae60 }}
  .c-red {{ color: #e74c3c }}
  .c-muted {{ color: #7f8c8d }}
  .c-warn {{ color: #e67e22 }}
  .c-score-best {{ color: #1e8449 }}
  .c-score-good {{ color: #27ae60 }}
  .c-score-mid {{ color: #d68910 }}
  /* Zusammenfassung */
  .summary {{ background: #ecf0f1; padding: 1.5rem; border-radius: 8px; margin-bottom: 1.5rem }}
  .summary h2 {{ margin-top: 0 }}
  /* Portfolio-Warnzeile */
  .warn-row {{ background: #fef9e7 }}
  .warn-row td {{ font-size: 0.8em; color: #7f8c8d; padding: 2px 10px }}
  /* Disclaimer */
  .disclaimer {{ color: #aaa; font-size: 0.8em }}
  .subtitle {{ color: #7f8c8d }}
  .section-title {{ margin-top: 2rem }}
  /* Button */
  .btn-add {{
    background: #1a7a3a; color: white; border: none; border-radius: 4px;
    padding: 4px 10px; cursor: pointer; font-weight: bold; font-size: 1em;
  }}
  .btn-add:hover {{ background: #1e8449 }}
  .btn-add:disabled {{ background: #95a5a6; cursor: default }}
  /* Responsive Tabellen-Wrapper */
  .table-wrap {{ overflow-x: auto }}
</style>
<script>
function addPosition(ticker, direction) {{
  var btn = event.target;
  btn.disabled = true;
  btn.textContent = '...';
  fetch('/api/portfolio/add', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ticker: ticker, direction: direction}})
  }})
  .then(function(r) {{ return r.json() }})
  .then(function(d) {{
    btn.textContent = 'OK';
    btn.style.background = '#1e8449';
  }})
  .catch(function(e) {{
    btn.textContent = '!';
    btn.style.background = '#e74c3c';
    btn.disabled = false;
  }});
}}
</script>
</head>
<body>
<h1>📊 Technical Analysis Stock Scanner</h1>
<p class="subtitle">Datum: {scan_time} &nbsp;|&nbsp; Langfrist-Score &ge; 5.0 &nbsp;|&nbsp; {fg_badge}</p>
{portfolio_section}
{stock_portfolio_section}
{summary}
{longterm_table}
{cfd_section}
<hr>
<p class="disclaimer">
  Nur technische Analyse — keine Anlageberatung. Langfrist-Signale basierend auf 200-Tage-Trends. CFD-Setups: Kurzfristiger Horizont 1–5 Tage.
</p>
</body>
</html>
"""
