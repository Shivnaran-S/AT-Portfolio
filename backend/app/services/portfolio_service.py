"""
Portfolio service — handles portfolio initialization, status, rebalancing, and fund management.
"""

import logging
import math
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.portfolio import Portfolio, Holding, TargetAllocation
from app.models.transaction import Transaction
from app.stock_config import STOCK_UNIVERSE, get_symbols, get_stock_info
from app.rl.data.market_data import MarketDataService
from app.rl.agents.portfolio_agent import PortfolioAgent

logger = logging.getLogger(__name__)


class PortfolioService:
    """Handles all portfolio-related business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._market_data = MarketDataService()
        self._portfolio_agent = PortfolioAgent()

    # ── Initialize Portfolio ──────────────────────────────────────────

    async def preview_initialization(self, user_id: str, capital: float) -> dict:
        """
        Generate an initialization plan without saving to the database.
        """
        max_inv = settings.max_investment
        if capital > max_inv:
            raise ValueError(f"Maximum investment limit is ₹{max_inv:,.2f}.")

        query = select(Portfolio).where(Portfolio.user_id == user_id)
        result = await self.db.execute(query)
        if result.scalar_one_or_none() is not None:
            raise ValueError("User already has a portfolio.")

        symbols = get_symbols()
        prices = self._market_data.get_current_prices(symbols)
        weights = self._get_portfolio_weights()

        alloc_data = []
        total_allocated = 0.0

        for i, stock in enumerate(STOCK_UNIVERSE):
            symbol = stock["symbol"]
            weight = float(weights[i]) if i < len(weights) else 0.0
            price = prices.get(symbol, 0.0)

            if price <= 0:
                continue

            target_amount = capital * weight
            target_quantity = math.floor(target_amount / price)
            actual_amount = target_quantity * price
            total_allocated += actual_amount
            alloc_data.append((i, symbol, weight, price, target_quantity))

        allocations = []
        for i, symbol, weight, price, target_quantity in sorted(alloc_data, key=lambda x: x[0]):
            actual_amount = target_quantity * price
            stock_info = get_stock_info(symbol) or {}
            
            allocations.append({
                "stock_symbol": symbol,
                "stock_name": stock_info.get("name", symbol),
                "sector": stock_info.get("sector", ""),
                "weight": round(weight, 6),
                "target_amount": round(actual_amount, 2),
                "target_quantity": target_quantity,
                "current_price": round(price, 2),
                "diff": target_quantity,  # for preview tables
            })

        return {
            "total_capital": capital,
            "cash_after_allocation": round(capital - total_allocated, 2),
            "allocations": allocations,
        }

    async def confirm_initialization(self, user_id: str, plan: dict) -> dict:
        """
        Save the previewed initialization plan to the database.
        """
        capital = plan["total_capital"]
        
        query = select(Portfolio).where(Portfolio.user_id == user_id)
        result = await self.db.execute(query)
        if result.scalar_one_or_none() is not None:
            raise ValueError("User already has a portfolio.")

        portfolio = Portfolio(
            user_id=user_id,
            total_capital=Decimal(str(capital)),
            cash_balance=Decimal(str(capital)),
        )
        self.db.add(portfolio)
        await self.db.flush()

        for a in plan["allocations"]:
            holding = Holding(
                portfolio_id=portfolio.id,
                stock_symbol=a["stock_symbol"],
                quantity=0,
                average_buy_price=Decimal("0.0000"),
            )
            self.db.add(holding)

            target = TargetAllocation(
                portfolio_id=portfolio.id,
                stock_symbol=a["stock_symbol"],
                weight=Decimal(str(a["weight"])),
                target_quantity=a["target_quantity"],
                target_amount=Decimal(str(a["target_amount"])),
            )
            self.db.add(target)

        transaction = Transaction(
            portfolio_id=portfolio.id,
            transaction_type="DEPOSIT",
            amount=Decimal(str(capital)),
            description=f"Initial investment of ₹{capital:,.2f}",
        )
        self.db.add(transaction)
        await self.db.commit()

        return {
            "portfolio_id": portfolio.id,
            "total_capital": capital,
            "cash_after_allocation": plan["cash_after_allocation"],
            "allocations": plan["allocations"],
        }

    # ── Portfolio Status ──────────────────────────────────────────────

    async def get_portfolio_status(self, user_id: str) -> dict:
        """
        Get comprehensive portfolio status including all P&L metrics.

        Calculates per-stock and total:
        - Invested amount, current value, P&L, P&L %
        - Realized and unrealized P&L
        """
        portfolio = await self._get_portfolio(user_id)
        if portfolio is None:
            raise ValueError("No portfolio found for this user.")

        # Load holdings
        query = select(Holding).where(Holding.portfolio_id == portfolio.id)
        result = await self.db.execute(query)
        holdings = result.scalars().all()

        # Get current prices
        symbols = get_symbols()
        prices = self._market_data.get_current_prices(symbols)

        # Calculate realized P&L from sell transactions
        tx_query = select(Transaction).where(
            Transaction.portfolio_id == portfolio.id,
            Transaction.transaction_type == "SELL",
        )
        tx_result = await self.db.execute(tx_query)
        sell_transactions = tx_result.scalars().all()
        realized_pnl = sum(float(tx.amount) for tx in sell_transactions)

        # Build holdings status
        holdings_status = []
        total_invested = 0.0
        total_current_value = 0.0

        for holding in holdings:
            if holding.quantity <= 0:
                continue

            stock_info = get_stock_info(holding.stock_symbol) or {}
            current_price = prices.get(holding.stock_symbol, 0.0)
            avg_price = float(holding.average_buy_price)

            invested = holding.quantity * avg_price
            current_value = holding.quantity * current_price
            pnl = current_value - invested
            pnl_pct = (pnl / invested * 100) if invested > 0 else 0.0

            total_invested += invested
            total_current_value += current_value

            holdings_status.append({
                "stock_symbol": holding.stock_symbol,
                "stock_name": stock_info.get("name", holding.stock_symbol),
                "sector": stock_info.get("sector", ""),
                "quantity": holding.quantity,
                "average_buy_price": round(avg_price, 2),
                "current_price": round(current_price, 2),
                "invested_amount": round(invested, 2),
                "current_value": round(current_value, 2),
                "profit_loss": round(pnl, 2),
                "profit_loss_percent": round(pnl_pct, 2),
            })

        total_pnl = total_current_value - total_invested + realized_pnl
        total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0
        unrealized_pnl = total_current_value - total_invested

        return {
            "portfolio_id": portfolio.id,
            "total_capital": float(portfolio.total_capital),
            "cash_balance": float(portfolio.cash_balance),
            "total_invested": round(total_invested, 2),
            "current_market_value": round(total_current_value, 2),
            "total_profit_loss": round(total_pnl, 2),
            "total_profit_loss_percent": round(total_pnl_pct, 2),
            "realized_profit_loss": round(realized_pnl, 2),
            "unrealized_profit_loss": round(unrealized_pnl, 2),
            "holdings": holdings_status,
        }

    # ── Fund Management ───────────────────────────────────────────────

    async def add_funds(self, user_id: str, amount: float) -> dict:
        """Add funds to the portfolio's cash balance.

        The total invested capital (total_capital + amount) cannot
        exceed the configured maximum investment limit.
        """
        portfolio = await self._get_portfolio(user_id)
        if portfolio is None:
            raise ValueError("No portfolio found.")

        # Enforce maximum investment limit
        max_inv = settings.max_investment
        new_total = float(portfolio.total_capital) + amount
        if new_total > max_inv:
            remaining = max_inv - float(portfolio.total_capital)
            raise ValueError(
                f"Maximum investment limit is ₹{max_inv:,.2f}. "
                f"You can add up to ₹{max(0, remaining):,.2f} more."
            )

        portfolio.total_capital += Decimal(str(amount))
        portfolio.cash_balance += Decimal(str(amount))

        transaction = Transaction(
            portfolio_id=portfolio.id,
            transaction_type="DEPOSIT",
            amount=Decimal(str(amount)),
            description=f"Added ₹{amount:,.2f} to portfolio",
        )
        self.db.add(transaction)
        await self.db.commit()

        return {
            "total_capital": float(portfolio.total_capital),
            "cash_balance": float(portfolio.cash_balance),
        }

    async def withdraw_funds(self, user_id: str, amount: float) -> dict:
        """
        Instantly withdraw funds from cash balance.
        """
        portfolio = await self._get_portfolio(user_id)
        if portfolio is None:
            raise ValueError("No portfolio found.")

        if amount > float(portfolio.cash_balance):
            raise ValueError(f"Cannot instantly withdraw ₹{amount:,.2f}. Available cash is ₹{portfolio.cash_balance:,.2f}.")

        portfolio.cash_balance -= Decimal(str(amount))
        portfolio.total_capital -= Decimal(str(amount))

        transaction = Transaction(
            portfolio_id=portfolio.id,
            transaction_type="WITHDRAWAL",
            amount=Decimal(str(amount)),
            description=f"Withdrew ₹{amount:,.2f} from portfolio",
        )
        self.db.add(transaction)
        await self.db.commit()

        return {
            "total_capital": float(portfolio.total_capital),
            "cash_balance": float(portfolio.cash_balance),
        }

    # ── Rebalancing ───────────────────────────────────────────────────

    async def preview_rebalance(self, user_id: str) -> dict:
        """
        Preview a portfolio rebalance without generating orders or modifying the database.
        """
        portfolio = await self._get_portfolio(user_id)
        if portfolio is None:
            raise ValueError("No portfolio found.")

        symbols = get_symbols()
        prices = self._market_data.get_current_prices(symbols)

        query = select(Holding).where(Holding.portfolio_id == portfolio.id)
        result = await self.db.execute(query)
        holdings = result.scalars().all()

        market_value = sum(
            h.quantity * prices.get(h.stock_symbol, 0.0) for h in holdings
        )
        total_value = float(portfolio.cash_balance) + market_value

        weights = self._get_portfolio_weights()

        alloc_data = []
        current_holdings = {h.stock_symbol: h.quantity for h in holdings}
        total_allocated = 0.0

        for i, stock in enumerate(STOCK_UNIVERSE):
            symbol = stock["symbol"]
            weight = float(weights[i]) if i < len(weights) else 0.0
            price = prices.get(symbol, 0.0)

            if price <= 0:
                continue

            target_amount = total_value * weight
            target_quantity = math.floor(target_amount / price)
            total_allocated += target_quantity * price
            alloc_data.append((i, symbol, weight, price, target_quantity))

        final_qty_map = {item[1]: item[4] for item in alloc_data}

        orders = []
        allocations = []
        for i, symbol, weight, price, _ in sorted(alloc_data, key=lambda x: x[0]):
            target_quantity = final_qty_map.get(symbol, 0)
            current_quantity = current_holdings.get(symbol, 0)
            diff = target_quantity - current_quantity

            stock_info = get_stock_info(symbol) or {}
            actual_amount = target_quantity * price

            allocations.append({
                "stock_symbol": symbol,
                "stock_name": stock_info.get("name", symbol),
                "sector": stock_info.get("sector", ""),
                "weight": round(weight, 6),
                "target_amount": round(actual_amount, 2),
                "target_quantity": target_quantity,
                "current_price": round(price, 2),
                "diff": diff,
            })

            if diff != 0:
                orders.append({
                    "stock_symbol": symbol,
                    "stock_name": stock_info.get("name", symbol),
                    "order_type": "BUY" if diff > 0 else "SELL",
                    "quantity": abs(diff),
                    "current_price": round(price, 2),
                    "current_holding": current_quantity,
                    "target_holding": target_quantity,
                })

        return {
            "portfolio_id": portfolio.id,
            "total_value": round(total_value, 2),
            "allocations": allocations,
            "orders": orders,
        }

    async def confirm_rebalance(self, user_id: str, plan: dict) -> dict:
        """
        Confirm a rebalance plan, updating targets.
        """
        portfolio = await self._get_portfolio(user_id)
        if portfolio is None:
            raise ValueError("No portfolio found.")

        # Update targets
        for a in plan["allocations"]:
            symbol = a["stock_symbol"]
            target_query = select(TargetAllocation).where(
                TargetAllocation.portfolio_id == portfolio.id,
                TargetAllocation.stock_symbol == symbol,
            )
            target_result = await self.db.execute(target_query)
            target = target_result.scalar_one_or_none()

            if target:
                target.weight = Decimal(str(a["weight"]))
                target.target_quantity = a["target_quantity"]
                target.target_amount = Decimal(str(a["target_amount"]))
            else:
                target = TargetAllocation(
                    portfolio_id=portfolio.id,
                    stock_symbol=symbol,
                    weight=Decimal(str(a["weight"])),
                    target_quantity=a["target_quantity"],
                    target_amount=Decimal(str(a["target_amount"])),
                )
                self.db.add(target)

        await self.db.commit()

        return {
            "portfolio_id": portfolio.id,
            "orders": plan.get("orders", []),
        }

    async def preview_withdraw(self, user_id: str, amount: float) -> dict:
        """
        Preview a withdrawal that exceeds cash balance, calculating optimal sells.
        """
        portfolio = await self._get_portfolio(user_id)
        if portfolio is None:
            raise ValueError("No portfolio found.")

        symbols = get_symbols()
        prices = self._market_data.get_current_prices(symbols)

        query = select(Holding).where(Holding.portfolio_id == portfolio.id)
        result = await self.db.execute(query)
        holdings = result.scalars().all()

        market_value = sum(
            h.quantity * prices.get(h.stock_symbol, 0.0) for h in holdings
        )
        total_value = float(portfolio.cash_balance) + market_value

        if amount > total_value:
            raise ValueError(f"Cannot withdraw ₹{amount:,.2f}. Total portfolio value is ₹{total_value:,.2f}.")
            
        target_total_value = total_value - amount
        weights = self._get_portfolio_weights()

        alloc_data = []
        current_holdings = {h.stock_symbol: h.quantity for h in holdings}
        total_allocated = 0.0

        for i, stock in enumerate(STOCK_UNIVERSE):
            symbol = stock["symbol"]
            weight = float(weights[i]) if i < len(weights) else 0.0
            price = prices.get(symbol, 0.0)

            if price <= 0:
                continue

            target_amount = target_total_value * weight
            target_quantity = math.floor(target_amount / price)
            total_allocated += target_quantity * price
            alloc_data.append((i, symbol, weight, price, target_quantity))

        final_qty_map = {item[1]: item[4] for item in alloc_data}

        orders = []
        allocations = []
        for i, symbol, weight, price, _ in sorted(alloc_data, key=lambda x: x[0]):
            target_quantity = final_qty_map.get(symbol, 0)
            current_quantity = current_holdings.get(symbol, 0)
            diff = target_quantity - current_quantity

            stock_info = get_stock_info(symbol) or {}
            actual_amount = target_quantity * price

            allocations.append({
                "stock_symbol": symbol,
                "stock_name": stock_info.get("name", symbol),
                "sector": stock_info.get("sector", ""),
                "weight": round(weight, 6),
                "target_amount": round(actual_amount, 2),
                "target_quantity": target_quantity,
                "current_price": round(price, 2),
                "diff": diff,
            })

            if diff != 0:
                orders.append({
                    "stock_symbol": symbol,
                    "stock_name": stock_info.get("name", symbol),
                    "order_type": "BUY" if diff > 0 else "SELL",
                    "quantity": abs(diff),
                    "current_price": round(price, 2),
                    "current_holding": current_quantity,
                    "target_holding": target_quantity,
                })

        return {
            "portfolio_id": portfolio.id,
            "total_value": round(target_total_value, 2),
            "allocations": allocations,
            "orders": orders,
        }

    async def confirm_withdraw(self, user_id: str, amount: float, plan: dict) -> dict:
        """
        Confirm a withdrawal plan, updating capital, cash, targets, and logging transaction.
        """
        portfolio = await self._get_portfolio(user_id)
        if portfolio is None:
            raise ValueError("No portfolio found.")

        # Update capital
        portfolio.total_capital -= Decimal(str(amount))

        # Withdraw from cash as much as possible, rest will come from sells
        if amount <= float(portfolio.cash_balance):
            portfolio.cash_balance -= Decimal(str(amount))
        else:
            portfolio.cash_balance = Decimal("0.00")
            
        # Log transaction
        transaction = Transaction(
            portfolio_id=portfolio.id,
            transaction_type="WITHDRAWAL",
            amount=Decimal(str(amount)),
            description=f"Withdrew ₹{amount:,.2f} from portfolio",
        )
        self.db.add(transaction)

        # Update targets
        for a in plan["allocations"]:
            symbol = a["stock_symbol"]
            target_query = select(TargetAllocation).where(
                TargetAllocation.portfolio_id == portfolio.id,
                TargetAllocation.stock_symbol == symbol,
            )
            target_result = await self.db.execute(target_query)
            target = target_result.scalar_one_or_none()

            if target:
                target.weight = Decimal(str(a["weight"]))
                target.target_quantity = a["target_quantity"]
                target.target_amount = Decimal(str(a["target_amount"]))
            else:
                target = TargetAllocation(
                    portfolio_id=portfolio.id,
                    stock_symbol=symbol,
                    weight=Decimal(str(a["weight"])),
                    target_quantity=a["target_quantity"],
                    target_amount=Decimal(str(a["target_amount"])),
                )
                self.db.add(target)

        await self.db.commit()

        return {
            "portfolio_id": portfolio.id,
            "orders": plan["orders"],
        }

    # ── Helpers ───────────────────────────────────────────────────────

    async def _get_portfolio(self, user_id: str) -> Portfolio | None:
        """Fetch the user's portfolio."""
        query = select(Portfolio).where(Portfolio.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    def _get_portfolio_weights(self) -> list[float]:
        """
        Get optimal portfolio weights from the PPO agent.

        If the model isn't trained yet, returns equal weights as a fallback.
        """
        num_stocks = len(STOCK_UNIVERSE)

        if not self._portfolio_agent.is_trained:
            logger.warning("Portfolio PPO model not trained. Using equal weights.")
            weights = [1.0 / num_stocks] * num_stocks
            return weights

        try:
            # Fetch recent data for prediction
            symbols = get_symbols()
            data = self._market_data.get_historical_data(symbols, period="6mo")

            if data.empty:
                logger.warning("No market data available. Using equal weights.")
                return [1.0 / num_stocks] * num_stocks

            close_prices = data["Close"][symbols].dropna()
            import numpy as np
            returns = MarketDataService.compute_returns(close_prices)
            returns_array = returns.values.astype(np.float32)

            features_df = MarketDataService.compute_technical_indicators(close_prices)
            features_df = features_df.loc[returns.index].dropna()
            returns_array = returns_array[-len(features_df):]
            features_array = features_df.values.astype(np.float32)

            weights = self._portfolio_agent.generate_weights(
                returns=returns_array,
                features=features_array,
            )
            return weights.tolist()

        except Exception as e:
            logger.error(f"Error generating weights: {e}. Using equal weights.")
            return [1.0 / num_stocks] * num_stocks
