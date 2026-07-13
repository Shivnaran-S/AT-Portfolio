"""
Training script for the Algorithmic Trading PPO agent.

Run with:
    python -m app.rl.training.train_trading

This script:
1. Creates TradingEnv with randomized GBM price paths
2. Trains a PPO agent for order execution (both BUY and SELL)
3. Validates that the agent distributes trades across multiple slices
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
    total_timesteps = 200_000

    logger.info(f"  Time steps per episode: {num_time_steps}")
    logger.info(f"  Total training timesteps: {total_timesteps}")
    logger.info("  Impact model: QUADRATIC (Almgren-Chriss style)")
    logger.info("  Price paths: RANDOMIZED on each episode reset")
    logger.info("  Training on both BUY and SELL order types")

    # Step 2: Train the agent
    logger.info("Step 2: Training PPO agent...")
    agent = TradingAgent()
    result = agent.train(
        total_timesteps=total_timesteps,
        num_time_steps=num_time_steps,
    )

    logger.info(f"Training result: {result}")

    # Step 3: Validation — run multiple episodes and check slice distribution
    logger.info("Step 3: Running validation episodes...")

    for order_type in ["BUY", "SELL"]:
        logger.info(f"\n  --- {order_type} Order Validation (5 episodes) ---")

        all_slice_counts = []
        all_max_fractions = []

        for episode in range(5):
            price_path = TradingAgent._generate_price_path(
                initial_price=np.random.uniform(500, 5000),
                num_steps=num_time_steps,
                volatility=np.random.uniform(0.01, 0.03),
                seed=42 + episode,
            )

            slices = agent.plan_execution(
                total_shares=50,
                price_path=price_path,
                num_time_steps=num_time_steps,
                order_type=order_type,
            )

            total_filled = sum(s["quantity"] for s in slices)
            max_single = max(s["quantity"] for s in slices) if slices else 0
            max_frac = max_single / 50 * 100

            all_slice_counts.append(len(slices))
            all_max_fractions.append(max_frac)

            logger.info(
                f"  Episode {episode + 1}: {len(slices)} slices, "
                f"max single trade = {max_single}/50 ({max_frac:.1f}%), "
                f"total filled = {total_filled}/50"
            )

            # Print individual slices for first episode
            if episode == 0:
                for s in slices:
                    logger.info(f"    {s['time']} — {s['quantity']} shares @ ₹{s['price']}")

        avg_slices = np.mean(all_slice_counts)
        avg_max_frac = np.mean(all_max_fractions)
        logger.info(f"\n  {order_type} Summary:")
        logger.info(f"    Average slices per order: {avg_slices:.1f}")
        logger.info(f"    Average max single-trade fraction: {avg_max_frac:.1f}%")

        if avg_slices < 3:
            logger.warning(
                f"  ⚠ Agent is using fewer than 3 slices on average. "
                "Consider increasing training timesteps or impact_factor."
            )
        else:
            logger.info(f"    ✓ Agent distributes trades well across {avg_slices:.0f}+ slices")

    logger.info("\n" + "=" * 60)
    logger.info("Training complete! Model saved to backend/app/rl/models/trading_ppo.zip")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
