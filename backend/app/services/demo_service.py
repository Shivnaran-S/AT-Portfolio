"""
Demo service — simulated market environment for demo mode.

Provides the same features as the live system but uses:
- GBM-generated price paths instead of real market data
- Compressed time simulation (configurable, default 2 minutes = one trading day)
- In-memory session storage (no database)
- Full investment of capital (no idle cash balance)

Trading decisions are made step-by-step: at each tick the agent observes
only the current price and decides whether to trade and how many shares.
"""

import asyncio
import logging
import math
import time
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np

from app.config import settings
from app.stock_config import STOCK_UNIVERSE, get_symbols, get_stock_info
from app.rl.agents.portfolio_agent import PortfolioAgent
from app.rl.agents.trading_agent import TradingAgent
from app.rl.data.market_data import MarketDataService

logger = logging.getLogger(__name__)


class StockExecutionContext:
    """
    Per-stock state during a step-by-step trading simulation.

    Tracks the GBM price path (revealed one step at a time), the
    accumulated price history visible to the agent, and remaining shares.
    """

    def __init__(
        self,
        symbol: str,
        stock_name: str,
        order_type: str,
        total_shares: int,
        price_path: np.ndarray,
    ):
        self.symbol = symbol
        self.stock_name = stock_name
        self.order_type = order_type
        self.total_shares = total_shares
        self.remaining_shares = total_shares
        self.price_path = price_path       # full GBM path (revealed incrementally)
        self.price_history: list[float] = []  # prices observed so far


class SimulationState:
    """Tracks the state of a running compressed trading simulation."""

    def __init__(
        self,
        total_steps: int,
        duration_seconds: int,
        stock_contexts: list[StockExecutionContext],
    ):
        self.status: str = "running"              # "running" | "completed"
        self.total_steps: int = total_steps
        self.current_step: int = 0
        self.duration_seconds: int = duration_seconds
        self.start_time: float = time.time()
        self.stock_contexts: list[StockExecutionContext] = stock_contexts
        self.executed_slices: list[dict] = []      # trades that actually happened
        self.execution_report: list[dict] = []     # final order-level report


class DemoSession:
    """In-memory representation of a demo user's portfolio."""

    def __init__(self, session_id: str, capital: float):
        self.session_id = session_id
        self.capital = capital
        self.cash_balance = capital
        self.holdings: dict[str, int] = {}           # symbol → quantity
        self.avg_prices: dict[str, float] = {}       # symbol → average buy price
        self.target_weights: dict[str, float] = {}   # symbol → weight
        self.target_quantities: dict[str, int] = {}  # symbol → target qty
        self.orders: list[dict] = []                 # order history
        self.transactions: list[dict] = []           # transaction history
        self.created_at = datetime.now(timezone.utc)
        self.simulated_prices: dict[str, float] = {} # current simulated prices
        self.realized_pnl: float = 0.0
        self.simulation: SimulationState | None = None  # active simulation


class DemoService:
    """
    Manages demo sessions with simulated market trading.

    Demo sessions are stored in-memory and do not persist across restarts.
    """

    def __init__(self):
        self._sessions: dict[str, DemoSession] = {}
        self._market_data = MarketDataService()
        self._portfolio_agent = PortfolioAgent()
        self._trading_agent = TradingAgent()

    # ── Session Management ────────────────────────────────────────────

    def create_session(self, capital: float) -> dict:
        """Create a new demo session with initial capital."""
        max_investment = settings.demo_max_investment
        if capital > max_investment:
            raise ValueError(
                f"Demo mode investment limit is ₹{max_investment:,.2f}."
            )

        session_id = str(uuid.uuid4())
        session = DemoSession(session_id=session_id, capital=capital)

        # Initialize with real current prices
        symbols = get_symbols()
        prices = self._market_data.get_current_prices(symbols)
        session.simulated_prices = prices.copy()

        # Initialize holdings at 0 for all stocks
        for stock in STOCK_UNIVERSE:
            session.holdings[stock["symbol"]] = 0
            session.avg_prices[stock["symbol"]] = 0.0

        self._sessions[session_id] = session

        return {
            "session_id": session_id,
            "capital": capital,
            "max_investment": max_investment,
        }

    # ── Portfolio Optimization ────────────────────────────────────────

    def optimize_portfolio(self, session_id: str) -> dict:
        """
        Run PPO portfolio optimization for the demo session.

        Returns target allocations. Applies greedy fill to invest
        all capital (no idle cash balance).
        """
        session = self._get_session(session_id)
        prices = session.simulated_prices

        # Get PPO weights (or equal weights if model not trained)
        num_stocks = len(STOCK_UNIVERSE)
        if self._portfolio_agent.is_trained:
            try:
                symbols = get_symbols()
                data = self._market_data.get_historical_data(symbols, period="6mo")
                close_prices = data["Close"][symbols].dropna()
                returns = MarketDataService.compute_returns(close_prices)
                features_df = MarketDataService.compute_technical_indicators(close_prices)

                # Align indices and drop NaN rows (same as training)
                common_index = returns.index.intersection(features_df.index)
                returns = returns.loc[common_index]
                features_df = features_df.loc[common_index].dropna()
                returns = returns.loc[features_df.index]

                returns_array = returns.values.astype(np.float32)
                features_array = features_df.values.astype(np.float32)
                weights = self._portfolio_agent.generate_weights(
                    returns=returns_array,
                    features=features_array,
                )
            except Exception:
                weights = np.ones(num_stocks) / num_stocks
        else:
            weights = np.ones(num_stocks) / num_stocks

        # Calculate allocations
        total_value = session.cash_balance + sum(
            session.holdings.get(s["symbol"], 0) * prices.get(s["symbol"], 0)
            for s in STOCK_UNIVERSE
        )

        # First pass: floor-based allocation
        alloc_data = []  # (index, symbol, weight, price, target_qty)
        total_allocated = 0.0

        for i, stock in enumerate(STOCK_UNIVERSE):
            symbol = stock["symbol"]
            weight = float(weights[i])
            price = prices.get(symbol, 0.0)

            if price <= 0:
                continue

            target_amount = total_value * weight
            target_qty = math.floor(target_amount / price)
            total_allocated += target_qty * price
            alloc_data.append((i, symbol, weight, price, target_qty))

        # Build final quantity lookup directly from target_qty
        final_qty_map = {item[1]: item[4] for item in alloc_data}

        allocations = []
        for i, symbol, weight, price, _ in sorted(alloc_data, key=lambda x: x[0]):
            target_qty = final_qty_map.get(symbol, 0)
            stock_info = get_stock_info(symbol) or {}

            session.target_weights[symbol] = weight
            session.target_quantities[symbol] = target_qty

            allocations.append({
                "stock_symbol": symbol,
                "stock_name": stock_info.get("name", symbol),
                "sector": stock_info.get("sector", ""),
                "weight": round(weight, 6),
                "target_amount": round(target_qty * price, 2),
                "target_quantity": target_qty,
                "current_price": round(price, 2),
                "current_holding": session.holdings.get(symbol, 0),
                "diff": target_qty - session.holdings.get(symbol, 0),
            })

        return {
            "session_id": session_id,
            "total_value": round(total_value, 2),
            "allocations": allocations,
        }

    # ── Step-by-Step Trading Simulation ───────────────────────────────

    def start_trading_simulation(self, session_id: str) -> dict:
        """
        Start a compressed, step-by-step trading simulation.

        At each tick the agent observes only the current simulated price
        and decides whether to trade and how many shares. Prices are
        revealed one at a time from a pre-generated GBM path.

        Returns metadata about the simulation.
        """
        session = self._get_session(session_id)

        if session.simulation and session.simulation.status == "running":
            raise ValueError("A simulation is already running for this session.")

        prices = session.simulated_prices
        total_steps = settings.demo_simulation_steps
        duration = settings.demo_simulation_duration_seconds

        # ── Build execution contexts per stock ──
        stock_contexts: list[StockExecutionContext] = []
        for stock in STOCK_UNIVERSE:
            symbol = stock["symbol"]
            target = session.target_quantities.get(symbol, 0)
            current = session.holdings.get(symbol, 0)
            diff = target - current

            if diff == 0:
                continue

            base_price = prices.get(symbol, 0.0)
            if base_price <= 0:
                continue

            # Generate simulated intraday price path
            price_path = TradingAgent._generate_price_path(
                initial_price=base_price,
                num_steps=total_steps,
                volatility=0.012,
            )

            ctx = StockExecutionContext(
                symbol=symbol,
                stock_name=stock["name"],
                order_type="BUY" if diff > 0 else "SELL",
                total_shares=abs(diff),
                price_path=price_path,
            )
            stock_contexts.append(ctx)

        if not stock_contexts:
            return {
                "status": "completed",
                "message": "No trades needed — portfolio is already at target.",
                "total_steps": 0,
                "duration_seconds": 0,
            }

        # Initialize simulation state
        sim = SimulationState(
            total_steps=total_steps,
            duration_seconds=duration,
            stock_contexts=stock_contexts,
        )
        session.simulation = sim

        # Start the background task
        asyncio.ensure_future(self._run_simulation(session))

        return {
            "status": "started",
            "total_steps": total_steps,
            "num_stocks": len(stock_contexts),
            "duration_seconds": duration,
        }

    async def _run_simulation(self, session: DemoSession):
        """
        Background task: step-by-step trading simulation.

        At each tick:
        1. Reveal the current price for each stock (from GBM path)
        2. Ask the PPO agent for a single-step decision
        3. If agent decides to trade, apply the trade to session state
        4. On the last step, force-execute all remaining shares
        """
        sim = session.simulation
        if sim is None:
            return

        total_steps = sim.total_steps
        interval = sim.duration_seconds / max(total_steps, 1)

        for step in range(total_steps):
            is_last = (step == total_steps - 1)
            now_iso = datetime.now(timezone.utc).isoformat()

            # ── Process each stock at this tick ──
            for ctx in sim.stock_contexts:
                if ctx.remaining_shares <= 0:
                    continue

                # Reveal the current price (step-by-step, no future look-ahead)
                current_price = float(ctx.price_path[step])
                ctx.price_history.append(current_price)

                # Ask the agent for a decision
                try:
                    shares, exec_price = self._trading_agent.decide_single_step(
                        remaining_shares=ctx.remaining_shares,
                        total_shares=ctx.total_shares,
                        current_step=step,
                        total_steps=total_steps,
                        current_price=current_price,
                        price_history=ctx.price_history,
                        order_type=ctx.order_type,
                        is_last_step=is_last,
                    )
                except FileNotFoundError:
                    # Model not trained — TWAP fallback: distribute evenly
                    if is_last:
                        shares = ctx.remaining_shares
                    else:
                        remaining_steps = total_steps - step
                        shares = max(1, ctx.remaining_shares // max(remaining_steps, 1))
                        shares = min(shares, ctx.remaining_shares)
                    exec_price = round(current_price, 4)

                if shares <= 0:
                    continue

                # ── Apply the trade ──
                cost = shares * exec_price
                symbol = ctx.symbol

                if ctx.order_type == "BUY":
                    if cost > session.cash_balance:
                        # Prevent negative cash balance by capping shares
                        shares = max(0, int(session.cash_balance // exec_price))
                        cost = shares * exec_price
                    
                    if shares > 0:
                        old_qty = session.holdings.get(symbol, 0)
                        old_avg = session.avg_prices.get(symbol, 0.0)
                        new_qty = old_qty + shares
                        session.avg_prices[symbol] = (
                            old_avg * old_qty + exec_price * shares
                        ) / new_qty
                        session.holdings[symbol] = new_qty
                        session.cash_balance -= cost

                elif ctx.order_type == "SELL":
                    avg = session.avg_prices.get(symbol, 0.0)
                    pnl = shares * (exec_price - avg)
                    session.realized_pnl += pnl
                    session.holdings[symbol] = max(
                        0, session.holdings.get(symbol, 0) - shares
                    )
                    session.cash_balance += cost

                ctx.remaining_shares -= shares

                # Record the execution
                sim.executed_slices.append({
                    "stock_symbol": symbol,
                    "stock_name": ctx.stock_name,
                    "order_type": ctx.order_type,
                    "quantity": shares,
                    "price": exec_price,
                    "time": now_iso,
                    "step": step,
                })

            sim.current_step = step + 1

            # ── Early termination: all shares purchased ──
            all_done = all(
                ctx.remaining_shares <= 0 for ctx in sim.stock_contexts
            )
            if all_done:
                logger.info(
                    f"All shares purchased at step {step + 1}/{total_steps}. "
                    "Terminating simulation early."
                )
                break

            # Wait for the next tick (unless it's the last step)
            if step < total_steps - 1:
                await asyncio.sleep(interval)

        # ── Simulation complete ──
        self._finalize_simulation(session)

    def _finalize_simulation(self, session: DemoSession):
        """Build the final execution report and mark simulation complete."""
        sim = session.simulation
        if sim is None:
            return

        # Aggregate executed slices into per-stock reports
        report_map: dict[str, dict] = {}
        for entry in sim.executed_slices:
            symbol = entry["stock_symbol"]
            if symbol not in report_map:
                ctx = next(
                    (c for c in sim.stock_contexts if c.symbol == symbol), None
                )
                report_map[symbol] = {
                    "stock_symbol": symbol,
                    "stock_name": entry["stock_name"],
                    "order_type": entry["order_type"],
                    "total_quantity": ctx.total_shares if ctx else 0,
                    "filled_quantity": 0,
                    "slices": [],
                    "status": "FILLED",
                }
            report_map[symbol]["filled_quantity"] += entry["quantity"]
            report_map[symbol]["slices"].append({
                "quantity": entry["quantity"],
                "price": entry["price"],
                "time": entry["time"],
                "step": entry["step"],
            })

        sim.execution_report = list(report_map.values())
        session.orders.extend(sim.execution_report)

        # Update simulated prices (small random movement after trading)
        for stock in STOCK_UNIVERSE:
            symbol = stock["symbol"]
            old_price = session.simulated_prices.get(symbol, 0.0)
            if old_price > 0:
                change = np.random.uniform(-0.01, 0.01)
                session.simulated_prices[symbol] = round(
                    old_price * (1 + change), 2
                )

        sim.status = "completed"
        logger.info(
            f"Demo simulation completed for session {session.session_id}: "
            f"{len(sim.executed_slices)} trades in {sim.total_steps} steps"
        )

    def get_simulation_status(self, session_id: str) -> dict:
        """
        Get the current status of a running or completed simulation.

        Progress is based on time steps (not trade count), since the agent
        may decide to wait at some steps.
        """
        session = self._get_session(session_id)
        sim = session.simulation

        if sim is None:
            return {"status": "idle", "message": "No simulation running."}

        elapsed = time.time() - sim.start_time
        progress = min(100.0, (sim.current_step / max(sim.total_steps, 1)) * 100)

        result = {
            "status": sim.status,
            "total_steps": sim.total_steps,
            "current_step": sim.current_step,
            "trades_executed": len(sim.executed_slices),
            "progress_percent": round(progress, 1),
            "elapsed_seconds": round(elapsed, 1),
            "duration_seconds": sim.duration_seconds,
            "executed_slices": sim.executed_slices[-20:],  # last 20 trades
        }

        if sim.status == "completed":
            result["execution_report"] = sim.execution_report
            result["orders_executed"] = len(sim.execution_report)

        return result

    # ── Status ────────────────────────────────────────────────────────

    def get_status(self, session_id: str) -> dict:
        """Get the current demo portfolio status."""
        session = self._get_session(session_id)
        prices = session.simulated_prices

        holdings_status = []
        total_invested = 0.0
        total_market_value = 0.0

        for stock in STOCK_UNIVERSE:
            symbol = stock["symbol"]
            qty = session.holdings.get(symbol, 0)
            if qty <= 0:
                continue

            avg_price = session.avg_prices.get(symbol, 0.0)
            current_price = prices.get(symbol, 0.0)
            invested = qty * avg_price
            current_value = qty * current_price
            pnl = current_value - invested
            pnl_pct = (pnl / invested * 100) if invested > 0 else 0.0

            total_invested += invested
            total_market_value += current_value

            holdings_status.append({
                "stock_symbol": symbol,
                "stock_name": stock["name"],
                "sector": stock["sector"],
                "quantity": qty,
                "average_buy_price": round(avg_price, 2),
                "current_price": round(current_price, 2),
                "invested_amount": round(invested, 2),
                "current_value": round(current_value, 2),
                "profit_loss": round(pnl, 2),
                "profit_loss_percent": round(pnl_pct, 2),
            })

        unrealized_pnl = total_market_value - total_invested
        total_pnl = unrealized_pnl + session.realized_pnl
        total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0

        return {
            "session_id": session_id,
            "total_capital": round(session.capital, 2),
            "cash_balance": round(session.cash_balance, 2),
            "total_invested": round(total_invested, 2),
            "current_market_value": round(total_market_value, 2),
            "total_profit_loss": round(total_pnl, 2),
            "total_profit_loss_percent": round(total_pnl_pct, 2),
            "realized_profit_loss": round(session.realized_pnl, 2),
            "unrealized_profit_loss": round(unrealized_pnl, 2),
            "holdings": holdings_status,
        }

    # ── Fund Management ───────────────────────────────────────────────

    def add_funds(self, session_id: str, amount: float) -> dict:
        """Add funds to the demo portfolio."""
        session = self._get_session(session_id)
        max_investment = settings.demo_max_investment
        if session.capital + amount > max_investment:
            raise ValueError(f"Demo mode total investment limit is ₹{max_investment:,.2f}.")

        session.capital += amount
        session.cash_balance += amount
        return {"capital": session.capital, "cash_balance": session.cash_balance}

    def withdraw_funds(self, session_id: str, amount: float) -> dict:
        """
        Withdraw funds by selling shares.

        Approach:
        1. Calculate current portfolio market value
        2. Compute remaining target value = current - withdrawal
        3. Re-optimize portfolio at reduced value
        4. Compute sell orders: sell_qty = current_holding - new_target
        5. Start a sell simulation (step-by-step, same as trading)
        6. After simulation completes, deduct the withdrawal amount

        Returns simulation metadata (poll simulation-status for progress).
        """
        session = self._get_session(session_id)
        prices = session.simulated_prices

        if session.simulation and session.simulation.status == "running":
            raise ValueError("A simulation is already running. Wait for it to complete.")

        # Current market value of holdings
        market_value = sum(
            session.holdings.get(s["symbol"], 0) * prices.get(s["symbol"], 0)
            for s in STOCK_UNIVERSE
        )
        total_value = market_value + session.cash_balance

        if amount > market_value:
            raise ValueError(
                f"Cannot withdraw ₹{amount:,.2f}. "
                f"Current market value of your holdings is ₹{market_value:,.2f}."
            )

        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive.")

        # ── Compute new target allocations at reduced value ──
        remaining_value = total_value - amount

        # Get current weights (or equal weights)
        num_stocks = len(STOCK_UNIVERSE)
        weights = {}
        total_weight = sum(session.target_weights.values())
        if total_weight > 0:
            # Reuse existing weights
            for stock in STOCK_UNIVERSE:
                symbol = stock["symbol"]
                weights[symbol] = session.target_weights.get(symbol, 1.0 / num_stocks)
        else:
            for stock in STOCK_UNIVERSE:
                weights[stock["symbol"]] = 1.0 / num_stocks

        # Compute new target quantities at reduced value
        total_steps = settings.demo_simulation_steps
        stock_contexts: list[StockExecutionContext] = []

        for stock in STOCK_UNIVERSE:
            symbol = stock["symbol"]
            price = prices.get(symbol, 0.0)
            if price <= 0:
                continue

            current_qty = session.holdings.get(symbol, 0)
            new_target_amt = remaining_value * weights.get(symbol, 0)
            new_target_qty = math.floor(new_target_amt / price)
            sell_qty = current_qty - new_target_qty

            if sell_qty <= 0:
                continue

            # Update the target quantity
            session.target_quantities[symbol] = new_target_qty

            # Generate price path for sell simulation
            price_path = TradingAgent._generate_price_path(
                initial_price=price,
                num_steps=total_steps,
                volatility=0.012,
            )

            ctx = StockExecutionContext(
                symbol=symbol,
                stock_name=stock["name"],
                order_type="SELL",
                total_shares=sell_qty,
                price_path=price_path,
            )
            stock_contexts.append(ctx)

        if not stock_contexts:
            # No shares to sell — just deduct from cash
            session.cash_balance -= min(amount, session.cash_balance)
            session.capital = max(0, session.capital - amount)
            return {
                "status": "completed",
                "message": "Withdrawal processed from cash balance.",
                "withdrawal_amount": amount,
            }

        # Store withdrawal amount to deduct after simulation completes
        session._pending_withdrawal = amount

        # Start sell simulation
        duration = settings.demo_simulation_duration_seconds
        sim = SimulationState(
            total_steps=total_steps,
            duration_seconds=duration,
            stock_contexts=stock_contexts,
        )
        session.simulation = sim

        asyncio.ensure_future(self._run_withdrawal_simulation(session))

        return {
            "status": "started",
            "total_steps": total_steps,
            "num_stocks": len(stock_contexts),
            "duration_seconds": duration,
            "withdrawal_amount": amount,
        }

    async def _run_withdrawal_simulation(self, session: DemoSession):
        """
        Run sell simulation for withdrawal, then deduct the amount.

        Reuses the same step-by-step logic as _run_simulation().
        """
        await self._run_simulation(session)

        # After simulation completes, deduct withdrawal
        withdrawal = getattr(session, "_pending_withdrawal", 0)
        if withdrawal > 0:
            session.capital = max(0, session.capital - withdrawal)
            # Cash balance was already increased by sell proceeds during simulation
            # Now deduct the withdrawal amount
            session.cash_balance -= withdrawal
            session._pending_withdrawal = 0
            logger.info(
                f"Withdrawal of ₹{withdrawal:,.2f} completed for session "
                f"{session.session_id}"
            )

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_session(self, session_id: str) -> DemoSession:
        """Retrieve a demo session by ID."""
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError("Demo session not found. Please start a new demo.")
        return session
