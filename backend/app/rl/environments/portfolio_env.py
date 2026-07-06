"""
Portfolio Optimization Gymnasium Environment.

MDP Design:
  State:  Price returns (lookback window), technical indicators, covariance features
  Action: Portfolio weights for each stock (continuous, normalized to sum to 1)
  Reward: Risk-adjusted log portfolio return with transaction cost penalty
"""

import gymnasium as gym
from gymnasium import spaces
import numpy as np


class PortfolioEnv(gym.Env):
    """
    Custom Gymnasium environment for PPO-based portfolio optimization.

    The agent learns to allocate capital across stocks by observing
    historical returns and technical indicators, then assigning weights
    that maximize risk-adjusted returns.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        returns: np.ndarray,
        features: np.ndarray | None = None,
        lookback_window: int = 30,
        transaction_cost_rate: float = 0.001,
        risk_penalty: float = 0.5,
    ):
        """
        Args:
            returns: Array of shape (num_days, num_stocks) with daily log returns.
            features: Optional array of shape (num_days, num_features) with
                      technical indicators. If None, only returns are used.
            lookback_window: Number of past days to include in the observation.
            transaction_cost_rate: Proportional cost for changing portfolio weights.
            risk_penalty: Weight for volatility penalty in the reward function.
        """
        super().__init__()

        self.returns = returns
        self.features = features
        self.lookback_window = lookback_window
        self.transaction_cost_rate = transaction_cost_rate
        self.risk_penalty = risk_penalty

        self.num_days = returns.shape[0]
        self.num_stocks = returns.shape[1]

        # Current step in the episode
        self._current_step = 0
        # Current portfolio weights
        self._current_weights = np.zeros(self.num_stocks, dtype=np.float32)
        # Portfolio value tracker (starts at 1.0)
        self._portfolio_value = 1.0

        # ── Spaces ────────────────────────────────────────────────────

        # Action: weight for each stock (0 to 1, will be normalized)
        self.action_space = spaces.Box(
            low=0.0, high=1.0, shape=(self.num_stocks,), dtype=np.float32
        )

        # Observation: flattened lookback returns + features + current weights
        obs_size = self.num_stocks * lookback_window  # lookback returns
        if features is not None:
            num_feature_cols = features.shape[1]
            obs_size += num_feature_cols  # latest features
        obs_size += self.num_stocks  # current weights

        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_size,), dtype=np.float32
        )

    # ── Core Methods ──────────────────────────────────────────────────

    def reset(self, seed=None, options=None):
        """Reset the environment to the start of a new episode."""
        super().reset(seed=seed)

        self._current_step = self.lookback_window
        # Start with equal weights
        self._current_weights = np.ones(self.num_stocks, dtype=np.float32) / self.num_stocks
        self._portfolio_value = 1.0

        observation = self._get_observation()
        return observation, {}

    def step(self, action: np.ndarray):
        """
        Execute one time step: rebalance the portfolio and move forward one day.

        Args:
            action: Raw weights from the agent (will be normalized to sum to 1).

        Returns:
            observation, reward, terminated, truncated, info
        """
        # Normalize action to valid portfolio weights (sum to 1)
        new_weights = self._normalize_weights(action)

        # Calculate transaction costs from weight changes
        weight_change = np.abs(new_weights - self._current_weights)
        transaction_cost = np.sum(weight_change) * self.transaction_cost_rate

        # Get today's returns
        day_returns = self.returns[self._current_step]

        # Portfolio return = weighted sum of individual stock returns
        portfolio_return = np.dot(new_weights, day_returns)

        # Update portfolio value
        self._portfolio_value *= np.exp(portfolio_return) * (1 - transaction_cost)

        # ── Reward: risk-adjusted return with transaction cost penalty ──
        # Log return (the primary signal)
        reward = portfolio_return

        # Penalize transaction costs
        reward -= transaction_cost

        # Penalize high volatility (using recent portfolio return variance)
        if self._current_step > self.lookback_window + 5:
            start = max(self.lookback_window, self._current_step - 20)
            recent_returns = []
            for i in range(start, self._current_step):
                r = np.dot(new_weights, self.returns[i])
                recent_returns.append(r)
            volatility = np.std(recent_returns) if len(recent_returns) > 1 else 0.0
            reward -= self.risk_penalty * volatility

        # Update state
        self._current_weights = new_weights
        self._current_step += 1

        # Check if episode is over
        terminated = self._current_step >= self.num_days - 1
        truncated = False

        observation = self._get_observation()

        info = {
            "portfolio_value": self._portfolio_value,
            "weights": new_weights.tolist(),
            "transaction_cost": transaction_cost,
        }

        return observation, float(reward), terminated, truncated, info

    # ── Helper Methods ────────────────────────────────────────────────

    def _get_observation(self) -> np.ndarray:
        """
        Build the observation vector from:
        1. Flattened lookback returns
        2. Latest technical indicators (if available)
        3. Current portfolio weights
        """
        parts = []

        # Lookback returns — shape: (lookback_window * num_stocks,)
        start = self._current_step - self.lookback_window
        lookback_returns = self.returns[start:self._current_step].flatten()
        parts.append(lookback_returns)

        # Latest features (if provided)
        if self.features is not None:
            latest_features = self.features[self._current_step]
            parts.append(latest_features)

        # Current portfolio weights
        parts.append(self._current_weights)

        observation = np.concatenate(parts).astype(np.float32)
        return observation

    @staticmethod
    def _normalize_weights(weights: np.ndarray) -> np.ndarray:
        """
        Normalize raw agent outputs to valid portfolio weights.

        Clips negative values to 0, then divides by sum so weights sum to 1.
        Falls back to equal weights if all values are zero.
        """
        weights = np.clip(weights, 0.0, None)
        total = np.sum(weights)
        if total < 1e-8:
            # Fallback to equal weights
            return np.ones_like(weights) / len(weights)
        return weights / total
