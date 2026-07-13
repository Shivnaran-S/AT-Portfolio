"""
Portfolio Agent Backtester.

Simulates monthly portfolio rebalancing over historical data
and reports risk-adjusted performance metrics.

Comparison: PPO agent vs equal-weight benchmark.
"""

import logging
from datetime import datetime

import numpy as np
import pandas as pd

from app.stock_config import get_symbols
from app.rl.agents.portfolio_agent import PortfolioAgent
from app.rl.data.market_data import MarketDataService

logger = logging.getLogger(__name__)


def run_portfolio_backtest(
    period: str = "2y",
    rebalance_frequency: str = "monthly",
    lookback_months: int = 6,
) -> dict:
    """
    Backtest the PPO portfolio agent against an equal-weight benchmark.

    Strategy:
    - Starting from month `lookback_months`, at each rebalance date:
      1. Use the preceding `lookback_months` of data to generate PPO weights
      2. Hold those weights until the next rebalance
    - Simultaneously track an equal-weight benchmark

    Args:
        period: Historical data period (e.g., "2y", "3y").
        rebalance_frequency: "monthly" or "quarterly".
        lookback_months: Months of history used for weight generation.

    Returns:
        Dict with metrics, equity curves, and weight history.
    """
    market_data = MarketDataService()
    agent = PortfolioAgent()

    symbols = get_symbols()
    num_stocks = len(symbols)

    # Fetch historical daily close prices
    data = market_data.get_historical_data(symbols, period=period)
    close_prices = data["Close"][symbols].dropna()

    if close_prices.empty or len(close_prices) < 130:
        return {"error": "Insufficient historical data for backtesting."}

    # Compute daily returns
    daily_returns = close_prices.pct_change().dropna()

    # Create monthly rebalancing dates
    monthly_end_dates = close_prices.resample("ME").last().index
    if len(monthly_end_dates) < lookback_months + 2:
        return {"error": "Not enough monthly data for backtest with given lookback."}

    # Skip first `lookback_months` for warm-up
    rebalance_dates = monthly_end_dates[lookback_months:]

    if rebalance_frequency == "quarterly":
        rebalance_dates = rebalance_dates[::3]

    # ── Run backtest ──
    ppo_equity = [1.0]
    bench_equity = [1.0]
    ppo_weights_history = []
    monthly_ppo_returns = []
    monthly_bench_returns = []

    equal_weights = np.ones(num_stocks) / num_stocks

    for i in range(len(rebalance_dates) - 1):
        start_date = rebalance_dates[i]
        end_date = rebalance_dates[i + 1]

        # Get the daily returns for this holding period
        mask = (daily_returns.index > start_date) & (daily_returns.index <= end_date)
        period_returns = daily_returns.loc[mask]

        if period_returns.empty:
            continue

        # ── PPO weights ──
        # Use data up to start_date for generating weights
        past_data = close_prices.loc[:start_date]
        if len(past_data) == 0:
            continue
        lookback_data = past_data.iloc[-lookback_months * 21:]

        try:
            if agent.is_trained:
                returns_lb = MarketDataService.compute_returns(lookback_data)
                features_lb = MarketDataService.compute_technical_indicators(lookback_data)

                common_idx = returns_lb.index.intersection(features_lb.index)
                returns_lb = returns_lb.loc[common_idx]
                features_lb = features_lb.loc[common_idx].dropna()
                returns_lb = returns_lb.loc[features_lb.index]

                if len(returns_lb) > 5:
                    ppo_weights = agent.generate_weights(
                        returns=returns_lb.values.astype(np.float32),
                        features=features_lb.values.astype(np.float32),
                    )
                else:
                    ppo_weights = equal_weights
            else:
                ppo_weights = equal_weights
        except Exception:
            ppo_weights = equal_weights

        ppo_weights = np.clip(ppo_weights, 0, 1)
        ppo_weights = ppo_weights / (ppo_weights.sum() + 1e-8)

        ppo_weights_history.append({
            "date": start_date.strftime("%Y-%m-%d"),
            "weights": {
                symbols[j]: round(float(ppo_weights[j]), 4)
                for j in range(num_stocks)
            },
        })

        # ── Calculate period returns ──
        ppo_period_return = (period_returns.values @ ppo_weights).sum()
        bench_period_return = (period_returns.values @ equal_weights).sum()

        # Actually compute daily cumulative for equity curve
        for _, day_ret in period_returns.iterrows():
            ppo_day = float(day_ret.values @ ppo_weights)
            bench_day = float(day_ret.values @ equal_weights)
            ppo_equity.append(ppo_equity[-1] * (1 + ppo_day))
            bench_equity.append(bench_equity[-1] * (1 + bench_day))

        monthly_ppo_returns.append(ppo_period_return)
        monthly_bench_returns.append(bench_period_return)

    if not monthly_ppo_returns:
        return {"error": "No backtest periods could be evaluated."}

    # ── Compute Metrics ──
    ppo_metrics = _compute_metrics(
        equity_curve=ppo_equity,
        period_returns=monthly_ppo_returns,
        label="PPO Agent",
    )
    bench_metrics = _compute_metrics(
        equity_curve=bench_equity,
        period_returns=monthly_bench_returns,
        label="Equal-Weight Benchmark",
    )

    # Excess return
    ppo_metrics["excess_return_vs_benchmark"] = round(
        ppo_metrics["annualized_return"] - bench_metrics["annualized_return"], 4
    )

    return {
        "ppo_agent": ppo_metrics,
        "benchmark": bench_metrics,
        "equity_curve": {
            "ppo": [round(v, 4) for v in ppo_equity],
            "benchmark": [round(v, 4) for v in bench_equity],
        },
        "weight_history": ppo_weights_history,
        "backtest_config": {
            "period": period,
            "rebalance_frequency": rebalance_frequency,
            "lookback_months": lookback_months,
            "num_stocks": num_stocks,
            "num_rebalance_periods": len(monthly_ppo_returns),
            "data_points": len(close_prices),
        },
    }


def _compute_metrics(
    equity_curve: list[float],
    period_returns: list[float],
    label: str,
) -> dict:
    """Compute performance metrics from equity curve and period returns."""
    equity = np.array(equity_curve)
    returns = np.array(period_returns)

    # Total return
    total_return = equity[-1] / equity[0] - 1.0

    # Annualized return (assuming monthly periods × 12)
    n_periods = len(returns)
    if n_periods > 0:
        annualized_return = (1 + total_return) ** (12 / max(n_periods, 1)) - 1
    else:
        annualized_return = 0.0

    # Volatility (annualized from monthly)
    monthly_vol = np.std(returns) if len(returns) > 1 else 0.0
    annual_vol = monthly_vol * np.sqrt(12)

    # Sharpe Ratio (assuming risk-free rate ≈ 6% for India)
    risk_free_monthly = 0.06 / 12
    excess_returns = returns - risk_free_monthly
    sharpe = (
        np.mean(excess_returns) / (np.std(excess_returns) + 1e-8) * np.sqrt(12)
        if len(excess_returns) > 1 else 0.0
    )

    # Sortino Ratio (downside deviation only)
    downside = excess_returns[excess_returns < 0]
    downside_std = np.std(downside) if len(downside) > 1 else 1e-8
    sortino = np.mean(excess_returns) / (downside_std + 1e-8) * np.sqrt(12)

    # Max Drawdown
    peak = np.maximum.accumulate(equity)
    drawdowns = (equity - peak) / (peak + 1e-8)
    max_drawdown = float(np.min(drawdowns))

    # Calmar Ratio
    calmar = annualized_return / (abs(max_drawdown) + 1e-8) if max_drawdown != 0 else 0.0

    # Win Rate (% of months with positive return)
    win_rate = float(np.mean(returns > 0)) if len(returns) > 0 else 0.0

    return {
        "label": label,
        "total_return": round(total_return, 4),
        "annualized_return": round(annualized_return, 4),
        "annualized_volatility": round(annual_vol, 4),
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "max_drawdown": round(max_drawdown, 4),
        "calmar_ratio": round(calmar, 4),
        "win_rate": round(win_rate, 4),
        "num_periods": n_periods,
    }
