"""
Basic tests for the AT-PORTFOLIO backend.

Run with: pytest tests/ -v
"""

from app.config import Settings
from app.stock_config import STOCK_UNIVERSE, get_symbols, get_stock_info


class TestConfig:
    """Test application configuration."""

    def test_settings_has_defaults(self):
        """Settings should have sensible defaults."""
        settings = Settings()
        assert settings.jwt_algorithm == "HS256"
        assert settings.jwt_expiration_minutes > 0
        assert settings.demo_max_investment > 0

    def test_cors_origins_is_string(self):
        """CORS origins should be a comma-separated string."""
        settings = Settings()
        assert isinstance(settings.cors_origins, str)


class TestStockConfig:
    """Test stock universe configuration."""

    def test_stock_universe_has_10_stocks(self):
        """Should have exactly 10 stocks."""
        assert len(STOCK_UNIVERSE) == 10

    def test_all_stocks_have_ns_suffix(self):
        """All ticker symbols should end with .NS (NSE)."""
        for stock in STOCK_UNIVERSE:
            assert stock["symbol"].endswith(".NS"), f"{stock['symbol']} missing .NS suffix"

    def test_all_stocks_have_required_fields(self):
        """Each stock must have symbol, name, and sector."""
        for stock in STOCK_UNIVERSE:
            assert "symbol" in stock
            assert "name" in stock
            assert "sector" in stock

    def test_get_symbols_returns_list(self):
        """get_symbols() should return a list of ticker strings."""
        symbols = get_symbols()
        assert isinstance(symbols, list)
        assert len(symbols) == 10
        assert all(isinstance(s, str) for s in symbols)

    def test_get_stock_info_found(self):
        """Should find a stock by its symbol."""
        info = get_stock_info("TCS.NS")
        assert info is not None
        assert info["name"] == "Tata Consultancy Services"

    def test_get_stock_info_not_found(self):
        """Should return None for an unknown symbol."""
        info = get_stock_info("FAKE.NS")
        assert info is None

    def test_sectors_are_diverse(self):
        """Stocks should span multiple sectors."""
        sectors = set(stock["sector"] for stock in STOCK_UNIVERSE)
        assert len(sectors) >= 8, f"Only {len(sectors)} unique sectors"


class TestAuthService:
    """Test authentication utilities (non-async tests)."""

    def test_password_hashing(self):
        """Hashed password should verify correctly."""
        from app.services.auth_service import AuthService

        plain = "test_password_123"
        hashed = AuthService.hash_password(plain)

        assert hashed != plain
        assert AuthService.verify_password(plain, hashed)
        assert not AuthService.verify_password("wrong_password", hashed)

    def test_jwt_token_roundtrip(self):
        """Token should encode and decode user_id correctly."""
        from app.services.auth_service import AuthService

        user_id = "test-user-id-123"
        token = AuthService.create_access_token(user_id)

        decoded_id = AuthService.decode_token(token)
        assert decoded_id == user_id

    def test_jwt_invalid_token(self):
        """Invalid token should return None."""
        from app.services.auth_service import AuthService

        result = AuthService.decode_token("invalid.token.here")
        assert result is None
