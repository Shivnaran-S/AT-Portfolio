"""
Authentication router — signup, login, and current user endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user import SignupRequest, LoginRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthService
from app.routers.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(request: SignupRequest, db: AsyncSession = Depends(get_db)):
    """
    Create a new user account.

    - **username**: 3–50 characters, must be unique.
    - **password**: minimum 6 characters.
    """
    auth_service = AuthService(db)
    try:
        user = await auth_service.create_user(request.username, request.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return UserResponse(id=user.id, username=user.username, has_portfolio=False)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Sign in with username and password.

    Returns a JWT access token on success.
    """
    auth_service = AuthService(db)
    user = await auth_service.authenticate_user(request.username, request.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    token = AuthService.create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Get the currently authenticated user's profile.

    Requires a valid JWT token in the Authorization header.
    """
    has_portfolio = current_user.portfolio is not None
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        has_portfolio=has_portfolio,
    )
