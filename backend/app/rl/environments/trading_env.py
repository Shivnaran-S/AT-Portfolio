"""
Algorithmic Trade Execution Gymnasium Environment.

MDP Design:
  State:  Remaining shares, time left, price, momentum, volume profile
  Action: Fraction of remaining shares to execute now (0.0 to 1.0)
  Reward: Negative implementation shortfall with urgency penalty
"""

import gymnasium as gym
from gymnasium import spaces
import numpy as np


class TradingEnv(gym.Env):
    """
    Custom Gymnasium environment for PPO-based order execution.

    The agent decides how many shares to trade at each time step,
    aiming to fill the entire order before market close while
    minimizing execution cost (implementation shortfall).
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        price_path: np.ndarray,
        total_shares: int = 100,
        num_time_steps: int = 78,
        spread_bps: float = 5.0,
        impact_factor: float = 0.1,
    ):
        """
        Args:
            price_path: Array of shape (num_time_steps,) with intraday prices.
            total_shares: Number of shares to execute in this episode.
            num_time_steps: Number of decision points in a trading day
                           (e.g., 78 five-minute intervals from 9:15 AM to 3:30 PM).
            spread_bps: Bid-ask spread in basis points.
            impact_factor: Market impact coefficient (price moves when we trade).
        """
        super().__init__()

        self.price_path = price_path
        self.total_shares = total_shares
        self.num_time_steps = num_time_steps
        self.spread_bps = spread_bps
        self.impact_factor = impact_factor

        # State variables
        self._current_step = 0
        self._remaining_shares = total_shares
        self._arrival_price = price_path[0] if len(price_path) > 0 else 100.0
        self._total_cost = 0.0
        self._execution_log: list[dict] = []

        # ── Spaces ────────────────────────────────────────────────────

        # Action: fraction of remaining shares to execute (0 to 1)
        self.action_space = spaces.Box(
            low=0.0, high=1.0, shape=(1,), dtype=np.float32
        )

        # Observation: [remaining_fraction, time_fraction, price_relative,
        #               momentum_5, momentum_10, spread]
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(6,), dtype=np.float32
        )

    # ── Core Methods ──────────────────────────────────────────────────

    def reset(self, seed=None, options=None):
        """Reset the environment for a new trading episode."""
        super().reset(seed=seed)

        self._current_step = 0
        self._remaining_shares = self.total_shares
        self._arrival_price = self.price_path[0]
        self._total_cost = 0.0
        self._execution_log = []

        observation = self._get_observation()
        return observation, {}

    def step(self, action: np.ndarray):
        """
        Execute one time step: trade some fraction of remaining shares.

        Args:
            action: Array of shape (1,) with the fraction to trade [0, 1].

        Returns:
            observation, reward, terminated, truncated, info
        """
        fraction = float(np.clip(action[0], 0.0, 1.0))

        # Calculate shares to trade
        shares_to_trade = max(0, int(round(fraction * self._remaining_shares)))

        # On the last step, trade everything remaining
        is_last_step = self._current_step >= self.num_time_steps - 1
        if is_last_step:
            shares_to_trade = self._remaining_shares

        # Current market price
        current_price = self.price_path[min(self._current_step, len(self.price_path) - 1)]

        # ── Execution price with market impact and spread ──
        # Spread cost: half the spread (we pay the ask for buys)
        spread_cost = current_price * (self.spread_bps / 10000) / 2

        # Market impact: proportional to trade size relative to typical volume
        impact = self.impact_factor * (shares_to_trade / max(self.total_shares, 1))
        execution_price = current_price + spread_cost + impact

        # Cost for this trade (implementation shortfall perspective)
        trade_cost = shares_to_trade * (execution_price - self._arrival_price)
        self._total_cost += trade_cost

        # Update state
        self._remaining_shares -= shares_to_trade
        self._current_step += 1

        # Log execution
        if shares_to_trade > 0:
            self._execution_log.append({
                "step": self._current_step - 1,
                "shares": shares_to_trade,
                "price": round(execution_price, 4),
            })

        # ── Reward ────────────────────────────────────────────────────
        # Negative implementation shortfall for this step
        reward = -trade_cost / (self.total_shares * self._arrival_price + 1e-8)

        # Small urgency penalty per step (encourages completing earlier)
        reward -= 0.001

        # Bonus for completing the order
        terminated = self._remaining_shares <= 0 or is_last_step
        truncated = False

        if terminated and self._remaining_shares > 0:
            # Penalty for not completing the order
            reward -= 1.0

        observation = self._get_observation()

        info = {
            "remaining_shares": self._remaining_shares,
            "total_cost": self._total_cost,
            "execution_log": self._execution_log.copy(),
        }

        return observation, float(reward), terminated, truncated, info

    # ── Helper Methods ────────────────────────────────────────────────

    def _get_observation(self) -> np.ndarray:
        """
        Build the observation vector:
        1. Remaining shares as fraction of total
        2. Remaining time as fraction of total
        3. Current price relative to arrival price
        4. Short-term momentum (5-step return)
        5. Medium-term momentum (10-step return)
        6. Spread estimate
        """
        step = min(self._current_step, len(self.price_path) - 1)
        current_price = self.price_path[step]

        # Remaining fraction
        remaining_frac = self._remaining_shares / max(self.total_shares, 1)

        # Time fraction remaining
        time_frac = 1.0 - (self._current_step / self.num_time_steps)

        # Price relative to arrival
        price_relative = current_price / self._arrival_price - 1.0

        # Momentum: short-term (5-step)
        if step >= 5:
            momentum_5 = (current_price / self.price_path[step - 5]) - 1.0
        else:
            momentum_5 = 0.0

        # Momentum: medium-term (10-step)
        if step >= 10:
            momentum_10 = (current_price / self.price_path[step - 10]) - 1.0
        else:
            momentum_10 = 0.0

        # Spread (normalized)
        spread = self.spread_bps / 100.0  # Convert to percentage

        obs = np.array(
            [remaining_frac, time_frac, price_relative, momentum_5, momentum_10, spread],
            dtype=np.float32,
        )
        return obs
