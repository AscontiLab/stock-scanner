"""Portfolio-Management: Aktive Positionen mit Empfehlung."""

import logging
import re
import time
import traceback
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from dashboard.config import settings

logger = logging.getLogger("portfolio")

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# Cache fuer check_positions (yfinance Rate-Limit)
_cache = {"data": None, "ts": 0}


def _get_portfolio_module():
    import cfd_portfolio
    return cfd_portfolio


def _check_cached():
    """Portfolio-Check mit 5min Cache."""
    now = time.time()
    if _cache["data"] is not None and (now - _cache["ts"]) < settings.CACHE_TTL_SECONDS:
        return _cache["data"]

    mod = _get_portfolio_module()
    positions = mod.list_positions()
    if not positions:
        _cache["data"] = []
        _cache["ts"] = now
        return []

    reports = mod.check_positions(positions)
    _cache["data"] = reports
    _cache["ts"] = now
    return reports


class AddPositionRequest(BaseModel):
    ticker: str
    direction: str


class ClosePositionRequest(BaseModel):
    ticker: str
    direction: str = ""


@router.get("/portfolio", response_class=HTMLResponse)
async def portfolio_page(request: Request):
    reports = _check_cached()
    return templates.TemplateResponse("portfolio.html", {
        "request": request,
        "positions": reports,
    })


_TICKER_RE = re.compile(r"^[A-Z0-9._]{1,12}$")


@router.post("/api/portfolio/add")
async def add_position(req: AddPositionRequest):
    ticker = req.ticker.strip().upper()
    direction = req.direction.strip().lower()
    if not _TICKER_RE.match(ticker):
        return JSONResponse(status_code=400, content={"ok": False, "error": "Ungueltiger Ticker"})
    if direction not in ("long", "short"):
        return JSONResponse(status_code=400, content={"ok": False, "error": "Richtung muss 'long' oder 'short' sein"})
    try:
        mod = _get_portfolio_module()
        result = mod.add_position(ticker, direction)
        _cache["data"] = None
        return {"ok": True, "message": f"{ticker} {direction} hinzugefuegt", "position": result}
    except Exception as e:
        logger.error("add_position %s %s fehlgeschlagen: %s\n%s", ticker, direction, e, traceback.format_exc())
        return JSONResponse(status_code=500, content={"ok": False, "error": f"Fehler: {e}"})


@router.post("/api/portfolio/close")
async def close_position(req: ClosePositionRequest):
    try:
        mod = _get_portfolio_module()
        direction = req.direction.lower() if req.direction else None
        closed = mod.close_position(req.ticker.upper(), direction)
        _cache["data"] = None
        if closed:
            return {"ok": True, "message": f"{req.ticker.upper()} geschlossen"}
        return JSONResponse(status_code=404, content={"ok": False, "error": "Position nicht gefunden"})
    except Exception as e:
        logger.error("close_position %s fehlgeschlagen: %s\n%s", req.ticker, e, traceback.format_exc())
        return JSONResponse(status_code=500, content={"ok": False, "error": f"Fehler: {e}"})


@router.get("/api/portfolio/check")
async def check_positions_json():
    reports = _check_cached()
    return {"positions": reports}
