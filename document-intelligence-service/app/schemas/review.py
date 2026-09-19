"""Pydantic request and response schemas for ReviewItem and confidence telemetry."""

import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import ReviewSeverity, ReviewStatus


class ReviewItemResponse(BaseModel):
    """Schema representing an individual review issue."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    question_id: Optional[uuid.UUID] = None
    page_id: Optional[uuid.UUID] = None
    severity: ReviewSeverity
    status: ReviewStatus
    reason: str
    details: Optional[str] = None
    confidence: Optional[float] = None
    created_at: datetime.datetime
    resolved_at: Optional[datetime.datetime] = None


class ReviewItemListResponse(BaseModel):
    """Paginated list of review issues."""

    items: list[ReviewItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ReviewItemUpdate(BaseModel):
    """Schema for updating a review item status."""

    status: ReviewStatus = Field(
        ...,
        description="Target status for review issue: OPEN, RESOLVED, or IGNORED",
    )


class DocumentReviewSummaryResponse(BaseModel):
    """Summary metrics of review issues and question confidence across a document."""

    document_id: uuid.UUID
    total_questions: int
    high_confidence_questions: int
    partial_questions: int
    review_required_questions: int
    open_review_items: int
    resolved_review_items: int
    ignored_review_items: int
    unmatched_answers: int
    ambiguous_answers: int
