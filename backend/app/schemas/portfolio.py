"""
Pydantic schemas for portfolio-related requests and responses.
"""

from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, Field


# ── Requests ──────────────────────────────────────────────────────────────

class InitializePortfolioRequest(BaseModel):
    """First-time portfolio setup with initial capital."""
    capital: float = Field(..., gt=0, examples=[500000.0])


class AddFundsRequest(BaseModel):
    """Deposit additional capital."""
    amount: float = Field(..., gt=0, examples=[100000.0])


class WithdrawFundsRequest(BaseModel):
    """Withdraw capital from the portfolio."""
    amount: float = Field(..., gt=0, examples=[50000.0])


# ── Responses ─────────────────────────────────────────────────────────────

class AllocationItem(BaseModel):
    """A single stock's allocation in the portfolio."""
    stock_symbol: str
    stock_name: str
    sector: str
    weight: float
    target_amount: float
    target_quantity: int
    current_price: float


class PortfolioAllocationResponse(BaseModel):
    """Response after portfolio optimization — shows target allocations."""
    portfolio_id: str
    total_capital: float
    cash_after_allocation: float
    allocations: list[AllocationItem]


class HoldingStatus(BaseModel):
    """Current status of a single stock holding."""
    stock_symbol: str
    stock_name: str
    sector: str
    quantity: int
    average_buy_price: float
    current_price: float
    invested_amount: float       # quantity * average_buy_price
    current_value: float         # quantity * current_price
    profit_loss: float           # current_value - invested_amount
    profit_loss_percent: float   # (profit_loss / invested_amount) * 100


class PortfolioStatusResponse(BaseModel):
    """Comprehensive portfolio status with all metrics."""
    portfolio_id: str
    total_capital: float
    cash_balance: float
    total_invested: float
    current_market_value: float
    total_profit_loss: float
    total_profit_loss_percent: float
    realized_profit_loss: float
    unrealized_profit_loss: float
    holdings: list[HoldingStatus]


class PortfolioHistoryPoint(BaseModel):
    """A single data point in portfolio value history."""
    date: str
    value: float


class PortfolioHistoryResponse(BaseModel):
    """Portfolio value over time for charts."""
    history: list[PortfolioHistoryPoint]
