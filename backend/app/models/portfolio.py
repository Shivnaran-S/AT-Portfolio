"""
Portfolio-related models — Portfolio, Holding, and TargetAllocation.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    String, DateTime, Numeric, Integer, ForeignKey, UniqueConstraint, CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Portfolio(Base):
    """
    A user's investment portfolio.

    Each user has exactly one portfolio (one-to-one with User).
    """

    __tablename__ = "portfolios"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # Total capital ever deposited (deposits minus withdrawals)
    total_capital: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0.00")
    )
    # Cash not yet invested in stocks
    cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0.00")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="portfolio")
    holdings: Mapped[list["Holding"]] = relationship(
        "Holding", back_populates="portfolio", cascade="all, delete-orphan"
    )
    target_allocations: Mapped[list["TargetAllocation"]] = relationship(
        "TargetAllocation", back_populates="portfolio", cascade="all, delete-orphan"
    )
    orders: Mapped[list["Order"]] = relationship(
        "Order", back_populates="portfolio", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="portfolio", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("cash_balance >= 0", name="ck_portfolios_cash_non_negative"),
    )

    def __repr__(self) -> str:
        return f"<Portfolio(id={self.id}, user_id={self.user_id})>"


class Holding(Base):
    """
    A single stock holding within a portfolio.

    Each portfolio has at most one Holding row per stock symbol.
    """

    __tablename__ = "holdings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    portfolio_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    stock_symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Weighted average price at which shares were purchased
    average_buy_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0.0000")
    )

    # Relationship
    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="holdings")

    __table_args__ = (
        UniqueConstraint("portfolio_id", "stock_symbol", name="uq_holdings_portfolio_stock"),
        CheckConstraint("quantity >= 0", name="ck_holdings_quantity_non_negative"),
    )

    def __repr__(self) -> str:
        return f"<Holding(symbol={self.stock_symbol}, qty={self.quantity})>"


class TargetAllocation(Base):
    """
    PPO-generated target allocation for a stock within a portfolio.

    Stores the optimal weight and resulting target quantity.
    """

    __tablename__ = "target_allocations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    portfolio_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    stock_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    # PPO-generated weight between 0.0 and 1.0
    weight: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    target_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0.00")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationship
    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="target_allocations")

    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "stock_symbol", name="uq_target_alloc_portfolio_stock"
        ),
        CheckConstraint("weight >= 0 AND weight <= 1", name="ck_target_alloc_weight_range"),
    )

    def __repr__(self) -> str:
        return f"<TargetAllocation(symbol={self.stock_symbol}, weight={self.weight})>"
