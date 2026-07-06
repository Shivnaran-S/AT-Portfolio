"""
Trading router — algorithmic trade execution and order management.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.models.portfolio import Portfolio
from app.routers.dependencies import get_current_user
from app.schemas.order import OrderResponse, OrderSliceResponse
from app.services.trading_service import TradingService

router = APIRouter(prefix="/api/trading", tags=["Trading"])


@router.post("/execute")
async def execute_trades(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute all pending orders using the PPO algorithmic trading agent.

    The agent determines optimal timing and order slicing for each trade,
    executing buy/sell orders with minimal market impact.
    """
    # Get user's portfolio
    query = select(Portfolio).where(Portfolio.user_id == current_user.id)
    result = await db.execute(query)
    portfolio = result.scalar_one_or_none()

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No portfolio found. Initialize your portfolio first.",
        )

    service = TradingService(db)
    executed = await service.execute_orders(portfolio.id)

    if not executed:
        return {"message": "No pending orders to execute.", "orders": []}

    return {
        "message": f"Executed {len(executed)} orders.",
        "orders": executed,
    }


@router.get("/orders", response_model=list[OrderResponse])
async def list_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all orders for the current user's portfolio.

    Returns orders with their execution slices, sorted by most recent first.
    """
    query = select(Portfolio).where(Portfolio.user_id == current_user.id)
    result = await db.execute(query)
    portfolio = result.scalar_one_or_none()

    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No portfolio found.",
        )

    service = TradingService(db)
    orders = await service.get_orders(portfolio.id)

    return [
        OrderResponse(
            id=o["id"],
            stock_symbol=o["stock_symbol"],
            order_type=o["order_type"],
            total_quantity=o["total_quantity"],
            filled_quantity=o["filled_quantity"],
            status=o["status"],
            created_at=o["created_at"],
            completed_at=o.get("completed_at"),
            slices=[
                OrderSliceResponse(
                    id=s["id"],
                    quantity=s["quantity"],
                    price=s["price"],
                    executed_at=s["executed_at"],
                )
                for s in o.get("slices", [])
            ],
        )
        for o in orders
    ]
