"""Document upload validation: extension, MIME type, file size, and header signature checks."""

from pathlib import Path
from typing import Tuple

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings
from app.db.models.enums import DocumentType

settings = get_settings()

SUPPORTED_EXTENSIONS = {
    ".pdf": DocumentType.PDF,
    ".jpg": DocumentType.JPG,
    ".jpeg": DocumentType.JPEG,
    ".png": DocumentType.PNG,
}

SUPPORTED_MIME_TYPES = {
    "application/pdf": DocumentType.PDF,
    "image/jpeg": DocumentType.JPEG,
    "image/jpg": DocumentType.JPG,
    "image/png": DocumentType.PNG,
}

# Magic byte signatures for file integrity inspection
FILE_SIGNATURES = {
    DocumentType.PDF: [b"%PDF-"],
    DocumentType.PNG: [b"\x89PNG\r\n\x1a\n"],
    DocumentType.JPG: [b"\xff\xd8\xff"],
    DocumentType.JPEG: [b"\xff\xd8\xff"],
}


async def validate_and_read_upload(
    upload_file: UploadFile,
) -> Tuple[DocumentType, str, str, bytes, int]:
    """Validate upload extension, MIME type, size limit, and magic bytes.

    Returns: (document_type, clean_filename, mime_type, header_bytes, total_size)
    """
    if not upload_file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "MISSING_FILENAME",
                "message": "Filename was not provided in upload request",
            },
        )

    # Sanitize and extract extension
    filename = Path(upload_file.filename).name
    ext = Path(filename).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_FILE_TYPE",
                "message": "Only PDF, JPG, JPEG and PNG files are supported",
            },
        )

    expected_doc_type = SUPPORTED_EXTENSIONS[ext]

    # Normalize MIME type
    raw_content_type = (upload_file.content_type or "").lower().strip()
    if raw_content_type not in SUPPORTED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_FILE_TYPE",
                "message": f"Unsupported MIME type '{raw_content_type}'. Expected PDF or JPEG/PNG image.",
            },
        )

    mime_doc_type = SUPPORTED_MIME_TYPES[raw_content_type]
    # Allow JPG and JPEG interchangeable compatibility
    jpg_types = {DocumentType.JPG, DocumentType.JPEG}
    if expected_doc_type != mime_doc_type and not (
        expected_doc_type in jpg_types and mime_doc_type in jpg_types
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "MIME_EXTENSION_MISMATCH",
                "message": f"File extension '{ext}' does not match Content-Type '{raw_content_type}'",
            },
        )

    # Read and inspect magic bytes signature
    header = await upload_file.read(16)
    if not header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "EMPTY_FILE",
                "message": "Uploaded file is empty (0 bytes)",
            },
        )

    valid_signatures = FILE_SIGNATURES[expected_doc_type]
    matches_signature = any(header.startswith(sig) for sig in valid_signatures)
    if not matches_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_FILE_CONTENT",
                "message": f"File header does not match expected {expected_doc_type.value} format signature",
            },
        )

    # Validate size limit via chunked reading
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    total_size = len(header)

    chunks: list[bytes] = [header]
    while chunk := await upload_file.read(1024 * 1024):  # 1MB chunks
        total_size += len(chunk)
        if total_size > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "code": "FILE_TOO_LARGE",
                    "message": f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB",
                },
            )
        chunks.append(chunk)

    full_content = b"".join(chunks)

    # Reset file pointer for any downstream callers
    await upload_file.seek(0)

    # Standardize MIME type string
    mime_map = {
        DocumentType.PDF: "application/pdf",
        DocumentType.JPG: "image/jpeg",
        DocumentType.JPEG: "image/jpeg",
        DocumentType.PNG: "image/png",
    }
    canonical_mime = mime_map[expected_doc_type]

    return expected_doc_type, filename, canonical_mime, full_content, total_size
