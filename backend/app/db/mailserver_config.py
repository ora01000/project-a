"""Persist SMTP/IMAP mail server settings in ``mailserver_config`` (singleton)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.db.database import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_mailserver_config_table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS mailserver_config (
            idx BIGSERIAL PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            smtp_host VARCHAR(200) NOT NULL DEFAULT '',
            smtp_port INTEGER NOT NULL DEFAULT 587,
            smtp_username VARCHAR(200) NOT NULL DEFAULT '',
            smtp_password TEXT NOT NULL DEFAULT '',
            from_address VARCHAR(200) NOT NULL DEFAULT '',
            smtp_auth INTEGER NOT NULL DEFAULT 1,
            use_tls INTEGER NOT NULL DEFAULT 1,
            use_ssl INTEGER NOT NULL DEFAULT 0,
            timeout_seconds DOUBLE PRECISION NOT NULL DEFAULT 30,
            receive_enabled INTEGER NOT NULL DEFAULT 0,
            imap_host VARCHAR(200) NOT NULL DEFAULT '',
            imap_port INTEGER NOT NULL DEFAULT 993,
            imap_use_ssl INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    for statement in (
        "ALTER TABLE mailserver_config ADD COLUMN IF NOT EXISTS smtp_auth INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE mailserver_config ADD COLUMN IF NOT EXISTS receive_enabled INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE mailserver_config ADD COLUMN IF NOT EXISTS imap_host VARCHAR(200) NOT NULL DEFAULT ''",
        "ALTER TABLE mailserver_config ADD COLUMN IF NOT EXISTS imap_port INTEGER NOT NULL DEFAULT 993",
        "ALTER TABLE mailserver_config ADD COLUMN IF NOT EXISTS imap_use_ssl INTEGER NOT NULL DEFAULT 1",
    ):
        connection.execute(statement)


@dataclass
class MailserverConfigRow:
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    from_address: str = ""
    smtp_auth: bool = True
    use_tls: bool = True
    use_ssl: bool = False
    timeout_seconds: float = 30.0
    receive_enabled: bool = False
    imap_host: str = ""
    imap_port: int = 993
    imap_use_ssl: bool = True
    updated_at: str = ""
    has_password: bool = False


def _col(row: Any, name: str, default: Any = None) -> Any:
    try:
        if name in row.keys():
            return row[name]
    except Exception:
        pass
    return default


def _row_from_db(row: Any | None) -> MailserverConfigRow | None:
    if row is None:
        return None
    password = str(row["smtp_password"] or "")
    smtp_auth_raw = _col(row, "smtp_auth", 1)
    receive_enabled_raw = _col(row, "receive_enabled", 0)
    imap_use_ssl_raw = _col(row, "imap_use_ssl", 1)
    return MailserverConfigRow(
        enabled=bool(int(row["enabled"] or 0)),
        smtp_host=str(row["smtp_host"] or ""),
        smtp_port=int(row["smtp_port"] or 587),
        smtp_username=str(row["smtp_username"] or ""),
        smtp_password=password,
        from_address=str(row["from_address"] or ""),
        smtp_auth=bool(int(smtp_auth_raw if smtp_auth_raw is not None else 1)),
        use_tls=bool(int(row["use_tls"] if row["use_tls"] is not None else 1)),
        use_ssl=bool(int(row["use_ssl"] or 0)),
        timeout_seconds=float(row["timeout_seconds"] or 30.0),
        receive_enabled=bool(int(receive_enabled_raw if receive_enabled_raw is not None else 0)),
        imap_host=str(_col(row, "imap_host", "") or ""),
        imap_port=int(_col(row, "imap_port", 993) or 993),
        imap_use_ssl=bool(int(imap_use_ssl_raw if imap_use_ssl_raw is not None else 1)),
        updated_at=str(row["updated_at"] or ""),
        has_password=bool(password),
    )


_SELECT_COLUMNS = """
    enabled, smtp_host, smtp_port, smtp_username, smtp_password,
    from_address, smtp_auth, use_tls, use_ssl, timeout_seconds,
    receive_enabled, imap_host, imap_port, imap_use_ssl, updated_at
"""


def get_mailserver_config(database_path: str | Path) -> MailserverConfigRow | None:
    with get_connection(database_path) as connection:
        ensure_mailserver_config_table(connection)
        row = connection.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM mailserver_config
            ORDER BY idx ASC
            LIMIT 1
            """
        ).fetchone()
        return _row_from_db(row)


def save_mailserver_config(
    database_path: str | Path,
    *,
    enabled: bool,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str | None,
    from_address: str,
    smtp_auth: bool,
    use_tls: bool,
    use_ssl: bool,
    timeout_seconds: float,
    receive_enabled: bool = False,
    imap_host: str = "",
    imap_port: int = 993,
    imap_use_ssl: bool = True,
) -> MailserverConfigRow:
    """Upsert singleton config. ``smtp_password=None`` or empty keeps existing password."""
    with get_connection(database_path) as connection:
        ensure_mailserver_config_table(connection)
        existing = connection.execute(
            """
            SELECT idx, smtp_password FROM mailserver_config ORDER BY idx ASC LIMIT 1
            """
        ).fetchone()

        if smtp_password is None or str(smtp_password) == "":
            password = str(existing["smtp_password"] or "") if existing else ""
        else:
            password = str(smtp_password)

        updated_at = _now_iso()
        values = (
            1 if enabled else 0,
            smtp_host.strip(),
            int(smtp_port),
            smtp_username.strip(),
            password,
            from_address.strip(),
            1 if smtp_auth else 0,
            1 if use_tls else 0,
            1 if use_ssl else 0,
            float(timeout_seconds),
            1 if receive_enabled else 0,
            imap_host.strip(),
            int(imap_port),
            1 if imap_use_ssl else 0,
            updated_at,
        )
        if existing is None:
            connection.execute(
                """
                INSERT INTO mailserver_config (
                    enabled, smtp_host, smtp_port, smtp_username, smtp_password,
                    from_address, smtp_auth, use_tls, use_ssl, timeout_seconds,
                    receive_enabled, imap_host, imap_port, imap_use_ssl, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        else:
            connection.execute(
                """
                UPDATE mailserver_config
                SET enabled = ?,
                    smtp_host = ?,
                    smtp_port = ?,
                    smtp_username = ?,
                    smtp_password = ?,
                    from_address = ?,
                    smtp_auth = ?,
                    use_tls = ?,
                    use_ssl = ?,
                    timeout_seconds = ?,
                    receive_enabled = ?,
                    imap_host = ?,
                    imap_port = ?,
                    imap_use_ssl = ?,
                    updated_at = ?
                WHERE idx = ?
                """,
                (*values, int(existing["idx"])),
            )

        row = connection.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM mailserver_config
            ORDER BY idx ASC
            LIMIT 1
            """
        ).fetchone()
        result = _row_from_db(row)
        if result is None:
            raise RuntimeError("mailserver_config save failed")
        return result
