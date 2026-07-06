"""
Market data router — provides stock universe, prices, and history.
"""

from fastapi import APIRouter, Query

from app.schemas.market import StockInfo, StockPriceResponse, StockHistoryResponse, StockHistoryPoint
from app.services.market_service import MarketService

router = APIRouter(prefix="/api/market", tags=["Market Data"])

# Shared service instance (stateless except for price cache)
_market_service = MarketService()


@router.get("/stocks", response_model=list[StockInfo])
async def list_stocks():
    """
    List all stocks in the tradable universe.

    Returns basic information about each stock: symbol, name, and sector.
    """
    stocks = _market_service.get_stock_universe()
    return [StockInfo(**s) for s in stocks]


@router.get("/prices", response_model=StockPriceResponse)
async def get_prices():
    """
    Get current prices for all stocks in the universe.

    Prices are cached for 5 minutes to avoid excessive API calls.
    """
    data = _market_service.get_live_prices()
    return StockPriceResponse(
        prices=[StockInfo(**p) for p in data["prices"]],
        last_updated=data["last_updated"],
    )


@router.get("/history/{symbol}", response_model=StockHistoryResponse)
async def get_stock_history(
    symbol: str,
    period: str = Query(default="1y", regex="^(1mo|3mo|6mo|1y|2y|5y)$"),
):
    """
    Get historical OHLCV data for a specific stock.

    - **symbol**: The stock ticker (e.g., TCS.NS).
    - **period**: Time period — 1mo, 3mo, 6mo, 1y, 2y, or 5y.
    """
    data = _market_service.get_stock_history(symbol, period)
    return StockHistoryResponse(
        symbol=data["symbol"],
        name=data["name"],
        history=[StockHistoryPoint(**p) for p in data["history"]],
    )
