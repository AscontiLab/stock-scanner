"""Eligibility checks for current daily prices, independent of scoring and storage."""

import logging
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)

# Calendar days, inclusive: tolerate weekends/holidays and brief provider outages.
# This is the age of the last usable bar, never the cache's fetched_at timestamp.
MAX_STALENESS_DAYS = 5

# Verified corporate actions; mergers are deliberately NOT treated as renames.
# Sources and effective dates are documented in README.md.
_RENAMED = {"BK": (date(2026, 5, 21), "BNY")}
_DELISTED = {
    "CTRA": (date(2026, 5, 7), "merged into Devon (DVN)"),
    "HOLX": (date(2026, 4, 7), "taken private"),
}


def resolve_current_ticker(ticker: str, as_of: date | None = None) -> str | None:
    """Canonical current symbol, or None for a known discontinued listing."""
    as_of = as_of or date.today()
    ticker = ticker.strip().upper()
    if ticker in _DELISTED:
        effective, reason = _DELISTED[ticker]
        if as_of >= effective:
            logger.error("%s: skipped, no longer traded since %s (%s)",
                           ticker, effective, reason)
            return None
    if ticker in _RENAMED:
        effective, successor = _RENAMED[ticker]
        if as_of >= effective:
            logger.info("%s: using renamed ticker %s since %s", ticker, successor, effective)
            return successor
    return ticker


def current_prices_or_none(
    ticker: str,
    df: pd.DataFrame | None,
    as_of: date | None = None,
    max_staleness_days: int = MAX_STALENESS_DAYS,
) -> pd.DataFrame | None:
    """Fail closed on missing/invalid/stale daily bars before they reach scoring.

    Daily indices represent exchange session dates. Preserve their local date
    when timezone-aware, rather than shifting a midnight bar to another day.
    Remove incomplete rows first, so a fresh NaN row cannot hide an old price.
    """
    if type(max_staleness_days) is not int or max_staleness_days < 0:
        raise ValueError("max_staleness_days must be a non-negative integer")
    if df is None or df.empty:
        return None
    required = {"Open", "High", "Low", "Close", "Volume"}
    if not isinstance(df.index, pd.DatetimeIndex) or not required.issubset(df.columns):
        logger.error("%s: skipped, invalid daily price data", ticker)
        return None
    df = df.dropna()
    df = df.loc[df.index.notna()].sort_index()
    if df.empty:
        return None
    latest = df.index.max().date()
    age_days = ((as_of or date.today()) - latest).days
    if age_days < 0 or age_days > max_staleness_days:
        logger.error("%s: skipped, last usable price %s is %d calendar days old "
                       "(allowed 0..%d)", ticker, latest, age_days, max_staleness_days)
        return None
    return df
