"""Deterministic provider-outage and corporate-action regressions (no network)."""

import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest
from yfinance.exceptions import YFRateLimitError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import price_cache
import price_data
import stock_scanner
from tickers.sources import filter_valid_tickers


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 7, 12, tzinfo=tz)


class FrozenDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 7)


def prices(end, count=260):
    index = pd.bdate_range(end=end, periods=count, name="Date")
    close = pd.Series([100 + i * 0.1 for i in range(count)], index=index)
    return pd.DataFrame({"Open": close - 0.2, "High": close + 1,
                         "Low": close - 1, "Close": close, "Volume": 1_000_000})


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(price_cache, "DB_PATH", tmp_path / "prices.db")
    monkeypatch.setattr(price_cache, "datetime", FrozenDatetime)
    monkeypatch.setattr(price_data, "date", FrozenDate)
    with price_cache._get_connection() as conn:
        price_cache._ensure_schema(conn)
    # Every download is stubbed. A real yfinance exception type models a
    # temporary rate limit; no flaky dependency on a live Yahoo outage.
    download = Mock(side_effect=YFRateLimitError())
    monkeypatch.setattr(price_cache.yf, "download", download)
    monkeypatch.setattr(stock_scanner, "resolve_name", lambda ticker: ticker)
    return download


@pytest.mark.parametrize("failure", ["exception", "empty", "none", "historical"])
@pytest.mark.parametrize("ticker,last_day", [
    ("UNKNOWN", "2026-05-20"), ("BNY", "2026-05-20"),
])
def test_months_old_cache_fails_closed(isolated_cache, caplog, ticker, last_day, failure):
    old = prices(last_day)
    price_cache.save_prices(ticker, old)  # fetched_at is TODAY, bar dates are old.
    if failure != "exception":
        isolated_cache.side_effect = None
        isolated_cache.return_value = {"empty": pd.DataFrame(), "none": None,
                                      "historical": old}[failure]
    assert price_cache.get_prices(ticker, "1y") is None
    assert "last usable price 2026-05-20" in caplog.text
    # Rejection must not destroy archived prices.
    assert price_cache.get_cached_prices(ticker, "2025-01-01", "2026-10-07") is not None


@pytest.mark.parametrize("ticker,last_day", [("CTRA", "2026-05-06"), ("HOLX", "2026-04-06")])
def test_delisted_symbols_never_download_or_score(isolated_cache, caplog, ticker, last_day):
    price_cache.save_prices(ticker, prices(last_day))
    assert price_cache.get_prices(ticker, "1y") is None
    assert stock_scanner.analyze_ticker(ticker, "S&P 500") is None
    isolated_cache.assert_not_called()
    assert "no longer traded" in caplog.text


def test_bk_uses_bny_data_and_canonical_scanner_identity(isolated_cache):
    price_cache.save_prices("BK", prices("2026-05-20"))
    fresh = prices("2026-10-06")
    isolated_cache.side_effect = None
    isolated_cache.return_value = fresh
    result = stock_scanner.analyze_ticker("BK", "S&P 500")
    assert result is not None
    assert result["ticker"] == "BNY"
    assert result["price"] == fresh["Close"].iloc[-1]
    assert all(call.args[0] == "BNY" for call in isolated_cache.call_args_list)
    cached = price_cache.get_cached_prices("BNY", "2025-01-01", "2026-10-07")
    pd.testing.assert_frame_equal(cached, fresh, check_freq=False, check_dtype=False)
    old = price_cache.get_cached_prices("BK", "2025-01-01", "2026-10-07")
    assert old.index.max() == pd.Timestamp("2026-05-20")


def test_failed_bny_download_never_reuses_legacy_bk_cache(isolated_cache):
    price_cache.save_prices("BK", prices("2026-05-20"))
    assert price_cache.get_prices("BK", "1y") is None
    isolated_cache.assert_called_once()
    assert isolated_cache.call_args.args == ("BNY",)


@pytest.mark.parametrize("symbol,before,on_or_after", [
    ("BK", "2026-05-20", "2026-05-21"),
    ("CTRA", "2026-05-06", "2026-05-07"),
    ("HOLX", "2026-04-06", "2026-04-07"),
])
def test_corporate_actions_are_effective_dated(symbol, before, on_or_after):
    assert price_data.resolve_current_ticker(symbol, date.fromisoformat(before)) == symbol
    expected = "BNY" if symbol == "BK" else None
    assert price_data.resolve_current_ticker(symbol, date.fromisoformat(on_or_after)) == expected


def test_universe_normalizes_rename_and_drops_delistings_without_duplicate_dvn():
    assert filter_valid_tickers(["BK", "BNY", "CTRA", "DVN", "HOLX", "AAPL"], "test") == [
        "BNY", "DVN", "AAPL"]


@pytest.mark.parametrize("failure", ["exception", "empty", "none"])
@pytest.mark.parametrize("last_day,count,accepted", [
    ("2026-10-06", 260, True),  # current-cache refresh path
    ("2026-10-02", 260, True),  # inclusive five-day boundary / weekend
    ("2026-10-01", 260, False), # six days must fail closed
    ("2026-10-06", 10, True),   # short cache, full-download fallback
])
def test_temporary_provider_failure_has_bounded_fallback(
    isolated_cache, failure, last_day, count, accepted
):
    cached = prices(last_day, count)
    price_cache.save_prices("AAPL", cached)
    price_cache._set_meta("AAPL", cached.index.min().strftime("%Y-%m-%d"))
    if failure != "exception":
        isolated_cache.side_effect = None
        isolated_cache.return_value = pd.DataFrame() if failure == "empty" else None
    result = price_cache.get_prices("AAPL", "1y")
    if accepted:
        pd.testing.assert_frame_equal(result, cached, check_freq=False, check_dtype=False)
    else:
        assert result is None
    isolated_cache.assert_called_once()


def test_stricter_limit_applies_to_incremental_success_and_failure(isolated_cache):
    price_cache.save_prices("AAPL", prices("2026-10-02"))
    assert price_cache.get_prices("AAPL", "1y", max_staleness_days=2) is None
    isolated_cache.side_effect = None
    isolated_cache.return_value = prices("2026-10-02", 1)
    assert price_cache.get_prices("AAPL", "1y", max_staleness_days=2) is None
    isolated_cache.return_value = prices("2026-10-06", 1)
    assert price_cache.get_prices("AAPL", "1y", max_staleness_days=2) is not None


def test_successful_refresh_recovers_stale_cache(isolated_cache):
    price_cache.save_prices("AAPL", prices("2026-05-20"))
    isolated_cache.side_effect = None
    fresh = prices("2026-10-06")
    fresh.columns = pd.MultiIndex.from_product([fresh.columns, ["AAPL"]])
    isolated_cache.return_value = fresh
    result = price_cache.get_prices("AAPL", "1y")
    assert result.index.max() == pd.Timestamp("2026-10-06")
    assert len(result) >= 250


def test_front_backfill_preserved(isolated_cache):
    price_cache.save_prices("AAPL", prices("2026-10-06", 60))
    isolated_cache.side_effect = [prices("2026-10-06"), pd.DataFrame()]
    result = price_cache.get_prices("AAPL", "1y")
    assert len(result) >= 250
    assert result.index.min() <= pd.Timestamp("2025-10-14")
    assert isolated_cache.call_args_list[0].kwargs["period"] == "1y"


def test_failed_front_backfill_does_not_bypass_staleness(isolated_cache):
    price_cache.save_prices("AAPL", prices("2026-05-20", 40))
    assert price_cache.get_prices("AAPL", "1y") is None
    assert isolated_cache.call_count == 2


@pytest.mark.parametrize("timezone", [None, "America/New_York", "Europe/Berlin"])
def test_freshness_uses_session_dates_and_valid_rows(timezone):
    old = prices("2026-10-01")
    old.loc[pd.Timestamp("2026-10-07")] = float("nan")
    old.index = old.index.tz_localize(timezone)
    assert price_data.current_prices_or_none("AAPL", old) is None
    recent = prices("2026-10-02")
    recent.index = recent.index.tz_localize(timezone)
    assert price_data.current_prices_or_none("AAPL", recent) is not None


@pytest.mark.parametrize("limit", [-1, None, float("inf"), float("nan"), True])
def test_invalid_limit_cannot_disable_guard(isolated_cache, limit):
    with pytest.raises(ValueError):
        price_cache.get_prices("AAPL", max_staleness_days=limit)
    isolated_cache.assert_not_called()


def test_future_or_invalid_date_cannot_pass_guard():
    assert price_data.current_prices_or_none("AAPL", prices("2026-10-08")) is None
    invalid = prices("2026-10-06", 1)
    invalid.index = pd.DatetimeIndex([pd.NaT])
    assert price_data.current_prices_or_none("AAPL", invalid) is None


@pytest.mark.parametrize("path", ["cache", "direct", "exception_fallback"])
def test_scanner_rejects_stale_data_before_indicators(monkeypatch, isolated_cache, path):
    old = prices("2026-05-20")
    monkeypatch.setattr(stock_scanner, "_USE_PRICE_CACHE", path != "direct")
    cache = Mock(return_value=old)
    if path == "exception_fallback":
        cache.side_effect = RuntimeError("temporary cache failure")
    monkeypatch.setattr(stock_scanner, "cached_get_prices", cache)
    isolated_cache.side_effect = None
    isolated_cache.return_value = old
    indicator = Mock(side_effect=AssertionError("stale prices reached indicators"))
    monkeypatch.setattr(stock_scanner, "compute_atr", indicator)
    assert stock_scanner.analyze_ticker("AAPL", "NASDAQ 100") is None
    indicator.assert_not_called()


def test_temporary_rate_limit_keeps_recent_stock_scoreable(isolated_cache):
    price_cache.save_prices("AAPL", prices("2026-10-06"))
    result = stock_scanner.analyze_ticker("AAPL", "NASDAQ 100")
    assert result is not None
    assert result["ticker"] == "AAPL"
    isolated_cache.assert_called_once()
