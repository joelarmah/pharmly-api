import uuid
from pathlib import Path
from typing import Protocol

from app.core.config import settings

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB


class StorageError(RuntimeError):
    """Raised when a file fails validation or fails to persist."""


class FileStorage(Protocol):
    async def save_prescription_image(
        self, prescription_id: str, filename: str, content: bytes
    ) -> str:
        """Persists the file and returns a publicly reachable URL."""
        ...


class LocalFileStorage:
    """Saves files to a local directory served via a static mount.

    Fine for dev and a single-instance deploy. Swap for an S3/GCS-backed
    implementation of the same protocol (see get_file_storage) if the app
    ever needs multi-instance deploys without a shared volume.
    """

    def __init__(self, base_dir: Path, public_base_url: str) -> None:
        self._base_dir = base_dir
        self._public_base_url = public_base_url.rstrip("/")

    async def save_prescription_image(
        self, prescription_id: str, filename: str, content: bytes
    ) -> str:
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise StorageError(f"Unsupported image type: {extension or 'unknown'}")
        if len(content) > MAX_IMAGE_BYTES:
            raise StorageError("Image is too large.")

        directory = self._base_dir / "prescriptions" / prescription_id
        directory.mkdir(parents=True, exist_ok=True)

        stored_name = f"{uuid.uuid4().hex}{extension}"
        (directory / stored_name).write_bytes(content)

        return f"{self._public_base_url}/uploads/prescriptions/{prescription_id}/{stored_name}"


def get_file_storage() -> FileStorage:
    return LocalFileStorage(
        base_dir=Path(settings.local_storage_dir),
        public_base_url=settings.public_base_url,
    )
