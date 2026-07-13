"""
Market data utilities — fetches and processes stock data from Yahoo Finance.

Uses yfinance for historical OHLCV data and current prices for NSE stocks.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sys

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import yfinance as yf

from app.stock_config import get_symbols

logger = logging.getLogger(__name__)

# NSE market hours in IST (Indian Standard Time)
_IST = ZoneInfo("Asia/Kolkata")
_MARKET_OPEN_HOUR, _MARKET_OPEN_MIN = 9, 15    # 9:15 AM IST
_MARKET_CLOSE_HOUR, _MARKET_CLOSE_MIN = 15, 30  # 3:30 PM IST

# Indian exchange calendar — covers all NSE/BSE holidays (Republic Day, Holi, Diwali, etc.)
_NSE_CALENDAR = xcals.get_calendar("XBOM")


class MarketDataService:
    """Fetches and processes market data for the stock universe."""

    def __init__(self):
        self._price_cache: dict[str, float] = {}
        self._cache_timestamp: datetime | None = None
        self._cache_ttl = timedelta(minutes=5)  # Refresh prices every 5 minutes

    # ── Market Hours Helper ────────────────────────────────────────────

    @staticmethod
    def _is_nse_market_open() -> tuple[bool, str]:
        """
        Check if NSE is currently open.

        Handles weekends, NSE holidays, and market hours.
        Uses the exchange_calendars XBOM calendar for holiday detection.

        Returns:
            (is_open, reason) — reason explains why the market is closed.
            Possible reasons: 'open', 'weekend', 'holiday', 'pre-market', 'post-market'.
        """
        now_ist = datetime.now(_IST)

        # Weekends (Saturday = 5, Sunday = 6)
        if now_ist.weekday() >= 5:
            return False, "weekend"

        # Check NSE holiday calendar (Republic Day, Holi, Diwali, etc.)
        today = pd.Timestamp(now_ist.date())
        if not _NSE_CALENDAR.is_session(today):
            return False, "holiday"

        # Check if within market hours (9:15 AM – 3:30 PM IST)
        market_open = now_ist.replace(
            hour=_MARKET_OPEN_HOUR, minute=_MARKET_OPEN_MIN,
            second=0, microsecond=0,
        )
        market_close = now_ist.replace(
            hour=_MARKET_CLOSE_HOUR, minute=_MARKET_CLOSE_MIN,
            second=0, microsecond=0,
        )
        if now_ist < market_open:
            return False, "pre-market"
        if now_ist > market_close:
            return False, "post-market"

        return True, "open"

    # ── Current Prices ────────────────────────────────────────────────

    def get_current_prices(self, symbols: list[str] | None = None) -> dict[str, float]:
        """
        Fetch the latest prices for the given symbols.

        During NSE market hours  → returns the live last-traded price.
        Outside market hours     → returns the previous closing price
                                   and logs an informational message.

        Uses yf.Ticker.fast_info (lightweight; avoids the heavy .info call).
        A 5-minute cache prevents excessive API requests.
        """
        if symbols is None:
            symbols = get_symbols()

        # Return cache if still fresh
        now = datetime.now()
        if (
            self._cache_timestamp is not None
            and now - self._cache_timestamp < self._cache_ttl
            and all(s in self._price_cache for s in symbols)
        ):
            return {s: self._price_cache[s] for s in symbols}

        # Determine if the market is currently open
        market_open, reason = self._is_nse_market_open()
        if not market_open:
            _CLOSED_MESSAGES = {
                "weekend":    "NSE market is closed (weekend).",
                "holiday":    "NSE market is closed (exchange holiday).",
                "pre-market": "NSE market has not opened yet (pre-market hours).",
                "post-market":"NSE market has closed for the day (post-market hours).",
            }
            logger.info(
                f"{_CLOSED_MESSAGES.get(reason, 'NSE market is closed.')} "
                f"Returning the latest available closing prices."
            )

        # Fetch fresh prices using Ticker.fast_info (lightweight API)
        prices = {}
        for symbol in symbols:
            try:
                fast = yf.Ticker(symbol).fast_info
                if market_open:
                    # Live last-traded price during market hours
                    price = fast.get("lastPrice", None)
                else:
                    # Latest closing price when market is closed
                    price = fast.get("previousClose", None)

                if price is not None:
                    prices[symbol] = float(price)
                else:
                    logger.warning(f"No price data available for {symbol}")
            except Exception as e:
                logger.error(f"Error fetching price for {symbol}: {e}")

        # Update cache
        self._price_cache.update(prices)
        self._cache_timestamp = now

        return prices

    # ── Historical Data ───────────────────────────────────────────────

    def get_historical_data(
        self,
        symbols: list[str] | None = None,
        period: str = "2y",
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data for the given symbols.

        Args:
            symbols: List of ticker symbols. Defaults to the full stock universe.
            period: yfinance period string (e.g., '1y', '2y', '5y').

        Returns:
            A DataFrame with MultiIndex columns (Price, Symbol).
        """
        if symbols is None:
            symbols = get_symbols()

        try:
            data = yf.download(symbols, period=period, progress=False, threads=True)
            return data
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return pd.DataFrame()

    def get_stock_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """
        Fetch historical OHLCV data for a single stock.

        Returns a DataFrame with columns: Open, High, Low, Close, Volume.
        """
        try:
            ticker = yf.Ticker(symbol)
            history = ticker.history(period=period)
            return history
        except Exception as e:
            logger.error(f"Error fetching history for {symbol}: {e}")
            return pd.DataFrame()

    def get_intraday_prices(
        self, symbol: str, interval: str = "5m", period: str = "60d"
    ) -> np.ndarray | None:
        """
        Fetch intraday close prices for a single stock.

        Uses yfinance's intraday data. For 5-min interval, yfinance
        provides up to ~60 days of data for free.

        Args:
            symbol: Ticker symbol (e.g., "TCS.NS").
            interval: Candle interval (e.g., "5m", "1m", "15m").
            period: How far back to fetch (e.g., "1d", "5d", "60d").

        Returns:
            numpy array of close prices, or None if data is unavailable.
        """
        try:
            data = yf.download(
                symbol, period=period, interval=interval,
                progress=False, threads=False,
            )
            if data.empty:
                logger.warning(f"No intraday data for {symbol}.")
                return None

            close = data["Close"]
            # yfinance may return a DataFrame with symbol column
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            prices = close.dropna().values.astype(np.float64)

            if len(prices) < 2:
                logger.warning(
                    f"Insufficient intraday data for {symbol}: {len(prices)} points."
                )
                return None

            return prices
        except Exception as e:
            logger.error(f"Error fetching intraday prices for {symbol}: {e}")
            return None

    # ── Technical Indicators ──────────────────────────────────────────

    @staticmethod
    def compute_technical_indicators(close_prices: pd.DataFrame) -> pd.DataFrame:
        """
        Compute technical indicators for each stock.

        Adds: RSI (14-day), MACD, MACD Signal, Bollinger Band Width,
        SMA_20, SMA_50 columns for each symbol.

        Args:
            close_prices: DataFrame with columns as symbols and index as dates.

        Returns:
            DataFrame with added technical indicator columns.
        """
        result = pd.DataFrame(index=close_prices.index)

        for symbol in close_prices.columns:
            prices = close_prices[symbol].dropna()

            # RSI (14-day Relative Strength Index)
            delta = prices.diff()
            gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
            rs = gain / loss.replace(0, np.nan)
            result[f"{symbol}_RSI"] = 100 - (100 / (1 + rs))

            # MACD (12-day EMA - 26-day EMA) and Signal (9-day EMA of MACD)
            ema_12 = prices.ewm(span=12, adjust=False).mean()
            ema_26 = prices.ewm(span=26, adjust=False).mean()
            macd = ema_12 - ema_26
            signal = macd.ewm(span=9, adjust=False).mean()
            result[f"{symbol}_MACD"] = macd
            result[f"{symbol}_MACD_Signal"] = signal

            # Bollinger Band Width (20-day)
            sma_20 = prices.rolling(window=20).mean()
            std_20 = prices.rolling(window=20).std()
            bb_upper = sma_20 + 2 * std_20
            bb_lower = sma_20 - 2 * std_20
            result[f"{symbol}_BB_Width"] = (bb_upper - bb_lower) / sma_20

            # Simple Moving Averages
            result[f"{symbol}_SMA_20"] = sma_20
            result[f"{symbol}_SMA_50"] = prices.rolling(window=50).mean()

        return result

    @staticmethod
    def compute_returns(close_prices: pd.DataFrame) -> pd.DataFrame:
        """Compute daily log returns."""
        return np.log(close_prices / close_prices.shift(1)).dropna()

    @staticmethod
    def compute_covariance_matrix(returns: pd.DataFrame) -> np.ndarray:
        """Compute the covariance matrix of daily returns."""
        return returns.cov().values

#The following code is only for testing purposes or viewing the downloaded data.
if __name__ == "__main__":
    mds = MarketDataService()
    sys.exit()
    symbols = ["TCS.NS", "HDFCBANK.NS"]
    raw_data = mds.get_historical_data(
        symbols= symbols,
        period= "2y",
    )
    #print(raw_data["Close"])

    close_prices = raw_data["Close"]
    if isinstance(close_prices, type(raw_data)):
        # Multi-symbol format
        close_prices = close_prices[symbols]
    close_prices = close_prices.dropna()

    returns = MarketDataService.compute_returns(close_prices)
    print(returns)
    features_df = MarketDataService.compute_technical_indicators(close_prices)
    print("Features:\n", features_df)
