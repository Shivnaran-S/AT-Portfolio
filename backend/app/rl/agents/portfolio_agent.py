"""
PPO agent for portfolio optimization.

Uses Stable-Baselines3's PPO implementation with MlpPolicy to learn
optimal portfolio weights from historical market data.
"""

import logging
import os

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.env_checker import check_env

from app.rl.environments.portfolio_env import PortfolioEnv

logger = logging.getLogger(__name__)

# Default path for saving/loading trained models
_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
_DEFAULT_MODEL_PATH = os.path.join(_MODEL_DIR, "portfolio_ppo")


class PortfolioAgent:
    """
    PPO-based portfolio optimization agent.

    This agent learns to allocate capital across a set of stocks
    by maximizing risk-adjusted returns.
    """

    def __init__(self, model_path: str | None = None):
        """
        Args:
            model_path: Path to a saved model (without .zip extension).
                        If None, uses the default path.
        """
        self.model_path = model_path or _DEFAULT_MODEL_PATH
        self.model: PPO | None = None

    # ── Training ──────────────────────────────────────────────────────

    def train(
        self,
        returns: np.ndarray,
        features: np.ndarray | None = None,
        total_timesteps: int = 50_000,
        lookback_window: int = 30,
    ) -> dict:
        """
        Train the PPO agent on historical return data.

        Args:
            returns: Array of shape (num_days, num_stocks) with daily log returns.
            features: Optional technical indicators array.
            total_timesteps: Total training steps for PPO.
            lookback_window: Number of days in the lookback observation.

        Returns:
            A dict with training info (e.g., final portfolio value).
        """
        # Create the environment
        env = PortfolioEnv(
            returns=returns,
            features=features,
            lookback_window=lookback_window,
        )

        # Validate the environment
        try:
            check_env(env, warn=True)
        except Exception as e:
            logger.warning(f"Environment check warning: {e}")

        # Initialize PPO with tuned hyperparameters
        self.model = PPO(
            policy="MlpPolicy",
            env=env,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,     # Encourage exploration
            verbose=1,
        )

        # Train
        logger.info(f"Training portfolio PPO for {total_timesteps} timesteps...")
        self.model.learn(total_timesteps=total_timesteps)

        # Save the trained model
        self.save_model()

        logger.info("Portfolio PPO training complete.")
        return {"status": "trained", "timesteps": total_timesteps}

    # ── Prediction ────────────────────────────────────────────────────

    def predict(self, observation: np.ndarray) -> np.ndarray:
        """
        Predict optimal portfolio weights given the current observation.

        Args:
            observation: The state vector matching the environment's observation space.

        Returns:
            Normalized portfolio weights array of shape (num_stocks,).
        """
        if self.model is None:
            self.load_model()

        action, _ = self.model.predict(observation, deterministic=True)

        # Normalize to valid weights
        weights = np.clip(action, 0.0, None)
        total = np.sum(weights)
        if total < 1e-8:
            weights = np.ones_like(weights) / len(weights)
        else:
            weights = weights / total

        """        
        # Apply Softmax to ensure weights are in [0, 1] and sum to exactly 1.
        # We subtract np.max(action) for numerical stability (prevents overflow).
        shifted_actions = action - np.max(action)
        exp_actions = np.exp(shifted_actions)
        weights = exp_actions / np.sum(exp_actions)
        """

        return weights

    def generate_weights(
        self,
        returns: np.ndarray,
        features: np.ndarray | None = None,
        lookback_window: int = 30,
    ) -> np.ndarray:
        """
        High-level method to generate portfolio weights from recent market data.

        This creates a temporary environment, builds the observation from the
        latest data, and runs a single prediction.

        Args:
            returns: Recent log returns array, shape (num_days, num_stocks).
                     Must have at least `lookback_window` days.
            features: Optional technical indicators for the latest day.
            lookback_window: Number of lookback days.

        Returns:
            Normalized portfolio weights, shape (num_stocks,).
        """
        if self.model is None:
            self.load_model()

        num_stocks = returns.shape[1]

        # Build observation manually from the latest data
        parts = []

        # Lookback returns (flatten the last `lookback_window` days)
        if returns.shape[0] >= lookback_window:
            lookback = returns[-lookback_window:].flatten()
        else:
            # Pad with zeros if not enough history
            lookback = np.zeros(lookback_window * num_stocks, dtype=np.float32)
            available = returns.flatten()
            lookback[-len(available):] = available

        parts.append(lookback)

        # Features (latest)
        if features is not None:
            parts.append(features[-1] if len(features.shape) > 1 else features)

        # Current weights (assume equal for initial allocation)
        current_weights = np.ones(num_stocks, dtype=np.float32) / num_stocks
        parts.append(current_weights)

        observation = np.concatenate(parts).astype(np.float32)

        return self.predict(observation)

    # ── Persistence ───────────────────────────────────────────────────

    def save_model(self, path: str | None = None):
        """Save the trained model to disk."""
        save_path = path or self.model_path
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        self.model.save(save_path)
        logger.info(f"Portfolio model saved to {save_path}")

    def load_model(self, path: str | None = None):
        """Load a trained model from disk."""
        load_path = path or self.model_path
        if not os.path.exists(load_path + ".zip"):
            raise FileNotFoundError(
                f"No trained model found at {load_path}.zip. "
                "Run the training script first: python -m app.rl.training.train_portfolio"
            )
        self.model = PPO.load(load_path)
        logger.info(f"Portfolio model loaded from {load_path}")

    @property
    def is_trained(self) -> bool:
        """Check if a trained model exists on disk."""
        return os.path.exists(self.model_path + ".zip")
