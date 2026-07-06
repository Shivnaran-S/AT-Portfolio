"""
Authentication service — handles user registration, login, and JWT tokens.
"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

# Bcrypt password hashing context
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Handles all authentication operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Password Utilities ────────────────────────────────────────────

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a plain-text password using bcrypt."""
        return _pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Check a plain-text password against a bcrypt hash."""
        return _pwd_context.verify(plain_password, hashed_password)

    # ── JWT Utilities ─────────────────────────────────────────────────

    @staticmethod
    def create_access_token(user_id: str) -> str:
        """
        Generate a JWT access token for the given user.

        The token contains the user_id in the 'sub' claim and expires
        after the configured number of minutes.
        """
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_expiration_minutes
        )
        payload = {"sub": user_id, "exp": expire}
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        return token

    @staticmethod
    def decode_token(token: str) -> str | None:
        """
        Decode a JWT token and return the user_id.

        Returns None if the token is invalid or expired.
        """
        try:
            payload = jwt.decode(
                token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
            )
            user_id: str = payload.get("sub")
            return user_id
        except JWTError:
            return None

    # ── User Operations ───────────────────────────────────────────────

    async def get_user_by_username(self, username: str) -> User | None:
        """Find a user by their username."""
        query = select(User).where(User.username == username)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: str) -> User | None:
        """Find a user by their ID."""
        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_user(self, username: str, password: str) -> User:
        """
        Register a new user.

        Raises ValueError if the username is already taken.
        """
        # Check if username is already taken
        existing = await self.get_user_by_username(username)
        if existing is not None:
            raise ValueError(f"Username '{username}' is already taken.")

        # Create the user with a hashed password
        user = User(
            username=username,
            password_hash=self.hash_password(password),
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def authenticate_user(self, username: str, password: str) -> User | None:
        """
        Verify credentials and return the user if valid.

        Returns None if the username doesn't exist or the password is wrong.
        """
        user = await self.get_user_by_username(username)
        if user is None:
            return None
        if not self.verify_password(password, user.password_hash):
            return None
        return user
