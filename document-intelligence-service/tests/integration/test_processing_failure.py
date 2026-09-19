"""Integration tests validating failure handling during async worker processing."""

import io
from unittest.mock import patch
import uuid
from fastapi.testclient import TestClient
import fitz
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models.document import Document
from app.db.models.enums import DocumentStatus, ProcessingJobStatus
from app.db.models.processing_job import ProcessingJob
from app.main import app
from app.services.document_processor import document_processor
from app.workers.tasks.document_processing import process_document

client = TestClient(app, raise_server_exceptions=False)


def register_user() -> str:
    email = f"fail_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "FailPassword123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": pwd})
    res = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    return res.json()["access_token"]


def create_dummy_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Dummy content for failure testing")
    b = doc.tobytes()
    doc.close()
    return b


def test_worker_processing_failure_transitions_to_failed_state() -> None:
    token = register_user()
    headers = {"Authorization": f"Bearer {token}"}

    pdf_bytes = create_dummy_pdf()
    upload_res = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("failure_sim.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]
    job_id = upload_res.json()["job_id"]

    # Simulate unexpected failure during document processing
    with patch.object(document_processor, "process", side_effect=RuntimeError("Simulated OCR failure")):
        # Call task with max retries reached so it fails permanently
        task_res = process_document.apply(
            args=[doc_id, job_id],
            retries=3,
        )
        assert task_res.result["status"] == "failed"

    # Verify document status is FAILED and not stuck in PROCESSING or QUEUED
    db = SessionLocal()
    try:
        doc = db.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
        assert doc is not None
        assert doc.status == DocumentStatus.FAILED
        assert doc.error_message is not None

        job = db.scalar(select(ProcessingJob).where(ProcessingJob.id == uuid.UUID(job_id)))
        assert job is not None
        assert job.status == ProcessingJobStatus.FAILED
        assert job.completed_at is not None
    finally:
        db.close()

    # Verify public status endpoint reflects FAILED cleanly without stack traces
    status_res = client.get(f"/api/v1/documents/{doc_id}/status", headers=headers)
    assert status_res.status_code == 200
    status_payload = status_res.json()
    assert status_payload["status"] == "FAILED"
    # Ensure no internal traceback is exposed to caller
    assert "Traceback" not in str(status_payload)
