"""Image file loading, validation, and color-space normalization service."""

import logging
from pathlib import Path
from PIL import Image

logger = logging.getLogger("document-intelligence-service")


class ImageService:
    """Safely loads and validates raster image files for OCR processing."""

    def load_image(self, file_path: str | Path) -> Image.Image:
        """Load image into memory, normalize mode, and ensure file descriptor is safely released."""
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Image file not found at '{path}'")

        try:
            with Image.open(path) as img:
                # Load pixel data into memory
                img.load()
                # Create memory copy so file handle can close safely
                image_copy = img.copy()

            # Normalize RGBA (PNG with transparency) or CMYK to RGB
            if image_copy.mode in ("RGBA", "LA", "P"):
                # Fill transparent pixels with white background for OCR
                background = Image.new("RGB", image_copy.size, (255, 255, 255))
                if image_copy.mode == "P":
                    image_copy = image_copy.convert("RGBA")
                background.paste(image_copy, mask=image_copy.split()[-1] if "A" in image_copy.mode else None)
                image_copy = background
            elif image_copy.mode not in ("RGB", "L"):
                image_copy = image_copy.convert("RGB")

            logger.info("Image loaded successfully from '%s' (%dx%d, mode=%s)", path.name, image_copy.width, image_copy.height, image_copy.mode)
            return image_copy

        except Exception as exc:
            logger.error("Failed to load image file '%s': %s", path, exc)
            raise ValueError(f"Unreadable or corrupt image file: {exc}") from exc


image_service = ImageService()
