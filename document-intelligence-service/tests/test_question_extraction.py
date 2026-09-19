"""Comprehensive test suite for Phase 6: Question Detection and Structured Question Extraction."""

import io
import uuid

from fastapi.testclient import TestClient
import fitz  # PyMuPDF
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models.document import Document
from app.db.models.enums import DocumentRole, DocumentStatus, QuestionStatus, QuestionType
from app.db.models.page import DocumentPage
from app.db.models.question import Question, QuestionOption, QuestionSource
from app.db.models.user import User
from app.main import app
from app.services.document_processor import document_processor
from app.services.extraction import (
    option_parser,
    question_boundary_detector,
    question_extractor,
    question_type_classifier,
)
from app.services.storage import get_storage_service

client = TestClient(app, raise_server_exceptions=False)


def register_and_get_token(email_prefix: str) -> str:
    """Helper to register a unique user and return JWT access token."""
    email = f"{email_prefix}_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "Password123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": pwd})
    res = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    return res.json()["access_token"]


@pytest.fixture
def user_a_token() -> str:
    return register_and_get_token("p6_user_a")


@pytest.fixture
def user_b_token() -> str:
    return register_and_get_token("p6_user_b")


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_sample_pdf_with_questions(pages_content: list[str]) -> bytes:
    """Helper to generate a multi-page PDF with selectable digital text."""
    doc = fitz.open()
    for text_block in pages_content:
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 50), text_block, fontsize=11)
    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes


# ==============================================================================
# 1. QUESTION BOUNDARY DETECTION TESTS
# ==============================================================================

def test_boundary_detection_numbering_and_prefixes():
    """Verify detection of various numbering schemes and prefix formats."""
    # Prefix formats
    b1 = question_boundary_detector.evaluate_line("Q1. What is the capital of Italy?", 0)
    assert b1 is not None
    assert b1.question_number == "1"
    assert "What is the capital of Italy?" in b1.remaining_text

    b2 = question_boundary_detector.evaluate_line("Q.2 Which planet is closest to the Sun?", 1)
    assert b2 is not None
    assert b2.question_number == "2"

    b3 = question_boundary_detector.evaluate_line("Question 3: Describe the cell cycle.", 2)
    assert b3 is not None
    assert b3.question_number == "3"

    b4 = question_boundary_detector.evaluate_line("Question No. 4 - Solve for x.", 3)
    assert b4 is not None
    assert b4.question_number == "4"

    # Standard numeric formats
    b5 = question_boundary_detector.evaluate_line("5. What is HTTP status 404?", 4)
    assert b5 is not None
    assert b5.question_number == "5"

    b6 = question_boundary_detector.evaluate_line("06) List three principles of OOP.", 5)
    assert b6 is not None
    assert b6.question_number == "06"

    b7 = question_boundary_detector.evaluate_line("7: Explain database normalization.", 6)
    assert b7 is not None
    assert b7.question_number == "7"

    b8 = question_boundary_detector.evaluate_line("12 - What is an index?", 7)
    assert b8 is not None
    assert b8.question_number == "12"

    # Roman numerals
    b9 = question_boundary_detector.evaluate_line("I. State Newton's First Law.", 8)
    assert b9 is not None
    assert b9.question_number == "I"

    b10 = question_boundary_detector.evaluate_line("IV. Define kinetic energy.", 9)
    assert b10 is not None
    assert b10.question_number == "IV"


def test_boundary_detection_unnumbered_and_negative_filters():
    """Verify unnumbered questions are detected and exam headers are ignored."""
    # Unnumbered question with interrogative and question mark
    b_un = question_boundary_detector.evaluate_line(
        "Which of the following algorithms guarantees finding the shortest path?",
        0,
    )
    assert b_un is not None
    assert b_un.question_number is None

    # Negative filters: exam headers, instructions, page numbers
    assert question_boundary_detector.is_heading("SECTION A - GENERAL KNOWLEDGE")
    assert question_boundary_detector.is_heading("PART II: ADVANCED MATHEMATICS")
    assert question_boundary_detector.is_heading("INSTRUCTIONS: Answer all questions.")
    assert question_boundary_detector.is_heading("Time Allowed: 3 Hours")
    assert question_boundary_detector.is_heading("Maximum Marks: 100")

    # evaluate_line should return None for headings
    assert question_boundary_detector.evaluate_line("SECTION A", 0) is None
    assert question_boundary_detector.evaluate_line("General Instructions: Read carefully.", 0) is None


# ==============================================================================
# 2. OPTION PARSER TESTS
# ==============================================================================

def test_option_parser_vertical_formats():
    """Verify parsing of vertical option formats and stem isolation."""
    lines = [
        "What is the capital of France?",
        "A. Berlin",
        "B. Madrid",
        "C. Paris",
        "D. Rome",
    ]
    stem, options = option_parser.parse_options(lines)
    assert stem == "What is the capital of France?"
    assert len(options) == 4
    assert [o.label for o in options] == ["A", "B", "C", "D"]
    assert [o.text for o in options] == ["Berlin", "Madrid", "Paris", "Rome"]
    assert [o.position for o in options] == [1, 2, 3, 4]


def test_option_parser_parenthesized_and_numeric_options():
    """Verify parsing of parenthesized letters, brackets, and numeric options."""
    lines = [
        "Select the primary key attribute:",
        "(a) email_address",
        "(b) user_id",
        "(c) first_name",
        "(d) last_name",
    ]
    stem, options = option_parser.parse_options(lines)
    assert stem == "Select the primary key attribute:"
    assert len(options) == 4
    assert [o.label for o in options] == ["A", "B", "C", "D"]
    assert options[1].text == "user_id"

    # Numeric options: (1), (2), (3), (4)
    num_lines = [
        "What is the value of 2 + 2?",
        "(1) 3",
        "(2) 4",
        "(3) 5",
        "(4) 6",
    ]
    stem_num, opt_num = option_parser.parse_options(num_lines)
    assert stem_num == "What is the value of 2 + 2?"
    assert len(opt_num) == 4
    assert [o.label for o in opt_num] == ["1", "2", "3", "4"]
    assert [o.text for o in opt_num] == ["3", "4", "5", "6"]


def test_option_parser_inline_horizontal_options():
    """Verify parsing of inline horizontal multiple-choice options on a single line."""
    lines = [
        "Which data structure follows the LIFO order?",
        "(A) Queue    (B) Stack    (C) Tree    (D) Graph",
    ]
    stem, options = option_parser.parse_options(lines)
    assert stem == "Which data structure follows the LIFO order?"
    assert len(options) == 4
    assert [o.label for o in options] == ["A", "B", "C", "D"]
    assert [o.text for o in options] == ["Queue", "Stack", "Tree", "Graph"]
    assert [o.position for o in options] == [1, 2, 3, 4]


# ==============================================================================
# 3. QUESTION TYPE CLASSIFICATION TESTS
# ==============================================================================

def test_question_type_classification():
    """Verify rule-based question type classification engine."""
    # MCQ
    _, mcq_opts = option_parser.parse_options(["Stem", "(A) 1", "(B) 2"])
    assert question_type_classifier.classify("Which option is correct?", mcq_opts) == QuestionType.MCQ

    # True / False
    _, tf_opts = option_parser.parse_options(["Stem", "(A) True", "(B) False"])
    assert question_type_classifier.classify("The sky is blue.", tf_opts) == QuestionType.TRUE_FALSE

    assert (
        question_type_classifier.classify("State whether true or false: Python is compiled.", [])
        == QuestionType.TRUE_FALSE
    )

    # Numerical
    assert (
        question_type_classifier.classify("Calculate the kinetic energy of a 5kg mass at 10 m/s.", [])
        == QuestionType.NUMERICAL
    )
    assert (
        question_type_classifier.classify("Find the value of x when 2x + 6 = 14.", [])
        == QuestionType.NUMERICAL
    )

    # Short Answer
    assert (
        question_type_classifier.classify("Define what is meant by polymorphic dispatch.", [])
        == QuestionType.SHORT_ANSWER
    )
    assert (
        question_type_classifier.classify("State the principle of conservation of energy.", [])
        == QuestionType.SHORT_ANSWER
    )

    # Long Answer
    assert (
        question_type_classifier.classify("Explain the complete lifecycle of a database transaction in detail.", [])
        == QuestionType.LONG_ANSWER
    )
    assert (
        question_type_classifier.classify("Describe the differences between TCP and UDP with diagrams.", [])
        == QuestionType.LONG_ANSWER
    )


def test_validator_short_stem_and_duplicate_options():
    """Verify validation logic flags short stems and sanitizes duplicate option labels."""
    from app.services.extraction.models import ExtractedOption, ExtractedQuestion
    from app.services.extraction.validators import extraction_validator

    # Test short stem -> marks PARTIAL
    invalid_q = ExtractedQuestion(
        question_number="1",
        question_text="Hi",
        source_pages=[(1, uuid.uuid4())],
    )
    validated = extraction_validator.validate(invalid_q)
    assert validated.status == QuestionStatus.PARTIAL
    assert validated.is_valid is False
    assert any("too short" in note for note in validated.validation_notes)

    # Test duplicate option labels -> sanitized to distinct labels and sequential positions
    dup_opts_q = ExtractedQuestion(
        question_number="2",
        question_text="Which options are duplicate?",
        options=[
            ExtractedOption(label="A", text="First choice", position=1),
            ExtractedOption(label="A", text="Second choice", position=2),
            ExtractedOption(label="B", text="Third choice", position=3),
        ],
        source_pages=[(1, uuid.uuid4())],
    )
    validated_dup = extraction_validator.validate(dup_opts_q)
    assert len(validated_dup.options) == 3
    assert validated_dup.options[0].label == "A"
    assert validated_dup.options[1].label == "A_2"
    assert validated_dup.options[2].label == "B"
    assert [o.position for o in validated_dup.options] == [1, 2, 3]


def test_extract_from_text_helper():
    """Verify extract_from_text handles multi-question string with options."""
    raw_text = (
        "1. What is the derivative of sin(x)?\n"
        "(A) cos(x)\n"
        "(B) -cos(x)\n"
        "(C) tan(x)\n"
        "(D) -sin(x)\n"
        "2. What is the integral of 1/x dx?\n"
        "(A) ln|x| + C\n"
        "(B) e^x + C\n"
    )
    extracted = question_extractor.extract_from_text(raw_text)
    assert len(extracted) == 2
    assert extracted[0].question_number == "1"
    assert extracted[0].question_type == QuestionType.MCQ
    assert len(extracted[0].options) == 4
    assert extracted[1].question_number == "2"
    assert extracted[1].question_type == QuestionType.MCQ
    assert len(extracted[1].options) == 2


# ==============================================================================
# 4. MULTI-PAGE QUESTION EXTRACTION AND PROVENANCE TESTS
# ==============================================================================

def test_multipage_question_continuation(db: Session):
    """Verify questions spanning across consecutive pages correctly track multiple QuestionSource records."""
    # Create test user for owner_id
    test_user = User(
        email=f"multi_owner_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="fake_hash",
        is_active=True,
    )
    db.add(test_user)
    db.flush()

    # Setup a dummy Document in database
    doc_id = uuid.uuid4()
    dummy_doc = Document(
        id=doc_id,
        owner_id=test_user.id,
        filename="multipage_exam.pdf",
        document_type="PDF",
        mime_type="application/pdf",
        document_role=DocumentRole.QUESTION_PAPER,
        file_size=1024,
        storage_path="mock/multipage_exam.pdf",
        status=DocumentStatus.PROCESSING,
    )
    db.add(dummy_doc)
    db.flush()

    # Page 1 contains Q1 stem and options A & B
    page1_text = (
        "SECTION A\n"
        "1. Consider a binary search tree containing integer keys.\n"
        "Which traversal yields the keys in strictly ascending order?\n"
        "(A) Pre-order\n"
        "(B) Post-order\n"
    )
    p1 = DocumentPage(
        id=uuid.uuid4(),
        document_id=doc_id,
        page_number=1,
        text_content=page1_text,
    )
    db.add(p1)

    # Page 2 contains continuation options C & D, followed by Q2
    page2_text = (
        "(C) In-order\n"
        "(D) Level-order\n"
        "2. What is the time complexity of binary search?\n"
        "(A) O(1)\n"
        "(B) O(log n)\n"
        "(C) O(n)\n"
        "(D) O(n^2)\n"
    )
    p2 = DocumentPage(
        id=uuid.uuid4(),
        document_id=doc_id,
        page_number=2,
        text_content=page2_text,
    )
    db.add(p2)
    db.commit()

    # Execute question extraction
    result = question_extractor.extract_and_persist(doc_id, db)
    assert result.total_questions == 2
    assert result.total_pages_processed == 2

    # Query Question 1 and verify multi-page provenance
    q1 = db.scalar(
        select(Question)
        .where(Question.document_id == doc_id, Question.question_number == "1")
    )
    assert q1 is not None
    assert q1.question_type == QuestionType.MCQ
    assert len(q1.options) == 4
    assert [o.label for o in q1.options] == ["A", "B", "C", "D"]
    assert q1.options[2].option_text == "In-order"

    # Verify QuestionSource records for Q1 link to BOTH Page 1 and Page 2
    sources = sorted(q1.sources, key=lambda s: s.page_sequence)
    assert len(sources) == 2
    assert sources[0].document_page_id == p1.id
    assert sources[0].page_sequence == 1
    assert sources[1].document_page_id == p2.id
    assert sources[1].page_sequence == 2

    # Query Question 2 and verify single-page provenance
    q2 = db.scalar(
        select(Question)
        .where(Question.document_id == doc_id, Question.question_number == "2")
    )
    assert q2 is not None
    assert len(q2.sources) == 1
    assert q2.sources[0].document_page_id == p2.id
    assert q2.sources[0].page_sequence == 1


def test_extraction_idempotency_safe_rerun(db: Session):
    """Verify that re-running extraction cleanly replaces questions without duplicating data or deleting pages."""
    test_user = User(
        email=f"idem_owner_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="fake_hash",
        is_active=True,
    )
    db.add(test_user)
    db.flush()

    doc_id = uuid.uuid4()
    dummy_doc = Document(
        id=doc_id,
        owner_id=test_user.id,
        filename="idempotency_test.pdf",
        document_type="PDF",
        mime_type="application/pdf",
        document_role=DocumentRole.QUESTION_PAPER,
        file_size=512,
        storage_path="mock/idempotency_test.pdf",
        status=DocumentStatus.PROCESSING,
    )
    db.add(dummy_doc)
    page = DocumentPage(
        id=uuid.uuid4(),
        document_id=doc_id,
        page_number=1,
        text_content="1. Define encapsulation.\n2. Define inheritance.\n",
    )
    db.add(page)
    db.commit()

    # First run
    res1 = question_extractor.extract_and_persist(doc_id, db)
    assert res1.total_questions == 2

    initial_q_count = db.scalar(
        select(Question).where(Question.document_id == doc_id)
    )
    assert initial_q_count is not None

    # Second run (simulating a retry or re-extraction)
    res2 = question_extractor.extract_and_persist(doc_id, db)
    assert res2.total_questions == 2

    # Verify count remains exactly 2 (not 4)
    all_questions = list(
        db.scalars(select(Question).where(Question.document_id == doc_id)).all()
    )
    assert len(all_questions) == 2

    # Verify pages were untouched
    page_count = db.scalars(
        select(DocumentPage).where(DocumentPage.document_id == doc_id)
    ).all()
    assert len(page_count) == 1


# ==============================================================================
# 5. REST API ENDPOINT TESTS (GET /documents/{document_id}/questions)
# ==============================================================================

def test_get_document_questions_api_owner_success(user_a_token: str):
    """Verify document owner can retrieve structured extracted questions via REST API."""
    # 1. Create PDF with questions
    content = [
        (
            "GENERAL EXAM - 2026\n"
            "1. What is the fastest sorting algorithm on average?\n"
            "(A) Bubble Sort\n"
            "(B) Quick Sort\n"
            "(C) Selection Sort\n"
            "(D) Insertion Sort\n"
            "2. Explain the concept of ACID properties in relational databases.\n"
        )
    ]
    pdf_bytes = create_sample_pdf_with_questions(content)

    # 2. Upload via API
    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("questions_exam.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]

    # 3. Synchronously run processing pipeline
    db_session = SessionLocal()
    try:
        doc = db_session.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
        assert doc is not None
        proc_result = document_processor.process(
            document_id=doc.id,
            storage_path=doc.storage_path,
            db=db_session,
        )
        assert proc_result["success"] is True
        assert proc_result["extracted_questions"] == 2
    finally:
        db_session.close()

    # 4. Fetch questions via GET /documents/{id}/questions
    q_res = client.get(
        f"/api/v1/documents/{doc_id}/questions",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert q_res.status_code == 200
    data = q_res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Check Question 1 (MCQ)
    q1 = data["items"][0]
    assert q1["question_number"] == "1"
    assert "What is the fastest sorting algorithm" in q1["question_text"]
    assert q1["question_type"] == "MCQ"
    assert q1["status"] == "EXTRACTED"
    assert len(q1["options"]) == 4
    assert q1["options"][1]["label"] == "B"
    assert q1["options"][1]["option_text"] == "Quick Sort"
    assert len(q1["sources"]) == 1

    # Check Question 2 (Long Answer)
    q2 = data["items"][1]
    assert q2["question_number"] == "2"
    assert "Explain the concept of ACID properties" in q2["question_text"]
    assert q2["question_type"] == "LONG_ANSWER"
    assert len(q2["options"]) == 0
    assert len(q2["sources"]) == 1


def test_get_document_questions_authorization_isolation(user_a_token: str, user_b_token: str):
    """Verify non-owner user cannot access questions extracted for another user's document."""
    pdf_bytes = create_sample_pdf_with_questions(["1. What is Python?\n(A) Language (B) Snake\n"])

    # User A uploads document
    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("secret_exam.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]

    # Process document
    db_session = SessionLocal()
    try:
        doc = db_session.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
        document_processor.process(
            document_id=doc.id,
            storage_path=doc.storage_path,
            db=db_session,
        )
    finally:
        db_session.close()

    # User B attempts to access User A's questions -> must return 404 NOT FOUND
    forbidden_res = client.get(
        f"/api/v1/documents/{doc_id}/questions",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert forbidden_res.status_code == 404
    assert forbidden_res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_get_document_questions_unauthenticated_and_not_found(user_a_token: str):
    """Verify 401 for unauthenticated requests and 404 for nonexistent documents."""
    random_doc_id = uuid.uuid4()

    # 401 without auth header
    res_no_auth = client.get(f"/api/v1/documents/{random_doc_id}/questions")
    assert res_no_auth.status_code == 401
    assert res_no_auth.json()["error"]["code"] == "UNAUTHORIZED"

    # 404 for nonexistent document ID
    res_not_found = client.get(
        f"/api/v1/documents/{random_doc_id}/questions",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert res_not_found.status_code == 404
    assert res_not_found.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
