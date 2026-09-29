"""Shared RFC822 parsing helpers for IMAP/POP3 inbound mail."""

from __future__ import annotations

import email.header
import re
from email.message import Message
from html import unescape
from pathlib import Path

from backend.app.services.received_mail_attachments import (
    is_allowed_attachment_filename,
    is_ignored_attachment_filename,
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


def normalize_body_newlines(text: str) -> str:
    """Keep line breaks for decision context; normalize to ``\\n`` only.

    Does **not** join soft-wrapped lines or collapse paragraph breaks.
    """
    if not text:
        return ""
    normalized = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u2028", "\n")  # line separator
        .replace("\u2029", "\n\n")  # paragraph separator
        .replace("\u0085", "\n")  # NEL
    )
    # Trim trailing spaces on each line, but keep the newline itself.
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    # Drop trailing whitespace at EOF only (preserve internal blank lines).
    return normalized.rstrip(" \t")


def html_to_plain_preserve_breaks(html: str) -> str:
    """Convert HTML mail bodies to plain text while preserving visual line breaks."""
    if not html:
        return ""
    text = html
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "• ", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|h[1-6]|tr|blockquote|table)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<(p|div|h[1-6]|tr|blockquote|table)(\s[^>]*)?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<hr\s*/?>", "\n---\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    return normalize_body_newlines(text)


def _decode_part_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    charset = part.get_content_charset() or "utf-8"
    if isinstance(payload, (bytes, bytearray)):
        return payload.decode(charset, errors="replace")
    if payload is None:
        raw = part.get_payload()
        return str(raw) if raw is not None else ""
    return str(payload)


def _iter_body_parts(msg: Message, content_type: str) -> list[str]:
    wanted = content_type.lower()
    parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            disposition = str(part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            if ctype != wanted:
                continue
            text = _decode_part_text(part)
            if text.strip():
                parts.append(text)
        return parts

    if (msg.get_content_type() or "").lower() == wanted:
        text = _decode_part_text(msg)
        if text.strip():
            parts.append(text)
    return parts


def extract_body_text(msg: Message) -> str:
    """Extract readable body text, preserving newlines for downstream agents."""
    plain_parts = _iter_body_parts(msg, "text/plain")
    html_parts = _iter_body_parts(msg, "text/html")

    plain = normalize_body_newlines("\n".join(plain_parts)) if plain_parts else ""
    html_plain = (
        normalize_body_newlines("\n".join(html_to_plain_preserve_breaks(p) for p in html_parts))
        if html_parts
        else ""
    )

    if plain and "\n" in plain.rstrip("\n"):
        return plain
    if html_plain and "\n" in html_plain.rstrip("\n"):
        # Prefer HTML-derived text when plain collapsed line breaks (common in some MUAs).
        if not plain or plain.count("\n") < html_plain.count("\n"):
            return html_plain
    if plain:
        return plain
    return html_plain


def iter_attachments(msg: Message) -> list[tuple[str, bytes]]:
    allowed, _unreadable = collect_mail_attachments(msg)
    return allowed


def collect_mail_attachments(msg: Message) -> tuple[list[tuple[str, bytes]], list[str]]:
    """Return (text attachments to save, other non-ignored unreadable names).

    Office documents and image files are skipped entirely (not saved, not listed).
    """
    allowed: list[tuple[str, bytes]] = []
    unreadable: list[str] = []
    for part in msg.walk():
        disposition = str(part.get("Content-Disposition") or "")
        filename = part.get_filename()
        decoded_name = decode_header_value(filename) if filename else ""
        content_type = (part.get_content_type() or "").lower()
        is_attachment = "attachment" in disposition.lower() or bool(decoded_name)
        if not is_attachment or not decoded_name:
            continue
        if is_ignored_attachment_filename(decoded_name) or content_type.startswith("image/"):
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
