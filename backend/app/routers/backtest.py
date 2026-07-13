"""
Backtest router — portfolio and trading agent evaluation endpoints.

Runs backtesting simulations and returns performance metrics.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.rl.backtesting.portfolio_backtest import run_portfolio_backtest
from app.rl.backtesting.trading_backtest import run_trading_backtest

router = APIRouter(prefix="/api/backtest", tags=["Backtesting"])


# ── Request Schemas ───────────────────────────────────────────────────

class PortfolioBacktestRequest(BaseModel):
    period: str = Field("2y", description="Historical data period (e.g., '1y', '2y', '3y')")
    rebalance_frequency: str = Field("monthly", description="'monthly' or 'quarterly'")
    lookback_months: int = Field(6, ge=1, le=12, description="Months of lookback for weight generation")


class TradingBacktestRequest(BaseModel):
    total_shares: int = Field(50, ge=1, le=1000, description="Shares to simulate executing per stock per day")
    order_type: str = Field("BUY", description="'BUY' or 'SELL'")
    num_days: int | None = Field(None, ge=1, le=60, description="Max days to test (None = all available)")


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("/portfolio")
async def backtest_portfolio(request: PortfolioBacktestRequest):
    """
    Run a backtest of the PPO portfolio optimization agent.

    Simulates monthly (or quarterly) rebalancing over the specified
    historical period. Compares PPO agent performance against an
    equal-weight benchmark.

    Returns:
    - Performance metrics: Sharpe ratio, Sortino ratio, max drawdown,
      annualized return, volatility, Calmar ratio, win rate
    - Equity curves for both PPO and benchmark
    - Weight history at each rebalance date
    """
    try:
        result = run_portfolio_backtest(
            period=request.period,
            rebalance_frequency=request.rebalance_frequency,
            lookback_months=request.lookback_months,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Portfolio backtest failed: {str(e)}",
        )

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"],
        )

    return result


@router.post("/trading")
async def backtest_trading(request: TradingBacktestRequest):
    """
    Run a backtest of the PPO trading execution agent.

    Tests the agent on historical 5-minute intraday data (last ~60 days
    from yfinance). For each stock and each available day, simulates
    executing an order and measures execution quality.

    Returns:
    - Aggregate metrics: implementation shortfall, VWAP improvement,
      avg slices, completion rate, cost savings vs naive
    - Per-stock breakdown with daily execution details
    """
    try:
        result = run_trading_backtest(
            total_shares=request.total_shares,
            order_type=request.order_type,
            num_days=request.num_days,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Trading backtest failed: {str(e)}",
        )

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"],
        )

    return result
