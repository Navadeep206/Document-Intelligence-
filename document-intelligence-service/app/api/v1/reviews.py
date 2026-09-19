"""Review API endpoints for human-in-the-loop issue triage and resolution."""

import logging
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.database import get_db
from app.db.models.document import Document
from app.db.models.enums import ReviewSeverity, ReviewStatus
from app.db.models.question import Question
from app.db.models.review import ReviewItem
from app.db.models.user import User
from app.schemas.review import (
    ReviewItemResponse,
    ReviewItemListResponse,
    ReviewItemUpdate,
)
from app.services.confidence.review_service import review_service

logger = logging.getLogger("document-intelligence-service")

router = APIRouter(tags=["Human Review"])


@router.get(
    "/reviews",
    response_model=ReviewItemListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Review Items",
    description="Retrieve all review issues across documents owned by the authenticated user.",
)
def list_review_items(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[Optional[ReviewStatus], Query(alias="status")] = None,
    severity: Optional[ReviewSeverity] = None,
    document_id: Optional[uuid.UUID] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ReviewItemListResponse:
    """List all review items across user's documents with optional filtering and pagination."""
    stmt = (
        select(ReviewItem)
        .join(Document, ReviewItem.document_id == Document.id)
        .where(Document.owner_id == current_user.id)
    )
    if status_filter:
        stmt = stmt.where(ReviewItem.status == status_filter)
    if severity:
        stmt = stmt.where(ReviewItem.severity == severity)
    if document_id:
        stmt = stmt.where(ReviewItem.document_id == document_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.order_by(ReviewItem.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return ReviewItemListResponse(
        items=[ReviewItemResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )



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
