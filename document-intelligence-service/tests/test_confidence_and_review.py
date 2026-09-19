"""Comprehensive test suite for Phase 8: Confidence Engine & Human Review System."""

import datetime
import io
from typing import Optional
import uuid

from fastapi.testclient import TestClient
import fitz  # PyMuPDF
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.database import SessionLocal
from app.db.models.document import Document
from app.db.models.enums import (
    AnswerSource,
    DocumentRole,
    DocumentType,
    QuestionStatus,
    QuestionType,
    ReviewSeverity,
    ReviewStatus,
)
from app.db.models.page import DocumentPage
from app.db.models.question import Question, QuestionOption, QuestionSource
from app.db.models.review import ReviewItem
from app.main import app
from app.services.confidence import (
    ConfidenceEngine,
    ConfidenceSignals,
    ReviewReasonCode,
    confidence_engine,
    review_service,
    signal_evaluator,
)
from app.services.document_processor import document_processor

client = TestClient(app, raise_server_exceptions=False)


def register_and_get_token(email_prefix: str) -> str:
    """Register a test user and return JWT access token."""
    email = f"{email_prefix}_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "Password123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": pwd})
    res = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    return res.json()["access_token"]


@pytest.fixture
def user_a_token() -> str:
    return register_and_get_token("p8_user_a")


@pytest.fixture
def user_b_token() -> str:
    return register_and_get_token("p8_user_b")


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_sample_pdf(pages_content: list[str]) -> bytes:
    """Generate multi-page PDF with selectable text."""
    doc = fitz.open()
    for text_block in pages_content:
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 50), text_block, fontsize=11)
    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes


# ==============================================================================
# 1. SIGNAL EVALUATOR UNIT TESTS
# ==============================================================================

def test_signal_high_quality_question():
    """Verify high-quality question with native text, complete options, and matched answer."""
    page_id = uuid.uuid4()
    mock_page = DocumentPage(
        id=page_id,
        document_id=uuid.uuid4(),
        page_number=1,
        text_content="Clean digital text",
        ocr_used=False,
    )
    pages_by_id = {page_id: mock_page}

    q = Question(
        id=uuid.uuid4(),
        document_id=mock_page.document_id,
        question_number="1",
        question_text="What is the standard acceleration due to gravity on Earth?",
        question_type=QuestionType.MCQ,
        status=QuestionStatus.EXTRACTED,
        answer="B",
        answer_confidence=0.98,
        answer_source=AnswerSource.ANSWER_KEY,
    )
    q.sources = [QuestionSource(document_page_id=page_id, page_sequence=1)]
    q.options = [
        QuestionOption(label="A", option_text="9.8 m/s", position=1),
        QuestionOption(label="B", option_text="9.81 m/s^2", position=2),
        QuestionOption(label="C", option_text="10 m/s^2", position=3),
        QuestionOption(label="D", option_text="8.9 m/s^2", position=4),
    ]

    res = confidence_engine.evaluate_question(
        question=q,
        pages_by_id=pages_by_id,
        duplicate_numbers_in_doc=set(),
        document_has_answer_key=True,
    )

    assert res.overall_confidence >= 0.90
    assert res.status == QuestionStatus.EXTRACTED
    assert res.review_required is False
    assert len(res.review_items) == 0


def test_signal_low_ocr_and_corrupted_text():
    """Verify low OCR confidence and corrupted text detection."""
    page_id = uuid.uuid4()
    mock_page = DocumentPage(
        id=page_id,
        document_id=uuid.uuid4(),
        page_number=1,
        text_content="Scanned text",
        ocr_used=True,
        ocr_confidence=0.45,
    )
    pages_by_id = {page_id: mock_page}

    q = Question(
        id=uuid.uuid4(),
        document_id=mock_page.document_id,
        question_number="2",
        question_text="What is the va|ue of x in equation x^2~~4?",
        question_type=QuestionType.SHORT_ANSWER,
        status=QuestionStatus.EXTRACTED,
    )
    q.sources = [QuestionSource(document_page_id=page_id, page_sequence=1)]

    res = confidence_engine.evaluate_question(
        question=q,
        pages_by_id=pages_by_id,
        duplicate_numbers_in_doc=set(),
        document_has_answer_key=False,
    )

    assert res.overall_confidence < 0.85
    assert res.review_required is True
    reasons = [item.reason for item in res.review_items]
    assert (
        ReviewReasonCode.LOW_OCR_CONFIDENCE.value in reasons
        or ReviewReasonCode.CORRUPTED_TEXT.value in reasons
    )


def test_signal_missing_question_number():
    """Verify unnumbered questions are flagged with MISSING_QUESTION_NUMBER without rejection."""
    page_id = uuid.uuid4()
    mock_page = DocumentPage(
        id=page_id,
        document_id=uuid.uuid4(),
        page_number=1,
        text_content="Which organ pumps blood throughout the human body?",
        ocr_used=False,
    )
    pages_by_id = {page_id: mock_page}

    q = Question(
        id=uuid.uuid4(),
        document_id=mock_page.document_id,
        question_number=None,
        question_text="Which organ pumps blood throughout the human body?",
        question_type=QuestionType.SHORT_ANSWER,
        status=QuestionStatus.EXTRACTED,
    )
    q.sources = [QuestionSource(document_page_id=page_id, page_sequence=1)]

    res = confidence_engine.evaluate_question(
        question=q,
        pages_by_id=pages_by_id,
        duplicate_numbers_in_doc=set(),
        document_has_answer_key=False,
    )

    reasons = [item.reason for item in res.review_items]
    assert ReviewReasonCode.MISSING_QUESTION_NUMBER.value in reasons
    assert res.signals.question_number_confidence == 0.40
    # Does not crash or set confidence to 0
    assert res.overall_confidence > 0.60


def test_signal_incomplete_and_missing_options():
    """Verify MCQ with missing option C flags MISSING_OPTION, while descriptive question does not."""
    page_id = uuid.uuid4()
    mock_page = DocumentPage(
        id=page_id,
        document_id=uuid.uuid4(),
        page_number=1,
        ocr_used=False,
    )
    pages_by_id = {page_id: mock_page}

    # MCQ missing Option C
    mcq = Question(
        id=uuid.uuid4(),
        document_id=mock_page.document_id,
        question_number="3",
        question_text="Select the valid programming language:",
        question_type=QuestionType.MCQ,
        status=QuestionStatus.EXTRACTED,
    )
    mcq.sources = [QuestionSource(document_page_id=page_id, page_sequence=1)]
    mcq.options = [
        QuestionOption(label="A", option_text="Python", position=1),
        QuestionOption(label="B", option_text="Rust", position=2),
        QuestionOption(label="D", option_text="HTML", position=3),  # Missing C!
    ]

    mcq_res = confidence_engine.evaluate_question(
        question=mcq,
        pages_by_id=pages_by_id,
        duplicate_numbers_in_doc=set(),
        document_has_answer_key=False,
    )
    mcq_reasons = [item.reason for item in mcq_res.review_items]
    assert ReviewReasonCode.MISSING_OPTION.value in mcq_reasons
    assert mcq_res.signals.option_completeness == 0.60

    # Descriptive question with no options
    desc_q = Question(
        id=uuid.uuid4(),
        document_id=mock_page.document_id,
        question_number="4",
        question_text="Explain the process of cellular respiration in mitochondria.",
        question_type=QuestionType.LONG_ANSWER,
        status=QuestionStatus.EXTRACTED,
    )
    desc_q.sources = [QuestionSource(document_page_id=page_id, page_sequence=1)]
    desc_q.options = []

    desc_res = confidence_engine.evaluate_question(
        question=desc_q,
        pages_by_id=pages_by_id,
        duplicate_numbers_in_doc=set(),
        document_has_answer_key=False,
    )
    desc_reasons = [item.reason for item in desc_res.review_items]
    assert ReviewReasonCode.MISSING_OPTION.value not in desc_reasons
    assert ReviewReasonCode.INCOMPLETE_OPTIONS.value not in desc_reasons
    assert desc_res.signals.option_completeness == 1.0


def test_signal_multi_page_continuity():
    """Verify consecutive multi-page questions receive full score, while non-consecutive trigger review."""
    p1 = DocumentPage(id=uuid.uuid4(), document_id=uuid.uuid4(), page_number=1, ocr_used=False)
    p2 = DocumentPage(id=uuid.uuid4(), document_id=p1.document_id, page_number=2, ocr_used=False)
    p5 = DocumentPage(id=uuid.uuid4(), document_id=p1.document_id, page_number=5, ocr_used=False)
    pages_by_id = {p1.id: p1, p2.id: p2, p5.id: p5}

    # Consecutive p1 -> p2
    q_consecutive = Question(
        id=uuid.uuid4(),
        document_id=p1.document_id,
        question_number="5",
        question_text="A lengthy question beginning on page 1 and finishing on page 2.",
        question_type=QuestionType.SHORT_ANSWER,
        status=QuestionStatus.EXTRACTED,
    )
    q_consecutive.sources = [
        QuestionSource(document_page_id=p1.id, page_sequence=1),
        QuestionSource(document_page_id=p2.id, page_sequence=2),
    ]
    res_c = confidence_engine.evaluate_question(
        question=q_consecutive,
        pages_by_id=pages_by_id,
        duplicate_numbers_in_doc=set(),
        document_has_answer_key=False,
    )
    assert res_c.signals.page_continuity == 1.0
    assert ReviewReasonCode.MULTI_PAGE_UNCERTAINTY.value not in [r.reason for r in res_c.review_items]

    # Non-consecutive p1 -> p5
    q_gap = Question(
        id=uuid.uuid4(),
        document_id=p1.document_id,
        question_number="6",
        question_text="A question spanning non-consecutive pages.",
        question_type=QuestionType.SHORT_ANSWER,
        status=QuestionStatus.EXTRACTED,
    )
    q_gap.sources = [
        QuestionSource(document_page_id=p1.id, page_sequence=1),
        QuestionSource(document_page_id=p5.id, page_sequence=2),
    ]
    res_g = confidence_engine.evaluate_question(
        question=q_gap,
        pages_by_id=pages_by_id,
        duplicate_numbers_in_doc=set(),
        document_has_answer_key=False,
    )
    assert res_g.signals.page_continuity == 0.40
    assert ReviewReasonCode.MULTI_PAGE_UNCERTAINTY.value in [r.reason for r in res_g.review_items]


def test_signal_answer_mapping_scenarios():
    """Verify answer mapping states: no answer key, matched, unmatched, and ambiguous."""
    page_id = uuid.uuid4()
    mock_page = DocumentPage(id=page_id, document_id=uuid.uuid4(), page_number=1, ocr_used=False)
    pages_by_id = {page_id: mock_page}

    # 1. No answer key provided for document
    q_nokey = Question(
        id=uuid.uuid4(),
        document_id=mock_page.document_id,
        question_number="7",
        question_text="What is the chemical formula of water?",
        question_type=QuestionType.SHORT_ANSWER,
        status=QuestionStatus.EXTRACTED,
    )
    q_nokey.sources = [QuestionSource(document_page_id=page_id, page_sequence=1)]
    res_nokey = confidence_engine.evaluate_question(
        q_nokey, pages_by_id, duplicate_numbers_in_doc=set(), document_has_answer_key=False
    )
    assert res_nokey.signals.answer_mapping == 0.85
    assert len(res_nokey.review_items) == 0

    # 2. Answer key exists and question is UNMATCHED
    q_unmatched = Question(
        id=uuid.uuid4(),
        document_id=mock_page.document_id,
        question_number="8",
        question_text="What is the atomic number of Gold?",
        question_type=QuestionType.SHORT_ANSWER,
        status=QuestionStatus.EXTRACTED,
        answer=None,
    )
    q_unmatched.sources = [QuestionSource(document_page_id=page_id, page_sequence=1)]
    res_unmatched = confidence_engine.evaluate_question(
        q_unmatched, pages_by_id, duplicate_numbers_in_doc=set(), document_has_answer_key=True
    )
    assert res_unmatched.signals.answer_mapping == 0.50
    assert ReviewReasonCode.UNMATCHED_ANSWER.value in [r.reason for r in res_unmatched.review_items]

    # 3. Answer key exists and question is AMBIGUOUS
    q_ambiguous = Question(
        id=uuid.uuid4(),
        document_id=mock_page.document_id,
        question_number="9",
        question_text="Sample ambiguous question",
        question_type=QuestionType.SHORT_ANSWER,
        status=QuestionStatus.EXTRACTED,
        answer=None,
    )
    q_ambiguous.sources = [QuestionSource(document_page_id=page_id, page_sequence=1)]
    res_ambiguous = confidence_engine.evaluate_question(
        q_ambiguous,
        pages_by_id,
        duplicate_numbers_in_doc=set(),
        document_has_answer_key=True,
        ambiguous_qrefs={"9"},
    )
    assert res_ambiguous.signals.answer_mapping == 0.30
    assert ReviewReasonCode.AMBIGUOUS_ANSWER.value in [r.reason for r in res_ambiguous.review_items]


# ==============================================================================
# 2. WEIGHTS CONFIGURATION VALIDATION
# ==============================================================================

def test_confidence_weights_configuration_validation():
    """Verify that configuration rejects confidence weights not summing to 1.0."""
    with pytest.raises(ValueError, match="Confidence weights must sum to 1.0"):
        Settings(
            CONFIDENCE_OCR_WEIGHT=0.50,
            CONFIDENCE_TEXT_WEIGHT=0.50,
            CONFIDENCE_BOUNDARY_WEIGHT=0.20,  # Sum = 1.20!
        )


# ==============================================================================
# 3. REVIEW SERVICE IDEMPOTENT DEDUPLICATION & SUMMARY
# ==============================================================================

def test_review_service_idempotent_deduplication(user_a_token: str, db: Session):
    """Verify running review sync repeatedly does not create duplicate review items."""
    user_a_id = uuid.UUID(
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {user_a_token}"}).json()["id"]
    )
    # Create document
    doc = Document(
        id=uuid.uuid4(),
        owner_id=user_a_id,
        filename="test_exam.pdf",
        storage_path="storage/test_exam.pdf",
        mime_type="application/pdf",
        document_type=DocumentType.PDF,
        file_size=1024,
        page_count=1,
    )
    db.add(doc)
    page = DocumentPage(
        id=uuid.uuid4(),
        document_id=doc.id,
        page_number=1,
        ocr_used=False,
    )
    db.add(page)

    # Question with missing number
    q = Question(
        id=uuid.uuid4(),
        document_id=doc.id,
        question_number=None,
        question_text="Unnumbered question for deduplication check",
        question_type=QuestionType.SHORT_ANSWER,
    )
    db.add(q)
    db.flush()
    db.add(QuestionSource(question_id=q.id, document_page_id=page.id, page_sequence=1))
    db.commit()

    # First run
    summary1 = review_service.sync_document_reviews(doc.id, db)
    items1 = db.scalars(select(ReviewItem).where(ReviewItem.document_id == doc.id)).all()
    assert len(items1) >= 1
    initial_count = len(items1)

    # Second run (should update, not duplicate)
    summary2 = review_service.sync_document_reviews(doc.id, db)
    items2 = db.scalars(select(ReviewItem).where(ReviewItem.document_id == doc.id)).all()
    assert len(items2) == initial_count
    assert summary2.open_review_items == summary1.open_review_items


# ==============================================================================
# 4. REST API: REVIEWS LIFECYCLE & RESOLUTION
# ==============================================================================

def test_review_lifecycle_and_apis(user_a_token: str, user_b_token: str, db: Session):
    """Verify PATCH /reviews/{id} resolution, ignoring, and authorization isolation."""
    user_a_id = uuid.UUID(
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {user_a_token}"}).json()["id"]
    )

    doc = Document(
        id=uuid.uuid4(),
        owner_id=user_a_id,
        filename="reviews_test.pdf",
        storage_path="storage/reviews_test.pdf",
        mime_type="application/pdf",
        document_type=DocumentType.PDF,
        file_size=1024,
        page_count=1,
    )
    db.add(doc)
    db.flush()

    q = Question(
        id=uuid.uuid4(),
        document_id=doc.id,
        question_number="1",
        question_text="Sample question for review API testing",
        question_type=QuestionType.SHORT_ANSWER,
    )
    db.add(q)
    db.flush()

    item = ReviewItem(
        id=uuid.uuid4(),
        document_id=doc.id,
        question_id=q.id,
        severity=ReviewSeverity.MEDIUM,
        status=ReviewStatus.OPEN,
        reason=ReviewReasonCode.LOW_OCR_CONFIDENCE.value,
        details="OCR confidence is 0.52",
        confidence=0.52,
    )
    db.add(item)
    db.commit()

    item_id = str(item.id)

    # 1. User B attempts to resolve User A's review item -> 404
    unauth_patch = client.patch(
        f"/api/v1/reviews/{item_id}",
        headers={"Authorization": f"Bearer {user_b_token}"},
        json={"status": "RESOLVED"},
    )
    assert unauth_patch.status_code == 404

    # 2. User A resolves review item
    resolve_res = client.patch(
        f"/api/v1/reviews/{item_id}",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"status": "RESOLVED"},
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "RESOLVED"
    assert resolve_res.json()["resolved_at"] is not None

    # 3. User A marks review item as IGNORED
    ignore_res = client.patch(
        f"/api/v1/reviews/{item_id}",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"status": "IGNORED"},
    )
    assert ignore_res.status_code == 200
    assert ignore_res.json()["status"] == "IGNORED"

    # 4. User A queries question review items via GET /questions/{id}/reviews
    q_reviews_res = client.get(
        f"/api/v1/questions/{q.id}/reviews",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert q_reviews_res.status_code == 200
    assert len(q_reviews_res.json()) == 1
    assert q_reviews_res.json()[0]["id"] == item_id

    # 5. User A queries document reviews via GET /documents/{id}/reviews
    doc_reviews_res = client.get(
        f"/api/v1/documents/{doc.id}/reviews",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert doc_reviews_res.status_code == 200
    assert doc_reviews_res.json()["total"] == 1
    assert doc_reviews_res.json()["items"][0]["status"] == "IGNORED"

    # 6. User A queries document review summary via GET /documents/{id}/reviews/summary
    summary_res = client.get(
        f"/api/v1/documents/{doc.id}/reviews/summary",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert summary_res.status_code == 200
    summary_data = summary_res.json()
    assert summary_data["document_id"] == str(doc.id)
    assert summary_data["ignored_review_items"] == 1


# ==============================================================================
# 5. END-TO-END PIPELINE INTEGRATION TEST
# ==============================================================================

def test_end_to_end_pipeline_confidence_and_review(user_a_token: str):
    """Verify document upload through processing generates confidence and review items."""
    content = [
        (
            "GENERAL SCIENCE EXAM\n"
            "1. What is the powerhouse of the cell?\n"
            "(A) Ribosome\n"
            "(B) Mitochondria\n"
            "(C) Nucleus\n"
            "(D) Golgi apparatus\n"
            "\n"
            "2. Which subatomic particle carries a negative charge?\n"  # Missing (C)!
            "(A) Proton\n"
            "(B) Neutron\n"
            "(D) Electron\n"  # Missing (C)!
        )
    ]
    pdf_bytes = create_sample_pdf(content)

    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("science_exam.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]

    db_session = SessionLocal()
    try:
        doc = db_session.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
        proc_result = document_processor.process(doc.id, doc.storage_path, db=db_session)
        assert proc_result["success"] is True
        assert proc_result["extracted_questions"] == 2
        assert "review_summary" in proc_result
        assert proc_result["review_summary"]["open_review_items"] >= 1
    finally:
        db_session.close()

    # Query questions
    q_res = client.get(
        f"/api/v1/documents/{doc_id}/questions",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert q_res.status_code == 200
    questions = q_res.json()["items"]
    assert len(questions) == 2

    # First question is high quality
    q1 = questions[0]
    assert q1["question_number"] == "1"
    assert q1["confidence"] >= 0.85
    assert q1["status"] == "EXTRACTED"
    assert q1["review_required"] is False

    # Second question has missing number and missing option C -> review_required
    q2 = questions[1]
    assert q2["review_required"] is True

    # Query reviews endpoint
    rev_res = client.get(
        f"/api/v1/documents/{doc_id}/reviews",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert rev_res.status_code == 200
    reasons = [item["reason"] for item in rev_res.json()["items"]]
    assert (
        ReviewReasonCode.MISSING_QUESTION_NUMBER.value in reasons
        or ReviewReasonCode.MISSING_OPTION.value in reasons
    )
