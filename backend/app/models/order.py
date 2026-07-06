"""
Order and OrderSlice models — track trade orders and their execution slices.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import String, DateTime, Numeric, Integer, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Order(Base):
    """
    A trade order (buy or sell) for a specific stock.

    The PPO algorithmic trading agent may split this into multiple OrderSlices.
    """

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    portfolio_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    order_type: Mapped[str] = mapped_column(String(4), nullable=False)  # 'BUY' or 'SELL'
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Status: PENDING, PARTIAL, FILLED, CANCELLED
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="orders")
    slices: Mapped[list["OrderSlice"]] = relationship(
        "OrderSlice", back_populates="order", cascade="all, delete-orphan",
        order_by="OrderSlice.executed_at",
    )

    __table_args__ = (
        CheckConstraint("order_type IN ('BUY', 'SELL')", name="ck_orders_type"),
        CheckConstraint("total_quantity > 0", name="ck_orders_total_qty_positive"),
        CheckConstraint("filled_quantity >= 0", name="ck_orders_filled_qty_non_negative"),
        CheckConstraint(
            "status IN ('PENDING', 'PARTIAL', 'FILLED', 'CANCELLED')",
            name="ck_orders_status",
        ),
    )

    @property
    def remaining_quantity(self) -> int:
        """Shares still to be executed."""
        return self.total_quantity - self.filled_quantity

    @property
    def is_complete(self) -> bool:
        """Whether the order has been fully filled."""
        return self.filled_quantity >= self.total_quantity

    def __repr__(self) -> str:
        return (
            f"<Order(id={self.id}, {self.order_type} {self.stock_symbol} "
            f"{self.filled_quantity}/{self.total_quantity})>"
        )


class OrderSlice(Base):
    """
    A single execution slice within an order.

    The PPO trading agent decides the timing and size of each slice.
    For example, buying 100 shares might be split into:
      - 25 shares at 10:49 AM
      - 50 shares at 12:35 PM
      - 25 shares at 03:01 PM
    """

    __tablename__ = "order_slices"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationship
    order: Mapped["Order"] = relationship("Order", back_populates="slices")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_slices_qty_positive"),
        CheckConstraint("price > 0", name="ck_order_slices_price_positive"),
    )

    def __repr__(self) -> str:
        return f"<OrderSlice(qty={self.quantity}, price={self.price}, at={self.executed_at})>"
