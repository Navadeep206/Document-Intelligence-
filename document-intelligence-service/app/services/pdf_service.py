"""PyMuPDF digital text extraction and high-resolution page rendering service."""

import io
import logging
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image

from app.core.config import get_settings

logger = logging.getLogger("document-intelligence-service")
settings = get_settings()


class PDFService:
    """Provides native digital text extraction and memory-safe page rendering."""

    def extract_native_text(self, page: fitz.Page, min_chars: Optional[int] = None) -> tuple[str, bool]:
        """Extract native selectable text from a PDF page and determine if content is sufficient.

        Uses an engineering heuristic considering:
        - Character count compared to threshold (MIN_NATIVE_TEXT_CHARS, default 20)
        - Alphanumeric character presence to reject scanned pages with invisible noisy OCR layers.
        """
        threshold = min_chars if min_chars is not None else settings.MIN_NATIVE_TEXT_CHARS
        raw_text = page.get_text("text") or ""
        stripped_text = raw_text.strip()

        char_count = len(stripped_text)
        alphanumeric_count = sum(1 for ch in stripped_text if ch.isalnum())

        # Heuristic: must exceed character threshold AND have meaningful alphanumeric density
        is_sufficient = (
            char_count >= threshold
            and (alphanumeric_count / max(1, char_count)) >= 0.25
        )

        logger.debug(
            "Page %d native text probe: chars=%d, alnum=%d, sufficient=%s",
            page.number + 1,
            char_count,
            alphanumeric_count,
            is_sufficient,
        )

        return raw_text, is_sufficient

    def render_page_to_image(self, page: fitz.Page, dpi: Optional[int] = None) -> Image.Image:
        """Render a PDF page to an in-memory PIL Image at configured DPI without disk persistence."""
        target_dpi = dpi or settings.OCR_DPI
        pix = page.get_pixmap(dpi=target_dpi)
        try:
            img_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_bytes))
            image.load()  # Load image data into memory before closing buffer
            return image
        finally:
            del pix  # Explicitly release C-level pixmap memory buffer


pdf_service = PDFService()
