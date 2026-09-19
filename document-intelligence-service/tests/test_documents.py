"""Document ingestion, validation, ownership, and authorization test suite."""

from unittest.mock import patch
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models.document import Document
from app.db.models.enums import DocumentRole, DocumentStatus, DocumentType
from app.main import app
from app.services.storage import get_storage_service

client = TestClient(app, raise_server_exceptions=False)

# Sample valid binary payloads
PDF_MAGIC_PAYLOAD = b"%PDF-1.4\n%Fake PDF content for test suite\n%%EOF"
PNG_MAGIC_PAYLOAD = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
JPEG_MAGIC_PAYLOAD = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb"


def register_and_get_token(email_prefix: str) -> str:
    """Helper registering a user and returning their JWT access token."""
    email = f"{email_prefix}_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "Password123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": pwd})
    res = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    return res.json()["access_token"]


@pytest.fixture
def user_a_token() -> str:
    return register_and_get_token("user_a")


@pytest.fixture
def user_b_token() -> str:
    return register_and_get_token("user_b")


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_upload_valid_pdf_success(user_a_token: str, db: Session) -> None:
    """Test uploading a valid PDF document."""
    files = {"file": ("physics_exam_2026.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")}
    data = {"document_role": "QUESTION_PAPER"}

    response = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files=files,
        data=data,
    )
    assert response.status_code == 202

    payload = response.json()
    doc_id = uuid.UUID(payload["id"])
    assert payload["filename"] == "physics_exam_2026.pdf"
    assert payload["status"] == "QUEUED"
    assert "job_id" in payload

    # Verify DB record exists and storage_path is randomized
    doc = db.scalar(select(Document).where(Document.id == doc_id))
    assert doc is not None
    assert doc.document_type == DocumentType.PDF
    assert doc.document_role == DocumentRole.QUESTION_PAPER
    assert doc.file_size == len(PDF_MAGIC_PAYLOAD)
    assert doc.storage_path.endswith(".pdf")
    assert doc.storage_path != "physics_exam_2026.pdf"

    # Verify file physically exists on storage
    storage = get_storage_service()
    assert storage.exists(doc.storage_path)


def test_upload_valid_png_and_jpeg(user_a_token: str) -> None:
    """Test uploading valid PNG and JPG images."""
    # PNG upload
    png_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("diagram.png", PNG_MAGIC_PAYLOAD, "image/png")},
    )
    assert png_res.status_code == 202
    assert png_res.json()["status"] == "QUEUED"

    # JPEG upload
    jpeg_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("page_scan.jpg", JPEG_MAGIC_PAYLOAD, "image/jpeg")},
        data={"document_role": "ANSWER_KEY"},
    )
    assert jpeg_res.status_code == 202
    assert jpeg_res.json()["status"] == "QUEUED"



def test_reject_unsupported_extension(user_a_token: str) -> None:
    """Test that executable scripts and unsupported extensions are rejected."""
    files = {"file": ("malicious.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/octet-stream")}
    response = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files=files,
    )
    assert response.status_code == 400
    assert "UNSUPPORTED_FILE_TYPE" in response.text


def test_reject_unsupported_mime_type(user_a_token: str) -> None:
    """Test that valid extension with invalid MIME type is rejected."""
    files = {"file": ("exam.pdf", PDF_MAGIC_PAYLOAD, "text/html")}
    response = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files=files,
    )
    assert response.status_code == 400


def test_reject_corrupted_file_signature(user_a_token: str) -> None:
    """Test that a text file renamed to .pdf fails signature inspection."""
    fake_pdf = b"Plain text file pretending to be a PDF"
    files = {"file": ("fake.pdf", fake_pdf, "application/pdf")}
    response = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files=files,
    )
    assert response.status_code == 400
    assert "INVALID_FILE_CONTENT" in response.text


def test_reject_oversized_file(user_a_token: str) -> None:
    """Test that file exceeding MAX_UPLOAD_SIZE_MB returns 413 Payload Too Large."""
    with patch("app.services.file_validator.settings.MAX_UPLOAD_SIZE_MB", 0.0001):  # ~100 bytes
        oversized_data = PDF_MAGIC_PAYLOAD + (b"A" * 1024)
        files = {"file": ("large.pdf", oversized_data, "application/pdf")}
        response = client.post(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {user_a_token}"},
            files=files,
        )
        assert response.status_code == 413
        assert "FILE_TOO_LARGE" in response.text


def test_path_traversal_filename_sanitization(user_a_token: str, db: Session) -> None:
    """Test that directory traversal sequences in filename are safely stripped."""
    traversal_name = "../../../etc/passwd.pdf"
    files = {"file": (traversal_name, PDF_MAGIC_PAYLOAD, "application/pdf")}
    response = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files=files,
    )
    assert response.status_code == 202
    assert response.json()["filename"] == "passwd.pdf"



def test_authorization_user_cannot_access_other_users_document(
    user_a_token: str,
    user_b_token: str,
) -> None:
    """Test that User B cannot view, download, or delete User A's document (returns 404)."""
    # User A uploads document
    res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("user_a_doc.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")},
    )
    doc_id = res.json()["id"]

    # User B attempts retrieval
    get_res = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert get_res.status_code == 404

    # User B attempts file download
    dl_res = client.get(
        f"/api/v1/documents/{doc_id}/file",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert dl_res.status_code == 404

    # User B attempts deletion
    del_res = client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert del_res.status_code == 404


def test_document_list_pagination_and_owner_isolation(
    user_a_token: str,
    user_b_token: str,
) -> None:
    """Test that GET /api/v1/documents returns only current user's documents."""
    # User A uploads 2 documents
    client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("doc_a1.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")},
    )
    client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("doc_a2.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")},
    )

    # User B uploads 1 document
    client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_b_token}"},
        files={"file": ("doc_b1.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")},
    )

    # Verify User A list
    list_a = client.get(
        "/api/v1/documents?page=1&page_size=10",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert list_a.status_code == 200
    data_a = list_a.json()
    assert data_a["total"] >= 2
    filenames_a = [item["filename"] for item in data_a["items"]]
    assert "doc_a1.pdf" in filenames_a
    assert "doc_a2.pdf" in filenames_a
    assert "doc_b1.pdf" not in filenames_a


def test_download_document_file_success(user_a_token: str) -> None:
    """Test authorized user downloading the original file."""
    res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("download_test.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")},
    )
    doc_id = res.json()["id"]

    dl_resp = client.get(
        f"/api/v1/documents/{doc_id}/file",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert dl_resp.status_code == 200
    assert dl_resp.content == PDF_MAGIC_PAYLOAD
    assert dl_resp.headers["content-type"] == "application/pdf"


def test_delete_document_success(user_a_token: str, db: Session) -> None:
    """Test deleting document cleans up both database and storage file."""
    res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("delete_me.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")},
    )
    doc_id = uuid.UUID(res.json()["id"])

    doc = db.scalar(select(Document).where(Document.id == doc_id))
    storage_path = doc.storage_path
    storage = get_storage_service()
    assert storage.exists(storage_path)

    # Delete via API
    del_resp = client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert del_resp.status_code == 204

    # Verify DB record is gone
    assert db.scalar(select(Document).where(Document.id == doc_id)) is None

    # Verify file is deleted from storage
    assert not storage.exists(storage_path)


def test_database_failure_cleans_up_stored_file(user_a_token: str) -> None:
    """Test transaction safety: if DB insert fails, the saved storage file is rolled back."""
    storage = get_storage_service()
    saved_paths: list[str] = []
    original_save = storage.save

    def tracking_save(content, ext):
        path, size = original_save(content, ext)
        saved_paths.append(path)
        return path, size

    with (
        patch.object(storage, "save", side_effect=tracking_save),
        patch("sqlalchemy.orm.Session.commit", side_effect=RuntimeError("Simulated DB commit error")),
    ):
        files = {"file": ("rollback_test.pdf", PDF_MAGIC_PAYLOAD, "application/pdf")}
        response = client.post(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {user_a_token}"},
            files=files,
        )
        assert response.status_code == 500

        # Verify the file was created and then cleaned up!
        assert len(saved_paths) == 1
        assert not storage.exists(saved_paths[0])
