"""Multi-tenant authorization isolation matrix test suite."""

import io
import uuid
from fastapi.testclient import TestClient
import fitz
import pytest
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models.document import Document
from app.db.models.enums import DocumentRole, DocumentStatus, DocumentType, QuestionStatus, QuestionType, ReviewSeverity, ReviewStatus
from app.db.models.question import Question
from app.db.models.review import ReviewItem
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def register_user(prefix: str) -> tuple[str, str]:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "MatrixPassword123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": pwd})
    res = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    return res.json()["access_token"], res.json().get("user_id", "")


def create_user_document_with_question_and_review(owner_token: str) -> tuple[str, str, str]:
    """Helper creating a document, question, and review item owned by a user."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "1. What is isolation in databases?\nA. ACID property")
    pdf_b = doc.tobytes()
    doc.close()

    res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {owner_token}"},
        files={"file": ("tenant_exam.pdf", io.BytesIO(pdf_b), "application/pdf")},
    )
    doc_id = res.json()["id"]

    db = SessionLocal()
    try:
        q = Question(
            id=uuid.uuid4(),
            document_id=uuid.UUID(doc_id),
            question_number="1",
            question_text="What is isolation in databases?",
            question_type=QuestionType.MCQ,
            status=QuestionStatus.EXTRACTED,
        )
        db.add(q)
        db.flush()

        item = ReviewItem(
            id=uuid.uuid4(),
            document_id=uuid.UUID(doc_id),
            question_id=q.id,
            severity=ReviewSeverity.LOW,
            status=ReviewStatus.OPEN,
            reason="TENANT_CHECK",
            details="Tenant review item",
        )
        db.add(item)
        db.commit()
        return doc_id, str(q.id), str(item.id)
    finally:
        db.close()


def test_authorization_matrix_tenant_isolation() -> None:
    token_a, _ = register_user("user_a")
    token_b, _ = register_user("user_b")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    doc_a_id, q_a_id, rev_a_id = create_user_document_with_question_and_review(token_a)
    doc_b_id, q_b_id, rev_b_id = create_user_document_with_question_and_review(token_b)

    # 1. User A -> Document A (Allowed)
    res_a_a = client.get(f"/api/v1/documents/{doc_a_id}", headers=headers_a)
    assert res_a_a.status_code == 200

    # 2. User B -> Document B (Allowed)
    res_b_b = client.get(f"/api/v1/documents/{doc_b_id}", headers=headers_b)
    assert res_b_b.status_code == 200

    # 3. User A -> Document B (Forbidden/Not Found - 404 to prevent ID enumeration)
    res_a_b = client.get(f"/api/v1/documents/{doc_b_id}", headers=headers_a)
    assert res_a_b.status_code == 404

    # 4. User B -> Document A (Forbidden/Not Found)
    res_b_a = client.get(f"/api/v1/documents/{doc_a_id}", headers=headers_b)
    assert res_b_a.status_code == 404

    # 5. User A -> Questions in Document B (Denied)
    res_q_a_b = client.get(f"/api/v1/documents/{doc_b_id}/questions", headers=headers_a)
    assert res_q_a_b.status_code == 404

    # 6. User B -> Questions in Document A (Denied)
    res_q_b_a = client.get(f"/api/v1/documents/{doc_a_id}/questions", headers=headers_b)
    assert res_q_b_a.status_code == 404

    # 7. User A -> Direct Question B retrieval (Denied)
    res_direct_q = client.get(f"/api/v1/questions/{q_b_id}", headers=headers_a)
    assert res_direct_q.status_code == 404

    # 8. User A -> Reviews in Document B (Denied)
    res_rev_doc = client.get(f"/api/v1/documents/{doc_b_id}/reviews", headers=headers_a)
    assert res_rev_doc.status_code == 404

    # 9. User A -> Question B Reviews (Denied)
    res_q_rev = client.get(f"/api/v1/questions/{q_b_id}/reviews", headers=headers_a)
    assert res_q_rev.status_code == 404

    # 10. User A -> Update Review B Status (Denied)
    res_patch_rev = client.patch(
        f"/api/v1/reviews/{rev_b_id}",
        headers=headers_a,
        json={"status": "RESOLVED"},
    )
    assert res_patch_rev.status_code == 404

    # 11. User A -> Answer Mappings of Document B (Denied)
    res_ans_map = client.get(f"/api/v1/documents/{doc_b_id}/answer-mappings", headers=headers_a)
    assert res_ans_map.status_code == 404

    # 12. User A -> Related Documents of Document B (Denied)
    res_rel_doc = client.get(f"/api/v1/documents/{doc_b_id}/related", headers=headers_a)
    assert res_rel_doc.status_code == 404
