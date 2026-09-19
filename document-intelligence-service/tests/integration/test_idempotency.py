"""Integration tests validating idempotency during task retries or document reprocessing."""

import io
import uuid
from fastapi.testclient import TestClient
import fitz
from sqlalchemy import func, select

from app.db.database import SessionLocal
from app.db.models.answer import AnswerMapping
from app.db.models.document import Document
from app.db.models.page import DocumentPage
from app.db.models.question import Question
from app.db.models.review import ReviewItem
from app.main import app
from app.services.document_processor import document_processor

client = TestClient(app, raise_server_exceptions=False)


def register_user() -> str:
    email = f"idemp_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "IdempPassword123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": pwd})
    res = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    return res.json()["access_token"]


def create_idempotency_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 50),
        "PHYSICS EXAMINATION\n\n"
        "1. State Newton's first law of motion.\n"
        "(A) Inertia  (B) Force  (C) Action-reaction  (D) Gravity\n\n"
        "2. What is the unit of electric charge?\n"
        "(A) Ampere  (B) Coulomb  (C) Volt  (D) Ohm\n"
    )
    b = doc.tobytes()
    doc.close()
    return b


def test_reprocessing_does_not_create_duplicates() -> None:
    token = register_user()
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = create_idempotency_pdf()
    upload_res = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("idempotency_exam.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]

    db = SessionLocal()
    try:
        doc = db.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
        assert doc is not None

        # Run processing execution #1
        document_processor.process(
            document_id=doc.id,
            storage_path=doc.storage_path,
            db=db,
        )

        # Record counts after run #1
        pages_count_1 = db.scalar(
            select(func.count()).select_from(DocumentPage).where(DocumentPage.document_id == doc.id)
        )
        questions_count_1 = db.scalar(
            select(func.count()).select_from(Question).where(Question.document_id == doc.id)
        )
        reviews_count_1 = db.scalar(
            select(func.count()).select_from(ReviewItem).where(ReviewItem.document_id == doc.id)
        )

        assert pages_count_1 == 1
        assert questions_count_1 == 2

        # Run processing execution #2 (simulating task retry or reprocessing)
        document_processor.process(
            document_id=doc.id,
            storage_path=doc.storage_path,
            db=db,
        )

        # Record counts after run #2
        pages_count_2 = db.scalar(
            select(func.count()).select_from(DocumentPage).where(DocumentPage.document_id == doc.id)
        )
        questions_count_2 = db.scalar(
            select(func.count()).select_from(Question).where(Question.document_id == doc.id)
        )
        reviews_count_2 = db.scalar(
            select(func.count()).select_from(ReviewItem).where(ReviewItem.document_id == doc.id)
        )

        # Idempotency assertions: exactly equal counts, no duplicates created
        assert pages_count_2 == pages_count_1
        assert questions_count_2 == questions_count_1
        assert reviews_count_2 == reviews_count_1

    finally:
        db.close()
