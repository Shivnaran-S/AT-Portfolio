"""
Pydantic schemas for trading-related requests and responses.
"""

from datetime import datetime
from pydantic import BaseModel


class OrderSliceResponse(BaseModel):
    """A single execution slice within an order."""
    id: str
    quantity: int
    price: float
    executed_at: str


class OrderResponse(BaseModel):
    """Details of a trade order."""
    id: str
    stock_symbol: str
    order_type: str          # BUY or SELL
    total_quantity: int
    filled_quantity: int
    status: str              # PENDING, PARTIAL, FILLED, CANCELLED
    created_at: str
    completed_at: str | None = None
    slices: list[OrderSliceResponse] = []


class ExecuteTradesRequest(BaseModel):
    """Request to execute pending algorithmic trades."""
    pass  # No body needed — executes all pending orders


class TradeExecutionUpdate(BaseModel):
    """Real-time update sent via WebSocket during trade execution."""
    order_id: str
    stock_symbol: str
    order_type: str
    slice_quantity: int
    slice_price: float
    executed_at: str
    total_filled: int
    total_quantity: int
    status: str
    message: str
