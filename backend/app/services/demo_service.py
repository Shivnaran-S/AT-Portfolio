"""
Demo service — simulated market environment for demo mode.

Provides the same features as the live system but uses:
- GBM-generated price paths instead of real market data
- Compressed time (2-3 minutes = one trading day)
- In-memory session storage (no database)
"""

import logging
import math
import time
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np

from app.config import settings
from app.stock_config import STOCK_UNIVERSE, get_symbols
from app.rl.agents.portfolio_agent import PortfolioAgent
from app.rl.agents.trading_agent import TradingAgent
from app.rl.data.market_data import MarketDataService

logger = logging.getLogger(__name__)


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

        Returns target allocations.
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

        allocations = []
        for i, stock in enumerate(STOCK_UNIVERSE):
            symbol = stock["symbol"]
            weight = float(weights[i])
            price = prices.get(symbol, 0.0)

            if price <= 0:
                continue

            target_amount = total_value * weight
            target_qty = math.floor(target_amount / price)

            session.target_weights[symbol] = weight
            session.target_quantities[symbol] = target_qty

            allocations.append({
                "stock_symbol": symbol,
                "stock_name": stock["name"],
                "sector": stock["sector"],
                "weight": round(weight, 6),
                "target_amount": round(target_amount, 2),
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

    # ── Simulated Trading ─────────────────────────────────────────────

    def run_trading_simulation(self, session_id: str) -> dict:
        """
        Run a compressed trading simulation (~instant for the API response).

        Simulates an entire trading day:
        1. Calculate order differences (target vs current holdings)
        2. For each order, use PPO trading agent (or TWAP fallback) to plan slices
        3. Simulate price evolution during execution
        4. Update holdings and cash balance

        Returns execution report.
        """
        session = self._get_session(session_id)
        prices = session.simulated_prices

        # Calculate orders needed
        orders_to_execute = []
        for stock in STOCK_UNIVERSE:
            symbol = stock["symbol"]
            target = session.target_quantities.get(symbol, 0)
            current = session.holdings.get(symbol, 0)
            diff = target - current

            if diff != 0:
                orders_to_execute.append({
                    "stock_symbol": symbol,
                    "order_type": "BUY" if diff > 0 else "SELL",
                    "quantity": abs(diff),
                    "price": prices.get(symbol, 0.0),
                })

        # Execute orders with simulated price paths
        execution_report = []
        now = datetime.now(timezone.utc)

        for order in orders_to_execute:
            symbol = order["stock_symbol"]
            base_price = order["price"]
            total_shares = order["quantity"]

            if base_price <= 0 or total_shares <= 0:
                continue

            # Generate simulated intraday price path
            price_path = TradingAgent._generate_price_path(
                initial_price=base_price,
                num_steps=78,
                volatility=0.012,
            )

            # Plan execution
            try:
                slices = self._trading_agent.plan_execution(
                    total_shares=total_shares,
                    price_path=price_path,
                    num_time_steps=78,
                    base_time=now,
                    step_minutes=1,  # Compressed time: 1 min per step
                )
            except FileNotFoundError:
                # TWAP fallback
                slices = self._twap_slices(total_shares, base_price, now)

            # Apply the trades
            total_cost = 0.0
            for s in slices:
                qty = s["quantity"]
                exec_price = s["price"]
                cost = qty * exec_price

                if order["order_type"] == "BUY":
                    # Update average price
                    old_qty = session.holdings.get(symbol, 0)
                    old_avg = session.avg_prices.get(symbol, 0.0)
                    new_qty = old_qty + qty
                    if new_qty > 0:
                        session.avg_prices[symbol] = (old_avg * old_qty + exec_price * qty) / new_qty
                    session.holdings[symbol] = new_qty
                    session.cash_balance -= cost
                    total_cost += cost

                elif order["order_type"] == "SELL":
                    avg = session.avg_prices.get(symbol, 0.0)
                    pnl = qty * (exec_price - avg)
                    session.realized_pnl += pnl
                    session.holdings[symbol] = max(0, session.holdings.get(symbol, 0) - qty)
                    session.cash_balance += cost
                    total_cost -= cost

            # Record order
            order_record = {
                "stock_symbol": symbol,
                "order_type": order["order_type"],
                "total_quantity": total_shares,
                "filled_quantity": sum(s["quantity"] for s in slices),
                "slices": slices,
                "status": "FILLED",
            }
            session.orders.append(order_record)
            execution_report.append(order_record)

        # Update simulated prices (small random movement after trading)
        for stock in STOCK_UNIVERSE:
            symbol = stock["symbol"]
            old_price = session.simulated_prices.get(symbol, 0.0)
            if old_price > 0:
                change = np.random.uniform(-0.01, 0.01)
                session.simulated_prices[symbol] = round(old_price * (1 + change), 2)

        return {
            "session_id": session_id,
            "orders_executed": len(execution_report),
            "execution_report": execution_report,
        }

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
        """Withdraw funds from the demo portfolio.

        Maximum withdrawal is limited to the current market value of
        the shares the user currently holds.
        """
        session = self._get_session(session_id)
        prices = session.simulated_prices

        # Cap = market value of holdings only
        market_value = sum(
            session.holdings.get(s["symbol"], 0) * prices.get(s["symbol"], 0)
            for s in STOCK_UNIVERSE
        )

        if amount > market_value:
            raise ValueError(
                f"Cannot withdraw ₹{amount:,.2f}. "
                f"Current market value of your holdings is ₹{market_value:,.2f}."
            )

        session.cash_balance -= min(amount, session.cash_balance)
        session.capital -= amount
        return {"capital": max(0, session.capital), "cash_balance": max(0, session.cash_balance)}

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_session(self, session_id: str) -> DemoSession:
        """Retrieve a demo session by ID."""
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError("Demo session not found. Please start a new demo.")
        return session

    @staticmethod
    def _twap_slices(total_shares: int, price: float, base_time: datetime) -> list[dict]:
        """Simple TWAP fallback for when PPO model isn't trained."""
        num_slices = min(4, total_shares)
        shares_per = total_shares // num_slices
        remainder = total_shares % num_slices

        slices = []
        for i in range(num_slices):
            qty = shares_per + (1 if i < remainder else 0)
            if qty <= 0:
                continue
            t = base_time + timedelta(seconds=i * 30)
            variation = np.random.uniform(-0.003, 0.003)
            slices.append({
                "time": t.isoformat(),
                "quantity": qty,
                "price": round(price * (1 + variation), 4),
            })
        return slices
