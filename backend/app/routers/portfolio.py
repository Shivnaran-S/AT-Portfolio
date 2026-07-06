"""
Portfolio router — portfolio initialization, status, fund management, and rebalancing.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.schemas.portfolio import (
    InitializePortfolioRequest,
    AddFundsRequest,
    WithdrawFundsRequest,
    PortfolioAllocationResponse,
    PortfolioStatusResponse,
    AllocationItem,
    HoldingStatus,
)
from app.services.portfolio_service import PortfolioService
from app.services.trading_service import TradingService

router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])


@router.post("/initialize", response_model=PortfolioAllocationResponse)
async def initialize_portfolio(
    request: InitializePortfolioRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Initialize a new portfolio with the given capital.

    This runs the PPO portfolio optimizer to generate optimal weights
    and calculates the number of shares to purchase for each stock.

    Can only be called once per user (first visit).
    """
    service = PortfolioService(db)
    try:
        result = await service.initialize_portfolio(current_user.id, request.capital)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return PortfolioAllocationResponse(
        portfolio_id=result["portfolio_id"],
        total_capital=result["total_capital"],
        cash_after_allocation=result["cash_after_allocation"],
        allocations=[AllocationItem(**a) for a in result["allocations"]],
    )


@router.get("/status", response_model=PortfolioStatusResponse)
async def get_portfolio_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get comprehensive portfolio status.

    Includes per-stock holdings, P&L, realized/unrealized profits,
    and total portfolio metrics.
    """
    service = PortfolioService(db)
    try:
        result = await service.get_portfolio_status(current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return PortfolioStatusResponse(
        portfolio_id=result["portfolio_id"],
        total_capital=result["total_capital"],
        cash_balance=result["cash_balance"],
        total_invested=result["total_invested"],
        current_market_value=result["current_market_value"],
        total_profit_loss=result["total_profit_loss"],
        total_profit_loss_percent=result["total_profit_loss_percent"],
        realized_profit_loss=result["realized_profit_loss"],
        unrealized_profit_loss=result["unrealized_profit_loss"],
        holdings=[HoldingStatus(**h) for h in result["holdings"]],
    )


@router.post("/add-funds")
async def add_funds(
    request: AddFundsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add funds to the portfolio's cash balance."""
    service = PortfolioService(db)
    try:
        result = await service.add_funds(current_user.id, request.amount)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result


@router.post("/withdraw-funds")
async def withdraw_funds(
    request: WithdrawFundsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Withdraw funds from the portfolio.

    Cannot withdraw more than the total portfolio value (market value + cash).
    """
    service = PortfolioService(db)
    try:
        result = await service.withdraw_funds(current_user.id, request.amount)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result


@router.post("/rebalance")
async def rebalance_portfolio(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Rebalance the portfolio using PPO-generated optimal weights.

    Computes the difference between current and target holdings,
    then creates buy/sell orders for the differences only.
    """
    service = PortfolioService(db)
    try:
        result = await service.rebalance_portfolio(current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Auto-create orders from the rebalancing plan
    if result["orders"]:
        trading_service = TradingService(db)
        order_data = [
            {
                "stock_symbol": o["stock_symbol"],
                "order_type": o["order_type"],
                "quantity": o["quantity"],
            }
            for o in result["orders"]
        ]
        await trading_service.create_orders_from_plan(result["portfolio_id"], order_data)

    return result
