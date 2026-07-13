"""
PPO agent for algorithmic trade execution.

Uses Stable-Baselines3's PPO to learn optimal order slicing —
deciding when and how many shares to trade at each time step.

Supports both BUY and SELL orders via the order_type parameter.

Market impact is quadratic (Almgren-Chriss style):
  impact = impact_factor × price × (fraction²)
This ensures the agent learns to spread trades across multiple steps.
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
    Handles both BUY and SELL orders.
    """

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path or _DEFAULT_MODEL_PATH
        self.model: PPO | None = None

    # ── Training ──────────────────────────────────────────────────────

    def train(
        self,
        num_episodes: int = 500,
        total_timesteps: int = 200_000,
        num_time_steps: int = 78,
    ) -> dict:
        """
        Train the PPO agent using synthetic intraday price paths.

        Each episode generates a new random GBM trajectory so the agent
        learns to generalize across different price behaviors.
        Trains on a mix of BUY and SELL episodes.

        Args:
            num_episodes: Number of episodes (used for env creation).
            total_timesteps: Total PPO training steps.
            num_time_steps: Decision points per trading day.

        Returns:
            Training info dict.
        """
        # Create env with randomize_on_reset=True so each episode has
        # a different GBM price path — prevents memorization.
        env_buy = TradingEnv(
            total_shares=100,
            num_time_steps=num_time_steps,
            order_type="BUY",
            initial_price=1000.0,
            volatility=0.02,
            randomize_on_reset=True,
        )

        # Initialize PPO
        self.model = PPO(
            policy="MlpPolicy",
            env=env_buy,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,   # Entropy bonus to encourage exploration
            verbose=1,
        )

        # Train half on BUY
        buy_steps = total_timesteps // 2
        logger.info(f"Training trading PPO for {buy_steps} BUY timesteps...")
        self.model.learn(total_timesteps=buy_steps)

        # Switch to SELL environment for the second half
        env_sell = TradingEnv(
            total_shares=100,
            num_time_steps=num_time_steps,
            order_type="SELL",
            initial_price=1000.0,
            volatility=0.02,
            randomize_on_reset=True,
        )
        self.model.set_env(env_sell)

        sell_steps = total_timesteps - buy_steps
        logger.info(f"Training trading PPO for {sell_steps} SELL timesteps...")
        self.model.learn(total_timesteps=sell_steps, reset_num_timesteps=False)

        # Save
        self.save_model()
        logger.info("Trading PPO training complete (BUY + SELL).")
        return {"status": "trained", "timesteps": total_timesteps}

    # ── Execution Planning (batch — for validation only) ──────────────

    def plan_execution(
        self,
        total_shares: int,
        price_path: np.ndarray,
        num_time_steps: int = 78,
        base_time: datetime | None = None,
        step_minutes: int = 5,
        order_type: str = "BUY",
    ) -> list[dict]:
        """
        Plan the execution of an order using the trained PPO agent.

        Runs the agent through the entire price path, recording each
        trading decision as an order slice. Used for validation only —
        live/demo execution uses decide_single_step() instead.
        """
        if self.model is None:
            self.load_model()

        if base_time is None:
            now = datetime.now(timezone.utc)
            base_time = now.replace(hour=3, minute=45, second=0, microsecond=0)

        # Create environment for this specific order
        env = TradingEnv(
            price_path=price_path,
            total_shares=total_shares,
            num_time_steps=num_time_steps,
            order_type=order_type,
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

    # ── Single-Step Decision ─────────────────────────────────────────

    def decide_single_step(
        self,
        remaining_shares: int,
        total_shares: int,
        current_step: int,
        total_steps: int,
        current_price: float,
        price_history: list[float],
        order_type: str = "BUY",
        spread_bps: float = 5.0,
        impact_factor: float = 0.1,
        is_last_step: bool = False,
    ) -> tuple[int, float]:
        """
        Make a single trading decision using only current/past prices.

        This method is the real-time counterpart of plan_execution().
        It does NOT require a full future price path — only the prices
        observed so far.

        Args:
            remaining_shares: Shares still to be executed.
            total_shares: Original order size.
            current_step: Current time step index (0-based).
            total_steps: Total number of steps in the trading period.
            current_price: The price observed right now.
            price_history: All prices observed so far (including current).
            order_type: "BUY" or "SELL".
            spread_bps: Bid-ask spread in basis points.
            impact_factor: Market impact coefficient.
            is_last_step: If True, force-execute all remaining shares.

        Returns:
            (shares_to_trade, execution_price) tuple.
            shares_to_trade may be 0 if the agent decides to wait.
        """
        if self.model is None:
            self.load_model()

        if remaining_shares <= 0:
            return 0, current_price

        # ── Force-execute on last step ──
        if is_last_step:
            shares_to_trade = remaining_shares
        else:
            # Build observation (same 7 features as TradingEnv)
            obs = self._build_observation(
                remaining_shares=remaining_shares,
                total_shares=total_shares,
                current_step=current_step,
                total_steps=total_steps,
                current_price=current_price,
                price_history=price_history,
                order_type=order_type,
                spread_bps=spread_bps,
            )

            # Get agent action
            action, _ = self.model.predict(obs, deterministic=True)
            
            # Interpret agent action as a TWAP multiplier [0, 2]
            action_val = float(np.clip(action[0], 0.0, 1.0))
            twap_multiplier = action_val * 2.0
            
            remaining_steps = max(1, total_steps - current_step)
            twap_shares = remaining_shares / remaining_steps
            
            raw_shares = twap_multiplier * twap_shares
            shares_to_trade = min(remaining_shares, int(round(raw_shares)))

        # ── Calculate execution price with QUADRATIC impact ──
        spread_cost = current_price * (spread_bps / 10000) / 2
        fraction_of_total = shares_to_trade / max(total_shares, 1)
        impact = impact_factor * current_price * (fraction_of_total ** 2)

        if order_type.upper() == "BUY":
            execution_price = current_price + spread_cost + impact
        else:
            execution_price = current_price - spread_cost - impact

        execution_price = round(execution_price, 4)
        return shares_to_trade, execution_price

    @staticmethod
    def _build_observation(
        remaining_shares: int,
        total_shares: int,
        current_step: int,
        total_steps: int,
        current_price: float,
        price_history: list[float],
        order_type: str,
        spread_bps: float,
    ) -> np.ndarray:
        """
        Build the 7-dim observation vector from accumulated price history.

        Mirrors TradingEnv._get_observation() but works with a growing
        list of observed prices instead of a fixed price_path array.
        """
        arrival_price = price_history[0] if price_history else current_price

        # 1. Remaining shares fraction
        remaining_frac = remaining_shares / max(total_shares, 1)

        # 2. Time fraction remaining
        time_frac = 1.0 - (current_step / total_steps)

        # 3. Price relative to arrival
        price_relative = current_price / arrival_price - 1.0

        # 4. Short-term momentum (5-step)
        n = len(price_history)
        if n >= 6:
            momentum_5 = (current_price / price_history[-6]) - 1.0
        else:
            momentum_5 = 0.0

        # 5. Medium-term momentum (10-step)
        if n >= 11:
            momentum_10 = (current_price / price_history[-11]) - 1.0
        else:
            momentum_10 = 0.0

        # 6. Spread (normalized)
        spread = spread_bps / 100.0

        # 7. Order type flag
        order_type_flag = 0.0 if order_type.upper() == "BUY" else 1.0

        return np.array(
            [remaining_frac, time_frac, price_relative,
             momentum_5, momentum_10, spread, order_type_flag],
            dtype=np.float32,
        )

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
