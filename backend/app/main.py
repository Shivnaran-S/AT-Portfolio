"""
AT-PORTFOLIO — FastAPI Application Entry Point.

This is the main module that creates the FastAPI app, registers all routers,
and configures middleware (CORS, etc.).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.routers import auth, market, portfolio, trading, demo

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Creates database tables on startup (for development).
    In production, use Alembic migrations instead.
    """
    logger.info("Starting AT-PORTFOLIO backend...")

    # Create tables if they don't exist (development convenience)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready.")

    yield  # Application runs here

    logger.info("Shutting down AT-PORTFOLIO backend...")
    await engine.dispose()


# ── Create the FastAPI application ────────────────────────────────────

app = FastAPI(
    title="AT-PORTFOLIO API",
    description=(
        "Algorithmic Trading & Portfolio Management platform powered by "
        "PPO (Proximal Policy Optimization). Provides portfolio optimization, "
        "algorithmic trade execution, and a demo mode with simulated markets."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS Middleware ───────────────────────────────────────────────────
# Allow the Vue.js frontend to make requests to this API.

origins = [origin.strip() for origin in settings.cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register Routers ─────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(market.router)
app.include_router(portfolio.router)
app.include_router(trading.router)
app.include_router(demo.router)


# ── Health Check ──────────────────────────────────────────────────────

@app.get("/api/health", tags=["System"])
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "service": "AT-PORTFOLIO API"}
