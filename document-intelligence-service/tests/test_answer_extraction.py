"""Comprehensive test suite for Phase 7: Answer-Key Detection, Extraction, and Association."""

import io
import uuid

from fastapi.testclient import TestClient
import fitz  # PyMuPDF
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models.answer import AnswerKey, AnswerMapping
from app.db.models.document import Document
from app.db.models.enums import (
    AnswerSource,
    DocumentRole,
    DocumentStatus,
    QuestionType,
    RelatedDocumentType,
)
from app.db.models.page import DocumentPage
from app.db.models.question import Question
from app.db.models.related_document import RelatedDocument
from app.db.models.user import User
from app.main import app
from app.services.answer_extraction import (
    answer_extractor,
    answer_key_detector,
    answer_matcher,
    answer_parser,
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
    return register_and_get_token("p7_user_a")


@pytest.fixture
def user_b_token() -> str:
    return register_and_get_token("p7_user_b")


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
# 1. ANSWER-KEY HEADER DETECTION & NEGATIVE CONTEXT
# ==============================================================================

def test_answer_key_header_detection():
    """Verify detection of answer-key headers and rejection of exam instructions."""
    # Positive signals
    assert answer_key_detector.is_answer_key_header("ANSWER KEY")
    assert answer_key_detector.is_answer_key_header("ANSWERS")
    assert answer_key_detector.is_answer_key_header("CORRECT ANSWERS")
    assert answer_key_detector.is_answer_key_header("SOLUTIONS")
    assert answer_key_detector.is_answer_key_header("KEY ANSWERS")
    assert answer_key_detector.is_answer_key_header("SECTION A: ANSWERS")
    assert answer_key_detector.is_answer_key_header("ANS. KEY")

    # Negative context (exam instructions that must not trigger answer key)
    assert not answer_key_detector.is_answer_key_header("Answer all questions.")
    assert not answer_key_detector.is_answer_key_header("Answer the following questions carefully:")
    assert not answer_key_detector.is_answer_key_header("Answer any five questions from this section.")
    assert not answer_key_detector.is_answer_key_header("Each question carries 2 marks.")
    assert not answer_key_detector.is_answer_key_header("Write your answers in the answer booklet.")


# ==============================================================================
# 2. ANSWER ENTRY PARSER FORMATS
# ==============================================================================

def test_answer_parser_various_formats():
    """Verify parsing of diverse answer entry styles."""
    # Standard format: 1. A, 2) B, 3 - C, 4: D, 5 A
    lines = [
        "1. A",
        "2) B",
        "3 - C",
        "4: D",
        "5 True",
        "6 False",
        "7. 42",
        "8. 3.14",
    ]
    parsed: list = []
    for line in lines:
        parsed.extend(answer_parser.parse_line(line, page_number=1))

    assert len(parsed) == 8
    assert parsed[0].normalized_reference == "1"
    assert parsed[0].answer_value == "A"
    assert parsed[1].normalized_reference == "2"
    assert parsed[1].answer_value == "B"
    assert parsed[4].normalized_reference == "5"
    assert parsed[4].answer_value == "True"
    assert parsed[6].normalized_reference == "7"
    assert parsed[6].answer_value == "42"

    # Prefixes: Q1 - A, Q.2 B, Question 3: C
    prefix_lines = [
        "Q1 - B",
        "Q.2 C",
        "Question 3: A",
        "Question No. 4 = D",
    ]
    p_entries = []
    for l in prefix_lines:
        p_entries.extend(answer_parser.parse_line(l, page_number=2))

    assert len(p_entries) == 4
    assert [e.normalized_reference for e in p_entries] == ["1", "2", "3", "4"]
    assert [e.answer_value for e in p_entries] == ["B", "C", "A", "D"]
    assert all(e.source_page == 2 for e in p_entries)


def test_answer_parser_grid_and_multi_answers():
    """Verify parsing of single-line tabular grid options and multiple answers."""
    # Grid / tabular line
    grid_line = "1. B   2. C   3. A   4. D"
    grid_entries = answer_parser.parse_line(grid_line, page_number=5)
    assert len(grid_entries) == 4
    assert [e.normalized_reference for e in grid_entries] == ["1", "2", "3", "4"]
    assert [e.answer_value for e in grid_entries] == ["B", "C", "A", "D"]

    # Multiple answers (e.g. 1. A, C or 15 = B/C)
    multi_line_1 = "1. A, C"
    e1 = answer_parser.parse_line(multi_line_1, page_number=1)
    assert len(e1) == 1
    assert e1[0].answer_value == "A, C"

    multi_line_2 = "15 = B/C"
    e2 = answer_parser.parse_line(multi_line_2, page_number=1)
    assert len(e2) == 1
    assert e2[0].normalized_reference == "15"
    assert e2[0].answer_value == "B/C"

    # Uncertain / unclear markers: 10 = ? or 11 = unclear
    uncert_line_1 = "10 = ?"
    u1 = answer_parser.parse_line(uncert_line_1, page_number=1)
    assert len(u1) == 1
    assert u1[0].is_uncertain is True
    assert u1[0].confidence == 0.0

    uncert_line_2 = "11: unclear"
    u2 = answer_parser.parse_line(uncert_line_2, page_number=1)
    assert len(u2) == 1
    assert u2[0].is_uncertain is True


# ==============================================================================
# 3. DETERMINISTIC ANSWER MATCHING & NO SILENT GUESSING
# ==============================================================================

def test_answer_matcher_scenarios():
    """Verify deterministic matching, normalized matching, and refusal to guess."""
    q_doc_id = uuid.uuid4()
    q1 = Question(id=uuid.uuid4(), document_id=q_doc_id, question_number="1", question_text="What is 1?")
    q2 = Question(id=uuid.uuid4(), document_id=q_doc_id, question_number="2", question_text="What is 2?")
    q4 = Question(id=uuid.uuid4(), document_id=q_doc_id, question_number="4", question_text="What is 4?")
    # Unnumbered question
    q_un = Question(id=uuid.uuid4(), document_id=q_doc_id, question_number=None, question_text="Unnumbered question.")
    questions = [q1, q2, q4, q_un]

    # Answers: 1 B, 2 C, 3 A, 4 D, 7 B, 10 = ?
    entries = [
        answer_parser.parse_line("1. B")[0],
        answer_parser.parse_line("2. C")[0],
        answer_parser.parse_line("3. A")[0],
        answer_parser.parse_line("4. D")[0],
        answer_parser.parse_line("7. B")[0],
        answer_parser.parse_line("10 = ?")[0],
    ]

    matches = answer_matcher.match_answers(entries, questions)
    assert len(matches) == 6

    # 1. Matched to q1
    assert matches[0].matched_question_id == q1.id
    assert matches[0].confidence >= 0.95
    assert matches[0].match_strategy == "EXACT"

    # 2. Matched to q2
    assert matches[1].matched_question_id == q2.id
    assert matches[1].confidence >= 0.95

    # 3. Answer 3 has NO matching question (q3 missing) -> UNMATCHED, question_id=None
    assert matches[2].matched_question_id is None
    assert matches[2].match_strategy == "UNMATCHED"

    # 4. Matched to q4 (even though 3 was skipped, 4 matches 4)
    assert matches[3].matched_question_id == q4.id

    # 5. Answer 7 has NO matching question -> MUST NOT arbitrarily match unnumbered question!
    assert matches[4].matched_question_id is None
    assert matches[4].match_strategy == "UNMATCHED"

    # 6. Uncertain answer -> UNCERTAIN, question_id=None
    assert matches[5].matched_question_id is None
    assert matches[5].match_strategy == "UNCERTAIN"


def test_answer_matcher_ambiguous_questions():
    """Verify that multiple questions with the same number are flagged ambiguous without random guessing."""
    q_doc_id = uuid.uuid4()
    # Two questions with number '1' (e.g. duplicate section numbers)
    q1_a = Question(id=uuid.uuid4(), document_id=q_doc_id, question_number="1", question_text="Part A Q1")
    q1_b = Question(id=uuid.uuid4(), document_id=q_doc_id, question_number="1", question_text="Part B Q1")

    entries = answer_parser.parse_line("1. B")
    matches = answer_matcher.match_answers(entries, [q1_a, q1_b])

    assert len(matches) == 1
    # Must NOT guess between q1_a and q1_b
    assert matches[0].matched_question_id is None
    assert matches[0].match_strategy == "AMBIGUOUS"
    assert matches[0].confidence == 0.30


# ==============================================================================
# 4. SAME-DOCUMENT ANSWER KEY EXTRACTION
# ==============================================================================

def test_same_document_answer_key(user_a_token: str):
    """Verify document containing both questions and an answer-key section."""
    content = [
        (
            "MATHEMATICS EXAMINATION - 2026\n"
            "1. What is the value of 5 + 3?\n"
            "(A) 6\n"
            "(B) 7\n"
            "(C) 8\n"
            "(D) 9\n"
            "2. What is the derivative of x^2?\n"
            "(A) x\n"
            "(B) 2x\n"
            "(C) x^2\n"
            "(D) 2\n"
        ),
        (
            "ANSWER KEY\n"
            "1. C\n"
            "2. B\n"
        ),
    ]
    pdf_bytes = create_sample_pdf(content)

    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("math_exam_with_key.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]

    # Process document
    db_session = SessionLocal()
    try:
        doc = db_session.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
        proc_result = document_processor.process(
            document_id=doc.id,
            storage_path=doc.storage_path,
            db=db_session,
        )
        assert proc_result["success"] is True
        assert proc_result["extracted_questions"] == 2
        assert proc_result["answers"]["extracted"] is True
        assert proc_result["answers"]["matched_count"] == 2
    finally:
        db_session.close()

    # Verify via GET /api/v1/documents/{id}/answers
    ans_res = client.get(
        f"/api/v1/documents/{doc_id}/answers",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert ans_res.status_code == 200
    ans_data = ans_res.json()
    assert ans_data["answer_key"] is not None
    assert ans_data["answer_key"]["document_id"] == doc_id
    assert ans_data["answer_key"]["source_document_id"] == doc_id
    assert len(ans_data["answers"]) == 2

    # Verify answers on Question records via GET /api/v1/documents/{id}/questions
    q_res = client.get(
        f"/api/v1/documents/{doc_id}/questions",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert q_res.status_code == 200
    questions = q_res.json()["items"]
    assert len(questions) == 2
    assert questions[0]["question_number"] == "1"
    assert questions[0]["answer"] == "C"
    assert questions[0]["answer_source"] == "ANSWER_KEY"
    assert questions[0]["answer_confidence"] >= 0.95

    assert questions[1]["question_number"] == "2"
    assert questions[1]["answer"] == "B"
    assert questions[1]["answer_source"] == "ANSWER_KEY"


# ==============================================================================
# 5. SEPARATE ANSWER-KEY DOCUMENT & RELATED DOCUMENT WORKFLOW
# ==============================================================================

def test_separate_answer_key_document_workflow(user_a_token: str):
    """Verify separate Question Paper and Answer Key documents connected via RelatedDocument."""
    # 1. Upload Question Paper
    qp_content = [
        (
            "PHYSICS FINAL EXAM\n"
            "1. What is the unit of force?\n"
            "(A) Joule\n"
            "(B) Newton\n"
            "2. State the unit of power.\n"
            "(A) Watt\n"
            "(B) Pascal\n"
        )
    ]
    qp_bytes = create_sample_pdf(qp_content)
    qp_upload = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("physics_paper.pdf", io.BytesIO(qp_bytes), "application/pdf")},
        data={"document_role": "QUESTION_PAPER"},
    )
    assert qp_upload.status_code == 202
    qp_id = qp_upload.json()["id"]

    # 2. Upload Answer Key Document
    ak_content = [
        (
            "ANSWER KEY - PHYSICS\n"
            "1. B\n"
            "2. A\n"
            "3. C\n"  # Unmatched extra answer
        )
    ]
    ak_bytes = create_sample_pdf(ak_content)
    ak_upload = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("physics_key.pdf", io.BytesIO(ak_bytes), "application/pdf")},
        data={"document_role": "ANSWER_KEY"},
    )
    assert ak_upload.status_code == 202
    ak_id = ak_upload.json()["id"]

    # 3. Process both documents
    db_session = SessionLocal()
    try:
        qp_doc = db_session.scalar(select(Document).where(Document.id == uuid.UUID(qp_id)))
        document_processor.process(qp_doc.id, qp_doc.storage_path, db=db_session)

        ak_doc = db_session.scalar(select(Document).where(Document.id == uuid.UUID(ak_id)))
        document_processor.process(ak_doc.id, ak_doc.storage_path, db=db_session)
    finally:
        db_session.close()

    # 4. Establish explicit ANSWER_KEY relationship via POST /documents/{id}/related
    rel_res = client.post(
        f"/api/v1/documents/{qp_id}/related",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"related_document_id": ak_id, "relationship_type": "ANSWER_KEY"},
    )
    assert rel_res.status_code == 201
    assert rel_res.json()["document_id"] == qp_id
    assert rel_res.json()["related_document_id"] == ak_id
    assert rel_res.json()["relationship_type"] == "ANSWER_KEY"

    # 5. Verify answers associated to Question Paper
    ans_res = client.get(
        f"/api/v1/documents/{qp_id}/answers",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert ans_res.status_code == 200
    ans_data = ans_res.json()
    assert ans_data["answer_key"] is not None
    assert ans_data["answer_key"]["document_id"] == qp_id
    assert ans_data["answer_key"]["source_document_id"] == ak_id
    assert len(ans_data["answers"]) == 3

    # Check that answer 1 and 2 are matched to question UUIDs, and answer 3 is unmatched
    answers = ans_data["answers"]
    assert answers[0]["question_reference"] == "1"
    assert answers[0]["question_id"] is not None
    assert answers[0]["answer_value"] == "B"

    assert answers[1]["question_reference"] == "2"
    assert answers[1]["question_id"] is not None
    assert answers[1]["answer_value"] == "A"

    assert answers[2]["question_reference"] == "3"
    assert answers[2]["question_id"] is None  # Preserved unmatched!

    # 6. Verify telemetry via GET /documents/{id}/answer-key
    summary_res = client.get(
        f"/api/v1/documents/{qp_id}/answer-key",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert summary_res.status_code == 200
    s_data = summary_res.json()
    assert s_data["total_mappings"] == 3
    assert s_data["matched_count"] == 2
    assert s_data["unmatched_count"] == 1

    # 7. Check individual question API GET /questions/{id}
    q1_id = answers[0]["question_id"]
    indiv_q_res = client.get(
        f"/api/v1/questions/{q1_id}",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert indiv_q_res.status_code == 200
    assert indiv_q_res.json()["id"] == q1_id
    assert indiv_q_res.json()["answer"] == "B"
    assert indiv_q_res.json()["answer_source"] == "ANSWER_KEY"


# ==============================================================================
# 6. IDEMPOTENCY & SAFE RE-EXTRACTION
# ==============================================================================

def test_answer_idempotency_safe_rerun(db: Session):
    """Verify re-running answer extraction replaces old mappings without creating duplicates."""
    user = User(
        email=f"ans_idem_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hash",
        is_active=True,
    )
    db.add(user)
    db.flush()

    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        owner_id=user.id,
        filename="exam.pdf",
        document_type="PDF",
        mime_type="application/pdf",
        document_role=DocumentRole.QUESTION_PAPER,
        file_size=1024,
        storage_path="mock/exam.pdf",
        status=DocumentStatus.PROCESSING,
    )
    db.add(doc)

    p1 = DocumentPage(
        id=uuid.uuid4(),
        document_id=doc_id,
        page_number=1,
        text_content="ANSWER KEY\n1. A\n2. B\n",
    )
    db.add(p1)

    q1 = Question(id=uuid.uuid4(), document_id=doc_id, question_number="1", question_text="Q1")
    q2 = Question(id=uuid.uuid4(), document_id=doc_id, question_number="2", question_text="Q2")
    db.add_all([q1, q2])
    db.commit()

    # First run
    res1 = answer_extractor.extract_and_associate(doc_id, doc_id, db)
    assert res1.total_entries == 2
    assert res1.matched_count == 2

    keys_count_1 = db.scalars(select(AnswerKey).where(AnswerKey.document_id == doc_id)).all()
    mappings_count_1 = db.scalars(select(AnswerMapping)).all()
    assert len(keys_count_1) == 1

    # Second run (simulating retry or re-extraction)
    res2 = answer_extractor.extract_and_associate(doc_id, doc_id, db)
    assert res2.total_entries == 2
    assert res2.matched_count == 2

    # Verify exactly 1 AnswerKey and exactly 2 AnswerMapping exist
    keys_count_2 = db.scalars(select(AnswerKey).where(AnswerKey.document_id == doc_id)).all()
    assert len(keys_count_2) == 1

    mappings = db.scalars(select(AnswerMapping).where(AnswerMapping.answer_key_id == keys_count_2[0].id)).all()
    assert len(mappings) == 2


# ==============================================================================
# 7. RELATED DOCUMENT API VALIDATIONS & SECURITY ISOLATION
# ==============================================================================

def test_related_document_api_validations(user_a_token: str, user_b_token: str):
    """Verify validation rules on related document creation (self, non-existent, duplicate, cross-tenant)."""
    # Create doc for User A
    pdf_bytes = create_sample_pdf(["Doc A content"])
    res_a1 = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("doc_a1.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    doc_a1_id = res_a1.json()["id"]

    res_a2 = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("doc_a2.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    doc_a2_id = res_a2.json()["id"]

    # Create doc for User B
    res_b = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_b_token}"},
        files={"file": ("doc_b.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    doc_b_id = res_b.json()["id"]

    # 1. Self-relationship rejected with 400
    res_self = client.post(
        f"/api/v1/documents/{doc_a1_id}/related",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"related_document_id": doc_a1_id, "relationship_type": "ANSWER_KEY"},
    )
    assert res_self.status_code == 400
    assert res_self.json()["error"]["code"] == "BAD_REQUEST"

    # 2. Non-existent document rejected with 404
    fake_id = str(uuid.uuid4())
    res_fake = client.post(
        f"/api/v1/documents/{doc_a1_id}/related",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"related_document_id": fake_id, "relationship_type": "ANSWER_KEY"},
    )
    assert res_fake.status_code == 404
    assert res_fake.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    # 3. User A attempts to relate User B's document -> rejected with 404 (isolation)
    res_cross = client.post(
        f"/api/v1/documents/{doc_a1_id}/related",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"related_document_id": doc_b_id, "relationship_type": "ANSWER_KEY"},
    )
    assert res_cross.status_code == 404
    assert res_cross.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    # 4. Valid relationship
    res_valid = client.post(
        f"/api/v1/documents/{doc_a1_id}/related",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"related_document_id": doc_a2_id, "relationship_type": "ANSWER_KEY"},
    )
    assert res_valid.status_code == 201

    # 5. Duplicate relationship rejected with 409
    res_dup = client.post(
        f"/api/v1/documents/{doc_a1_id}/related",
        headers={"Authorization": f"Bearer {user_a_token}"},
        json={"related_document_id": doc_a2_id, "relationship_type": "ANSWER_KEY"},
    )
    assert res_dup.status_code == 409
    assert res_dup.json()["error"]["code"] == "HTTP_409"


def test_answer_apis_security_isolation(user_a_token: str, user_b_token: str):
    """Verify tenant isolation across answers, answer-key, and question APIs."""
    pdf_bytes = create_sample_pdf(["ANSWER KEY\n1. A\n"])
    res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("owner_a_key.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    doc_id = res.json()["id"]

    # User B attempts to access User A's answers
    res_ans = client.get(
        f"/api/v1/documents/{doc_id}/answers",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert res_ans.status_code == 404
    assert res_ans.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    # User B attempts to access User A's answer-key summary
    res_summary = client.get(
        f"/api/v1/documents/{doc_id}/answer-key",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert res_summary.status_code == 404
    assert res_summary.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    # User B attempts to access non-existent / unauthorized individual question
    fake_q_id = str(uuid.uuid4())
    res_q = client.get(
        f"/api/v1/questions/{fake_q_id}",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert res_q.status_code == 404
    assert res_q.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
