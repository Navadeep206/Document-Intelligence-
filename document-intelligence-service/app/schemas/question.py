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
    """List of questions extracted from a document."""

    document_id: uuid.UUID
    total: int
    items: list[QuestionResponse]
