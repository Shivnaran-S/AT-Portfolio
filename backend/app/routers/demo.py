"""
Demo router — simulated portfolio optimization and trading.

All endpoints operate on in-memory demo sessions (no authentication required).
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.demo_service import DemoService

router = APIRouter(prefix="/api/demo", tags=["Demo Mode"])

# Shared demo service instance (holds all sessions in memory)
_demo_service = DemoService()


# ── Request Schemas ───────────────────────────────────────────────────

class StartDemoRequest(BaseModel):
    capital: float = Field(..., gt=0, examples=[500000.0])

class DemoFundsRequest(BaseModel):
    session_id: str
    amount: float = Field(..., gt=0)

class DemoSessionRequest(BaseModel):
    session_id: str


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("/start")
async def start_demo(request: StartDemoRequest):
    """
    Start a new demo session with the given capital.

    No authentication required. Returns a session_id to use in subsequent calls.
    """
    try:
        result = _demo_service.create_session(request.capital)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result


@router.post("/optimize")
async def optimize_demo(request: DemoSessionRequest):
    """
    Run PPO portfolio optimization for the demo session.

    Returns optimal weights and target allocations for all stocks.
    """
    try:
        result = _demo_service.optimize_portfolio(request.session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result


@router.post("/trade")
async def trade_demo(request: DemoSessionRequest):
    """
    Run a simulated trading session.

    The PPO trading agent executes buy/sell orders with optimal timing
    and order slicing in a compressed simulated market environment.
    """
    try:
        result = _demo_service.run_trading_simulation(request.session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result


@router.post("/add-funds")
async def add_demo_funds(request: DemoFundsRequest):
    """Add funds to the demo portfolio."""
    try:
        result = _demo_service.add_funds(request.session_id, request.amount)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result


@router.post("/withdraw-funds")
async def withdraw_demo_funds(request: DemoFundsRequest):
    """Withdraw funds from the demo portfolio."""
    try:
        result = _demo_service.withdraw_funds(request.session_id, request.amount)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return result


@router.post("/rebalance")
async def rebalance_demo(request: DemoSessionRequest):
    """
    Rebalance the demo portfolio.

    Runs optimization first, then executes the required trades.
    """
    try:
        # First optimize
        opt_result = _demo_service.optimize_portfolio(request.session_id)
        # Then trade
        trade_result = _demo_service.run_trading_simulation(request.session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {
        "optimization": opt_result,
        "trading": trade_result,
    }


@router.get("/status/{session_id}")
async def get_demo_status(session_id: str):
    """
    Get the current status of a demo portfolio.

    Returns holdings, P&L, and all portfolio metrics.
    """
    try:
        result = _demo_service.get_status(session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return result
