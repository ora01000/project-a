"""Fetch unread IMAP messages into received_mail (+ allowed attachments)."""

from __future__ import annotations

import email
import email.policy
import imaplib
import logging
import uuid
from pathlib import Path

from backend.app.config import ReceivedMailSettings, load_received_mail_settings
from backend.app.db.mailserver_config import get_mailserver_config
from backend.app.db.received_mail import insert_received_mail, message_already_stored
from backend.app.services.mail_message_parse import (
    address_list,
    decode_header_value,
    extract_body_text,
    iter_attachments,
    save_attachments,
)

logger = logging.getLogger(__name__)

MAILBOX = "INBOX"


def _connect_imap(host: str, port: int, *, use_ssl: bool, timeout: float) -> imaplib.IMAP4:
    if use_ssl:
        return imaplib.IMAP4_SSL(host, port, timeout=timeout)
    return imaplib.IMAP4(host, port, timeout=timeout)


def poll_imap_once(
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
            attachments = iter_attachments(msg)
            saved_names = save_attachments(
                mail_uuid,
                attachments,
                poll_settings.attachment_home,
            )
            insert_received_mail(
                database_path,
                message_id=message_id,
                imap_uid=imap_uid,
                mailbox=MAILBOX,
                subject=decode_header_value(msg.get("Subject")),
                from_address=address_list(msg, "From"),
                to_addresses=address_list(msg, "To"),
                cc_addresses=address_list(msg, "Cc"),
                body_text=extract_body_text(msg),
                received_at=decode_header_value(msg.get("Date")),
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
