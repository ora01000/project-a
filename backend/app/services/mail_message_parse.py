"""Shared RFC822 parsing helpers for IMAP/POP3 inbound mail."""

from __future__ import annotations

import email.header
from email.message import Message
from pathlib import Path

from backend.app.services.received_mail_attachments import (
    is_allowed_attachment_filename,
    sanitize_attachment_filename,
)


def decode_header_value(raw: str | None) -> str:
    if not raw:
        return ""
    parts: list[str] = []
    for chunk, charset in email.header.decode_header(raw):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(str(chunk))
    return " ".join(parts).strip()


def address_list(msg: Message, header: str) -> str:
    values = msg.get_all(header, [])
    if not values:
        return ""
    joined = ", ".join(str(value) for value in values)
    return decode_header_value(joined)


def extract_body_text(msg: Message) -> str:
    if msg.is_multipart():
        plain_parts: list[str] = []
        for part in msg.walk():
            content_type = (part.get_content_type() or "").lower()
            disposition = str(part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            if content_type != "text/plain":
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            plain_parts.append(payload.decode(charset, errors="replace"))
        if plain_parts:
            return "\n".join(plain_parts).strip()
        return ""

    if (msg.get_content_type() or "").lower() == "text/plain":
        payload = msg.get_payload(decode=True)
        if payload is None:
            return str(msg.get_payload() or "")
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace").strip()
    return ""


def iter_attachments(msg: Message) -> list[tuple[str, bytes]]:
    allowed, _unreadable = collect_mail_attachments(msg)
    return allowed


def collect_mail_attachments(msg: Message) -> tuple[list[tuple[str, bytes]], list[str]]:
    """Return (text attachments to save, unreadable/office attachment names)."""
    allowed: list[tuple[str, bytes]] = []
    unreadable: list[str] = []
    for part in msg.walk():
        disposition = str(part.get("Content-Disposition") or "")
        filename = part.get_filename()
        decoded_name = decode_header_value(filename) if filename else ""
        is_attachment = "attachment" in disposition.lower() or bool(decoded_name)
        if not is_attachment or not decoded_name:
            continue
        if not is_allowed_attachment_filename(decoded_name):
            unreadable.append(sanitize_attachment_filename(decoded_name))
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, (bytes, bytearray)):
            unreadable.append(sanitize_attachment_filename(decoded_name))
            continue
        allowed.append((sanitize_attachment_filename(decoded_name), bytes(payload)))
    return allowed, unreadable


def save_attachments(mail_uuid: str, attachments: list[tuple[str, bytes]], home: Path) -> list[str]:
    from backend.app.services.received_mail_attachments import ensure_attachment_dir

    if not attachments:
        return []
    directory = ensure_attachment_dir(mail_uuid, home=home)
    saved: list[str] = []
    used_names: set[str] = set()
    for filename, payload in attachments:
        name = filename
        if name in used_names:
            stem = Path(name).stem
            suffix = Path(name).suffix
            index = 2
            while f"{stem}_{index}{suffix}" in used_names:
                index += 1
            name = f"{stem}_{index}{suffix}"
        used_names.add(name)
        (directory / name).write_bytes(payload)
        saved.append(name)
    return saved
