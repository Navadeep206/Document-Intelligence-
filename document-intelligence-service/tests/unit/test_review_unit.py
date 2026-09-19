"""Unit tests for review items lifecycle, transitions, and deduplication."""

import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.document import Document
from app.db.models.enums import (
    DocumentRole,
    DocumentStatus,
    DocumentType,
    QuestionStatus,
    QuestionType,
    ReviewSeverity,
    ReviewStatus,
)
from app.db.models.page import DocumentPage
from app.db.models.question import Question
from app.db.models.review import ReviewItem
from app.db.models.user import User
from app.services.confidence.review_service import review_service


@pytest.fixture
def test_user(db: Session) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"review_test_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="argon2id$testhash",
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def review_doc(db: Session, test_user: User) -> tuple[Document, Question]:
    doc = Document(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        filename="exam_reviews.pdf",
        storage_path="mock/path.pdf",
        mime_type="application/pdf",
        document_type=DocumentType.PDF,
        document_role=DocumentRole.QUESTION_PAPER,
        file_size=1024,
        status=DocumentStatus.COMPLETED,
    )
    db.add(doc)
    db.flush()

    page = DocumentPage(
        id=uuid.uuid4(),
        document_id=doc.id,
        page_number=1,
        text_content="Page 1 content with low OCR",
        ocr_used=True,
        ocr_confidence=0.40,
    )
    db.add(page)
    db.flush()

    q = Question(
        id=uuid.uuid4(),
        document_id=doc.id,
        question_number=None,  # missing number -> triggers review
        question_text="Short text",
        question_type=QuestionType.UNKNOWN,
        status=QuestionStatus.REVIEW_REQUIRED,
    )
    db.add(q)
    db.commit()
    return doc, q


def test_review_sync_and_deduplication(db: Session, review_doc: tuple[Document, Question]) -> None:
    doc, q = review_doc
    # Run sync 1
    summary1 = review_service.sync_document_reviews(doc.id, db)
    items1 = db.scalars(select(ReviewItem).where(ReviewItem.document_id == doc.id)).all()
    count1 = len(items1)
    assert count1 > 0

    # Run sync 2 (should be idempotent - no duplicate items created)
    summary2 = review_service.sync_document_reviews(doc.id, db)
    items2 = db.scalars(select(ReviewItem).where(ReviewItem.document_id == doc.id)).all()
    assert len(items2) == count1


def test_resolve_and_ignore_review_transitions(db: Session, review_doc: tuple[Document, Question], test_user: User) -> None:
    doc, q = review_doc
    item = ReviewItem(
        id=uuid.uuid4(),
        document_id=doc.id,
        question_id=q.id,
        severity=ReviewSeverity.HIGH,
        status=ReviewStatus.OPEN,
        reason="MISSING_QUESTION_NUMBER",
        details="Question lacks an identifiable number marker",
    )
    db.add(item)
    db.commit()

    # 1. Transition OPEN -> RESOLVED
    resolved = review_service.resolve_review_item(
        review_id=item.id,
        new_status=ReviewStatus.RESOLVED,
        current_user_id=test_user.id,
        db=db,
    )
    assert resolved.status == ReviewStatus.RESOLVED
    assert resolved.resolved_at is not None

    # 2. Transition RESOLVED -> IGNORED
    ignored = review_service.resolve_review_item(
        review_id=item.id,
        new_status=ReviewStatus.IGNORED,
        current_user_id=test_user.id,
        db=db,
    )
    assert ignored.status == ReviewStatus.IGNORED

    # 3. Re-open: IGNORED -> OPEN
    reopened = review_service.resolve_review_item(
        review_id=item.id,
        new_status=ReviewStatus.OPEN,
        current_user_id=test_user.id,
        db=db,
    )
    assert reopened.status == ReviewStatus.OPEN


def test_nonexistent_review_resolution_raises(db: Session, test_user: User) -> None:
    with pytest.raises(ValueError):
        review_service.resolve_review_item(
            review_id=uuid.uuid4(),
            new_status=ReviewStatus.RESOLVED,
            current_user_id=test_user.id,
            db=db,
        )
