"""Dispatch inbound mail polling to IMAP or POP3 based on mailserver_config."""

from __future__ import annotations

from pathlib import Path

from backend.app.config import ReceivedMailSettings, load_received_mail_settings
from backend.app.db.mailserver_config import (
    RECEIVE_PROTOCOL_IMAP,
    RECEIVE_PROTOCOL_POP3,
    get_mailserver_config,
    normalized_receive_protocol,
)
from backend.app.services.mail_imap_poller import poll_imap_once
from backend.app.services.mail_pop3_poller import poll_pop3_once


def poll_received_mail_once(
    database_path: Path,
    settings: ReceivedMailSettings | None = None,
) -> int:
    """Fetch new messages using the configured receive protocol."""
    poll_settings = settings or load_received_mail_settings()
    config = get_mailserver_config(database_path)
    if config is None or not config.receive_enabled:
        return 0

    protocol = normalized_receive_protocol(config.receive_protocol)
    if protocol == RECEIVE_PROTOCOL_POP3:
        return poll_pop3_once(database_path, poll_settings)
    return poll_imap_once(database_path, poll_settings)
