"""
Pydantic schemas for market data responses.
"""

from pydantic import BaseModel


class StockInfo(BaseModel):
    """Basic information about a stock in the universe."""
    symbol: str
    name: str
    sector: str
    current_price: float | None = None
    change_percent: float | None = None


class StockPriceResponse(BaseModel):
    """Current prices for all stocks."""
    prices: list[StockInfo]
    last_updated: str


class StockHistoryPoint(BaseModel):
    """A single OHLCV data point."""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class StockHistoryResponse(BaseModel):
    """Historical price data for a stock."""
    symbol: str
    name: str
    history: list[StockHistoryPoint]
