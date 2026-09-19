"""Document inspection and structural analysis service."""

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from PIL import Image

from app.core.config import get_settings

logger = logging.getLogger("document-intelligence-service")
settings = get_settings()


class DocumentInspectionError(Exception):
    """Base exception for document inspection failures."""


class CorruptDocumentError(DocumentInspectionError):
    """Raised when a document is corrupted, malformed, or unreadable."""


class UnreadableDocumentError(DocumentInspectionError):
    """Raised when a document cannot be accessed or is password protected."""


@dataclass
class PageInspectionDetail:
    """Detailed structural metrics for an individual document page."""

    page_number: int
    width: float
    height: float
    rotation: int
    has_digital_text: bool
    char_count: int


@dataclass
class DocumentInspectionReport:
    """Comprehensive inspection report for an ingested document."""

    file_path: Path
    format: str
    page_count: int
    has_digital_text: bool
    is_scanned: bool
    pages: list[PageInspectionDetail] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentInspector:
    """Analyzes and validates document integrity, page counts, and text selectability."""

    def inspect(self, file_path: str | Path) -> DocumentInspectionReport:
        """Inspect document file and return structural characteristics."""
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Document file not found at '{path}'")

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self._inspect_pdf(path)
        elif suffix in [".jpg", ".jpeg", ".png"]:
            return self._inspect_image(path)
        else:
            raise UnreadableDocumentError(f"Unsupported document format: '{suffix}'")

    def _inspect_pdf(self, path: Path) -> DocumentInspectionReport:
        """Inspect PDF file using PyMuPDF."""
        try:
            doc = fitz.open(path)
        except Exception as exc:
            logger.error("Failed to open PDF '%s': %s", path, exc)
            raise CorruptDocumentError(f"Cannot open PDF document: {exc}") from exc

        try:
            if doc.is_encrypted:
                raise UnreadableDocumentError("Encrypted or password-protected PDFs are not supported")

            page_count = doc.page_count
            if page_count == 0:
                raise CorruptDocumentError("PDF document has 0 pages")

            pages_detail: list[PageInspectionDetail] = []
            digital_text_pages = 0

            for page_idx in range(page_count):
                page = doc.load_page(page_idx)
                rect = page.rect
                raw_text = page.get_text("text") or ""
                char_count = len(raw_text.strip())

                has_digital_text = char_count >= settings.MIN_NATIVE_TEXT_CHARS
                if has_digital_text:
                    digital_text_pages += 1

                pages_detail.append(
                    PageInspectionDetail(
                        page_number=page_idx + 1,
                        width=rect.width,
                        height=rect.height,
                        rotation=page.rotation,
                        has_digital_text=has_digital_text,
                        char_count=char_count,
                    )
                )

            # Document is considered digital if at least one page contains substantial selectable text
            has_digital_text = digital_text_pages > 0
            is_scanned = digital_text_pages == 0

            logger.info(
                "PDF inspected '%s': %d pages, %d with native text (is_scanned=%s)",
                path.name,
                page_count,
                digital_text_pages,
                is_scanned,
            )

            return DocumentInspectionReport(
                file_path=path,
                format="PDF",
                page_count=page_count,
                has_digital_text=has_digital_text,
                is_scanned=is_scanned,
                pages=pages_detail,
                metadata={
                    "title": doc.metadata.get("title", ""),
                    "author": doc.metadata.get("author", ""),
                    "digital_text_pages": digital_text_pages,
                },
            )
        finally:
            doc.close()

    def _inspect_image(self, path: Path) -> DocumentInspectionReport:
        """Inspect image file using Pillow."""
        try:
            with Image.open(path) as img:
                img.verify()

            # Re-open for reading metadata (verify() corrupts handle for some operations)
            with Image.open(path) as img:
                width, height = img.size
                img_format = img.format or path.suffix.upper().lstrip(".")
                img_mode = img.mode

            page_detail = PageInspectionDetail(
                page_number=1,
                width=float(width),
                height=float(height),
                rotation=0,
                has_digital_text=False,
                char_count=0,
            )

            logger.info(
                "Image inspected '%s': format=%s, dimensions=%dx%d, mode=%s",
                path.name,
                img_format,
                width,
                height,
                img_mode,
            )

            return DocumentInspectionReport(
                file_path=path,
                format=img_format,
                page_count=1,
                has_digital_text=False,
                is_scanned=True,
                pages=[page_detail],
                metadata={
                    "mode": img_mode,
                    "dimensions": (width, height),
                },
            )
        except Exception as exc:
            logger.error("Failed to inspect image '%s': %s", path, exc)
            raise CorruptDocumentError(f"Corrupted or invalid image file: {exc}") from exc


document_inspector = DocumentInspector()
