"""Storage service abstraction and local filesystem implementation."""

from abc import ABC, abstractmethod
import logging
import os
from pathlib import Path
from typing import BinaryIO, Union
import uuid

from app.core.config import get_settings

logger = logging.getLogger("document-intelligence-service")
settings = get_settings()


class StorageService(ABC):
    """Abstract interface defining document binary persistence operations."""

    @abstractmethod
    def save(
        self,
        file_obj: Union[BinaryIO, bytes],
        extension: str,
    ) -> tuple[str, int]:
        """Save file stream or bytes using randomized naming.

        Returns (relative_storage_path, total_bytes_written).
        """
        pass

    @abstractmethod
    def delete(self, storage_path: str) -> bool:
        """Delete file associated with relative storage path."""
        pass

    @abstractmethod
    def exists(self, storage_path: str) -> bool:
        """Check whether file exists in storage."""
        pass

    @abstractmethod
    def get_absolute_path(self, storage_path: str) -> Path:
        """Retrieve verified absolute path, preventing directory traversal."""
        pass


class LocalStorageService(StorageService):
    """Local filesystem implementation of the StorageService interface."""

    def __init__(self, base_dir: Union[str, Path, None] = None) -> None:
        raw_path = base_dir or settings.UPLOAD_DIR
        self.base_dir: Path = Path(raw_path).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, storage_path: str) -> Path:
        """Resolve path and verify it strictly resides within self.base_dir."""
        # Strip leading slashes to prevent root escapes
        clean_path = storage_path.lstrip("/\\")
        candidate = (self.base_dir / clean_path).resolve()
        if not candidate.is_relative_to(self.base_dir):
            logger.error(
                "Path traversal attempt blocked: %s (base: %s)",
                storage_path,
                self.base_dir,
            )
            raise ValueError("Invalid storage path: directory traversal detected")
        return candidate

    def save(
        self,
        file_obj: Union[BinaryIO, bytes],
        extension: str,
    ) -> tuple[str, int]:
        """Save file using a secure UUID-generated filename."""
        clean_ext = extension.lstrip(".").lower()
        unique_name = f"{uuid.uuid4().hex}.{clean_ext}"
        destination = self._resolve_safe_path(unique_name)

        bytes_written = 0
        try:
            if isinstance(file_obj, bytes):
                destination.write_bytes(file_obj)
                bytes_written = len(file_obj)
            else:
                with open(destination, "wb") as f_out:
                    while chunk := file_obj.read(1024 * 1024):  # 1MB chunks
                        f_out.write(chunk)
                        bytes_written += len(chunk)
            logger.info("Saved %d bytes to local storage: %s", bytes_written, unique_name)
            return unique_name, bytes_written
        except Exception as exc:
            # Clean up partial file on failure
            if destination.exists():
                try:
                    destination.unlink()
                except OSError:
                    pass
            logger.error("Failed to write file to local storage: %s", exc)
            raise

    def delete(self, storage_path: str) -> bool:
        """Remove file from storage if present."""
        try:
            target = self._resolve_safe_path(storage_path)
            if target.is_file():
                target.unlink()
                logger.info("Deleted file from storage: %s", storage_path)
                return True
            return False
        except Exception as exc:
            logger.error("Error deleting storage path '%s': %s", storage_path, exc)
            return False

    def exists(self, storage_path: str) -> bool:
        """Check if file exists."""
        try:
            target = self._resolve_safe_path(storage_path)
            return target.is_file()
        except ValueError:
            return False

    def get_absolute_path(self, storage_path: str) -> Path:
        """Return safe absolute Path on local filesystem."""
        target = self._resolve_safe_path(storage_path)
        if not target.is_file():
            raise FileNotFoundError(f"Storage path '{storage_path}' not found")
        return target


_storage_instance: StorageService | None = None


def get_storage_service() -> StorageService:
    """Return configured storage service singleton."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = LocalStorageService()
    return _storage_instance
