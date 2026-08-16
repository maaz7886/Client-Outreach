"""Safe attachment storage: allowlisted extensions, UUID filenames, size caps."""

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import get_settings

ALLOWED_EXTENSIONS: dict[str, str] = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "txt": "text/plain",
    "zip": "application/zip",
    "rar": "application/vnd.rar",
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "webp": "image/webp",
}


def _storage_root() -> Path:
    root = Path(get_settings().attachment_storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _safe_original_name(name: str) -> str:
    cleaned = Path(name).name.strip()
    if not cleaned or cleaned in {".", ".."}:
        raise HTTPException(422, "Invalid filename")
    return cleaned[:255]


def extension_for(filename: str) -> str:
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(422, f"File type .{ext or '?'} not allowed. Allowed: {allowed}")
    return ext


async def read_upload(upload: UploadFile) -> tuple[bytes, str, str, str]:
    """Validate upload and return (content, original_filename, stored_filename, mime_type)."""
    if not upload.filename:
        raise HTTPException(422, "Missing filename")
    original = _safe_original_name(upload.filename)
    ext = extension_for(original)
    content = await upload.read()
    max_size = get_settings().max_attachment_size_bytes
    if len(content) > max_size:
        raise HTTPException(
            422,
            f"File too large ({len(content)} bytes). Max: {max_size} bytes.",
        )
    if not content:
        raise HTTPException(422, "Empty file")
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    return content, original, stored_name, ALLOWED_EXTENSIONS[ext]


def save_bytes(content: bytes, stored_filename: str) -> str:
    """Write file to storage; return relative storage_path."""
    dest = _storage_root() / stored_filename
    dest.write_bytes(content)
    return stored_filename


def read_bytes(storage_path: str) -> bytes:
    path = (_storage_root() / storage_path).resolve()
    root = _storage_root()
    if not str(path).startswith(str(root)):
        raise ValueError("Invalid storage path")
    return path.read_bytes()


def delete_file(storage_path: str) -> None:
    path = (_storage_root() / storage_path).resolve()
    root = _storage_root()
    if str(path).startswith(str(root)) and path.is_file():
        path.unlink(missing_ok=True)
