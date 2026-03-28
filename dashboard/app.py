"""Stock Scanner Dashboard — FastAPI Entry Point."""

import secrets
import sys
from pathlib import Path

# Parent-Dir fuer Import von cfd_portfolio, cfd_backtesting etc.
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard.config import settings
from dashboard.routes import signals, portfolio, backtesting, stocks

app = FastAPI(title="Stock Scanner Dashboard", docs_url=None, redoc_url=None)

# CORS — nur explizit freigegebene Origins
_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()] if settings.CORS_ORIGINS else []
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Bearer-Token Auth fuer /api/* Endpoints."""
    token = settings.DASHBOARD_TOKEN
    if token and request.url.path.startswith("/api/"):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or not secrets.compare_digest(auth[7:], token):
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    return await call_next(request)


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Router einbinden
app.include_router(signals.router)
app.include_router(portfolio.router)
app.include_router(backtesting.router)
app.include_router(stocks.router)
