"""End-to-end integration test covering the complete service lifecycle."""

import io
import uuid
from fastapi.testclient import TestClient
import fitz
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models.document import Document
from app.db.models.enums import DocumentStatus, ReviewStatus
from app.db.models.review import ReviewItem
from app.main import app
from app.services.document_processor import document_processor

client = TestClient(app, raise_server_exceptions=False)


def create_exam_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 50),
        "MIDTERM EXAMINATION\n\n"
        "1. Which protocol provides reliable transport on the Internet?\n"
        "(A) UDP  (B) TCP  (C) IP  (D) ICMP\n\n"
        "2. Explain the difference between process and thread.\n"
    )
    b = doc.tobytes()
    doc.close()
    return b


def create_key_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 50),
        "OFFICIAL ANSWER KEY\n\n"
        "1. B\n"
    )
    b = doc.tobytes()
    doc.close()
    return b


def test_complete_api_lifecycle() -> None:
    # 1. Health checks
    health_res = client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "healthy"

    # 2. Register user
    email = f"lifecycle_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "LifecyclePass123!"
    reg_res = client.post("/api/v1/auth/register", json={"email": email, "password": pwd})
    assert reg_res.status_code == 201

    # 3. Login
    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 4. Auth Me
    me_res = client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email

    # 5. Upload Exam Document
    exam_bytes = create_exam_pdf()
    upload_res = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("computer_networks.pdf", io.BytesIO(exam_bytes), "application/pdf")},
        data={"document_role": "QUESTION_PAPER"},
    )
    assert upload_res.status_code == 202
    exam_doc_id = upload_res.json()["id"]

    # 6. Check Processing Status
    status_res = client.get(f"/api/v1/documents/{exam_doc_id}/status", headers=headers)
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["document_id"] == exam_doc_id
    assert status_data["status"] == "QUEUED"

    # 7. Execute document processing
    db = SessionLocal()
    try:
        doc = db.scalar(select(Document).where(Document.id == uuid.UUID(exam_doc_id)))
        assert doc is not None
        document_processor.process(
            document_id=doc.id,
            storage_path=doc.storage_path,
            db=db,
        )
    finally:
        db.close()

    # 8. Check Status after processing -> COMPLETED
    status_res2 = client.get(f"/api/v1/documents/{exam_doc_id}/status", headers=headers)
    assert status_res2.status_code == 200
    status_data2 = status_res2.json()
    assert status_data2["status"] == "COMPLETED"
    assert status_data2["pages_processed"] >= 1
    assert status_data2["questions_extracted"] >= 1

    # 9. Get Document Metadata
    doc_res = client.get(f"/api/v1/documents/{exam_doc_id}", headers=headers)
    assert doc_res.status_code == 200
    doc_data = doc_res.json()
    assert doc_data["filename"] == "computer_networks.pdf"
    assert doc_data["question_count"] >= 1
    assert "storage_path" not in doc_data

    # 10. List Extracted Questions (paginated)
    q_list_res = client.get(
        f"/api/v1/documents/{exam_doc_id}/questions?page=1&page_size=10",
        headers=headers,
    )
    assert q_list_res.status_code == 200
    q_list = q_list_res.json()
    assert q_list["total"] >= 1
    assert len(q_list["items"]) >= 1
    first_q = q_list["items"][0]
    assert "question_text" in first_q
    q_id = first_q["id"]

    # 11. Retrieve Single Question Detail
    q_detail_res = client.get(f"/api/v1/questions/{q_id}", headers=headers)
    assert q_detail_res.status_code == 200
    assert q_detail_res.json()["id"] == q_id

    # 12. Upload Answer Key Document
    key_bytes = create_key_pdf()
    upload_key_res = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("networks_key.pdf", io.BytesIO(key_bytes), "application/pdf")},
        data={"document_role": "ANSWER_KEY"},
    )
    assert upload_key_res.status_code == 202
    key_doc_id = upload_key_res.json()["id"]

    # Process key document
    db2 = SessionLocal()
    try:
        key_doc = db2.scalar(select(Document).where(Document.id == uuid.UUID(key_doc_id)))
        document_processor.process(
            document_id=key_doc.id,
            storage_path=key_doc.storage_path,
            db=db2,
        )
    finally:
        db2.close()

    # 13. Create Related Document Link (Question Paper -> Answer Key)
    rel_res = client.post(
        f"/api/v1/documents/{exam_doc_id}/related",
        headers=headers,
        json={"related_document_id": key_doc_id, "relationship_type": "ANSWER_KEY"},
    )
    assert rel_res.status_code == 201

    # 14. Get Related Documents
    get_rel_res = client.get(f"/api/v1/documents/{exam_doc_id}/related", headers=headers)
    assert get_rel_res.status_code == 200
    assert get_rel_res.json()["total"] >= 1

    # 15. Get Answer Mappings
    mappings_res = client.get(f"/api/v1/documents/{exam_doc_id}/answer-mappings", headers=headers)
    assert mappings_res.status_code == 200
    assert "items" in mappings_res.json()

    # 16. Get Reviews and resolve an item if any
    rev_res = client.get(f"/api/v1/documents/{exam_doc_id}/reviews", headers=headers)
    assert rev_res.status_code == 200

    # Create synthetic review item if none to test resolve workflow
    db3 = SessionLocal()
    try:
        item = ReviewItem(
            id=uuid.uuid4(),
            document_id=uuid.UUID(exam_doc_id),
            question_id=uuid.UUID(q_id),
            severity="LOW",
            status=ReviewStatus.OPEN,
            reason="OPTIONAL_MANUAL_CHECK",
            details="Lifecycle verification review item",
        )
        db3.add(item)
        db3.commit()
        item_id = str(item.id)
    finally:
        db3.close()

    resolve_res = client.patch(
        f"/api/v1/reviews/{item_id}",
        headers=headers,
        json={"status": "RESOLVED"},
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "RESOLVED"
