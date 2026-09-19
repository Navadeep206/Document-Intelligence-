"""FastAPI application entrypoint, lifespan configuration, and middleware registration."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import RequestLoggingMiddleware, logger, setup_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle manager handling startup initialization and clean shutdown."""
    setup_logging()
    logger.info(
        "Starting %s [env=%s, debug=%s, prefix=%s]",
        settings.APP_NAME,
        settings.APP_ENV,
        settings.DEBUG,
        settings.API_V1_PREFIX,
    )
    yield
    logger.info("Shutting down %s cleanly", settings.APP_NAME)


def create_application() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    app = FastAPI(
        title="Document Intelligence & Question Extraction Service",
        description=(
            "Production-oriented backend service for scalable, asynchronous "
            "document processing, question/option extraction, and answer-key reconciliation."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS configuration
    if settings.ALLOWED_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.ALLOWED_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Request duration and tracing middleware
    app.add_middleware(RequestLoggingMiddleware)

    # Global error handlers
    register_exception_handlers(app)

    from app.api.v1.health import router as health_router

    # Mount API routes
    app.include_router(health_router, prefix="/health", tags=["Health"])
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_application()
