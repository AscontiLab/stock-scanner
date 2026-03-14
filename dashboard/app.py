"""Stock Scanner Dashboard — FastAPI Entry Point."""

import sys
from pathlib import Path

# Parent-Dir fuer Import von cfd_portfolio, cfd_backtesting etc.
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard.routes import signals, portfolio, backtesting

app = FastAPI(title="Stock Scanner Dashboard", docs_url=None, redoc_url=None)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Router einbinden
app.include_router(signals.router)
app.include_router(portfolio.router)
app.include_router(backtesting.router)
