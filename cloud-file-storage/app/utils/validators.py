from __future__ import annotations

from pathlib import PurePosixPath

from app.core.config import settings
from app.core.exceptions import APIError


_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_ALLOWED_REPORTED_TYPES = {
    ".pdf": {"application/pdf", "application/x-pdf", "application/octet-stream"},
    ".png": {"image/png", "application/octet-stream"},
    ".jpg": {"image/jpeg", "image/jpg", "application/octet-stream"},
    ".jpeg": {"image/jpeg", "image/jpg", "application/octet-stream"},
    ".txt": {"text/plain", "application/octet-stream"},
    ".csv": {"text/csv", "application/vnd.ms-excel", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
}


def sanitize_filename(filename: str | None) -> str:
    # Upload clients may send either POSIX or Windows path separators.
    name = (filename or "").replace("\\", "/").split("/")[-1].strip()
    if not name or name in {".", ".."} or len(name) > 255:
        raise APIError(400, "invalid_filename", "A valid filename is required")
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise APIError(400, "invalid_filename", "Filename contains unsupported characters")
    return name


def get_extension(filename: str) -> str:
    return PurePosixPath(filename).suffix.lower()


def is_allowed_file(filename: str) -> bool:
    return get_extension(filename) in settings.allowed_extensions


def validate_upload(filename: str | None, content_type: str | None, body: bytes) -> tuple[str, str]:
    safe_name = sanitize_filename(filename)
    extension = get_extension(safe_name)
    if extension not in settings.allowed_extensions:
        raise APIError(415, "unsupported_file_type", "This file extension is not allowed")
    if len(body) > settings.max_upload_bytes:
        raise APIError(413, "file_too_large", "File exceeds the configured upload size limit")
    reported_type = (content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    if reported_type not in _ALLOWED_REPORTED_TYPES[extension]:
        raise APIError(415, "unsupported_file_type", "File content type does not match its extension")

    # Check common binary formats so a renamed executable cannot pass based only on its suffix.
    if extension == ".pdf" and not body.startswith(b"%PDF-"):
        raise APIError(415, "invalid_file_content", "File content is not a valid PDF")
    if extension == ".png" and not body.startswith(b"\x89PNG\r\n\x1a\n"):
        raise APIError(415, "invalid_file_content", "File content is not a valid PNG image")
    if extension in {".jpg", ".jpeg"} and not body.startswith(b"\xff\xd8\xff"):
        raise APIError(415, "invalid_file_content", "File content is not a valid JPEG image")
    if extension == ".docx" and not body.startswith(b"PK\x03\x04"):
        raise APIError(415, "invalid_file_content", "File content is not a valid DOCX archive")

    return safe_name, _CONTENT_TYPES[extension]
