"""API v1 router aggregating all v1 sub-routers."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.questions import router as questions_router
from app.api.v1.reviews import router as reviews_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["Health"])
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(documents_router, prefix="/documents", tags=["Documents"])
api_router.include_router(questions_router, prefix="/questions", tags=["Questions"])
api_router.include_router(reviews_router, tags=["Human Review"])

__all__ = ["api_router"]
