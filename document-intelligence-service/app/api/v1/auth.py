"""Authentication endpoints: registration, login, and user profile."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.auth import TokenResponse, UserLogin, UserRegister, UserResponse

logger = logging.getLogger("document-intelligence-service")
router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New User Account",
    description="Creates a new user account with normalized email and Argon2id hashed password.",
)
def register(
    payload: UserRegister,
    db: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    """Register a new user account."""
    normalized_email = payload.email.lower().strip()

    # Check for existing account
    existing_user = db.scalar(
        select(User).where(User.email == normalized_email)
    )
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "EMAIL_ALREADY_REGISTERED",
                "message": "An account with this email address already exists",
            },
        )

    # Hash password with Argon2id
    hashed = hash_password(payload.password)

    new_user = User(
        email=normalized_email,
        password_hash=hashed,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    logger.info("New user registered successfully: %s", new_user.id)
    return UserResponse.model_validate(new_user)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User Login",
    description="Authenticate user with email and password, returning a signed JWT access token.",
)
def login(
    payload: UserLogin,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    """Authenticate credentials and generate JWT token."""
    normalized_email = payload.email.lower().strip()

    user = db.scalar(
        select(User).where(User.email == normalized_email)
    )

    invalid_cred_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "INVALID_CREDENTIALS",
            "message": "Invalid email or password",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )

    if user is None:
        # Run dummy verify to mitigate timing attacks against non-existent accounts
        verify_password("dummy", "$argon2id$v=19$m=65536,t=3,p=4$dummyhashforprotection$dummy")
        raise invalid_cred_exception

    if not verify_password(payload.password, user.password_hash):
        raise invalid_cred_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "USER_INACTIVE",
                "message": "User account has been deactivated",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=str(user.id))
    logger.info("User logged in successfully: %s", user.id)
    return TokenResponse(access_token=access_token, token_type="bearer")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current User Profile",
    description="Returns account metadata for the authenticated user.",
)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Return authenticated user profile."""
    return UserResponse.model_validate(current_user)
