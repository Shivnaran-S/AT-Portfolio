"""
Transaction model — records all financial movements in a portfolio.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import String, DateTime, Numeric, Text, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Transaction(Base):
    """
    An immutable record of a financial event: deposit, withdrawal, buy, or sell.

    This provides a full audit trail of all money movements.
    """

    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    portfolio_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # DEPOSIT, WITHDRAWAL, BUY, SELL
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    stock_symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quantity: Mapped[int | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationship
    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="transactions")

    __table_args__ = (
        CheckConstraint(
            "transaction_type IN ('DEPOSIT', 'WITHDRAWAL', 'BUY', 'SELL')",
            name="ck_transactions_type",
        ),
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
    )

    def __repr__(self) -> str:
        return f"<Transaction({self.transaction_type} ₹{self.amount})>"
