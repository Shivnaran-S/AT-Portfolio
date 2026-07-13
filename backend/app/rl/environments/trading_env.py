"""
Algorithmic Trade Execution Gymnasium Environment.

MDP Design:
  State:  Remaining shares, time left, price, momentum, volume profile,
          order type flag
  Action: Fraction of remaining shares to execute now (0.0 to 1.0)
  Reward: Negative implementation shortfall (quadratic market impact)

Market impact follows an Almgren-Chriss-style quadratic model:
  impact = impact_factor × price × (fraction²)
This penalizes large trades heavily, naturally incentivizing the agent
to spread execution across multiple time steps.
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

    Supports both BUY and SELL orders with correct spread, impact,
    and reward calculations for each side.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        price_path: np.ndarray | None = None,
        total_shares: int = 100,
        num_time_steps: int = 78,
        spread_bps: float = 5.0,
        impact_factor: float = 0.1,
        order_type: str = "BUY",
        initial_price: float = 1000.0,
        volatility: float = 0.02,
        drift: float = 0.0001,
        randomize_on_reset: bool = False,
    ):
        """
        Args:
            price_path: Optional fixed price path. If None, a GBM path
                        is generated from initial_price.
            total_shares: Number of shares to execute in this episode.
            num_time_steps: Number of decision points in a trading day
                           (e.g., 78 five-minute intervals).
            spread_bps: Bid-ask spread in basis points.
            impact_factor: Market impact coefficient. Impact is quadratic:
                           impact = impact_factor × price × (fraction²).
            order_type: "BUY" or "SELL".
            initial_price: Starting price for GBM generation (used if
                           price_path is None or randomize_on_reset=True).
            volatility: GBM per-step volatility.
            drift: GBM per-step drift.
            randomize_on_reset: If True, generate a new random GBM price
                                path on each reset() call (for training).
        """
        super().__init__()

        self.total_shares = total_shares
        self.num_time_steps = num_time_steps
        self.spread_bps = spread_bps
        self.impact_factor = impact_factor
        self.order_type = order_type.upper()

        # GBM parameters (for generating new paths)
        self._initial_price = initial_price
        self._volatility = volatility
        self._drift = drift
        self._randomize_on_reset = randomize_on_reset

        # Set initial price path
        if price_path is not None:
            self.price_path = price_path
        else:
            self.price_path = self._generate_gbm_path()

        # State variables
        self._current_step = 0
        self._remaining_shares = total_shares
        self._arrival_price = self.price_path[0] if len(self.price_path) > 0 else initial_price
        self._total_cost = 0.0
        self._execution_log: list[dict] = []

        # ── Spaces ────────────────────────────────────────────────────

        # Action: fraction of remaining shares to execute (0 to 1)
        self.action_space = spaces.Box(
            low=0.0, high=1.0, shape=(1,), dtype=np.float32
        )

        # Observation: [remaining_fraction, time_fraction, price_relative,
        #               momentum_5, momentum_10, spread, order_type_flag]
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(7,), dtype=np.float32
        )

    # ── Core Methods ──────────────────────────────────────────────────

    def reset(self, seed=None, options=None):
        """Reset the environment for a new trading episode."""
        super().reset(seed=seed)

        # Generate a new price path for training diversity
        if self._randomize_on_reset:
            self.price_path = self._generate_gbm_path(rng=self.np_random)

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
        action_val = float(np.clip(action[0], 0.0, 1.0))
        twap_multiplier = action_val * 2.0
        
        remaining_steps = max(1, self.num_time_steps - self._current_step)
        twap_shares = self._remaining_shares / remaining_steps
        raw_shares = twap_multiplier * twap_shares

        # Calculate shares to trade
        if self._randomize_on_reset:
            floor_shares = int(raw_shares)
            if self.np_random.random() < (raw_shares - floor_shares):
                shares_to_trade = floor_shares + 1
            else:
                shares_to_trade = floor_shares
        else:
            shares_to_trade = int(round(raw_shares))

        # On the last step, trade everything remaining
        is_last_step = self._current_step >= self.num_time_steps - 1
        if is_last_step:
            shares_to_trade = self._remaining_shares
            
        shares_to_trade = min(shares_to_trade, self._remaining_shares)

        # Current market price
        current_price = self.price_path[min(self._current_step, len(self.price_path) - 1)]

        # ── Execution price with QUADRATIC market impact ──
        # Half-spread cost
        spread_cost = current_price * (self.spread_bps / 10000) / 2

        # Quadratic market impact (Almgren-Chriss style):
        # Trading a large fraction at once is disproportionately expensive.
        # fraction_of_total = shares / total_shares
        fraction_of_total = shares_to_trade / max(self.total_shares, 1)
        impact = self.impact_factor * current_price * (fraction_of_total ** 2)

        if self.order_type == "BUY":
            # Buyer pays the ask: price goes UP with spread and impact
            execution_price = current_price + spread_cost + impact
        else:
            # Seller hits the bid: price goes DOWN with spread and impact
            execution_price = current_price - spread_cost - impact

        # Cost for this trade (implementation shortfall perspective)
        if self.order_type == "BUY":
            # Shortfall = how much more we paid vs arrival price
            trade_cost = shares_to_trade * (execution_price - self._arrival_price)
        else:
            # Shortfall = how much less we received vs arrival price
            trade_cost = shares_to_trade * (self._arrival_price - execution_price)

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
                "fraction": round(fraction_of_total, 4),
            })

        # ── Reward ────────────────────────────────────────────────────
        # Negative implementation shortfall for this step (normalized)
        reward = -trade_cost / (self.total_shares * self._arrival_price + 1e-8)

        # No urgency penalty — quadratic impact naturally discourages
        # large trades, and the last-step force-execute provides
        # completion pressure.

        # Check termination
        terminated = self._remaining_shares <= 0 or is_last_step
        truncated = False

        # Completion bonus: small reward for finishing the order
        if terminated and self._remaining_shares <= 0:
            reward += 0.01  # bonus for completing

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
        7. Order type flag (0.0 = BUY, 1.0 = SELL)
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

        # Order type flag: 0.0 for BUY, 1.0 for SELL
        order_type_flag = 0.0 if self.order_type == "BUY" else 1.0

        obs = np.array(
            [remaining_frac, time_frac, price_relative,
             momentum_5, momentum_10, spread, order_type_flag],
            dtype=np.float32,
        )
        return obs

    def _generate_gbm_path(self, rng=None) -> np.ndarray:
        """Generate a GBM price path for this episode."""
        if rng is None:
            rng = np.random.default_rng()

        prices = np.zeros(self.num_time_steps)
        prices[0] = self._initial_price

        for t in range(1, self.num_time_steps):
            shock = rng.normal(0, 1)
            prices[t] = prices[t - 1] * np.exp(
                (self._drift - 0.5 * self._volatility ** 2)
                + self._volatility * shock
            )

        return prices
