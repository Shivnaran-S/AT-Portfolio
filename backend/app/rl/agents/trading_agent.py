"""
PPO agent for algorithmic trade execution.

Uses Stable-Baselines3's PPO to learn optimal order slicing —
deciding when and how many shares to trade at each time step.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import numpy as np
from stable_baselines3 import PPO

from app.rl.environments.trading_env import TradingEnv

logger = logging.getLogger(__name__)

_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
_DEFAULT_MODEL_PATH = os.path.join(_MODEL_DIR, "trading_ppo")


class TradingAgent:
    """
    PPO-based algorithmic trade execution agent.

    This agent determines the optimal timing and quantity for each
    order slice, minimizing implementation shortfall.
    """

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path or _DEFAULT_MODEL_PATH
        self.model: PPO | None = None

    # ── Training ──────────────────────────────────────────────────────

    def train(
        self,
        num_episodes: int = 500,
        total_timesteps: int = 100_000,
        num_time_steps: int = 78,
    ) -> dict:
        """
        Train the PPO agent using synthetic intraday price paths.

        Generates GBM (Geometric Brownian Motion) price paths for training
        to simulate realistic intraday stock price behavior.

        Args:
            num_episodes: Number of episodes (used for env creation).
            total_timesteps: Total PPO training steps.
            num_time_steps: Decision points per trading day.

        Returns:
            Training info dict.
        """
        # Generate a sample price path for the environment
        price_path = self._generate_price_path(
            initial_price=1000.0,
            num_steps=num_time_steps,
            volatility=0.02,
        )

        env = TradingEnv(
            price_path=price_path,
            total_shares=100,
            num_time_steps=num_time_steps,
        )

        # Initialize PPO
        self.model = PPO(
            policy="MlpPolicy",
            env=env,
            learning_rate=3e-4,
            n_steps=1024,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            verbose=1,
        )

        # Train
        logger.info(f"Training trading PPO for {total_timesteps} timesteps...")
        self.model.learn(total_timesteps=total_timesteps)

        # Save
        self.save_model()
        logger.info("Trading PPO training complete.")
        return {"status": "trained", "timesteps": total_timesteps}

    # ── Execution Planning ────────────────────────────────────────────

    def plan_execution(
        self,
        total_shares: int,
        price_path: np.ndarray,
        num_time_steps: int = 78,
        base_time: datetime | None = None,
        step_minutes: int = 5,
    ) -> list[dict]:
        """
        Plan the execution of an order using the trained PPO agent.

        Runs the agent through the entire price path, recording each
        trading decision as an order slice.

        Args:
            total_shares: Number of shares to execute.
            price_path: Intraday price path array.
            num_time_steps: Number of time steps.
            base_time: Start time for the trading day (default: 9:15 AM IST).
            step_minutes: Minutes between each decision point.

        Returns:
            List of execution slices: [{"time": ..., "quantity": ..., "price": ...}, ...]
        """
        if self.model is None:
            self.load_model()

        if base_time is None:
            # Default to 9:15 AM IST (Indian market open)
            now = datetime.now(timezone.utc)
            base_time = now.replace(hour=3, minute=45, second=0, microsecond=0)  # 9:15 AM IST

        # Create environment for this specific order
        env = TradingEnv(
            price_path=price_path,
            total_shares=total_shares,
            num_time_steps=num_time_steps,
        )

        # Run the agent
        obs, _ = env.reset()
        execution_slices = []
        step = 0

        while True:
            action, _ = self.model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)

            # Check if new slices were generated
            current_log = info.get("execution_log", [])
            for entry in current_log[len(execution_slices):]:
                slice_time = base_time + timedelta(minutes=entry["step"] * step_minutes)
                execution_slices.append({
                    "time": slice_time.isoformat(),
                    "quantity": entry["shares"],
                    "price": entry["price"],
                })

            step += 1
            if terminated or truncated:
                break

        return execution_slices

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _generate_price_path(
        initial_price: float,
        num_steps: int,
        volatility: float = 0.02,
        drift: float = 0.0001,
        seed: int | None = None,
    ) -> np.ndarray:
        """
        Generate a synthetic intraday price path using Geometric Brownian Motion.

        Args:
            initial_price: Starting price.
            num_steps: Number of time steps.
            volatility: Per-step volatility (standard deviation of returns).
            drift: Per-step drift (expected return).
            seed: Random seed for reproducibility.

        Returns:
            Array of prices, shape (num_steps,).
        """
        rng = np.random.default_rng(seed)
        dt = 1.0  # Normalized time step
        prices = np.zeros(num_steps)
        prices[0] = initial_price

        for t in range(1, num_steps):
            random_shock = rng.normal(0, 1)
            prices[t] = prices[t - 1] * np.exp(
                (drift - 0.5 * volatility ** 2) * dt + volatility * random_shock * np.sqrt(dt)
            )

        return prices

    # ── Persistence ───────────────────────────────────────────────────

    def save_model(self, path: str | None = None):
        """Save the trained model to disk."""
        save_path = path or self.model_path
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        self.model.save(save_path)
        logger.info(f"Trading model saved to {save_path}")

    def load_model(self, path: str | None = None):
        """Load a trained model from disk."""
        load_path = path or self.model_path
        if not os.path.exists(load_path + ".zip"):
            raise FileNotFoundError(
                f"No trained model found at {load_path}.zip. "
                "Run the training script first: python -m app.rl.training.train_trading"
            )
        self.model = PPO.load(load_path)
        logger.info(f"Trading model loaded from {load_path}")

    @property
    def is_trained(self) -> bool:
        """Check if a trained model exists on disk."""
        return os.path.exists(self.model_path + ".zip")
