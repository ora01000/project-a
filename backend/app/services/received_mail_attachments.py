"""Attachment path helpers and allowlist for received mail."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from backend.app.config import load_received_mail_settings

logger = logging.getLogger(__name__)

ATTACHMENT_TEXT_MAX_CHARS = 20_000

# Text-readable attachments only. Office/images are ignored (not stored, not decided on).
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
        ".csv",
        ".md",
        ".json",
        ".yaml",
        ".yml",
        ".xml",
        ".ini",
        ".toml",
        ".properties",
    }
)

OFFICE_ATTACHMENT_EXTENSIONS = frozenset(
    {
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".odt",
        ".ods",
        ".odp",
        ".hwp",
        ".hwpx",
    }
)

IMAGE_ATTACHMENT_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".webp",
        ".tif",
        ".tiff",
        ".svg",
        ".ico",
        ".heic",
        ".heif",
    }
)

_UNSAFE_NAME = re.compile(r"[^\w.\-()+@]+", re.UNICODE)


def is_allowed_attachment_filename(filename: str) -> bool:
    name = Path(filename or "").name.strip()
    if not name or name in {".", ".."}:
        return False
    suffix = Path(name).suffix.lower()
    return suffix in ALLOWED_ATTACHMENT_EXTENSIONS


def is_office_attachment_filename(filename: str) -> bool:
    suffix = Path(filename or "").suffix.lower()
    return suffix in OFFICE_ATTACHMENT_EXTENSIONS


def is_image_attachment_filename(filename: str) -> bool:
    suffix = Path(filename or "").suffix.lower()
    return suffix in IMAGE_ATTACHMENT_EXTENSIONS


def is_ignored_attachment_filename(filename: str) -> bool:
    """Office docs and images: do not store and do not feed into job_decision."""
    return is_office_attachment_filename(filename) or is_image_attachment_filename(filename)


def is_unreadable_attachment_filename(filename: str) -> bool:
    if is_ignored_attachment_filename(filename):
        return False
    return not is_allowed_attachment_filename(filename)


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


def read_text_attachment_content(
    mail_uuid: str,
    filename: str,
    *,
    max_chars: int = ATTACHMENT_TEXT_MAX_CHARS,
    home: Path | None = None,
) -> str:
    path = resolve_attachment_file(mail_uuid, filename, home=home)
    if not path.is_file():
        return f"[missing attachment file: {filename}]"
    text = path.read_bytes().decode("utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[truncated]..."
    return text


def load_received_mail_text_attachments(
    mail_uuid: str,
    attachment_names: list[str] | None,
    *,
    max_chars: int = ATTACHMENT_TEXT_MAX_CHARS,
    home: Path | None = None,
) -> list[tuple[str, str]]:
    """Return (filename, content) for allowed text attachments of a received_mail."""
    loaded: list[tuple[str, str]] = []
    for name in attachment_names or []:
        filename = (name or "").strip()
        if not filename or not is_allowed_attachment_filename(filename):
            continue
        try:
            loaded.append(
                (
                    filename,
                    read_text_attachment_content(
                        mail_uuid,
                        filename,
                        max_chars=max_chars,
                        home=home,
                    ),
                )
            )
        except Exception as exc:
            logger.warning(
                "failed to read received_mail attachment uuid=%s file=%s: %s",
                mail_uuid,
                filename,
                exc,
            )
            loaded.append((filename, f"[failed to read {filename}: {exc}]"))
    return loaded


def format_text_attachments_for_prompt(attachments: list[tuple[str, str]]) -> str:
    if not attachments:
        return ""
    parts = ["=== attachments (text) ==="]
    for name, content in attachments:
        parts.append(f"--- file: {name} ---")
        parts.append(content)
        parts.append("")
    return "\n".join(parts).rstrip()
