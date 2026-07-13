"""
Trading Agent Backtester.

Evaluates execution quality of the PPO trading agent by running it
on historical 5-minute intraday price data and comparing against
benchmarks (VWAP, arrival price, naive all-at-once).

Uses yfinance for free intraday data (last ~60 days, 5-min interval).
"""

import logging
from datetime import datetime, timezone

import numpy as np

from app.stock_config import get_symbols, get_stock_info, STOCK_UNIVERSE
from app.rl.agents.trading_agent import TradingAgent
from app.rl.data.market_data import MarketDataService

logger = logging.getLogger(__name__)


def run_trading_backtest(
    total_shares: int = 50,
    order_type: str = "BUY",
    num_days: int | None = None,
) -> dict:
    """
    Backtest the PPO trading agent on historical 5-minute intraday data.

    For each available trading day in the last ~60 days:
    1. Load real 5-minute OHLCV data for each stock
    2. Run the PPO agent step-by-step through the real prices
    3. Compare agent's avg execution price to VWAP and arrival price
    4. Compare agent's cost to "naive" (buy everything at step 0)

    Args:
        total_shares: Number of shares to simulate executing per stock per day.
        order_type: "BUY" or "SELL".
        num_days: Max days to backtest (None = all available).

    Returns:
        Dict with per-stock metrics, aggregate metrics, and execution logs.
    """
    market_data = MarketDataService()
    agent = TradingAgent()
    symbols = get_symbols()

    if not agent.is_trained:
        return {"error": "Trading agent is not trained. Run training first."}

    # ── Collect results per stock ──
    stock_results = []

    for symbol in symbols:
        stock_info = get_stock_info(symbol) or {}
        stock_name = stock_info.get("name", symbol)

        # Fetch 5-min intraday data (last ~60 days)
        intraday = market_data.get_intraday_prices(symbol, interval="5m")
        if intraday is None or len(intraday) < 20:
            logger.warning(f"Insufficient intraday data for {symbol}, skipping.")
            continue

        # Group by trading day
        intraday_series = _to_series(intraday)
        if intraday_series is None:
            continue

        daily_groups = _group_by_day(intraday_series)

        if num_days:
            daily_groups = daily_groups[-num_days:]

        if not daily_groups:
            continue

        # Run backtest for each day
        day_results = []
        for day_date, day_prices in daily_groups:
            if len(day_prices) < 10:
                continue

            result = _backtest_single_day(
                agent=agent,
                prices=day_prices,
                total_shares=total_shares,
                order_type=order_type,
            )
            result["date"] = day_date
            day_results.append(result)

        if not day_results:
            continue

        # Aggregate per-stock metrics
        avg_shortfall = np.mean([r["implementation_shortfall_pct"] for r in day_results])
        avg_vwap_imp = np.mean([r["vwap_improvement_pct"] for r in day_results])
        avg_slices = np.mean([r["num_slices"] for r in day_results])
        avg_max_frac = np.mean([r["max_single_slice_pct"] for r in day_results])
        avg_naive_saving = np.mean([r["cost_saving_vs_naive_pct"] for r in day_results])
        completion_rate = np.mean([1 if r["completed"] else 0 for r in day_results])

        stock_results.append({
            "symbol": symbol,
            "stock_name": stock_name,
            "num_days_tested": len(day_results),
            "avg_implementation_shortfall_pct": round(avg_shortfall, 4),
            "avg_vwap_improvement_pct": round(avg_vwap_imp, 4),
            "avg_slices_per_order": round(avg_slices, 1),
            "avg_max_single_slice_pct": round(avg_max_frac, 1),
            "avg_cost_saving_vs_naive_pct": round(avg_naive_saving, 4),
            "completion_rate": round(completion_rate, 4),
            "daily_results": day_results[-5:],  # last 5 days for detail
        })

    if not stock_results:
        return {"error": "No stocks had sufficient intraday data for backtesting."}

    # ── Aggregate metrics across all stocks ──
    all_shortfalls = [s["avg_implementation_shortfall_pct"] for s in stock_results]
    all_vwap = [s["avg_vwap_improvement_pct"] for s in stock_results]
    all_slices = [s["avg_slices_per_order"] for s in stock_results]
    all_max_frac = [s["avg_max_single_slice_pct"] for s in stock_results]
    all_naive = [s["avg_cost_saving_vs_naive_pct"] for s in stock_results]
    all_completion = [s["completion_rate"] for s in stock_results]

    aggregate = {
        "avg_implementation_shortfall_pct": round(np.mean(all_shortfalls), 4),
        "avg_vwap_improvement_pct": round(np.mean(all_vwap), 4),
        "avg_slices_per_order": round(np.mean(all_slices), 1),
        "avg_max_single_slice_pct": round(np.mean(all_max_frac), 1),
        "avg_cost_saving_vs_naive_pct": round(np.mean(all_naive), 4),
        "overall_completion_rate": round(np.mean(all_completion), 4),
        "total_stocks_tested": len(stock_results),
        "total_days_tested": sum(s["num_days_tested"] for s in stock_results),
    }

    return {
        "aggregate_metrics": aggregate,
        "per_stock_results": stock_results,
        "backtest_config": {
            "total_shares": total_shares,
            "order_type": order_type,
            "num_days_requested": num_days,
        },
    }


def _backtest_single_day(
    agent: TradingAgent,
    prices: np.ndarray,
    total_shares: int,
    order_type: str,
) -> dict:
    """
    Run the trading agent through one day's 5-min prices and measure quality.

    Returns execution metrics for this single day.
    """
    num_steps = len(prices)
    arrival_price = prices[0]
    remaining = total_shares
    price_history: list[float] = []
    executions: list[dict] = []

    # ── Step-by-step execution ──
    for step in range(num_steps):
        if remaining <= 0:
            break

        current_price = float(prices[step])
        price_history.append(current_price)
        is_last = (step == num_steps - 1)

        try:
            shares, exec_price = agent.decide_single_step(
                remaining_shares=remaining,
                total_shares=total_shares,
                current_step=step,
                total_steps=num_steps,
                current_price=current_price,
                price_history=price_history,
                order_type=order_type,
                is_last_step=is_last,
            )
        except Exception:
            # Fallback: TWAP
            if is_last:
                shares = remaining
            else:
                shares = max(1, total_shares // num_steps)
                shares = min(shares, remaining)
            exec_price = current_price

        if shares > 0:
            executions.append({
                "step": step,
                "shares": shares,
                "price": exec_price,
            })
            remaining -= shares

    # ── Compute metrics ──
    if not executions:
        return {
            "completed": False,
            "num_slices": 0,
            "max_single_slice_pct": 0,
            "implementation_shortfall_pct": 0,
            "vwap_improvement_pct": 0,
            "cost_saving_vs_naive_pct": 0,
        }

    # Agent's volume-weighted average price
    total_shares_exec = sum(e["shares"] for e in executions)
    agent_vwap = sum(e["shares"] * e["price"] for e in executions) / max(total_shares_exec, 1)

    # Market VWAP (equal volume across all steps — approximation)
    market_vwap = float(np.mean(prices))

    # Naive execution: buy everything at step 0 with full impact
    fraction_naive = 1.0
    naive_spread = arrival_price * (5.0 / 10000) / 2
    naive_impact = 0.1 * arrival_price * (fraction_naive ** 2)
    if order_type.upper() == "BUY":
        naive_price = arrival_price + naive_spread + naive_impact
    else:
        naive_price = arrival_price - naive_spread - naive_impact

    # Implementation shortfall (vs arrival price)
    if order_type.upper() == "BUY":
        shortfall_pct = (agent_vwap - arrival_price) / arrival_price * 100
        vwap_imp_pct = (market_vwap - agent_vwap) / market_vwap * 100
        naive_saving_pct = (naive_price - agent_vwap) / naive_price * 100
    else:
        shortfall_pct = (arrival_price - agent_vwap) / arrival_price * 100
        vwap_imp_pct = (agent_vwap - market_vwap) / market_vwap * 100
        naive_saving_pct = (agent_vwap - naive_price) / naive_price * 100

    # Max single slice as % of total
    max_single = max(e["shares"] for e in executions)
    max_frac = max_single / total_shares * 100

    return {
        "completed": remaining <= 0,
        "num_slices": len(executions),
        "max_single_slice_pct": round(max_frac, 1),
        "agent_vwap": round(agent_vwap, 4),
        "market_vwap": round(market_vwap, 4),
        "arrival_price": round(arrival_price, 4),
        "naive_price": round(naive_price, 4),
        "implementation_shortfall_pct": round(shortfall_pct, 4),
        "vwap_improvement_pct": round(vwap_imp_pct, 4),
        "cost_saving_vs_naive_pct": round(naive_saving_pct, 4),
    }


def _to_series(data) -> np.ndarray | None:
    """Convert intraday data to a flat price array."""
    if isinstance(data, np.ndarray):
        return data
    if hasattr(data, "values"):
        return data.values.flatten()
    if isinstance(data, list):
        return np.array(data, dtype=float)
    return None


def _group_by_day(prices_array: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """
    Split a continuous 5-min price array into per-day chunks.

    Assumes ~78 5-min intervals per NSE trading day.
    Returns list of (date_string, day_prices) tuples.
    """
    steps_per_day = 78
    num_days = len(prices_array) // steps_per_day
    groups = []

    for d in range(num_days):
        start = d * steps_per_day
        end = start + steps_per_day
        day_prices = prices_array[start:end]

        # Approximate date (we don't have actual timestamps here)
        date_str = f"Day-{d + 1}"
        groups.append((date_str, day_prices))

    # Handle remaining partial day
    remaining = len(prices_array) % steps_per_day
    if remaining >= 10:
        day_prices = prices_array[-remaining:]
        groups.append((f"Day-{num_days + 1} (partial)", day_prices))

    return groups
