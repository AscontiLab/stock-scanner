"""
Ticker-Quellen: Wikipedia-Scraping fuer Index-Zusammensetzungen mit Fallback-Listen.
"""

import io
import re
import urllib.request

import pandas as pd


# ---------------------------------------------------------------------------
# Fallback-Listen (statisch, falls Wikipedia nicht erreichbar)
# ---------------------------------------------------------------------------

NASDAQ100_FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO",
    "COST", "NFLX", "AMD", "ADBE", "ASML", "QCOM", "INTC", "INTU", "AMAT",
    "CSCO", "TXN", "AMGN", "MU", "ISRG", "BKNG", "LRCX", "MDLZ", "REGN",
    "ADI", "PANW", "KLAC", "MRVL", "CDNS", "SNPS", "PYPL", "SBUX", "GILD",
    "ADP", "CTAS", "ORLY", "PCAR", "MNST", "CHTR", "NXPI", "MELI", "FTNT",
    "WDAY", "CPRT", "PAYX", "EXC", "SIRI", "ODFL", "VRSK", "BIIB", "DLTR",
    "DXCM", "ANSS", "FANG", "FAST", "IDXX", "ILMN", "KDP", "KHC", "LCID",
    "LULU", "MAR", "MCHP", "MRNA", "MTCH", "OKTA", "ROST", "TTWO",
    "VRSN", "VRTX", "XEL", "ZS", "ZM", "TEAM", "CRWD", "DDOG", "SNOW",
    "ABNB", "EBAY", "WBA", "CEG", "ON", "GFS", "ENPH", "ALGN", "GEHC",
    "FSLR", "SWKS", "BMRN", "AKAM", "CTSH",
]

SP500_FALLBACK = [
    "JPM", "UNH", "V", "MA", "LLY", "JNJ", "PG", "HD", "MRK", "ABBV",
    "BAC", "KO", "PEP", "WMT", "CVX", "XOM", "CRM", "ACN", "TMO", "MCD",
    "ABT", "ORCL", "NEE", "DHR", "PM", "IBM", "RTX", "CAT", "HON", "GE",
    "T", "VZ", "CMCSA", "MS", "GS", "BLK", "SCHW", "C", "WFC", "AXP",
    "LOW", "SPGI", "DE", "NKE", "AMAT", "MMM", "UPS", "LMT", "MO", "USB",
    "DUK", "SO", "AEP", "SRE", "D", "PCG", "EXC", "ETR", "AWK", "ES",
    "BMY", "AMGN", "GILD", "REGN", "VRTX", "BIIB", "MRNA", "ILMN",
    "ZTS", "IDXX", "A", "BDX", "BAX", "EW", "ISRG", "IQV", "CI", "HUM",
    "CNC", "MOH", "DVA", "HCA", "UHS", "THC", "ELV", "CVS", "WBA", "CAH",
    "MCK", "ABC", "AmerisourceBergen", "PFE", "MDT", "SYK", "BSX", "ZBH",
    "DXCM", "HAL", "SLB", "BKR", "MPC", "VLO", "PSX", "COP", "PXD", "EOG",
    "DVN", "HES", "MRO", "APA", "FANG", "OXY", "WMB", "OKE", "KMI", "ET",
    "FCX", "NEM", "AA", "X", "NUE", "STLD", "CLF", "MP", "ALB", "SQM",
    "AMT", "PLD", "CCI", "EQIX", "PSA", "EXR", "AVB", "EQR", "MAA", "UDR",
]

DAX40_FALLBACK = [
    "ADS.DE", "AIR.DE", "ALV.DE", "BAS.DE", "BAYN.DE", "BEI.DE", "BMW.DE",
    "BNR.DE", "CON.DE", "1COV.DE", "DHER.DE", "DHL.DE", "DTE.DE", "DTG.DE",
    "ENR.DE", "EOAN.DE", "FRE.DE", "HEI.DE", "HEN3.DE", "IFX.DE", "INL.DE",
    "MBG.DE", "MRK.DE", "MTX.DE", "MUV2.DE", "P911.DE", "PAH3.DE", "QIA.DE",
    "RHM.DE", "RWE.DE", "SAP.DE", "SIE.DE", "SHL.DE", "SY1.DE", "VNA.DE",
    "VOW3.DE", "ZAL.DE", "DBK.DE", "DB1.DE", "HFG.DE",
]

EUROSTOXX50_FALLBACK = [
    # France
    "AI.PA", "AIR.PA", "ACA.PA", "BN.PA", "BNP.PA", "DG.PA", "EL.PA",
    "ENGI.PA", "GLE.PA", "KER.PA", "LR.PA", "MC.PA", "OR.PA", "ORA.PA",
    "RMS.PA", "SAF.PA", "SAN.PA", "SGO.PA", "SU.PA", "TTE.PA",
    # Germany
    "ALV.DE", "BAS.DE", "BAYN.DE", "BMW.DE", "DBK.DE", "DTE.DE",
    "MBG.DE", "MUV2.DE", "RWE.DE", "SAP.DE", "SIE.DE", "VOW3.DE",
    # Netherlands
    "ADYEN.AS", "ASML.AS", "INGA.AS", "PHIA.AS", "PRX.AS", "URW.AS",
    # Spain
    "BBVA.MC", "IBE.MC", "ITX.MC", "SAN.MC",
    # Italy
    "ENEL.MI", "ENI.MI", "STLAM.MI",
    # Belgium
    "ABI.BR",
    # Ireland
    "CRG.IR",
    # Finland
    "NOKIA.HE",
]

TECDAX_FALLBACK = [
    "ADTN.DE", "AIXA.DE", "BC8.DE", "COK.DE", "AFX.DE", "DTE.DE",
    "DRW3.DE", "EVT.DE", "FNTN.DE", "GFT.DE", "IFX.DE", "MUM.DE",
    "NEM.DE", "NDX1.DE", "PNE.DE", "QIA.DE", "RAA.DE", "SAP.DE",
    "SIE.DE", "SHL.DE", "WAF.DE", "S92.DE", "SAX.DE", "TMV.DE",
    "SRT3.DE", "EVD.DE",
]

MDAX_FALLBACK = [
    "BOSS.DE", "LHA.DE", "FRA.DE", "G1A.DE", "HOT.DE", "JUN3.DE",
    "KGX.DE", "KBX.DE", "LXS.DE", "LEG.DE", "PSM.DE", "PUM.DE",
    "G24.DE", "TLX.DE", "TKA.DE", "TUI1.DE", "WCH.DE", "EVD.DE",
    "DUE.DE", "FIE.DE", "FPE3.DE", "KRN.DE", "EVK.DE", "GXI.DE",
    "HAG.DE", "DWS.DE", "GYC.DE", "HBH.DE", "PFV.DE", "NOEJ.DE",
]

SDAX_FALLBACK = [
    "AT1.DE", "BFSA.DE", "BVB.DE", "DMP.DE", "ELG.DE", "FTK.DE",
    "HYQ.DE", "JEN.DE", "JST.DE", "OHB.DE", "SIX2.DE", "SZU.DE",
    "TAK.DE", "VBK.DE", "BSL.DE", "BDT.DE", "DEZ.DE", "IIND.DE",
    "KWS.DE", "LPKF.DE", "PHA.DE", "YSN.DE", "STO3.DE", "WUW.DE",
]

# Exchange-Suffix Mapping fuer EURO STOXX 50 Wikipedia-Scraping
COUNTRY_TO_SUFFIX = {
    "France": ".PA",
    "Germany": ".DE",
    "Netherlands": ".AS",
    "Spain": ".MC",
    "Italy": ".MI",
    "Belgium": ".BR",
    "Finland": ".HE",
    "Ireland": ".IR",
    "Portugal": ".LS",
    "Austria": ".VI",
}

# Quellen-Tracking: {list_name: (source, count)}
TICKER_SOURCES: dict[str, tuple[str, int]] = {}


def _set_source(list_name: str, source: str, count: int) -> None:
    """Speichert die Quelle einer Ticker-Liste (wiki/fallback)."""
    TICKER_SOURCES[list_name] = (source, count)


def filter_valid_tickers(tickers: list, label: str) -> list:
    """
    Entfernt ungueltige Ticker (kein valides Symbolformat).
    Erlaubt Buchstaben/Ziffern sowie . und -; muss mit alnum starten.
    """
    pattern = re.compile(r"^[A-Z0-9][A-Z0-9.\-]+$")
    valid = []
    invalid = 0
    for t in tickers:
        t = str(t).strip().upper()
        if not t:
            invalid += 1
            continue
        if pattern.match(t):
            valid.append(t)
        else:
            invalid += 1
    if invalid:
        print(f"  Hinweis: {label} – {invalid} ungültige Ticker entfernt.")
    return valid


def _fetch_html(url: str) -> str | None:
    """Fetch HTML with a browser-like User-Agent to avoid 403 blocks."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except Exception:
        return None


def _safe_read_html(url: str) -> list:
    """Liest HTML-Tabellen von einer URL. Fallback auf verschiedene Parser."""
    html = _fetch_html(url)
    if html:
        try:
            return pd.read_html(io.StringIO(html), flavor="lxml")
        except Exception:
            try:
                return pd.read_html(io.StringIO(html))
            except Exception:
                pass
    return []


def _add_de_suffix(tickers: list) -> list:
    """Fuegt .DE Suffix an Ticker ohne Exchange-Suffix an."""
    result = []
    for x in tickers:
        x = str(x).strip()
        if not x:
            continue
        result.append(x if "." in x else x + ".DE")
    return result


def get_nasdaq100_tickers() -> list:
    """Laedt NASDAQ 100 Ticker von Wikipedia oder nutzt Fallback."""
    tables = _safe_read_html("https://en.wikipedia.org/wiki/NASDAQ-100")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = t[col].dropna().tolist()
                tickers = [str(x).strip().replace(".", "-") for x in tickers if str(x).strip()]
                if len(tickers) > 50:
                    _set_source("NASDAQ 100", "wiki", len(tickers))
                    return tickers
    _set_source("NASDAQ 100", "fallback", len(NASDAQ100_FALLBACK))
    return NASDAQ100_FALLBACK


def get_sp500_tickers() -> list:
    """Laedt S&P 500 Ticker von Wikipedia oder nutzt Fallback."""
    tables = _safe_read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = t[col].dropna().tolist()
                tickers = [str(x).strip().replace(".", "-") for x in tickers if str(x).strip()]
                if len(tickers) > 400:
                    _set_source("S&P 500", "wiki", len(tickers))
                    return tickers
    _set_source("S&P 500", "fallback", len(SP500_FALLBACK))
    return SP500_FALLBACK


def get_dax40_tickers() -> list:
    """Laedt DAX 40 Ticker von Wikipedia oder nutzt Fallback."""
    tables = _safe_read_html("https://en.wikipedia.org/wiki/DAX")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = t[col].dropna().tolist()
                tickers = [str(x).strip() for x in tickers if str(x).strip()]
                tickers = [x if x.endswith(".DE") else x + ".DE" for x in tickers]
                if len(tickers) >= 30:
                    _set_source("DAX 40", "wiki", len(tickers))
                    return tickers
    _set_source("DAX 40", "fallback", len(DAX40_FALLBACK))
    return DAX40_FALLBACK


def get_eurostoxx50_tickers() -> list:
    """Laedt Euro Stoxx 50 Ticker von Wikipedia oder nutzt Fallback."""
    tables = _safe_read_html("https://en.wikipedia.org/wiki/Euro_Stoxx_50")
    for t in tables:
        cols_lower = {str(c).lower(): c for c in t.columns}
        ticker_col = next(
            (cols_lower[k] for k in cols_lower if "ticker" in k or "symbol" in k), None
        )
        country_col = next(
            (cols_lower[k] for k in cols_lower if "country" in k), None
        )
        if ticker_col is None:
            continue
        result = []
        for _, row in t.iterrows():
            ticker = str(row[ticker_col]).strip()
            if not ticker or ticker.lower() == "nan":
                continue
            if "." in ticker:
                result.append(ticker)
            elif country_col:
                country = str(row[country_col]).strip()
                suffix = COUNTRY_TO_SUFFIX.get(country, "")
                result.append(ticker + suffix)
            else:
                result.append(ticker)
        if len(result) >= 40:
            _set_source("Euro Stoxx 50", "wiki", len(result))
            return result
    _set_source("Euro Stoxx 50", "fallback", len(EUROSTOXX50_FALLBACK))
    return EUROSTOXX50_FALLBACK


def get_tecdax_tickers() -> list:
    """Laedt TecDAX Ticker von Wikipedia oder nutzt Fallback."""
    tables = _safe_read_html("https://en.wikipedia.org/wiki/TecDAX")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = _add_de_suffix(t[col].dropna().tolist())
                if len(tickers) >= 20:
                    _set_source("TecDAX", "wiki", len(tickers))
                    return tickers
    _set_source("TecDAX", "fallback", len(TECDAX_FALLBACK))
    return TECDAX_FALLBACK


def get_mdax_tickers() -> list:
    """Laedt MDAX Ticker von Wikipedia oder nutzt Fallback."""
    tables = _safe_read_html("https://en.wikipedia.org/wiki/MDAX")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = _add_de_suffix(t[col].dropna().tolist())
                if len(tickers) >= 30:
                    _set_source("MDAX", "wiki", len(tickers))
                    return tickers
    _set_source("MDAX", "fallback", len(MDAX_FALLBACK))
    return MDAX_FALLBACK


def get_sdax_tickers() -> list:
    """Laedt SDAX Ticker von Wikipedia oder nutzt Fallback."""
    tables = _safe_read_html("https://en.wikipedia.org/wiki/SDAX")
    for t in tables:
        for col in t.columns:
            if "ticker" in str(col).lower() or "symbol" in str(col).lower():
                tickers = _add_de_suffix(t[col].dropna().tolist())
                if len(tickers) >= 50:
                    _set_source("SDAX", "wiki", len(tickers))
                    return tickers
    _set_source("SDAX", "fallback", len(SDAX_FALLBACK))
    return SDAX_FALLBACK
