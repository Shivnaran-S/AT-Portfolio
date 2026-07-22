"""
Portfolio router — portfolio initialization, status, fund management, and rebalancing.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Body
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
from app.rl.data.market_data import MarketDataService

router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])

def _check_market_open():
    """Raises HTTPException if the market is closed."""
    is_open, reason = MarketDataService._is_nse_market_open()
    if not is_open:
        msg = "Market is currently closed."
        if reason == "weekend":
            msg = "Trades cannot be executed during the weekend."
        elif reason == "holiday":
            msg = "Trades cannot be executed during a market holiday."
        elif reason == "pre-market":
            msg = "Trades cannot be executed during pre-market hours. Market opens at 9:15 AM."
        elif reason == "post-market":
            msg = "Trades cannot be executed during post-market hours. Market closes at 3:30 PM."
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.post("/initialize-preview", response_model=PortfolioAllocationResponse)
async def preview_initialize_portfolio(
    request: InitializePortfolioRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Preview a new portfolio allocation with the given capital.
    Does not save to database.
    """
    service = PortfolioService(db)
    try:
        result = await service.preview_initialization(current_user.id, request.capital)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return PortfolioAllocationResponse(
        portfolio_id="preview",
        total_capital=result["total_capital"],
        cash_after_allocation=result["cash_after_allocation"],
        allocations=[AllocationItem(**a) for a in result["allocations"]],
    )


@router.post("/initialize", response_model=PortfolioAllocationResponse)
async def confirm_initialize_portfolio(
    plan: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Confirm and save the portfolio initialization plan.
    Creates BUY orders for initial allocations.
    """
    _check_market_open()
    
    service = PortfolioService(db)
    try:
        result = await service.confirm_initialization(current_user.id, plan)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if result["allocations"]:
        trading_service = TradingService(db)
        order_data = [
            {
                "stock_symbol": a["stock_symbol"],
                "order_type": "BUY",
                "quantity": a["target_quantity"],
            }
            for a in result["allocations"]
            if a["target_quantity"] > 0
        ]
        if order_data:
            await trading_service.create_orders_from_plan(
                result["portfolio_id"], order_data
            )

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


@router.post("/withdraw-preview")
async def preview_withdraw_funds(
    request: WithdrawFundsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Preview a withdrawal that requires selling shares.
    """
    service = PortfolioService(db)
    try:
        result = await service.preview_withdraw(current_user.id, request.amount)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result

@router.post("/withdraw-funds")
async def confirm_withdraw_funds(
    amount: float = Body(...),
    plan: dict | None = Body(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Confirm withdrawal and execute sell trades.
    If no plan is provided, acts as an instant withdrawal from cash balance.
    """
    service = PortfolioService(db)
    
    if plan is None:
        try:
            result = await service.withdraw_funds(current_user.id, amount)
            return result
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
            
    _check_market_open()
    
    try:
        result = await service.confirm_withdraw(current_user.id, amount, plan)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if result.get("orders"):
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


@router.post("/rebalance-preview")
async def preview_rebalance_portfolio(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Preview the rebalancing plan using PPO-generated optimal weights.
    Computes differences but does not create orders or modify database.
    """
    service = PortfolioService(db)
    try:
        result = await service.preview_rebalance(current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result

@router.post("/rebalance")
async def confirm_rebalance_portfolio(
    plan: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Confirm the rebalancing plan.
    Saves target allocations and creates the buy/sell orders.
    """
    _check_market_open()
    
    service = PortfolioService(db)
    try:
        result = await service.confirm_rebalance(current_user.id, plan)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

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
