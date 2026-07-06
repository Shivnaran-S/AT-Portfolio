"""
Market service — provides stock information and prices to the API layer.
"""

from datetime import datetime, timezone

from app.stock_config import STOCK_UNIVERSE, get_symbols
from app.rl.data.market_data import MarketDataService


class MarketService:
    """Business logic for market data endpoints."""

    def __init__(self):
        self._data_service = MarketDataService()

    def get_stock_universe(self) -> list[dict]:
        """
        Return the full list of tradable stocks with metadata.

        Each stock includes: symbol, name, sector.
        """
        return STOCK_UNIVERSE.copy()

    def get_live_prices(self) -> dict:
        """
        Fetch current prices for all stocks in the universe.

        Returns a dict with 'prices' (list of stock info with prices)
        and 'last_updated' timestamp.
        """
        symbols = get_symbols()
        prices = self._data_service.get_current_prices(symbols)

        stock_prices = []
        for stock in STOCK_UNIVERSE:
            symbol = stock["symbol"]
            current_price = prices.get(symbol)
            stock_prices.append({
                "symbol": symbol,
                "name": stock["name"],
                "sector": stock["sector"],
                "current_price": round(current_price, 2) if current_price else None,
                "change_percent": None,  # Could be computed from historical data
            })

        return {
            "prices": stock_prices,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def get_stock_history(self, symbol: str, period: str = "1y") -> dict:
        """
        Fetch historical OHLCV data for a single stock.

        Returns a dict with symbol, name, and history as a list of data points.
        """
        # Validate symbol
        stock_info = None
        for stock in STOCK_UNIVERSE:
            if stock["symbol"] == symbol:
                stock_info = stock
                break

        if stock_info is None:
            return {"symbol": symbol, "name": "Unknown", "history": []}

        history_df = self._data_service.get_stock_history(symbol, period)
        history_points = []

        if not history_df.empty:
            for date, row in history_df.iterrows():
                history_points.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]),
                })

        return {
            "symbol": symbol,
            "name": stock_info["name"],
            "history": history_points,
        }
