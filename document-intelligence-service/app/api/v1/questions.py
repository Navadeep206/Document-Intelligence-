"""Individual question retrieval endpoints."""

import logging
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user
from app.db.database import get_db
from app.db.models.document import Document
from app.db.models.question import Question
from app.db.models.user import User
from app.schemas.question import QuestionResponse

logger = logging.getLogger("document-intelligence-service")
router = APIRouter()


@router.get(
    "/{question_id}",
    response_model=QuestionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Individual Question",
    description="Retrieve a single structured question by its UUID with options, source pages, and associated answers.",
)
def get_question(
    question_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> QuestionResponse:
    """Retrieve question for authorized document owner."""
    question = db.scalar(
        select(Question)
        .join(Document, Question.document_id == Document.id)
        .where(
            Question.id == question_id,
            Document.owner_id == current_user.id,
        )
        .options(
            selectinload(Question.options),
            selectinload(Question.sources),
            selectinload(Question.review_items),
        )
    )

    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "QUESTION_NOT_FOUND",
                "message": "Question not found",
            },
        )

    return QuestionResponse.model_validate(question)
