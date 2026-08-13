"""Attachment path helpers and allowlist for received mail."""

from __future__ import annotations

import re
from pathlib import Path

from backend.app.config import load_received_mail_settings

# Text-readable attachments only (certificates / scripts / logs).
ALLOWED_ATTACHMENT_EXTENSIONS = frozenset(
    {
        ".crt",
        ".cer",
        ".csr",
        ".key",
        ".pem",
        ".sh",
        ".bash",
        ".txt",
        ".log",
        ".conf",
        ".cfg",
    }
)

_UNSAFE_NAME = re.compile(r"[^\w.\-()+@]+", re.UNICODE)


def is_allowed_attachment_filename(filename: str) -> bool:
    name = Path(filename or "").name.strip()
    if not name or name in {".", ".."}:
        return False
    suffix = Path(name).suffix.lower()
    return suffix in ALLOWED_ATTACHMENT_EXTENSIONS


def sanitize_attachment_filename(filename: str) -> str:
    raw = Path(filename or "").name.strip() or "attachment.bin"
    cleaned = _UNSAFE_NAME.sub("_", raw).strip("._") or "attachment.bin"
    return cleaned[:180]


def received_mail_attachment_dir(mail_uuid: str, *, home: Path | None = None) -> Path:
    settings = load_received_mail_settings()
    root = Path(home) if home is not None else settings.attachment_home
    safe_uuid = mail_uuid.strip()
    if not safe_uuid or "/" in safe_uuid or "\\" in safe_uuid or ".." in safe_uuid:
        raise ValueError("invalid received_mail uuid")
    return root / safe_uuid


def ensure_attachment_dir(mail_uuid: str, *, home: Path | None = None) -> Path:
    path = received_mail_attachment_dir(mail_uuid, home=home)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_attachment_file(
    mail_uuid: str,
    filename: str,
    *,
    home: Path | None = None,
) -> Path:
    directory = received_mail_attachment_dir(mail_uuid, home=home)
    safe_name = sanitize_attachment_filename(filename)
    target = (directory / safe_name).resolve()
    if not str(target).startswith(str(directory.resolve())):
        raise ValueError("invalid attachment path")
    return target
