"""Review API endpoints for human-in-the-loop issue triage and resolution."""

import logging
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.database import get_db
from app.db.models.document import Document
from app.db.models.enums import ReviewStatus
from app.db.models.question import Question
from app.db.models.review import ReviewItem
from app.db.models.user import User
from app.schemas.review import (
    ReviewItemResponse,
    ReviewItemUpdate,
)
from app.services.confidence.review_service import review_service

logger = logging.getLogger("document-intelligence-service")

router = APIRouter(tags=["Human Review"])


@router.patch(
    "/reviews/{review_id}",
    response_model=ReviewItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Review Item Status",
    description="Mark a human review issue as RESOLVED, IGNORED, or reopen as OPEN. Restricted to document owner.",
)
def update_review_item(
    review_id: uuid.UUID,
    payload: ReviewItemUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReviewItemResponse:
    """Update resolution state of an identified review issue."""
    item = db.scalar(
        select(ReviewItem)
        .join(Document, ReviewItem.document_id == Document.id)
        .where(ReviewItem.id == review_id, Document.owner_id == current_user.id)
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review item was not found or access is denied",
        )

    resolved_item = review_service.resolve_review_item(
        review_id=review_id,
        new_status=payload.status,
        current_user_id=current_user.id,
        db=db,
    )
    return ReviewItemResponse.model_validate(resolved_item)


@router.get(
    "/questions/{question_id}/reviews",
    response_model=list[ReviewItemResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Question Review Items",
    description="Retrieve all identified review issues for a specific question. Restricted to document owner.",
)
def get_question_review_items(
    question_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ReviewItemResponse]:
    """List all review issues associated with a specific extracted question."""
    question = db.scalar(
        select(Question)
        .join(Document, Question.document_id == Document.id)
        .where(Question.id == question_id, Document.owner_id == current_user.id)
    )
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question was not found or access is denied",
        )

    items = db.scalars(
        select(ReviewItem)
        .where(ReviewItem.question_id == question_id)
        .order_by(ReviewItem.created_at.desc())
    ).all()

    return [ReviewItemResponse.model_validate(item) for item in items]
