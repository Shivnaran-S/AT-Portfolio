"""
Training script for the Portfolio Optimization PPO agent.

Run with:
    python -m app.rl.training.train_portfolio

This script:
1. Fetches 3 years of historical data for all stocks via yfinance
2. Computes log returns and technical indicators
3. Creates the PortfolioEnv environment
4. Trains a PPO agent using Stable-Baselines3
5. Saves the trained model to app/rl/models/
"""

import logging
import sys

import numpy as np

from app.rl.data.market_data import MarketDataService
from app.rl.agents.portfolio_agent import PortfolioAgent
from app.stock_config import get_symbols

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    """Train the portfolio optimization PPO agent."""
    logger.info("=" * 60)
    logger.info("Portfolio Optimization PPO — Training Script")
    logger.info("=" * 60)

    # Step 1: Fetch historical data
    logger.info("Step 1: Fetching historical data from Yahoo Finance...")
    data_service = MarketDataService()
    symbols = get_symbols()
    raw_data = data_service.get_historical_data(symbols, period="3y")

    if raw_data.empty:
        logger.error("Failed to fetch historical data. Check internet connection.")
        sys.exit(1)

    # Extract close prices
    close_prices = raw_data["Close"]
    if isinstance(close_prices, type(raw_data)):
        # Multi-symbol format
        close_prices = close_prices[symbols]
    close_prices = close_prices.dropna()

    logger.info(f"  Retrieved {len(close_prices)} trading days for {len(symbols)} stocks.")

    # Step 2: Compute returns and features
    logger.info("Step 2: Computing log returns and technical indicators...")
    returns = MarketDataService.compute_returns(close_prices)
    features_df = MarketDataService.compute_technical_indicators(close_prices)

    # Align indices and drop NaN rows
    common_index = returns.index.intersection(features_df.index)
    returns = returns.loc[common_index]
    features_df = features_df.loc[common_index].dropna()
    returns = returns.loc[features_df.index]

    returns_array = returns.values.astype(np.float32)
    features_array = features_df.values.astype(np.float32)

    logger.info(f"  Returns shape: {returns_array.shape}")
    logger.info(f"  Features shape: {features_array.shape}")

    # Step 3: Train the agent
    logger.info("Step 3: Training PPO agent...")
    agent = PortfolioAgent()
    result = agent.train(
        returns=returns_array,
        features=features_array,
        total_timesteps=50_000,
        lookback_window=30,
    )

    logger.info(f"Training result: {result}")
    logger.info("=" * 60)
    logger.info("Training complete! Model saved to backend/app/rl/models/portfolio_ppo.zip")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
