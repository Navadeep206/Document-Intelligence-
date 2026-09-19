"""Concurrency and multi-document independent processing test suite."""

import io
import uuid
from fastapi.testclient import TestClient
import fitz
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models.document import Document
from app.db.models.enums import DocumentStatus
from app.db.models.page import DocumentPage
from app.db.models.question import Question
from app.main import app
from app.services.document_processor import document_processor

client = TestClient(app, raise_server_exceptions=False)


def register_user() -> str:
    email = f"concurrent_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "ConcurrentPass123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": pwd})
    res = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    return res.json()["access_token"]


def create_pdf_for_subject(subject: str, q1_text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), f"{subject} EXAM\n\n1. {q1_text}\n(A) True (B) False\n")
    b = doc.tobytes()
    doc.close()
    return b


def test_concurrent_independent_document_processing() -> None:
    token = register_user()
    headers = {"Authorization": f"Bearer {token}"}

    docs_data = [
        ("Math", "What is calculus?"),
        ("Biology", "What is mitosis?"),
        ("History", "When was the Magna Carta signed?"),
    ]

    uploaded_doc_ids = []

    # Upload all 3 documents
    for subject, q_text in docs_data:
        pdf_bytes = create_pdf_for_subject(subject, q_text)
        res = client.post(
            "/api/v1/documents",
            headers=headers,
            files={"file": (f"{subject.lower()}_exam.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
        assert res.status_code == 202
        uploaded_doc_ids.append((res.json()["id"], subject, q_text))

    db = SessionLocal()
    try:
        # Process each document
        for doc_id_str, subject, q_text in uploaded_doc_ids:
            doc_id = uuid.UUID(doc_id_str)
            doc = db.scalar(select(Document).where(Document.id == doc_id))
            assert doc is not None

            document_processor.process(
                document_id=doc.id,
                storage_path=doc.storage_path,
                db=db,
            )

        # Verify cross-association isolation
        for doc_id_str, subject, expected_q_text in uploaded_doc_ids:
            doc_id = uuid.UUID(doc_id_str)
            doc = db.scalar(select(Document).where(Document.id == doc_id))
            assert doc.status == DocumentStatus.COMPLETED

            pages = db.scalars(select(DocumentPage).where(DocumentPage.document_id == doc_id)).all()
            assert len(pages) == 1
            assert pages[0].document_id == doc_id
            assert subject in pages[0].text_content

            questions = db.scalars(select(Question).where(Question.document_id == doc_id)).all()
            assert len(questions) >= 1
            for q in questions:
                # Question strictly belongs to this document
                assert q.document_id == doc_id
                assert expected_q_text in q.question_text
    finally:
        db.close()
