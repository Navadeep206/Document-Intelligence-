"""Tesseract OCR integration service with word-level confidence aggregation."""

from dataclasses import dataclass, field
import logging
from typing import Any, Optional

from PIL import Image
import pytesseract

from app.core.config import get_settings

logger = logging.getLogger("document-intelligence-service")
settings = get_settings()


@dataclass
class OCRResult:
    """Encapsulates text extraction output, aggregated confidence, and telemetry from OCR."""

    text: str
    confidence: Optional[float]  # 0.0 to 1.0
    language: str
    rotation: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class OCRService:
    """Executes optical character recognition with confidence scoring and orientation detection."""

    def __init__(self, tesseract_cmd: Optional[str] = None, default_lang: Optional[str] = None):
        self.tesseract_cmd = tesseract_cmd or settings.TESSERACT_CMD
        self.default_lang = default_lang or settings.OCR_LANGUAGE
        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

    def detect_orientation(self, image: Image.Image) -> int:
        """Attempt to detect page rotation angle (0, 90, 180, 270) via Tesseract OSD."""
        try:
            osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
            rotation = int(osd.get("rotate", 0))
            if rotation in [0, 90, 180, 270]:
                return rotation
            return 0
        except Exception as exc:
            # OSD often fails on sparse or low-text pages; fallback to 0 degrees
            logger.debug("Tesseract orientation detection skipped or inconclusive: %s", exc)
            return 0

    def extract_text(self, image: Image.Image, lang: Optional[str] = None) -> OCRResult:
        """Extract text from image and compute aggregated page-level confidence."""
        language = lang or self.default_lang

        # 1. Orientation check
        detected_rotation = self.detect_orientation(image)
        working_image = image
        if detected_rotation in [90, 180, 270]:
            # Rotate image to correct orientation for text reading
            working_image = image.rotate(-detected_rotation, expand=True)
            logger.info("Image corrected by %d degrees for OCR processing", detected_rotation)

        try:
            # 2. Extract structural text
            extracted_text = pytesseract.image_to_string(working_image, lang=language)

            # 3. Extract word-level bounding boxes and confidence scores
            data = pytesseract.image_to_data(working_image, lang=language, output_type=pytesseract.Output.DICT)

            valid_confidences: list[float] = []
            word_count = 0

            texts = data.get("text", [])
            confs = data.get("conf", [])

            for w_text, w_conf in zip(texts, confs):
                word = str(w_text).strip()
                if not word:
                    continue
                word_count += 1
                try:
                    conf_val = float(w_conf)
                    # Tesseract assigns -1 for whitespace, non-text, or structural elements
                    if conf_val >= 0.0:
                        valid_confidences.append(conf_val)
                except (ValueError, TypeError):
                    continue

            # 4. Calculate aggregated page-level confidence (0.0 to 1.0)
            if valid_confidences:
                mean_conf = sum(valid_confidences) / len(valid_confidences)
                # Tesseract conf is 0–100 -> scale to 0.0–1.0
                page_confidence = round(max(0.0, min(1.0, mean_conf / 100.0)), 4)
            elif word_count > 0:
                page_confidence = 0.0
            else:
                page_confidence = 0.0

            logger.info(
                "OCR extracted: words=%d, valid_conf_words=%d, page_confidence=%.4f, rot=%d",
                word_count,
                len(valid_confidences),
                page_confidence,
                detected_rotation,
            )

            return OCRResult(
                text=extracted_text,
                confidence=page_confidence,
                language=language,
                rotation=detected_rotation,
                metadata={
                    "total_words": word_count,
                    "measured_words": len(valid_confidences),
                    "rotation": detected_rotation,
                },
            )

        except pytesseract.TesseractNotFoundError as exc:
            logger.error("Tesseract executable not found at '%s': %s", self.tesseract_cmd, exc)
            raise RuntimeError(f"Tesseract executable '{self.tesseract_cmd}' not found") from exc
        except Exception as exc:
            logger.error("OCR extraction failed: %s", exc)
            raise RuntimeError(f"OCR processing failed: {exc}") from exc


ocr_service = OCRService()
