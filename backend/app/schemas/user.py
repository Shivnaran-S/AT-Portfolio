"""
Pydantic schemas for authentication requests and responses.
"""

from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    """Data required to create a new account."""
    username: str = Field(..., min_length=3, max_length=50, examples=["investor1"])
    password: str = Field(..., min_length=6, max_length=100, examples=["securepass123"])


class LoginRequest(BaseModel):
    """Data required to sign in."""
    username: str = Field(..., examples=["investor1"])
    password: str = Field(..., examples=["securepass123"])


class TokenResponse(BaseModel):
    """JWT token returned after successful login."""
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public user information."""
    id: str
    username: str
    has_portfolio: bool = False

    class Config:
        from_attributes = True
