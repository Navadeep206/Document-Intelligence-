"""Comprehensive test suite for Phase 5: Document Ingestion, Page Processing, and OCR."""

import io
from unittest.mock import MagicMock, patch
import uuid

from fastapi.testclient import TestClient
import fitz  # PyMuPDF
from PIL import Image, ImageDraw
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models.document import Document
from app.db.models.enums import DocumentRole, DocumentStatus
from app.db.models.page import DocumentPage
from app.main import app
from app.services.document_inspector import (
    CorruptDocumentError,
    DocumentInspectionReport,
    document_inspector,
)
from app.services.document_processor import document_processor
from app.services.ocr_service import ocr_service
from app.services.storage import get_storage_service
from app.services.text_normalizer import normalize_extracted_text
from app.workers.tasks.document_processing import process_document

client = TestClient(app, raise_server_exceptions=False)


def register_and_get_token(email_prefix: str) -> str:
    """Helper registering a user and returning their JWT access token."""
    email = f"{email_prefix}_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "Password123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": pwd})
    res = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    return res.json()["access_token"]


@pytest.fixture
def user_a_token() -> str:
    return register_and_get_token("p5_user_a")


@pytest.fixture
def user_b_token() -> str:
    return register_and_get_token("p5_user_b")


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_digital_pdf(text: str) -> bytes:
    """Create an in-memory PDF containing selectable digital text."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 standard
    page.insert_text((50, 72), text, fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_image_bytes(text: str, fmt: str = "PNG") -> bytes:
    """Create an in-memory image with drawn text for OCR testing."""
    img = Image.new("RGB", (600, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 50), text, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def create_scanned_pdf(text: str) -> bytes:
    """Create a PDF embedding an image of text with no selectable digital text layer."""
    img_bytes = create_image_bytes(text, "PNG")
    doc = fitz.open()
    img_doc = fitz.open("png", img_bytes)
    rect = fitz.Rect(0, 0, 595, 842)
    page = doc.new_page(width=595, height=842)
    page.insert_image(rect, stream=img_bytes)
    pdf_bytes = doc.tobytes()
    img_doc.close()
    doc.close()
    return pdf_bytes


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------

def test_text_normalizer_cleanup() -> None:
    """Verify non-destructive text normalization."""
    raw = "Question 1: What is energy?\r\n  (A) Power * Time   \r\n\r\n\r\n(B) Force / Distance\x0c"
    normalized = normalize_extracted_text(raw)

    assert "\r" not in normalized
    assert "\x0c" not in normalized
    assert "Question 1: What is energy?" in normalized
    assert "  (A) Power * Time" in normalized  # leading indent preserved, trailing whitespace stripped
    assert "\n\n\n" not in normalized  # collapsed to 2 newlines
    assert "\n\n" in normalized


def test_document_inspector_digital_pdf(tmp_path) -> None:
    """Inspect digital PDF with native selectable text."""
    content = "Sample examination paper with plenty of digital characters for detection."
    pdf_path = tmp_path / "digital.pdf"
    pdf_path.write_bytes(create_digital_pdf(content))

    report = document_inspector.inspect(pdf_path)
    assert report.format == "PDF"
    assert report.page_count == 1
    assert report.has_digital_text is True
    assert report.is_scanned is False
    assert len(report.pages) == 1
    assert report.pages[0].has_digital_text is True


def test_document_inspector_scanned_pdf(tmp_path) -> None:
    """Inspect scanned PDF where text is embedded only in images."""
    pdf_path = tmp_path / "scanned.pdf"
    pdf_path.write_bytes(create_scanned_pdf("Scanned Question Text"))

    report = document_inspector.inspect(pdf_path)
    assert report.format == "PDF"
    assert report.page_count == 1
    assert report.has_digital_text is False
    assert report.is_scanned is True
    assert report.pages[0].has_digital_text is False


def test_document_inspector_image(tmp_path) -> None:
    """Inspect standalone image file."""
    img_path = tmp_path / "question_diagram.png"
    img_path.write_bytes(create_image_bytes("Figure 1. Circuit diagram"))

    report = document_inspector.inspect(img_path)
    assert report.format == "PNG"
    assert report.page_count == 1
    assert report.is_scanned is True
    assert report.has_digital_text is False


def test_document_inspector_corrupt_file(tmp_path) -> None:
    """Corrupted file raises CorruptDocumentError."""
    bad_pdf = tmp_path / "corrupt.pdf"
    bad_pdf.write_bytes(b"%PDF-1.4\ncorrupted garbage that fitz cannot parse")

    with pytest.raises(CorruptDocumentError):
        document_inspector.inspect(bad_pdf)


def test_ocr_service_real_text_and_confidence() -> None:
    """Verify real Tesseract OCR invocation and confidence aggregation."""
    img_bytes = create_image_bytes("PHYSICS EXAMINATION 2026")
    img = Image.open(io.BytesIO(img_bytes))

    result = ocr_service.extract_text(img)
    assert result.confidence is not None
    assert 0.0 <= result.confidence <= 1.0
    assert result.language == "eng"
    assert "PHYSICS" in result.text.upper() or "EXAMINATION" in result.text.upper()


def test_ocr_service_empty_image_confidence() -> None:
    """Blank image yields 0.0 confidence without failing."""
    blank = Image.new("RGB", (400, 200), color=(255, 255, 255))
    result = ocr_service.extract_text(blank)
    assert result.confidence == 0.0
    assert result.text.strip() == ""


# ---------------------------------------------------------------------------
# Integration Tests: End-to-End Ingestion Pipeline
# ---------------------------------------------------------------------------

def test_digital_pdf_pipeline_uses_native_text(user_a_token: str, db: Session) -> None:
    """Digital PDF must extract native text without invoking OCR."""
    text_content = "Q1. State Archimedes' principle and write its formula.\nOption A: Buoyancy\nOption B: Gravity"
    pdf_bytes = create_digital_pdf(text_content)

    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("physics_digital.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]
    job_id = upload_res.json()["job_id"]

    # Execute background Celery task
    task_res = process_document.apply(args=[doc_id, job_id])
    assert task_res.result["status"] == "completed"

    # Verify Document state in PostgreSQL
    db.expire_all()
    doc = db.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
    assert doc.status == DocumentStatus.COMPLETED
    assert doc.page_count == 1
    assert doc.processed_at is not None

    # Verify DocumentPage state in PostgreSQL
    pages = db.scalars(select(DocumentPage).where(DocumentPage.document_id == uuid.UUID(doc_id))).all()
    assert len(pages) == 1
    page1 = pages[0]
    assert page1.page_number == 1
    assert page1.ocr_used is False
    assert page1.ocr_confidence is None
    assert "Archimedes" in page1.text_content


def test_scanned_pdf_pipeline_triggers_ocr_fallback(user_a_token: str, db: Session) -> None:
    """Scanned PDF with no digital text layer falls back to page rendering and OCR."""
    scanned_text = "CHEMISTRY TEST QUESTION ONE"
    pdf_bytes = create_scanned_pdf(scanned_text)

    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("scanned_chem.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]
    job_id = upload_res.json()["job_id"]

    # Execute task
    task_res = process_document.apply(args=[doc_id, job_id])
    assert task_res.result["status"] == "completed"

    db.expire_all()
    doc = db.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
    assert doc.status == DocumentStatus.COMPLETED
    assert doc.page_count == 1

    pages = db.scalars(select(DocumentPage).where(DocumentPage.document_id == uuid.UUID(doc_id))).all()
    assert len(pages) == 1
    page1 = pages[0]
    assert page1.ocr_used is True
    assert page1.ocr_confidence is not None
    assert 0.0 <= page1.ocr_confidence <= 1.0


def test_png_image_pipeline_ocr(user_a_token: str, db: Session) -> None:
    """Raster image document routes directly to OCR and creates page 1."""
    img_bytes = create_image_bytes("MATHEMATICS ALGEBRA QUESTION", "PNG")

    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("math_scan.png", img_bytes, "image/png")},
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]
    job_id = upload_res.json()["job_id"]

    task_res = process_document.apply(args=[doc_id, job_id])
    assert task_res.result["status"] == "completed"

    db.expire_all()
    doc = db.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
    assert doc.status == DocumentStatus.COMPLETED
    assert doc.page_count == 1

    page = db.scalar(select(DocumentPage).where(DocumentPage.document_id == uuid.UUID(doc_id)))
    assert page.page_number == 1
    assert page.ocr_used is True
    assert page.ocr_confidence is not None


def test_multipage_pdf_processing(user_a_token: str, db: Session) -> None:
    """Multi-page document processes each page independently with correct sequence."""
    doc = fitz.open()
    # Page 1: Digital text
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 72), "Page 1: Digital Question Paper Content.", fontsize=12)
    # Page 2: Digital text
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 72), "Page 2: Second examination page with native text.", fontsize=12)
    # Page 3: Scanned image page
    p3 = doc.new_page(width=595, height=842)
    img_b = create_image_bytes("Page 3 Scanned Diagram Text", "PNG")
    p3.insert_image(fitz.Rect(50, 50, 500, 200), stream=img_b)

    pdf_bytes = doc.tobytes()
    doc.close()

    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("multipage.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]
    job_id = upload_res.json()["job_id"]

    task_res = process_document.apply(args=[doc_id, job_id])
    assert task_res.result["status"] == "completed"

    db.expire_all()
    doc_rec = db.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
    assert doc_rec.page_count == 3
    assert doc_rec.status == DocumentStatus.COMPLETED

    pages = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == uuid.UUID(doc_id))
        .order_by(DocumentPage.page_number.asc())
    ).all()

    assert len(pages) == 3
    assert pages[0].page_number == 1
    assert pages[0].ocr_used is False
    assert pages[1].page_number == 2
    assert pages[1].ocr_used is False
    assert pages[2].page_number == 3
    assert pages[2].ocr_used is True


def test_partial_processing_handling(user_a_token: str, db: Session) -> None:
    """Document where one page fails marks PARTIAL status while preserving successful pages."""
    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 72), "Valid First Page Content for Examination.", fontsize=12)
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 72), "Second Page Content to Trigger Error.", fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()

    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("partial_doc.pdf", pdf_bytes, "application/pdf")},
    )
    doc_id = upload_res.json()["id"]
    job_id = upload_res.json()["job_id"]

    # Mock native text extraction so page 2 raises an error
    original_extract = document_processor.pdf_service.extract_native_text

    def selective_failure(page, min_chars=None):
        if page.number == 1:  # 0-indexed page 2
            raise RuntimeError("Simulated rendering/extraction corruption on page 2")
        return original_extract(page, min_chars)

    with patch.object(document_processor.pdf_service, "extract_native_text", side_effect=selective_failure):
        task_res = process_document.apply(args=[doc_id, job_id])
        assert task_res.result["status"] == "completed"

    db.expire_all()
    doc_rec = db.scalar(select(Document).where(Document.id == uuid.UUID(doc_id)))
    # Document status should be PARTIAL
    assert doc_rec.status == DocumentStatus.PARTIAL
    assert doc_rec.page_count == 2

    # Both page records exist (page 1 with text, page 2 recorded)
    pages = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == uuid.UUID(doc_id))
        .order_by(DocumentPage.page_number.asc())
    ).all()
    assert len(pages) == 2
    assert "Valid First Page" in pages[0].text_content


def test_get_document_pages_api(user_a_token: str, user_b_token: str) -> None:
    """GET /api/v1/documents/{id}/pages returns pages to owner and 404 to unauthorized user."""
    pdf_bytes = create_digital_pdf("Biology Test Paper Section A: Plant Anatomy.")
    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("biology_pages.pdf", pdf_bytes, "application/pdf")},
    )
    doc_id = upload_res.json()["id"]
    job_id = upload_res.json()["job_id"]

    # Process document
    process_document.apply(args=[doc_id, job_id])

    # Owner retrieves pages
    pages_res = client.get(
        f"/api/v1/documents/{doc_id}/pages",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert pages_res.status_code == 200
    pages_data = pages_res.json()
    assert pages_data["total_pages"] == 1
    assert len(pages_data["items"]) == 1
    assert pages_data["items"][0]["page_number"] == 1
    assert "Plant Anatomy" in pages_data["items"][0]["text_content"]

    # Non-owner receives 404
    unauth_res = client.get(
        f"/api/v1/documents/{doc_id}/pages",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert unauth_res.status_code == 404


def test_status_endpoint_returns_page_count(user_a_token: str) -> None:
    """GET /api/v1/documents/{id}/status reports page_count after inspection."""
    pdf_bytes = create_digital_pdf("English Literature Exam Questions.")
    upload_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {user_a_token}"},
        files={"file": ("english_test.pdf", pdf_bytes, "application/pdf")},
    )
    doc_id = upload_res.json()["id"]
    job_id = upload_res.json()["job_id"]

    process_document.apply(args=[doc_id, job_id])

    status_res = client.get(
        f"/api/v1/documents/{doc_id}/status",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["document_status"] == "COMPLETED"
    assert status_data["page_count"] == 1
