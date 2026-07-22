"""
Trading service — handles algorithmic trade execution with PPO order slicing.

Non-demo (live) mode:
- Uses real intraday market data from yfinance
- Enforces NSE market hours (9:15 AM – 3:30 PM IST, Mon–Fri)
- Supports both BUY and SELL orders
- Executes step-by-step: fetches latest price every 5 minutes, asks
  the agent for a single decision, executes if the agent decides to trade.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.portfolio import Portfolio, Holding
from app.models.order import Order, OrderSlice
from app.models.transaction import Transaction
from app.stock_config import get_symbols, get_stock_info
from app.rl.data.market_data import MarketDataService
from app.rl.agents.trading_agent import TradingAgent

logger = logging.getLogger(__name__)

# IST offset: UTC+5:30
_IST = timezone(timedelta(hours=5, minutes=30))

# In-memory execution state for live trading (keyed by portfolio_id)
_live_executions: dict[str, dict] = {}

# Step interval for live trading (seconds) — 5 minutes
_LIVE_STEP_INTERVAL = 300


class TradingService:
    """Handles algorithmic trade execution using PPO order slicing."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._market_data = MarketDataService()
        self._trading_agent = TradingAgent()

    # ── Market Hours Check ────────────────────────────────────────────

    @staticmethod
    def _is_market_open() -> bool:
        """
        Check if the NSE market is currently open.

        Market hours: 9:15 AM – 3:30 PM IST, Monday to Friday.
        Returns True if within trading hours, False otherwise.
        """
        now_ist = datetime.now(_IST)

        # Weekday check (Mon=0, Sun=6)
        if now_ist.weekday() >= 5:  # Saturday or Sunday
            return False

        market_open = now_ist.replace(
            hour=settings.nse_market_open_hour,
            minute=settings.nse_market_open_minute,
            second=0, microsecond=0,
        )
        market_close = now_ist.replace(
            hour=settings.nse_market_close_hour,
            minute=settings.nse_market_close_minute,
            second=0, microsecond=0,
        )

        return market_open <= now_ist <= market_close

    @staticmethod
    def _remaining_steps_today() -> int:
        """
        Calculate how many 5-minute steps remain until market close.

        Returns at least 1 to avoid division by zero.
        """
        now_ist = datetime.now(_IST)
        market_close = now_ist.replace(
            hour=settings.nse_market_close_hour,
            minute=settings.nse_market_close_minute,
            second=0, microsecond=0,
        )
        remaining_seconds = max(0, (market_close - now_ist).total_seconds())
        steps = int(remaining_seconds / _LIVE_STEP_INTERVAL)
        return max(steps, 1)

    # ── Start Live Execution (Non-blocking) ───────────────────────────

    async def start_execution(
        self,
        portfolio_id: str,
        session_factory: async_sessionmaker | None = None,
    ) -> dict:
        """
        Start step-by-step live execution as a background task.

        Validates market hours, loads pending orders, and starts
        a background asyncio task that fetches real prices every
        5 minutes and makes agent decisions one step at a time.

        Args:
            portfolio_id: The portfolio to execute orders for.
            session_factory: SQLAlchemy async_sessionmaker for creating
                fresh DB sessions in the background task.

        Returns immediately with execution metadata.
        """
        # ── Market hours enforcement ──
        if not self._is_market_open():
            raise ValueError(
                "Trading can only be done during market hours "
                f"({settings.nse_market_open_hour}:{settings.nse_market_open_minute:02d} AM "
                f"– {settings.nse_market_close_hour}:{settings.nse_market_close_minute:02d} PM IST, "
                "Mon–Fri)."
            )

        # Check for already-running execution
        if portfolio_id in _live_executions:
            existing = _live_executions[portfolio_id]
            if existing.get("status") == "running":
                raise ValueError("Execution is already running for this portfolio.")

        # Fetch pending orders
        query = select(Order).where(
            Order.portfolio_id == portfolio_id,
            Order.status.in_(["PENDING", "PARTIAL"]),
        )
        result = await self.db.execute(query)
        pending_orders = result.scalars().all()

        if not pending_orders:
            return {"status": "completed", "message": "No pending orders to execute."}

        total_steps = self._remaining_steps_today()

        # Initialize per-order state
        order_states = []
        for order in pending_orders:
            stock_info = get_stock_info(order.stock_symbol) or {}
            order_states.append({
                "order_id": order.id,
                "symbol": order.stock_symbol,
                "stock_name": stock_info.get("name", order.stock_symbol),
                "order_type": order.order_type,
                "total_shares": order.remaining_quantity,
                "remaining_shares": order.remaining_quantity,
                "price_history": [],
            })

        # Store execution state
        exec_state = {
            "status": "running",
            "portfolio_id": portfolio_id,
            "total_steps": total_steps,
            "current_step": 0,
            "start_time": time.time(),
            "order_states": order_states,
            "executed_slices": [],
        }
        _live_executions[portfolio_id] = exec_state

        # Start background task
        asyncio.ensure_future(
            self._run_live_execution(
                portfolio_id=portfolio_id,
                session_factory=session_factory,
            )
        )

        return {
            "status": "started",
            "total_steps": total_steps,
            "num_orders": len(order_states),
            "step_interval_seconds": _LIVE_STEP_INTERVAL,
        }

    def stop_execution(self, portfolio_id: str) -> dict:
        """
        Gracefully stop a running live execution.
        """
        exec_state = _live_executions.get(portfolio_id)
        if not exec_state or exec_state.get("status") != "running":
            raise ValueError("No running execution found for this portfolio.")
            
        exec_state["stop_requested"] = True
        return {"status": "stopping", "message": "Stop requested. The execution will halt shortly."}

    async def _run_live_execution(
        self,
        portfolio_id: str,
        session_factory: async_sessionmaker | None = None,
    ):
        """
        Background task: step-by-step live trading.

        Every 5 minutes:
        1. Fetch latest real price for each pending order
        2. Build observation from price history
        3. Ask the PPO agent for a single-step decision
        4. If the agent decides to trade, write to DB
        5. On last step (near market close), force-execute remaining
        """
        exec_state = _live_executions.get(portfolio_id)
        if exec_state is None:
            return

        market_data = MarketDataService()
        agent = TradingAgent()
        total_steps = exec_state["total_steps"]

        for step in range(total_steps):
            # Check if market is still open
            if not self._is_market_open():
                logger.info("Market closed. Force-executing remaining orders.")
                is_last = True
            else:
                is_last = (step == total_steps - 1)

            now_iso = datetime.now(timezone.utc).isoformat()

            # ── Process each order at this tick ──
            for ostate in exec_state["order_states"]:
                if ostate["remaining_shares"] <= 0:
                    continue

                # Fetch latest real price
                prices = market_data.get_current_prices([ostate["symbol"]])
                current_price = prices.get(ostate["symbol"], 0.0)
                if current_price <= 0:
                    continue

                ostate["price_history"].append(current_price)

                # Ask the agent for a decision
                try:
                    shares, exec_price = agent.decide_single_step(
                        remaining_shares=ostate["remaining_shares"],
                        total_shares=ostate["total_shares"],
                        current_step=step,
                        total_steps=total_steps,
                        current_price=current_price,
                        price_history=ostate["price_history"],
                        order_type=ostate["order_type"],
                        is_last_step=is_last,
                    )
                except FileNotFoundError:
                    # Model not trained — TWAP fallback: distribute evenly
                    if is_last:
                        shares = ostate["remaining_shares"]
                    else:
                        remaining_steps = total_steps - step
                        shares = max(1, ostate["remaining_shares"] // max(remaining_steps, 1))
                        shares = min(shares, ostate["remaining_shares"])
                    exec_price = round(current_price, 4)

                if shares <= 0:
                    continue

                if ostate["order_type"] == "BUY":
                    # Check DB for available cash to prevent negative cash constraint violation
                    try:
                        if session_factory:
                            async with session_factory() as db:
                                portfolio = await db.get(Portfolio, portfolio_id)
                                if portfolio and portfolio.cash_balance < Decimal(str(round(shares * exec_price, 2))):
                                    shares = max(0, int(float(portfolio.cash_balance) / exec_price))
                    except Exception as e:
                        logger.error(f"Error checking cash balance: {e}")
                
                if shares <= 0:
                    continue

                ostate["remaining_shares"] -= shares

                # Record in execution state
                exec_state["executed_slices"].append({
                    "stock_symbol": ostate["symbol"],
                    "stock_name": ostate["stock_name"],
                    "order_type": ostate["order_type"],
                    "quantity": shares,
                    "price": exec_price,
                    "time": now_iso,
                    "step": step,
                })

                # ── Write to database ──
                if session_factory:
                    try:
                        async with session_factory() as db:
                            await self._record_trade_in_db(
                                db=db,
                                order_id=ostate["order_id"],
                                portfolio_id=portfolio_id,
                                stock_symbol=ostate["symbol"],
                                order_type=ostate["order_type"],
                                quantity=shares,
                                price=exec_price,
                                executed_at=datetime.now(timezone.utc),
                            )
                    except Exception as e:
                        logger.error(f"DB write error for {ostate['symbol']}: {e}")

            exec_state["current_step"] = step + 1

            # ── Early termination: all orders filled ──
            all_done = all(
                o["remaining_shares"] <= 0 for o in exec_state["order_states"]
            )
            if all_done:
                logger.info(
                    f"All orders filled at step {step + 1}/{total_steps}. "
                    "Terminating execution early."
                )
                break

            # Exit early if market closed
            if is_last:
                break

            # Wait for next tick (5 minutes), polling for stop flag every second
            if step < total_steps - 1:
                interrupted = False
                for _ in range(_LIVE_STEP_INTERVAL):
                    if exec_state.get("stop_requested"):
                        interrupted = True
                        break
                    await asyncio.sleep(1)
                    
                if interrupted:
                    logger.info(f"Execution stopped by user for portfolio {portfolio_id}")
                    exec_state["status"] = "stopped"
                    return

        # ── Execution complete ──
        exec_state["status"] = "completed"
        logger.info(
            f"Live execution completed for portfolio {portfolio_id}: "
            f"{len(exec_state['executed_slices'])} trades in {exec_state['current_step']} steps"
        )

    @staticmethod
    async def _record_trade_in_db(
        db: AsyncSession,
        order_id: str,
        portfolio_id: str,
        stock_symbol: str,
        order_type: str,
        quantity: int,
        price: float,
        executed_at: datetime,
    ):
        """Write a single trade execution to the database."""
        # Create order slice
        order_slice = OrderSlice(
            order_id=order_id,
            quantity=quantity,
            price=Decimal(str(round(price, 4))),
            executed_at=executed_at,
        )
        db.add(order_slice)

        # Update order filled quantity
        order = await db.get(Order, order_id)
        if order:
            order.filled_quantity += quantity
            if order.filled_quantity >= order.total_quantity:
                order.status = "FILLED"
                order.completed_at = executed_at
            elif order.filled_quantity > 0:
                order.status = "PARTIAL"

        # Update holding
        holding_query = select(Holding).where(
            Holding.portfolio_id == portfolio_id,
            Holding.stock_symbol == stock_symbol,
        )
        result = await db.execute(holding_query)
        holding = result.scalar_one_or_none()

        if holding is None:
            holding = Holding(
                portfolio_id=portfolio_id,
                stock_symbol=stock_symbol,
                quantity=quantity if order_type == "BUY" else 0,
                average_buy_price=Decimal(str(round(price, 4))),
            )
            db.add(holding)
        elif order_type == "BUY":
            old_total = float(holding.average_buy_price) * holding.quantity
            new_total = price * quantity
            new_qty = holding.quantity + quantity
            if new_qty > 0:
                new_avg = (old_total + new_total) / new_qty
                holding.average_buy_price = Decimal(str(round(new_avg, 4)))
            holding.quantity = new_qty
        elif order_type == "SELL":
            holding.quantity = max(0, holding.quantity - quantity)

        # Update portfolio cash balance
        portfolio = await db.get(Portfolio, portfolio_id)
        if portfolio:
            trade_amount = Decimal(str(round(quantity * price, 2)))
            if order_type == "BUY":
                portfolio.cash_balance -= trade_amount
            else:
                portfolio.cash_balance += trade_amount

        # Record transaction
        tx = Transaction(
            portfolio_id=portfolio_id,
            transaction_type=order_type,
            amount=Decimal(str(round(quantity * price, 2))),
            stock_symbol=stock_symbol,
            quantity=quantity,
            description=(
                f"{'Bought' if order_type == 'BUY' else 'Sold'} "
                f"{quantity} shares of {stock_symbol} @ ₹{price:.2f}"
            ),
        )
        db.add(tx)

        await db.commit()

    # ── Execution Status ──────────────────────────────────────────────

    @staticmethod
    def get_execution_status(portfolio_id: str) -> dict:
        """
        Get the current status of a live execution.

        Returns progress, executed trades so far, and final status.
        """
        exec_state = _live_executions.get(portfolio_id)
        if exec_state is None:
            return {"status": "idle", "message": "No execution running."}

        elapsed = time.time() - exec_state["start_time"]
        total = exec_state["total_steps"]
        current = exec_state["current_step"]
        progress = min(100.0, (current / max(total, 1)) * 100)

        result = {
            "status": exec_state["status"],
            "total_steps": total,
            "current_step": current,
            "trades_executed": len(exec_state["executed_slices"]),
            "progress_percent": round(progress, 1),
            "elapsed_seconds": round(elapsed, 1),
            "step_interval_seconds": _LIVE_STEP_INTERVAL,
            "executed_slices": exec_state["executed_slices"][-20:],
        }

        return result

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
