"""Pydantic schemas for AnswerKey and AnswerMapping API responses."""

import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class AnswerKeyResponse(BaseModel):
    """Metadata representation of an answer key schedule."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    source_document_id: Optional[uuid.UUID] = None
    name: str
    format_description: Optional[str] = None
    confidence: Optional[float] = None
    created_at: datetime.datetime


class AnswerMappingResponse(BaseModel):
    """Detailed answer entry representation linking reference to question."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    answer_key_id: uuid.UUID
    question_id: Optional[uuid.UUID] = None
    question_reference: Optional[str] = None
    answer_value: str
    confidence: Optional[float] = None
    source_page: Optional[int] = None
    status: str = "MATCHED"
    created_at: datetime.datetime


class AnswerMappingListResponse(BaseModel):
    """Paginated collection of answer mappings for a document."""

    document_id: uuid.UUID
    items: list[AnswerMappingResponse]
    page: int = Field(default=1, ge=1, description="Current page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    total: int = Field(default=0, ge=0, description="Total mappings")
    total_pages: int = Field(default=1, ge=0, description="Total pages")


class DocumentAnswersResponse(BaseModel):
    """Aggregate answer information for a question document."""

    document_id: uuid.UUID
    answer_key: Optional[AnswerKeyResponse] = None
    answers: list[AnswerMappingResponse] = Field(default_factory=list)


class AnswerKeySummaryResponse(BaseModel):
    """Summary telemetry for an answer key associated with a document."""

    document_id: uuid.UUID
    answer_key_id: Optional[uuid.UUID] = None
    source_document_id: Optional[uuid.UUID] = None
    confidence: Optional[float] = None
    total_mappings: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
