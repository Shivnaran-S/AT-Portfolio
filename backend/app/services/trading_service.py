"""
Trading service — handles algorithmic trade execution with PPO order slicing.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Portfolio, Holding
from app.models.order import Order, OrderSlice
from app.models.transaction import Transaction
from app.stock_config import get_symbols
from app.rl.data.market_data import MarketDataService
from app.rl.agents.trading_agent import TradingAgent

logger = logging.getLogger(__name__)


class TradingService:
    """Handles algorithmic trade execution using PPO order slicing."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._market_data = MarketDataService()
        self._trading_agent = TradingAgent()

    # ── Execute Orders ────────────────────────────────────────────────

    async def execute_orders(self, portfolio_id: str) -> list[dict]:
        """
        Execute all pending orders for a portfolio using PPO algorithmic trading.

        For each order:
        1. Generate an intraday price path (simulated for now)
        2. Use the PPO trading agent to plan execution slices
        3. Record each slice in the database
        4. Update holdings atomically

        Returns a list of executed order reports.
        """
        # Fetch pending orders
        query = select(Order).where(
            Order.portfolio_id == portfolio_id,
            Order.status.in_(["PENDING", "PARTIAL"]),
        )
        result = await self.db.execute(query)
        pending_orders = result.scalars().all()

        if not pending_orders:
            return []

        prices = self._market_data.get_current_prices(get_symbols())
        executed_orders = []

        for order in pending_orders:
            current_price = prices.get(order.stock_symbol, 0.0)
            if current_price <= 0:
                continue

            # Generate a simulated intraday price path
            price_path = TradingAgent._generate_price_path(
                initial_price=current_price,
                num_steps=78,
                volatility=0.015,
            )

            # Get execution plan from PPO agent
            try:
                slices = self._trading_agent.plan_execution(
                    total_shares=order.remaining_quantity,
                    price_path=price_path,
                    num_time_steps=78,
                )
            except FileNotFoundError:
                # Model not trained — use simple TWAP fallback
                logger.warning("Trading model not trained. Using TWAP fallback.")
                slices = self._twap_fallback(
                    order.remaining_quantity, current_price, num_slices=4
                )

            # Execute each slice
            for slice_data in slices:
                qty = slice_data["quantity"]
                price = slice_data["price"]
                exec_time = datetime.fromisoformat(slice_data["time"])

                # Create order slice record
                order_slice = OrderSlice(
                    order_id=order.id,
                    quantity=qty,
                    price=Decimal(str(round(price, 4))),
                    executed_at=exec_time,
                )
                self.db.add(order_slice)

                # Update order filled quantity
                order.filled_quantity += qty

                # Update holding
                await self._update_holding(
                    portfolio_id=portfolio_id,
                    stock_symbol=order.stock_symbol,
                    quantity=qty if order.order_type == "BUY" else -qty,
                    price=price,
                    order_type=order.order_type,
                )

            # Update order status
            if order.filled_quantity >= order.total_quantity:
                order.status = "FILLED"
                order.completed_at = datetime.now(timezone.utc)
            elif order.filled_quantity > 0:
                order.status = "PARTIAL"

            executed_orders.append({
                "id": order.id,
                "stock_symbol": order.stock_symbol,
                "order_type": order.order_type,
                "total_quantity": order.total_quantity,
                "filled_quantity": order.filled_quantity,
                "status": order.status,
                "slices": [
                    {
                        "quantity": s["quantity"],
                        "price": s["price"],
                        "time": s["time"],
                    }
                    for s in slices
                ],
            })

        await self.db.commit()
        return executed_orders

    # ── Create Orders from Allocation ─────────────────────────────────

    async def create_orders_from_plan(
        self, portfolio_id: str, orders: list[dict]
    ) -> list[str]:
        """
        Create Order records from a rebalancing plan.

        Args:
            portfolio_id: The portfolio ID.
            orders: List of dicts with stock_symbol, order_type, quantity.

        Returns:
            List of created order IDs.
        """
        order_ids = []
        for order_data in orders:
            if order_data["quantity"] <= 0:
                continue

            order = Order(
                portfolio_id=portfolio_id,
                stock_symbol=order_data["stock_symbol"],
                order_type=order_data["order_type"],
                total_quantity=order_data["quantity"],
            )
            self.db.add(order)
            await self.db.flush()
            order_ids.append(order.id)

        await self.db.commit()
        return order_ids

    # ── Order Queries ─────────────────────────────────────────────────

    async def get_orders(self, portfolio_id: str) -> list[dict]:
        """Get all orders for a portfolio."""
        query = (
            select(Order)
            .where(Order.portfolio_id == portfolio_id)
            .order_by(Order.created_at.desc())
        )
        result = await self.db.execute(query)
        orders = result.scalars().all()

        order_list = []
        for order in orders:
            # Fetch slices
            slice_query = select(OrderSlice).where(OrderSlice.order_id == order.id)
            slice_result = await self.db.execute(slice_query)
            slices = slice_result.scalars().all()

            order_list.append({
                "id": order.id,
                "stock_symbol": order.stock_symbol,
                "order_type": order.order_type,
                "total_quantity": order.total_quantity,
                "filled_quantity": order.filled_quantity,
                "status": order.status,
                "created_at": order.created_at.isoformat() if order.created_at else "",
                "completed_at": order.completed_at.isoformat() if order.completed_at else None,
                "slices": [
                    {
                        "id": s.id,
                        "quantity": s.quantity,
                        "price": float(s.price),
                        "executed_at": s.executed_at.isoformat() if s.executed_at else "",
                    }
                    for s in slices
                ],
            })

        return order_list

    # ── Helpers ───────────────────────────────────────────────────────

    async def _update_holding(
        self,
        portfolio_id: str,
        stock_symbol: str,
        quantity: int,
        price: float,
        order_type: str,
    ):
        """
        Update a holding after a trade execution.

        For BUY: increases quantity and updates average buy price.
        For SELL: decreases quantity and records realized P&L.
        """
        query = select(Holding).where(
            Holding.portfolio_id == portfolio_id,
            Holding.stock_symbol == stock_symbol,
        )
        result = await self.db.execute(query)
        holding = result.scalar_one_or_none()

        if holding is None:
            # Create new holding
            holding = Holding(
                portfolio_id=portfolio_id,
                stock_symbol=stock_symbol,
                quantity=max(0, quantity),
                average_buy_price=Decimal(str(round(price, 4))),
            )
            self.db.add(holding)
            return

        if order_type == "BUY":
            # Update weighted average buy price
            old_total = float(holding.average_buy_price) * holding.quantity
            new_total = price * quantity
            new_quantity = holding.quantity + quantity
            if new_quantity > 0:
                new_avg = (old_total + new_total) / new_quantity
                holding.average_buy_price = Decimal(str(round(new_avg, 4)))
            holding.quantity = new_quantity

            # Record buy transaction
            tx = Transaction(
                portfolio_id=portfolio_id,
                transaction_type="BUY",
                amount=Decimal(str(round(abs(quantity) * price, 2))),
                stock_symbol=stock_symbol,
                quantity=abs(quantity),
                description=f"Bought {abs(quantity)} shares of {stock_symbol} @ ₹{price:.2f}",
            )
            self.db.add(tx)

            # Reduce cash balance
            portfolio_query = select(Portfolio).where(Portfolio.id == portfolio_id)
            portfolio_result = await self.db.execute(portfolio_query)
            portfolio = portfolio_result.scalar_one()
            portfolio.cash_balance -= Decimal(str(round(abs(quantity) * price, 2)))

        elif order_type == "SELL":
            abs_qty = abs(quantity)
            # Record realized P&L
            realized_pnl = abs_qty * (price - float(holding.average_buy_price))

            # Record sell transaction (amount = sale proceeds)
            tx = Transaction(
                portfolio_id=portfolio_id,
                transaction_type="SELL",
                amount=Decimal(str(round(abs_qty * price, 2))),
                stock_symbol=stock_symbol,
                quantity=abs_qty,
                description=f"Sold {abs_qty} shares of {stock_symbol} @ ₹{price:.2f} (P&L: ₹{realized_pnl:.2f})",
            )
            self.db.add(tx)

            holding.quantity = max(0, holding.quantity - abs_qty)

            # Add proceeds to cash balance
            portfolio_query = select(Portfolio).where(Portfolio.id == portfolio_id)
            portfolio_result = await self.db.execute(portfolio_query)
            portfolio = portfolio_result.scalar_one()
            portfolio.cash_balance += Decimal(str(round(abs_qty * price, 2)))

    @staticmethod
    def _twap_fallback(total_shares: int, price: float, num_slices: int = 4) -> list[dict]:
        """
        Simple Time-Weighted Average Price fallback when PPO model isn't trained.

        Splits the order into equal slices at regular intervals.
        """
        from datetime import timedelta
        base_time = datetime.now(timezone.utc)
        shares_per_slice = total_shares // num_slices
        remainder = total_shares % num_slices

        slices = []
        for i in range(num_slices):
            qty = shares_per_slice + (1 if i < remainder else 0)
            if qty <= 0:
                continue
            slice_time = base_time + timedelta(minutes=i * 90)  # ~90 min apart
            # Add small random price variation
            variation = np.random.uniform(-0.005, 0.005)
            slice_price = price * (1 + variation)
            slices.append({
                "time": slice_time.isoformat(),
                "quantity": qty,
                "price": round(slice_price, 4),
            })

        return slices
