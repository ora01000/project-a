"""Fetch POP3 messages into received_mail (+ allowed attachments)."""

from __future__ import annotations

import email
import email.policy
import logging
import poplib
import uuid
from pathlib import Path

from backend.app.config import ReceivedMailSettings, load_received_mail_settings
from backend.app.db.mailserver_config import get_mailserver_config
from backend.app.db.received_mail import insert_received_mail, message_already_stored
from backend.app.services.mail_message_parse import (
    address_list,
    collect_mail_attachments,
    decode_header_value,
    extract_body_text,
    save_attachments,
)

logger = logging.getLogger(__name__)

MAILBOX = "POP3"


def _connect_pop3(host: str, port: int, *, use_ssl: bool, timeout: float) -> poplib.POP3:
    if use_ssl:
        return poplib.POP3_SSL(host, port, timeout=timeout)
    return poplib.POP3(host, port, timeout=timeout)


def _parse_uidl_entries(response: list[bytes | str]) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    for line in response:
        if isinstance(line, bytes):
            text = line.decode("ascii", errors="replace").strip()
        else:
            text = str(line).strip()
        if not text:
            continue
        parts = text.split(None, 1)
        if len(parts) != 2:
            continue
        try:
            msg_num = int(parts[0])
        except ValueError:
            continue
        uidl = parts[1].strip()
        if uidl:
            entries.append((msg_num, uidl))
    return entries


def poll_pop3_once(
    database_path: Path,
    settings: ReceivedMailSettings | None = None,
) -> int:
    """Fetch POP3 messages not yet stored. Returns number of newly stored mails."""
    poll_settings = settings or load_received_mail_settings()
    config = get_mailserver_config(database_path)
    if config is None or not config.receive_enabled:
        return 0
    if not config.pop3_host.strip() or not config.smtp_username.strip():
        logger.warning("mail receive enabled but POP3 host/username missing")
        return 0

    timeout = float(config.timeout_seconds or 30.0)
    client = _connect_pop3(
        config.pop3_host.strip(),
        int(config.pop3_port or 995),
        use_ssl=bool(config.pop3_use_ssl),
        timeout=timeout,
    )
    stored = 0
    try:
        client.user(config.smtp_username)
        client.pass_(config.smtp_password)

        _, uidl_lines, _ = client.uidl()
        uidl_entries = _parse_uidl_entries(uidl_lines)
        if not uidl_entries:
            return 0

        for msg_num, pop3_uidl in uidl_entries:
            if message_already_stored(
                database_path,
                message_id="",
                mailbox=MAILBOX,
                imap_uid=None,
                pop3_uidl=pop3_uidl,
            ):
                continue

            _, retr_lines, octets = client.retr(msg_num)
            if not retr_lines:
                continue
            raw_bytes = b"\r\n".join(
                line if isinstance(line, bytes) else line.encode("ascii", errors="replace")
                for line in retr_lines
            )
            msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)
            message_id = (msg.get("Message-ID") or msg.get("Message-Id") or "").strip()
            if message_already_stored(
                database_path,
                message_id=message_id,
                mailbox=MAILBOX,
                imap_uid=None,
                pop3_uidl=pop3_uidl,
            ):
                continue

            mail_uuid = str(uuid.uuid4())
            attachments, unreadable_names = collect_mail_attachments(msg)
            saved_names = save_attachments(
                mail_uuid,
                attachments,
                poll_settings.attachment_home,
            )
            insert_received_mail(
                database_path,
                message_id=message_id,
                imap_uid=None,
                pop3_uidl=pop3_uidl,
                mailbox=MAILBOX,
                subject=decode_header_value(msg.get("Subject")),
                from_address=address_list(msg, "From"),
                to_addresses=address_list(msg, "To"),
                cc_addresses=address_list(msg, "Cc"),
                body_text=extract_body_text(msg),
                received_at=decode_header_value(msg.get("Date")),
                attachment_names=saved_names,
                unreadable_attachment_names=unreadable_names,
                mail_uuid=mail_uuid,
            )
            if not config.pop3_leave_on_server:
                client.dele(msg_num)
            stored += 1
            logger.info(
                "stored received_mail uuid=%s pop3_uidl=%s attachments=%s octets=%s",
                mail_uuid,
                pop3_uidl,
                len(saved_names),
                octets,
            )
    finally:
        try:
            client.quit()
        except Exception:
            pass

    return stored
