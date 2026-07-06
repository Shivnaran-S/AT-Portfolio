"""
Training script for the Algorithmic Trading PPO agent.

Run with:
    python -m app.rl.training.train_trading

This script:
1. Generates synthetic intraday price paths using GBM
2. Creates the TradingEnv environment
3. Trains a PPO agent for order execution
4. Saves the trained model to app/rl/models/
"""

import logging
import sys

import numpy as np

from app.rl.agents.trading_agent import TradingAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    """Train the algorithmic trading PPO agent."""
    logger.info("=" * 60)
    logger.info("Algorithmic Trading PPO — Training Script")
    logger.info("=" * 60)

    # Step 1: Configure training parameters
    logger.info("Step 1: Configuring training parameters...")
    num_time_steps = 78  # 5-min intervals in NSE trading day (9:15 AM - 3:30 PM)
    total_timesteps = 100_000

    logger.info(f"  Time steps per episode: {num_time_steps}")
    logger.info(f"  Total training timesteps: {total_timesteps}")

    # Step 2: Train the agent
    # The TradingAgent internally generates GBM price paths for training
    logger.info("Step 2: Training PPO agent with synthetic price paths...")
    agent = TradingAgent()
    result = agent.train(
        total_timesteps=total_timesteps,
        num_time_steps=num_time_steps,
    )

    logger.info(f"Training result: {result}")

    # Step 3: Quick validation
    logger.info("Step 3: Running a quick validation episode...")
    price_path = TradingAgent._generate_price_path(
        initial_price=1500.0,
        num_steps=num_time_steps,
        volatility=0.015,
        seed=42,
    )

    slices = agent.plan_execution(
        total_shares=50,
        price_path=price_path,
        num_time_steps=num_time_steps,
    )

    logger.info(f"  Execution plan has {len(slices)} slices:")
    total_executed = 0
    for s in slices:
        total_executed += s["quantity"]
        logger.info(f"    {s['time']} — {s['quantity']} shares @ ₹{s['price']}")

    logger.info(f"  Total shares executed: {total_executed} / 50")

    logger.info("=" * 60)
    logger.info("Training complete! Model saved to backend/app/rl/models/trading_ppo.zip")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
