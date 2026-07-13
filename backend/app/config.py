"""
Application configuration using Pydantic Settings.

Reads values from environment variables or a .env file.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the AT-PORTFOLIO backend."""

    # ---- Database ----
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/atportfolio"

    # ---- JWT Authentication ----
    jwt_secret_key: str = "change-this-to-a-random-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # ---- CORS ----
    cors_origins: str = "http://localhost:5173"

    # ---- Investment Limits ----
    max_investment: float = 10_000_000      # ₹1 Crore (live mode)
    demo_max_investment: float = 1_000_000  # ₹10 Lakhs (demo mode)

    # ---- Demo Simulation ----
    demo_simulation_duration_seconds: int = 60   # 5 minutes compressed trading day
    demo_simulation_steps: int = 78               # Number of 5-min intervals in a trading day

    # ---- NSE Market Hours (IST) ----
    nse_market_open_hour: int = 9
    nse_market_open_minute: int = 15
    nse_market_close_hour: int = 15
    nse_market_close_minute: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Single global instance — import this wherever settings are needed.
settings = Settings()
