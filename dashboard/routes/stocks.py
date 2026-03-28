"""Investment-Portfolio Seite: Gehaltene Langfrist-Aktien mit Warnungen."""

import re
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from dashboard.config import settings
from utils import read_csv as _read_csv

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

SCANNER_DIR = settings.SCANNER_DIR

# Cache fuer check_stocks (vermeidet wiederholtes Parsen)
_cache = {"data": None, "ts": 0}

_TICKER_RE = re.compile(r"^[A-Z0-9._]{1,12}$")


def _get_portfolio_module():
    """Laedt das investment_portfolio Modul."""
    import investment_portfolio
    return investment_portfolio


def _check_cached():
    """Portfolio-Check mit 5min Cache."""
    now = time.time()
    if _cache["data"] is not None and (now - _cache["ts"]) < settings.CACHE_TTL_SECONDS:
        return _cache["data"]

    mod = _get_portfolio_module()
    stocks = mod.list_stocks()
    if not stocks:
        _cache["data"] = []
        _cache["ts"] = now
        return []

    # Scan-Ergebnisse laden
    all_rows = _read_csv(SCANNER_DIR / "trading_signals.csv")
    reports = mod.check_stocks(stocks, all_rows)
    _cache["data"] = reports
    _cache["ts"] = now
    return reports


class AddStockRequest(BaseModel):
    ticker: str
    market: str = ""


class RemoveStockRequest(BaseModel):
    ticker: str


@router.get("/stocks", response_class=HTMLResponse)
async def stocks_page(request: Request):
    """Investment-Portfolio Seite."""
    reports = _check_cached()
    mod = _get_portfolio_module()
    stock_count = len(mod.list_stocks())
    return templates.TemplateResponse("stocks.html", {
        "request": request,
        "stock_reports": reports,
        "stock_count": stock_count,
    })


@router.post("/api/stocks/add")
async def add_stock_api(req: AddStockRequest):
    """Aktie zum Investment-Portfolio hinzufuegen."""
    ticker = req.ticker.strip().upper()
    if not _TICKER_RE.match(ticker):
        return JSONResponse(status_code=400, content={"ok": False, "error": "Ungueltiger Ticker"})
    try:
        mod = _get_portfolio_module()
        success = mod.add_stock(ticker, req.market)
        _cache["data"] = None  # Cache invalidieren
        if success:
            return {"ok": True, "message": f"{ticker} hinzugefuegt"}
        return JSONResponse(status_code=409, content={"ok": False, "error": f"{ticker} bereits im Portfolio"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": f"Fehler: {e}"})


@router.post("/api/stocks/remove")
async def remove_stock_api(req: RemoveStockRequest):
    """Aktie aus Investment-Portfolio entfernen."""
    ticker = req.ticker.strip().upper()
    if not _TICKER_RE.match(ticker):
        return JSONResponse(status_code=400, content={"ok": False, "error": "Ungueltiger Ticker"})
    try:
        mod = _get_portfolio_module()
        success = mod.remove_stock(ticker)
        _cache["data"] = None  # Cache invalidieren
        if success:
            return {"ok": True, "message": f"{ticker} entfernt"}
        return JSONResponse(status_code=404, content={"ok": False, "error": f"{ticker} nicht im Portfolio"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": f"Fehler: {e}"})


@router.get("/api/stocks/check")
async def check_stocks_json():
    """Alle gehaltenen Aktien mit Warnungen als JSON."""
    reports = _check_cached()
    return {"stocks": reports}
