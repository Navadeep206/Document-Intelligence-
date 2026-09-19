"""Tests for Phase 4: Asynchronous Document Processing Pipeline.

Validates:
1. Document upload returns HTTP 202 Accepted with job_id and QUEUED status.
2. Background Celery task execution lifecycle (QUEUED -> PROCESSING -> COMPLETED).
3. ProcessingJob lifecycle (PENDING -> RUNNING -> COMPLETED).
4. Task idempotency guard (skipping redundant execution if already completed).
5. Missing file pre-flight failure handling without retrying.
6. Transient error retry handling and retry exhaustion.
7. Real-time processing status polling endpoint GET /api/v1/documents/{id}/status.
8. Status endpoint authorization isolation (404 for non-owners).
9. Broker dispatch failure handling (HTTP 503 and FAILED status).
"""

from unittest.mock import MagicMock, patch
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models.document import Document
from app.db.models.enums import DocumentRole, DocumentStatus, DocumentType, ProcessingJobStatus
from app.db.models.processing_job import ProcessingJob
from app.main import app
from app.services.document_processor import document_processor
from app.services.storage import get_storage_service
from app.workers.tasks.document_processing import process_document

import fitz

client = TestClient(app, raise_server_exceptions=False)

def _build_test_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Valid Pipeline Test Examination Content with sufficient digital characters.")
    pdf_b = doc.tobytes()
    doc.close()
    return pdf_b

PDF_MAGIC_PAYLOAD = _build_test_pdf()



def register_and_get_token(email_prefix: str) -> str:
    """Helper registering a user and returning their JWT access token."""
    email = f"{email_prefix}_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "Password123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": pwd})
    res = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    return res.json()["access_token"]


@pytest.fixture
def user_a_token() -> str:
    return register_and_get_token("pipe_user_a")


@pytest.fixture
def user_b_token() -> str:
    return register_and_get_token("pipe_user_b")


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_upload_returns_202_accepted_with_queued_status_and_job_id(
    user_a_token: str,
    db: Session,
) -> None:
    """Upload must return HTTP 202 Accepted with Document QUEUED and ProcessingJob PENDING."""
    files = {"file": ("biology_test.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")}
    data = {"document_role": "QUESTION_PAPER"}

    response = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files=files,
        data=data,
    )
    assert response.status_code == 202
    payload = response.json()

    assert "id" in payload
    assert "job_id" in payload
    assert payload["filename"] == "biology_test.pdf"
    assert payload["status"] == "QUEUED"

    doc_id = uuid.UUID(payload["id"])
    job_id = uuid.UUID(payload["job_id"])

    # Verify database state
    doc = db.scalar(select(Document).where(Document.id == doc_id))
    assert doc is not None
    assert doc.status == DocumentStatus.QUEUED

    job = db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id))
    assert job is not None
    assert job.document_id == doc_id
    assert job.status in [ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING, ProcessingJobStatus.COMPLETED]
    assert job.task_id is not None


def test_celery_task_successful_execution_and_status_transitions(
    user_a_token: str,
    db: Session,
) -> None:
    """Celery task execution transitions Document and ProcessingJob to COMPLETED."""
    files = {"file": ("chemistry_paper.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")}
    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files=files,
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]
    job_id = upload_res.json()["job_id"]

    # Execute task synchronously via Celery apply()
    task_result = process_document.apply(args=[doc_id, job_id])
    res_data = task_result.result

    assert res_data["status"] == "completed"
    assert res_data["document_id"] == doc_id
    assert res_data["job_id"] == job_id
    assert res_data["result"]["success"] is True

    # Verify updated database entities
    doc = db.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
    assert doc.status == DocumentStatus.COMPLETED
    assert doc.error_message is None

    job = db.scalar(select(ProcessingJob).where(ProcessingJob.id == uuid.UUID(job_id)))
    assert job.status == ProcessingJobStatus.COMPLETED
    assert job.started_at is not None
    assert job.completed_at is not None
    assert job.error_message is None
    assert job.attempt == 1


def test_celery_task_idempotency_guard(
    user_a_token: str,
    db: Session,
) -> None:
    """Executing task on an already COMPLETED job returns idempotency response without re-processing."""
    files = {"file": ("idempotency_test.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")}
    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files=files,
    )
    doc_id = upload_res.json()["id"]
    job_id = upload_res.json()["job_id"]

    # First execution
    first_run = process_document.apply(args=[doc_id, job_id])
    assert first_run.result["status"] == "completed"

    # Second execution (idempotency check)
    second_run = process_document.apply(args=[doc_id, job_id])
    assert second_run.result["status"] == "already_completed"
    assert second_run.result["job_id"] == job_id

    # Verify entity remains COMPLETED
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.id == uuid.UUID(job_id)))
    assert job.status == ProcessingJobStatus.COMPLETED


def test_celery_task_missing_storage_file_fails_fast(
    user_a_token: str,
    db: Session,
) -> None:
    """If the physical file is deleted or missing, the task fails immediately without retrying."""
    files = {"file": ("missing_file_test.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")}
    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files=files,
    )
    doc_id = upload_res.json()["id"]
    job_id = upload_res.json()["job_id"]

    # Delete physical file from storage before worker processes it
    doc = db.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
    storage = get_storage_service()
    storage.delete(doc.storage_path)

    # Execute task
    task_res = process_document.apply(args=[doc_id, job_id])
    assert task_res.result["status"] == "failed"
    assert task_res.result["reason"] == "file_missing"

    # Verify DB reflects permanent failure
    db.expire_all()
    doc_updated = db.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
    assert doc_updated.status == DocumentStatus.FAILED
    assert "missing" in doc_updated.error_message.lower()

    job_updated = db.scalar(select(ProcessingJob).where(ProcessingJob.id == uuid.UUID(job_id)))
    assert job_updated.status == ProcessingJobStatus.FAILED
    assert job_updated.completed_at is not None
    assert "missing" in job_updated.error_message.lower()


def test_celery_task_retry_exhaustion_marks_failed(
    user_a_token: str,
    db: Session,
) -> None:
    """When transient errors occur repeatedly and exceed max retries, doc and job mark FAILED."""
    files = {"file": ("retry_exhaust_test.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")}
    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files=files,
    )
    doc_id = upload_res.json()["id"]
    job_id = upload_res.json()["job_id"]

    # Simulate task called when retries are already exhausted (retries == max_retries = 3)
    with patch.object(document_processor, "process", side_effect=RuntimeError("Simulated OCR failure")):
        task_res = process_document.apply(
            args=[doc_id, job_id],
            retries=3,
        )
        assert task_res.result["status"] == "failed"
        assert "Max retries exceeded" in task_res.result["error"]

    db.expire_all()
    doc_updated = db.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
    assert doc_updated.status == DocumentStatus.FAILED
    assert "retries" in doc_updated.error_message.lower()

    job_updated = db.scalar(select(ProcessingJob).where(ProcessingJob.id == uuid.UUID(job_id)))
    assert job_updated.status == ProcessingJobStatus.FAILED
    assert job_updated.completed_at is not None


def test_get_document_status_endpoint_owner_success(
    user_a_token: str,
    db: Session,
) -> None:
    """Authorized document owner can poll GET /api/v1/documents/{id}/status and inspect job details."""
    files = {"file": ("status_poll_test.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")}
    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files=files,
    )
    doc_id = upload_res.json()["id"]
    job_id = upload_res.json()["job_id"]

    # Query status endpoint
    status_res = client.get(
        f"/api/v1/documents/{doc_id}/status",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert status_res.status_code == 200
    data = status_res.json()

    assert data["document_id"] == doc_id
    assert data["document_status"] in ["QUEUED", "PROCESSING", "COMPLETED"]
    assert data["job"] is not None
    assert data["job"]["id"] == job_id
    assert data["job"]["task_id"] is not None
    assert data["job"]["attempt"] >= 1

    # Execute task and re-check status
    process_document.apply(args=[doc_id, job_id])

    status_res2 = client.get(
        f"/api/v1/documents/{doc_id}/status",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert status_res2.status_code == 200
    data2 = status_res2.json()
    assert data2["document_status"] == "COMPLETED"
    assert data2["job"]["status"] == "COMPLETED"
    assert data2["job"]["completed_at"] is not None


def test_get_document_status_authorization_isolation(
    user_a_token: str,
    user_b_token: str,
) -> None:
    """Non-owner querying document status receives 404 NOT_FOUND to avoid information leakage."""
    files = {"file": ("private_doc.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")}
    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files=files,
    )
    doc_id = upload_res.json()["id"]

    # User B attempts to access User A's processing status
    status_res = client.get(
        f"/api/v1/documents/{doc_id}/status",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert status_res.status_code == 404
    assert "DOCUMENT_NOT_FOUND" in status_res.text


def test_upload_broker_dispatch_failure_marks_failed_and_returns_503(
    user_a_token: str,
    db: Session,
) -> None:
    """If Celery broker dispatch fails after DB commit, job and doc transition to FAILED and API returns 503."""
    with patch("app.api.v1.documents.process_document.delay", side_effect=Exception("Redis connection refused")):
        files = {"file": ("broker_fail_test.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")}
        response = client.post(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {user_a_token}"},
            files=files,
        )
        assert response.status_code == 503
        assert "TASK_DISPATCH_FAILED" in response.text

        # Verify DB records were marked FAILED instead of staying perpetually QUEUED
        failed_docs = db.scalars(
            select(Document).where(Document.filename == "broker_fail_test.pdf")
        ).all()
        assert len(failed_docs) >= 1
        failed_doc = failed_docs[-1]
        assert failed_doc.status == DocumentStatus.FAILED

        failed_job = db.scalar(
            select(ProcessingJob).where(ProcessingJob.document_id == failed_doc.id)
        )
        assert failed_job is not None
        assert failed_job.status == ProcessingJobStatus.FAILED
        assert "Task dispatch failed" in failed_job.error_message
