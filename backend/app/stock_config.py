"""
Configurable stock universe for the Indian Stock Market (NSE).

To add, remove, or replace a company, simply edit the STOCK_UNIVERSE list below.
Use the Yahoo Finance ticker format: SYMBOL.NS for NSE stocks.
"""

STOCK_UNIVERSE = [
    {
        "symbol": "TCS.NS",
        "name": "Tata Consultancy Services",
        "sector": "Information Technology",
    },
    {
        "symbol": "HDFCBANK.NS",
        "name": "HDFC Bank",
        "sector": "Banking & Finance",
    },
    {
        "symbol": "SUNPHARMA.NS",
        "name": "Sun Pharmaceutical Industries",
        "sector": "Healthcare & Pharmaceuticals",
    },
    {
        "symbol": "MARUTI.NS",
        "name": "Maruti Suzuki India",
        "sector": "Automobile",
    },
    {
        "symbol": "RELIANCE.NS",
        "name": "Reliance Industries",
        "sector": "Energy",
    },
    {
        "symbol": "HINDUNILVR.NS",
        "name": "Hindustan Unilever",
        "sector": "Consumer Goods",
    },
    {
        "symbol": "LT.NS",
        "name": "Larsen & Toubro",
        "sector": "Infrastructure & Construction",
    },
    {
        "symbol": "BHARTIARTL.NS",
        "name": "Bharti Airtel",
        "sector": "Telecommunications",
    },
    {
        "symbol": "TITAN.NS",
        "name": "Titan Company",
        "sector": "Manufacturing",
    },
    {
        "symbol": "HDFCLIFE.NS",
        "name": "HDFC Life Insurance",
        "sector": "Insurance",
    },
]


def get_symbols() -> list[str]:
    """Return a list of all ticker symbols in the stock universe."""
    return [stock["symbol"] for stock in STOCK_UNIVERSE]

def get_stock_info(symbol: str) -> dict | None:
    """Look up a stock by its symbol. Returns None if not found."""
    for stock in STOCK_UNIVERSE:
        if stock["symbol"] == symbol:
            return stock
    return None
