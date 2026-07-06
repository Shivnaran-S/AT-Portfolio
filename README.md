# AT-PORTFOLIO — Algorithmic Trading & Portfolio Management

> **PPO-powered Portfolio Optimization & Algorithmic Trading for the Indian Stock Market (NSE)**

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)
![Vue.js](https://img.shields.io/badge/Vue.js-3-4FC08D?logo=vuedotjs)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql)
![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-EE4C2C?logo=pytorch)

---

## Overview

AT-PORTFOLIO is a full-stack investment platform that uses **Proximal Policy Optimization (PPO)**, a reinforcement learning algorithm, to:

1. **Optimize Portfolio Allocation** — Analyze 10 diversified NSE stocks and generate optimal portfolio weights based on historical price data and technical indicators.
2. **Execute Algorithmic Trades** — Determine optimal timing and order slicing for trade execution throughout the trading day, minimizing market impact and maximizing execution quality.
3. **Manage Portfolios** — Track holdings, P&L (realized and unrealized), portfolio growth, and support fund deposits/withdrawals with automatic rebalancing.

### Key Features

- 🧠 **Dual PPO Models** — Separate MDPs for portfolio optimization and trade execution
- 📊 **Real-time Dashboard** — Live portfolio tracking with comprehensive metrics
- 🔄 **Smart Rebalancing** — Only trades the difference between current and target allocations
- 🎮 **Demo Mode** — Simulated market environment for strategy experimentation
- 📈 **10 NSE Stocks** — Diversified across IT, Banking, Pharma, Auto, Energy, and more
- 🔐 **Secure Auth** — JWT-based authentication with bcrypt password hashing

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vue.js 3, Vite, Pinia, Chart.js, Vue Router |
| Backend | FastAPI, SQLAlchemy 2.0 (async), Pydantic V2 |
| Database | PostgreSQL (via asyncpg) |
| ML/RL | Stable-Baselines3 (PPO), Gymnasium, PyTorch |
| Data | yfinance, pandas, NumPy |

---

## Project Structure

```
AT2/
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── main.py           # Entry point
│   │   ├── config.py         # Settings
│   │   ├── database.py       # Async DB engine
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── routers/          # API endpoints
│   │   ├── services/         # Business logic
│   │   └── rl/               # Reinforcement learning
│   │       ├── environments/ # Gymnasium environments
│   │       ├── agents/       # PPO agents
│   │       ├── data/         # Market data utilities
│   │       └── training/     # Training scripts
│   ├── alembic/              # Database migrations
│   ├── tests/                # Backend tests
│   └── requirements.txt
├── frontend/                 # Vue.js 3 + Vite application
│   ├── src/
│   │   ├── views/            # Page components
│   │   ├── components/       # Reusable UI components
│   │   ├── stores/           # Pinia state management
│   │   ├── composables/      # Reusable logic
│   │   └── router/           # Vue Router config
│   └── package.json
├── .gitignore
├── README.md
└── LICENSE
```

---

## Setup Instructions

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+

### Backend Setup

```bash
# Navigate to backend
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env with your database credentials

#Create a database named "atportfolio" in PostgreSQL
psql -U postgres
CREATE DATABASE atportfolio;

# Run database migrations (IMPORTANT: Ensure you're in the backend directory and the virtual environment is activated)
alembic upgrade head

# Train RL models (first time only)
python -m app.rl.training.train_portfolio
python -m app.rl.training.train_trading

# Start the server
uvicorn app.main:app --reload
```

### Frontend Setup

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

### Access the Application

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

---

## Stock Universe

| Company | Symbol | Sector |
|---------|--------|--------|
| TCS | TCS.NS | Information Technology |
| HDFC Bank | HDFCBANK.NS | Banking & Finance |
| Sun Pharma | SUNPHARMA.NS | Healthcare & Pharma |
| Maruti Suzuki | MARUTI.NS | Automobile |
| Reliance Industries | RELIANCE.NS | Energy |
| Hindustan Unilever | HINDUNILVR.NS | Consumer Goods |
| Larsen & Toubro | LT.NS | Infrastructure |
| Bharti Airtel | BHARTIARTL.NS | Telecom |
| Titan Company | TITAN.NS | Manufacturing |
| HDFC Life | HDFCLIFE.NS | Insurance |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/signup` | Create account |
| POST | `/api/auth/login` | Sign in |
| GET | `/api/auth/me` | Current user |
| GET | `/api/market/stocks` | Stock universe |
| GET | `/api/market/prices` | Current prices |
| POST | `/api/portfolio/initialize` | First-time setup |
| GET | `/api/portfolio/status` | Portfolio metrics |
| POST | `/api/portfolio/add-funds` | Deposit funds |
| POST | `/api/portfolio/withdraw-funds` | Withdraw funds |
| POST | `/api/portfolio/rebalance` | Rebalance portfolio |
| POST | `/api/trading/execute` | Execute trades |
| GET | `/api/trading/orders` | Order history |
| POST | `/api/demo/start` | Start demo session |
| POST | `/api/demo/optimize` | Demo optimization |
| POST | `/api/demo/trade` | Demo trading |

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
