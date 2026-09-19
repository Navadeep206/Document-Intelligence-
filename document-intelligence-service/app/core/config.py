"""Application configuration module using Pydantic Settings."""

from functools import lru_cache
import json
from typing import Annotated, Any, Union

from pydantic import BeforeValidator, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_cors_origins(v: Any) -> list[str]:
    """Parse ALLOWED_ORIGINS whether provided as JSON list or comma-separated string."""
    if isinstance(v, list):
        return [str(item).strip() for item in v if str(item).strip()]
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return []
        if v.startswith("[") and v.endswith("]"):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in v.split(",") if item.strip()]
    return []


class Settings(BaseSettings):
    """Central application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application Metadata
    APP_NAME: str = Field(default="document-intelligence-service")
    APP_ENV: str = Field(default="development")
    DEBUG: bool = Field(default=False)
    API_V1_PREFIX: str = Field(default="/api/v1")

    # Database Configuration (PostgreSQL)
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@postgres:5432/document_intelligence"
    )

    # Redis & Distributed Coordination
    REDIS_URL: str = Field(default="redis://redis:6379/0")

    # Celery Worker Configuration
    CELERY_BROKER_URL: str = Field(default="redis://redis:6379/1")
    CELERY_RESULT_BACKEND: str = Field(default="redis://redis:6379/2")
    CELERY_WORKER_CONCURRENCY: int = Field(default=2)
    CELERY_TASK_MAX_RETRIES: int = Field(default=3)
    CELERY_TASK_RETRY_BACKOFF: int = Field(default=5)

    # CORS Configuration
    ALLOWED_ORIGINS: Annotated[list[str], BeforeValidator(parse_cors_origins)] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # Operational & File Handling Controls
    LOG_LEVEL: str = Field(default="INFO")
    MAX_UPLOAD_SIZE_MB: int = Field(default=25)
    UPLOAD_DIR: str = Field(default="./storage/uploads")

    # Security & Authentication (JWT)
    JWT_SECRET_KEY: str = Field(
        default="insecure-dev-secret-key-must-be-replaced-in-production-1234567890"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)

    # Document Ingestion & OCR Processing (Phase 5)
    TESSERACT_CMD: str = Field(default="tesseract")
    OCR_DPI: int = Field(default=250)
    MIN_NATIVE_TEXT_CHARS: int = Field(default=20)
    OCR_LANGUAGE: str = Field(default="eng")

    # Confidence Engine Configuration (Phase 8)
    CONFIDENCE_OCR_WEIGHT: float = Field(default=0.20)
    CONFIDENCE_TEXT_WEIGHT: float = Field(default=0.20)
    CONFIDENCE_BOUNDARY_WEIGHT: float = Field(default=0.15)
    CONFIDENCE_NUMBER_WEIGHT: float = Field(default=0.10)
    CONFIDENCE_OPTIONS_WEIGHT: float = Field(default=0.10)
    CONFIDENCE_SOURCE_WEIGHT: float = Field(default=0.10)
    CONFIDENCE_PAGE_WEIGHT: float = Field(default=0.05)
    CONFIDENCE_ANSWER_WEIGHT: float = Field(default=0.10)

    # Status Classification Thresholds
    CONFIDENCE_THRESHOLD_EXTRACTED: float = Field(default=0.85)
    CONFIDENCE_THRESHOLD_PARTIAL: float = Field(default=0.60)

    @model_validator(mode="after")
    def validate_confidence_configuration(self) -> "Settings":
        total_weight = (
            self.CONFIDENCE_OCR_WEIGHT
            + self.CONFIDENCE_TEXT_WEIGHT
            + self.CONFIDENCE_BOUNDARY_WEIGHT
            + self.CONFIDENCE_NUMBER_WEIGHT
            + self.CONFIDENCE_OPTIONS_WEIGHT
            + self.CONFIDENCE_SOURCE_WEIGHT
            + self.CONFIDENCE_PAGE_WEIGHT
            + self.CONFIDENCE_ANSWER_WEIGHT
        )
        if abs(total_weight - 1.0) > 1e-4:
            raise ValueError(
                f"Confidence weights must sum to 1.0, got {total_weight:.4f}"
            )
        if self.CONFIDENCE_THRESHOLD_PARTIAL >= self.CONFIDENCE_THRESHOLD_EXTRACTED:
            raise ValueError(
                f"CONFIDENCE_THRESHOLD_PARTIAL ({self.CONFIDENCE_THRESHOLD_PARTIAL}) must be less than CONFIDENCE_THRESHOLD_EXTRACTED ({self.CONFIDENCE_THRESHOLD_EXTRACTED})"
            )
        return self



@lru_cache
def get_settings() -> Settings:
    """Return cached instance of application settings."""
    return Settings()
