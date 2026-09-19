"""Unit tests for file validation, size enforcement, and security sanitization."""

import io
from fastapi import HTTPException, UploadFile
import pytest

from app.db.models.enums import DocumentType
from app.services.file_validator import validate_and_read_upload

PDF_HEADER = b"%PDF-1.4\n%Fake PDF content\n%%EOF"
PNG_HEADER = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF"


def make_upload(filename: str, content: bytes, content_type: str) -> UploadFile:
    """Helper to create FastAPI UploadFile from bytes."""
    return UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers={"content-type": content_type},
    )


@pytest.mark.asyncio
async def test_valid_pdf_validation() -> None:
    upload = make_upload("math_exam.pdf", PDF_HEADER, "application/pdf")
    doc_type, filename, mime, content, size = await validate_and_read_upload(upload)
    assert doc_type == DocumentType.PDF
    assert filename == "math_exam.pdf"
    assert mime == "application/pdf"
    assert size == len(PDF_HEADER)


@pytest.mark.asyncio
async def test_valid_png_validation() -> None:
    upload = make_upload("diagram.png", PNG_HEADER, "image/png")
    doc_type, filename, mime, content, size = await validate_and_read_upload(upload)
    assert doc_type == DocumentType.PNG
    assert filename == "diagram.png"
    assert mime == "image/png"


@pytest.mark.asyncio
async def test_valid_jpeg_and_jpg_validation() -> None:
    upload_jpg = make_upload("scan.jpg", JPEG_HEADER, "image/jpeg")
    doc_type, filename, mime, _, _ = await validate_and_read_upload(upload_jpg)
    assert doc_type in [DocumentType.JPG, DocumentType.JPEG]
    assert mime == "image/jpeg"

    upload_jpeg = make_upload("scan2.jpeg", JPEG_HEADER, "image/jpeg")
    doc_type, filename, mime, _, _ = await validate_and_read_upload(upload_jpeg)
    assert doc_type in [DocumentType.JPG, DocumentType.JPEG]


@pytest.mark.asyncio
async def test_unsupported_txt_extension_rejected() -> None:
    upload = make_upload("document.txt", b"Plain text content", "text/plain")
    with pytest.raises(HTTPException) as exc_info:
        await validate_and_read_upload(upload)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.asyncio
async def test_unsupported_exe_rejected() -> None:
    upload = make_upload("malware.exe", b"MZ\x90\x00", "application/x-msdownload")
    with pytest.raises(HTTPException) as exc_info:
        await validate_and_read_upload(upload)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.asyncio
async def test_empty_file_rejected() -> None:
    upload = make_upload("empty.pdf", b"", "application/pdf")
    with pytest.raises(HTTPException) as exc_info:
        await validate_and_read_upload(upload)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "EMPTY_FILE"


@pytest.mark.asyncio
async def test_corrupted_file_signature_rejected() -> None:
    upload = make_upload("fake.pdf", b"NOT_A_REAL_PDF_HEADER", "application/pdf")
    with pytest.raises(HTTPException) as exc_info:
        await validate_and_read_upload(upload)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_FILE_CONTENT"


@pytest.mark.asyncio
async def test_mime_extension_mismatch_rejected() -> None:
    upload = make_upload("spoofed.pdf", PDF_HEADER, "image/png")
    with pytest.raises(HTTPException) as exc_info:
        await validate_and_read_upload(upload)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "MIME_EXTENSION_MISMATCH"


@pytest.mark.asyncio
async def test_path_traversal_sanitization() -> None:
    upload = make_upload("../../../etc/shadow.pdf", PDF_HEADER, "application/pdf")
    _, safe_filename, _, _, _ = await validate_and_read_upload(upload)
    assert ".." not in safe_filename
    assert "/" not in safe_filename
    assert safe_filename == "shadow.pdf"


@pytest.mark.asyncio
async def test_oversized_file_rejected(monkeypatch) -> None:
    from app.core.config import get_settings
    settings = get_settings()
    # Temporarily set MAX_UPLOAD_SIZE_MB to 1 MB for testing
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)

    oversized_data = PDF_HEADER + b"A" * (2 * 1024 * 1024)
    upload = make_upload("big.pdf", oversized_data, "application/pdf")
    with pytest.raises(HTTPException) as exc_info:
        await validate_and_read_upload(upload)
    assert exc_info.value.status_code == 413
    assert exc_info.value.detail["code"] == "FILE_TOO_LARGE"
