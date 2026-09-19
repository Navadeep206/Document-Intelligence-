"""Image preprocessing pipeline tailored for optical character recognition."""

import logging
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

logger = logging.getLogger("document-intelligence-service")


class PreprocessingService:
    """Provides modular, configurable image enhancement operations for OCR."""

    def preprocess_image(
        self,
        image: Image.Image,
        auto_rotate: bool = True,
        to_grayscale: bool = True,
        enhance_contrast: bool = True,
        denoise: bool = False,
    ) -> Image.Image:
        """Apply sequential non-destructive image preprocessing stages for OCR.

        Avoids aggressive binarization/thresholding by default to prevent character erosion.
        """
        processed = image.copy()

        # 1. Orientation normalization from EXIF metadata (if available)
        if auto_rotate:
            try:
                processed = ImageOps.exif_transpose(processed) or processed
            except Exception as exc:
                logger.debug("EXIF orientation transpose skipped: %s", exc)

        # 2. Grayscale conversion
        if to_grayscale and processed.mode != "L":
            processed = processed.convert("L")

        # 3. Contrast enhancement
        if enhance_contrast:
            try:
                # Autocontrast normalizes dark/light distribution across available spectrum
                processed = ImageOps.autocontrast(processed, cutoff=2)
                # Moderate contrast boost to emphasize text strokes against noisy paper
                enhancer = ImageEnhance.Contrast(processed)
                processed = enhancer.enhance(1.4)
            except Exception as exc:
                logger.debug("Contrast enhancement skipped: %s", exc)

        # 4. Optional subtle noise reduction (useful for scanned physical documents)
        if denoise:
            try:
                processed = processed.filter(ImageFilter.MedianFilter(size=3))
            except Exception as exc:
                logger.debug("Denoising filter skipped: %s", exc)

        return processed


preprocessing_service = PreprocessingService()
