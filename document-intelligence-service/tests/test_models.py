"""Database domain model unit tests validating relationships, constraints, and cascades."""

from collections.abc import Generator
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import (
    AnswerKey,
    AnswerMapping,
    AnswerSource,
    Document,
    DocumentPage,
    DocumentRole,
    DocumentStatus,
    DocumentType,
    ProcessingJob,
    ProcessingJobStatus,
    Question,
    QuestionOption,
    QuestionSource,
    QuestionStatus,
    QuestionType,
    RelatedDocument,
    RelatedDocumentType,
    ReviewItem,
    ReviewSeverity,
    ReviewStatus,
    User,
)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Provide a transactional database session rolled back after each test."""
    session = SessionLocal()
    transaction = session.begin_nested()
    try:
        yield session
    finally:
        transaction.rollback()
        session.close()


def create_sample_user(db: Session, email_suffix: str = "") -> User:
    """Helper creating an active user record."""
    user = User(
        id=uuid.uuid4(),
        email=f"user_{uuid.uuid4().hex[:8]}{email_suffix}@example.com",
        password_hash="argon2id$mocked_hash_for_testing",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def create_sample_document(
    db: Session,
    owner_id: uuid.UUID,
    role: DocumentRole = DocumentRole.QUESTION_PAPER,
) -> Document:
    """Helper creating a sample document record."""
    doc = Document(
        id=uuid.uuid4(),
        owner_id=owner_id,
        filename="exam_physics_2026.pdf",
        storage_path="documents/2026/exam_physics_2026.pdf",
        mime_type="application/pdf",
        document_type=DocumentType.PDF,
        document_role=role,
        file_size=1048576,
        status=DocumentStatus.UPLOADED,
    )
    db.add(doc)
    db.flush()
    return doc


def test_user_email_uniqueness(db: Session) -> None:
    """Test that creating two users with the identical email raises IntegrityError."""
    shared_email = f"duplicate_{uuid.uuid4().hex[:8]}@example.com"
    u1 = User(
        id=uuid.uuid4(),
        email=shared_email,
        password_hash="hash_1",
        is_active=True,
    )
    db.add(u1)
    db.flush()

    u2 = User(
        id=uuid.uuid4(),
        email=shared_email,
        password_hash="hash_2",
        is_active=True,
    )
    db.add(u2)
    with pytest.raises(IntegrityError):
        db.flush()


def test_document_user_relationship(db: Session) -> None:
    """Test Document to User relationship bidirectionality."""
    user = create_sample_user(db)
    doc = create_sample_document(db, user.id)

    assert doc.owner.id == user.id
    assert doc.owner.email == user.email
    assert doc in user.documents


def test_document_page_relationship(db: Session) -> None:
    """Test Document to DocumentPage relationship and ordering."""
    user = create_sample_user(db)
    doc = create_sample_document(db, user.id)

    p1 = DocumentPage(
        id=uuid.uuid4(),
        document_id=doc.id,
        page_number=1,
        text_content="Page 1 header and instructions",
        ocr_used=False,
    )
    p2 = DocumentPage(
        id=uuid.uuid4(),
        document_id=doc.id,
        page_number=2,
        text_content="Page 2 questions",
        ocr_used=True,
        ocr_confidence=0.98,
    )
    db.add_all([p1, p2])
    db.flush()

    assert len(doc.pages) == 2
    assert [p.page_number for p in doc.pages] == [1, 2]
    assert p1.document.id == doc.id


def test_unique_document_page_numbers(db: Session) -> None:
    """Test that duplicate page numbers for the same document are rejected."""
    user = create_sample_user(db)
    doc = create_sample_document(db, user.id)

    p1 = DocumentPage(
        id=uuid.uuid4(),
        document_id=doc.id,
        page_number=1,
        text_content="Page 1 content",
    )
    db.add(p1)
    db.flush()

    p2 = DocumentPage(
        id=uuid.uuid4(),
        document_id=doc.id,
        page_number=1,
        text_content="Duplicate page 1 content",
    )
    db.add(p2)
    with pytest.raises(IntegrityError):
        db.flush()


def test_question_options_relationship(db: Session) -> None:
    """Test Question to QuestionOption relationship and unique position/label."""
    user = create_sample_user(db)
    doc = create_sample_document(db, user.id)

    q = Question(
        id=uuid.uuid4(),
        document_id=doc.id,
        question_number="1",
        question_text="What is the speed of light in vacuum?",
        question_type=QuestionType.MCQ,
        status=QuestionStatus.EXTRACTED,
        confidence=0.99,
    )
    db.add(q)
    db.flush()

    opt_a = QuestionOption(
        id=uuid.uuid4(),
        question_id=q.id,
        label="A",
        option_text="3 x 10^8 m/s",
        position=1,
    )
    opt_b = QuestionOption(
        id=uuid.uuid4(),
        question_id=q.id,
        label="B",
        option_text="3 x 10^6 m/s",
        position=2,
    )
    db.add_all([opt_a, opt_b])
    db.flush()

    assert len(q.options) == 2
    assert [opt.label for opt in q.options] == ["A", "B"]

    # Duplicate label on same question must fail
    dup_label = QuestionOption(
        id=uuid.uuid4(),
        question_id=q.id,
        label="A",
        option_text="Conflict option",
        position=3,
    )
    db.add(dup_label)
    with pytest.raises(IntegrityError):
        db.flush()


def test_question_source_pages_multipage_relationship(db: Session) -> None:
    """Test Question spanning across multiple physical DocumentPages with QuestionSource."""
    user = create_sample_user(db)
    doc = create_sample_document(db, user.id)

    p3 = DocumentPage(
        id=uuid.uuid4(),
        document_id=doc.id,
        page_number=3,
        text_content="Question 14 paragraph begins...",
    )
    p4 = DocumentPage(
        id=uuid.uuid4(),
        document_id=doc.id,
        page_number=4,
        text_content="...Question 14 options follow.",
    )
    db.add_all([p3, p4])
    db.flush()

    q14 = Question(
        id=uuid.uuid4(),
        document_id=doc.id,
        question_number="14",
        question_text="Long comprehension question spanning pages 3 and 4",
        question_type=QuestionType.LONG_ANSWER,
        status=QuestionStatus.EXTRACTED,
    )
    db.add(q14)
    db.flush()

    src1 = QuestionSource(
        id=uuid.uuid4(),
        question_id=q14.id,
        document_page_id=p3.id,
        page_sequence=1,
    )
    src2 = QuestionSource(
        id=uuid.uuid4(),
        question_id=q14.id,
        document_page_id=p4.id,
        page_sequence=2,
    )
    db.add_all([src1, src2])
    db.flush()

    assert len(q14.sources) == 2
    assert [s.document_page.page_number for s in q14.sources] == [3, 4]


def test_confidence_range_constraints(db: Session) -> None:
    """Test that confidence outside [0.0, 1.0] violates PostgreSQL check constraint."""
    user = create_sample_user(db)
    doc = create_sample_document(db, user.id)

    invalid_q = Question(
        id=uuid.uuid4(),
        document_id=doc.id,
        question_text="Invalid confidence question",
        question_type=QuestionType.NUMERICAL,
        status=QuestionStatus.EXTRACTED,
        confidence=1.25,  # Exceeds 1.0
    )
    db.add(invalid_q)
    with pytest.raises(IntegrityError):
        db.flush()


def test_related_document_self_reference_prevention(db: Session) -> None:
    """Test that a document cannot establish a RelatedDocument relationship with itself."""
    user = create_sample_user(db)
    doc = create_sample_document(db, user.id)

    self_relation = RelatedDocument(
        id=uuid.uuid4(),
        document_id=doc.id,
        related_document_id=doc.id,  # Self-referencing
        relationship_type=RelatedDocumentType.ANSWER_KEY,
    )
    db.add(self_relation)
    with pytest.raises(IntegrityError):
        db.flush()


def test_document_deletion_cascade_behavior(db: Session) -> None:
    """Test that deleting a Document cascades to pages, jobs, questions, and options,

    while independent related documents remain intact.
    """
    user = create_sample_user(db)
    doc_qp = create_sample_document(db, user.id, role=DocumentRole.QUESTION_PAPER)
    doc_ak = create_sample_document(db, user.id, role=DocumentRole.ANSWER_KEY)

    # 1. Add dependent entities to Question Paper
    page = DocumentPage(id=uuid.uuid4(), document_id=doc_qp.id, page_number=1)
    job = ProcessingJob(
        id=uuid.uuid4(),
        document_id=doc_qp.id,
        status=ProcessingJobStatus.COMPLETED,
    )
    question = Question(
        id=uuid.uuid4(),
        document_id=doc_qp.id,
        question_text="Cascade test question",
        question_type=QuestionType.MCQ,
    )
    db.add_all([page, job, question])
    db.flush()

    option = QuestionOption(
        id=uuid.uuid4(),
        question_id=question.id,
        label="A",
        option_text="Test Option",
        position=1,
    )
    review = ReviewItem(
        id=uuid.uuid4(),
        document_id=doc_qp.id,
        question_id=question.id,
        reason="Low resolution OCR",
        severity=ReviewSeverity.LOW,
        status=ReviewStatus.OPEN,
    )
    # 2. Add relation link between QP and AK
    relation = RelatedDocument(
        id=uuid.uuid4(),
        document_id=doc_qp.id,
        related_document_id=doc_ak.id,
        relationship_type=RelatedDocumentType.ANSWER_KEY,
    )
    db.add_all([option, review, relation])
    db.flush()

    page_id = page.id
    job_id = job.id
    question_id = question.id
    option_id = option.id
    review_id = review.id
    relation_id = relation.id
    doc_ak_id = doc_ak.id

    # 3. Delete Document QP
    db.delete(doc_qp)
    db.flush()

    # 4. Verify cascade deletions on dependent entities
    assert db.get(DocumentPage, page_id) is None
    assert db.get(ProcessingJob, job_id) is None
    assert db.get(Question, question_id) is None
    assert db.get(QuestionOption, option_id) is None
    assert db.get(ReviewItem, review_id) is None
    assert db.get(RelatedDocument, relation_id) is None

    # 5. Verify related Answer Key document was NOT deleted
    retained_ak = db.get(Document, doc_ak_id)
    assert retained_ak is not None
    assert retained_ak.id == doc_ak_id
