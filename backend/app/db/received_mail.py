"""Persist inbound mail rows fetched by the IMAP/POP3 poller."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.db.database import get_connection

DECISION_TYPE_PENDING = 0
DECISION_TYPE_INSUFFICIENT = 5  # job-worthy but missing materials
DECISION_TYPE_JOB = 10
DECISION_TYPE_NON_JOB = 11

VALID_DECISION_TYPES = frozenset(
    {
        DECISION_TYPE_PENDING,
        DECISION_TYPE_INSUFFICIENT,
        DECISION_TYPE_JOB,
        DECISION_TYPE_NON_JOB,
    }
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_received_mail_table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS received_mail (
            idx BIGSERIAL PRIMARY KEY,
            uuid VARCHAR(36) NOT NULL UNIQUE,
            decision_type INTEGER NOT NULL DEFAULT 0,
            message_id VARCHAR(500) NOT NULL DEFAULT '',
            imap_uid BIGINT,
            pop3_uidl VARCHAR(500) NOT NULL DEFAULT '',
            mailbox VARCHAR(100) NOT NULL DEFAULT 'INBOX',
            subject TEXT NOT NULL DEFAULT '',
            from_address VARCHAR(500) NOT NULL DEFAULT '',
            to_addresses TEXT NOT NULL DEFAULT '',
            cc_addresses TEXT NOT NULL DEFAULT '',
            body_text TEXT NOT NULL DEFAULT '',
            received_at TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL DEFAULT '',
            attachment_count INTEGER NOT NULL DEFAULT 0,
            attachment_names TEXT NOT NULL DEFAULT '[]',
            unreadable_attachment_names TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_received_mail_mailbox_uid
            ON received_mail (mailbox, imap_uid)
            WHERE imap_uid IS NOT NULL
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_received_mail_message_id
            ON received_mail (message_id)
            WHERE message_id <> ''
        """
    )
    connection.execute(
        "ALTER TABLE received_mail ADD COLUMN IF NOT EXISTS pop3_uidl VARCHAR(500) NOT NULL DEFAULT ''"
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_received_mail_pop3_uidl
            ON received_mail (pop3_uidl)
            WHERE pop3_uidl <> ''
        """
    )
    connection.execute(
        """
        ALTER TABLE received_mail
            ADD COLUMN IF NOT EXISTS unreadable_attachment_names TEXT NOT NULL DEFAULT '[]'
        """
    )


@dataclass(frozen=True)
class ReceivedMailRecord:
    idx: int
    uuid: str
    decision_type: int
    message_id: str
    imap_uid: int | None
    pop3_uidl: str
    mailbox: str
    subject: str
    from_address: str
    to_addresses: str
    cc_addresses: str
    body_text: str
    received_at: str
    fetched_at: str
    attachment_count: int
    attachment_names: list[str]
    unreadable_attachment_names: list[str]


def _parse_attachment_names(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw]
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _row_to_record(row: Any) -> ReceivedMailRecord:
    return ReceivedMailRecord(
        idx=int(row["idx"]),
        uuid=str(row["uuid"]),
        decision_type=int(row["decision_type"] or 0),
        message_id=str(row["message_id"] or ""),
        imap_uid=int(row["imap_uid"]) if row["imap_uid"] is not None else None,
        pop3_uidl=str(row["pop3_uidl"] or ""),
        mailbox=str(row["mailbox"] or "INBOX"),
        subject=str(row["subject"] or ""),
        from_address=str(row["from_address"] or ""),
        to_addresses=str(row["to_addresses"] or ""),
        cc_addresses=str(row["cc_addresses"] or ""),
        body_text=str(row["body_text"] or ""),
        received_at=str(row["received_at"] or ""),
        fetched_at=str(row["fetched_at"] or ""),
        attachment_count=int(row["attachment_count"] or 0),
        attachment_names=_parse_attachment_names(row["attachment_names"]),
        unreadable_attachment_names=_parse_attachment_names(
            row["unreadable_attachment_names"] if "unreadable_attachment_names" in row.keys() else "[]"
        ),
    )


_SELECT = """
    idx, uuid, decision_type, message_id, imap_uid, pop3_uidl, mailbox, subject,
    from_address, to_addresses, cc_addresses, body_text, received_at,
    fetched_at, attachment_count, attachment_names, unreadable_attachment_names
"""


def message_already_stored(
    database_path: str | Path,
    *,
    message_id: str,
    mailbox: str,
    imap_uid: int | None,
    pop3_uidl: str | None = None,
) -> bool:
    with get_connection(database_path) as connection:
        ensure_received_mail_table(connection)
        normalized_id = message_id.strip()
        if normalized_id:
            row = connection.execute(
                """
                SELECT idx FROM received_mail
                WHERE message_id = ?
                LIMIT 1
                """,
                (normalized_id,),
            ).fetchone()
            if row is not None:
                return True
        normalized_uidl = (pop3_uidl or "").strip()
        if normalized_uidl:
            row = connection.execute(
                """
                SELECT idx FROM received_mail
                WHERE pop3_uidl = ?
                LIMIT 1
                """,
                (normalized_uidl,),
            ).fetchone()
            if row is not None:
                return True
        if imap_uid is not None:
            row = connection.execute(
                """
                SELECT idx FROM received_mail
                WHERE mailbox = ? AND imap_uid = ?
                LIMIT 1
                """,
                (mailbox.strip() or "INBOX", int(imap_uid)),
            ).fetchone()
            if row is not None:
                return True
        return False


def insert_received_mail(
    database_path: str | Path,
    *,
    message_id: str,
    imap_uid: int | None,
    pop3_uidl: str | None = None,
    mailbox: str,
    subject: str,
    from_address: str,
    to_addresses: str,
    cc_addresses: str,
    body_text: str,
    received_at: str,
    attachment_names: list[str],
    unreadable_attachment_names: list[str] | None = None,
    mail_uuid: str | None = None,
) -> ReceivedMailRecord:
    mail_id = (mail_uuid or str(uuid.uuid4())).strip()
    fetched_at = _now_iso()
    names_json = json.dumps(list(attachment_names), ensure_ascii=False)
    unreadable_json = json.dumps(list(unreadable_attachment_names or []), ensure_ascii=False)
    with get_connection(database_path) as connection:
        ensure_received_mail_table(connection)
        row = connection.execute(
            """
            INSERT INTO received_mail (
                uuid, decision_type, message_id, imap_uid, pop3_uidl, mailbox, subject,
                from_address, to_addresses, cc_addresses, body_text,
                received_at, fetched_at, attachment_count, attachment_names,
                unreadable_attachment_names
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING
                idx, uuid, decision_type, message_id, imap_uid, pop3_uidl, mailbox, subject,
                from_address, to_addresses, cc_addresses, body_text, received_at,
                fetched_at, attachment_count, attachment_names, unreadable_attachment_names
            """,
            (
                mail_id,
                DECISION_TYPE_PENDING,
                message_id.strip(),
                int(imap_uid) if imap_uid is not None else None,
                (pop3_uidl or "").strip(),
                mailbox.strip() or "INBOX",
                subject,
                from_address,
                to_addresses,
                cc_addresses,
                body_text,
                received_at.strip(),
                fetched_at,
                len(attachment_names),
                names_json,
                unreadable_json,
            ),
        ).fetchone()
        return _row_to_record(row)


def get_received_mail_by_uuid(
    database_path: str | Path,
    mail_uuid: str,
) -> ReceivedMailRecord | None:
    with get_connection(database_path) as connection:
        ensure_received_mail_table(connection)
        row = connection.execute(
            f"""
            SELECT {_SELECT}
            FROM received_mail
            WHERE uuid = ?
            LIMIT 1
            """,
            (mail_uuid.strip(),),
        ).fetchone()
        return _row_to_record(row) if row else None


def list_received_mail(
    database_path: str | Path,
    *,
    limit: int = 50,
    offset: int = 0,
    decision_type: int | None = None,
) -> list[ReceivedMailRecord]:
    capped = max(1, min(int(limit), 200))
    skip = max(0, int(offset))
    with get_connection(database_path) as connection:
        ensure_received_mail_table(connection)
        if decision_type is None:
            rows = connection.execute(
                f"""
                SELECT {_SELECT}
                FROM received_mail
                ORDER BY idx DESC
                LIMIT ? OFFSET ?
                """,
                (capped, skip),
            ).fetchall()
        else:
            rows = connection.execute(
                f"""
                SELECT {_SELECT}
                FROM received_mail
                WHERE decision_type = ?
                ORDER BY idx DESC
                LIMIT ? OFFSET ?
                """,
                (int(decision_type), capped, skip),
            ).fetchall()
        return [_row_to_record(row) for row in rows]


def list_pending_received_mail(
    database_path: str | Path,
    *,
    limit: int = 50,
) -> list[ReceivedMailRecord]:
    """Oldest pending (decision_type=0) rows for sequential JOB_DECISION processing."""
    capped = max(1, min(int(limit), 200))
    with get_connection(database_path) as connection:
        ensure_received_mail_table(connection)
        rows = connection.execute(
            f"""
            SELECT {_SELECT}
            FROM received_mail
            WHERE decision_type = ?
            ORDER BY idx ASC
            LIMIT ?
            """,
            (DECISION_TYPE_PENDING, capped),
        ).fetchall()
        return [_row_to_record(row) for row in rows]


def update_decision_type(
    database_path: str | Path,
    mail_uuid: str,
    decision_type: int,
) -> ReceivedMailRecord | None:
    if decision_type not in VALID_DECISION_TYPES:
        raise ValueError(f"invalid decision_type: {decision_type}")
    with get_connection(database_path) as connection:
        ensure_received_mail_table(connection)
        connection.execute(
            """
            UPDATE received_mail
            SET decision_type = ?
            WHERE uuid = ?
            """,
            (int(decision_type), mail_uuid.strip()),
        )
    return get_received_mail_by_uuid(database_path, mail_uuid)
