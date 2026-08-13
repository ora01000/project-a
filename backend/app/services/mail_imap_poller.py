"""Fetch unread IMAP messages into received_mail (+ allowed attachments)."""

from __future__ import annotations

import email
import email.header
import email.policy
import imaplib
import logging
import uuid
from email.message import Message
from pathlib import Path

from backend.app.config import ReceivedMailSettings, load_received_mail_settings
from backend.app.db.mailserver_config import get_mailserver_config
from backend.app.db.received_mail import insert_received_mail, message_already_stored
from backend.app.services.received_mail_attachments import (
    ensure_attachment_dir,
    is_allowed_attachment_filename,
    sanitize_attachment_filename,
)

logger = logging.getLogger(__name__)

MAILBOX = "INBOX"


def _decode_header_value(raw: str | None) -> str:
    if not raw:
        return ""
    parts: list[str] = []
    for chunk, charset in email.header.decode_header(raw):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(str(chunk))
    return " ".join(parts).strip()


def _address_list(msg: Message, header: str) -> str:
    values = msg.get_all(header, [])
    if not values:
        return ""
    joined = ", ".join(str(value) for value in values)
    return _decode_header_value(joined)


def _extract_body_text(msg: Message) -> str:
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


def _iter_attachments(msg: Message) -> list[tuple[str, bytes]]:
    attachments: list[tuple[str, bytes]] = []
    for part in msg.walk():
        disposition = str(part.get("Content-Disposition") or "")
        filename = part.get_filename()
        decoded_name = _decode_header_value(filename) if filename else ""
        is_attachment = "attachment" in disposition.lower() or bool(decoded_name)
        if not is_attachment:
            continue
        if not decoded_name:
            continue
        if not is_allowed_attachment_filename(decoded_name):
            logger.info("skip unsupported attachment name=%s", decoded_name)
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, (bytes, bytearray)):
            continue
        attachments.append((sanitize_attachment_filename(decoded_name), bytes(payload)))
    return attachments


def _save_attachments(mail_uuid: str, attachments: list[tuple[str, bytes]], home: Path) -> list[str]:
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


def _connect_imap(host: str, port: int, *, use_ssl: bool, timeout: float) -> imaplib.IMAP4:
    if use_ssl:
        return imaplib.IMAP4_SSL(host, port, timeout=timeout)
    return imaplib.IMAP4(host, port, timeout=timeout)


def poll_received_mail_once(
    database_path: Path,
    settings: ReceivedMailSettings | None = None,
) -> int:
    """Fetch UNSEEN messages. Returns number of newly stored mails."""
    poll_settings = settings or load_received_mail_settings()
    config = get_mailserver_config(database_path)
    if config is None or not config.receive_enabled:
        return 0
    if not config.imap_host.strip() or not config.smtp_username.strip():
        logger.warning("mail receive enabled but IMAP host/username missing")
        return 0

    timeout = float(config.timeout_seconds or 30.0)
    client = _connect_imap(
        config.imap_host.strip(),
        int(config.imap_port or 993),
        use_ssl=bool(config.imap_use_ssl),
        timeout=timeout,
    )
    stored = 0
    try:
        client.login(config.smtp_username, config.smtp_password)
        status, _ = client.select(MAILBOX, readonly=False)
        if status != "OK":
            logger.warning("IMAP select %s failed: %s", MAILBOX, status)
            return 0

        status, data = client.uid("search", None, "UNSEEN")
        if status != "OK" or not data or not data[0]:
            return 0

        uids = [token for token in data[0].split() if token]
        for uid_bytes in uids:
            try:
                imap_uid = int(uid_bytes.decode("ascii"))
            except (ValueError, UnicodeDecodeError):
                continue

            status, fetched = client.uid("fetch", uid_bytes, "(RFC822)")
            if status != "OK" or not fetched:
                continue
            raw_bytes: bytes | None = None
            for item in fetched:
                if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                    raw_bytes = bytes(item[1])
                    break
            if raw_bytes is None:
                continue

            msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)
            message_id = (msg.get("Message-ID") or msg.get("Message-Id") or "").strip()
            if message_already_stored(
                database_path,
                message_id=message_id,
                mailbox=MAILBOX,
                imap_uid=imap_uid,
            ):
                client.uid("store", uid_bytes, "+FLAGS", "(\\Seen)")
                continue

            mail_uuid = str(uuid.uuid4())
            attachments = _iter_attachments(msg)
            saved_names = _save_attachments(
                mail_uuid,
                attachments,
                poll_settings.attachment_home,
            )
            insert_received_mail(
                database_path,
                message_id=message_id,
                imap_uid=imap_uid,
                mailbox=MAILBOX,
                subject=_decode_header_value(msg.get("Subject")),
                from_address=_address_list(msg, "From"),
                to_addresses=_address_list(msg, "To"),
                cc_addresses=_address_list(msg, "Cc"),
                body_text=_extract_body_text(msg),
                received_at=_decode_header_value(msg.get("Date")),
                attachment_names=saved_names,
                mail_uuid=mail_uuid,
            )
            client.uid("store", uid_bytes, "+FLAGS", "(\\Seen)")
            stored += 1
            logger.info(
                "stored received_mail uuid=%s uid=%s attachments=%s",
                mail_uuid,
                imap_uid,
                len(saved_names),
            )
    finally:
        try:
            client.logout()
        except Exception:
            pass

    return stored
