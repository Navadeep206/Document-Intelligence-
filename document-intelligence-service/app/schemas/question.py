"""Pydantic schemas for Question and Option API responses."""

import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import AnswerSource, QuestionStatus, QuestionType


class QuestionOptionResponse(BaseModel):
    """Multiple choice option response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_id: uuid.UUID
    label: str
    option_text: str
    position: int
    created_at: datetime.datetime


class QuestionSourceResponse(BaseModel):
    """Provenance tracking response linking question to document page."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_page_id: uuid.UUID
    page_sequence: int
    created_at: datetime.datetime


class QuestionResponse(BaseModel):
    """Detailed structured question representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    question_number: Optional[str] = None
    question_text: str
    question_type: QuestionType
    status: QuestionStatus
    confidence: Optional[float] = None
    answer: Optional[str] = None
    answer_confidence: Optional[float] = None
    answer_source: Optional[AnswerSource] = None
    review_required: bool = False
    review_count: int = 0
    options: list[QuestionOptionResponse] = Field(default_factory=list)
    sources: list[QuestionSourceResponse] = Field(default_factory=list)
    created_at: datetime.datetime
    updated_at: datetime.datetime


class QuestionListResponse(BaseModel):
    """Paginated collection of questions extracted from a document."""

    document_id: uuid.UUID
    items: list[QuestionResponse]
    page: int = Field(default=1, ge=1, description="Current page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    total: int = Field(default=0, ge=0, description="Total questions matching query")
    total_pages: int = Field(default=1, ge=0, description="Total pages of questions")
