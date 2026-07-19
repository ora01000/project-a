from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection

NOTICE_SELECT_COLUMNS = """
    idx,
    writer,
    write_date,
    from_date,
    until_date,
    title,
    notice,
    welcome_popup
"""


@dataclass(frozen=True)
class Notice:
    idx: int
    writer: str
    write_date: str
    from_date: str
    until_date: str
    title: str
    notice: str
    welcome_popup: bool


def _row_to_notice(row) -> Notice:
    return Notice(
        idx=int(row["idx"]),
        writer=str(row["writer"]),
        write_date=str(row["write_date"]),
        from_date=str(row["from_date"]),
        until_date=str(row["until_date"]),
        title=str(row["title"]),
        notice=str(row["notice"] or ""),
        welcome_popup=bool(int(row["welcome_popup"] or 0)),
    )


def list_notices(database_path: str | Path) -> list[Notice]:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT {NOTICE_SELECT_COLUMNS}
            FROM notice_board
            ORDER BY idx DESC
            """
        ).fetchall()
    return [_row_to_notice(row) for row in rows]


def list_welcome_notices(
    database_path: str | Path,
    *,
    at: str | None = None,
) -> list[Notice]:
    """Notices with welcome_popup enabled and at within [from_date, until_date]."""
    from backend.app.db.job_datetime import normalize_job_datetime, now_job_datetime

    now = (at or now_job_datetime()).strip()
    matched: list[Notice] = []
    for notice in list_notices(database_path):
        if not notice.welcome_popup:
            continue
        try:
            start = normalize_job_datetime(notice.from_date, default_time="00:00:00")
            end = normalize_job_datetime(notice.until_date, default_time="00:00:00")
        except ValueError:
            continue
        if start <= now <= end:
            matched.append(notice)
    return matched


def get_notice_by_idx(database_path: str | Path, idx: int) -> Notice | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            f"""
            SELECT {NOTICE_SELECT_COLUMNS}
            FROM notice_board
            WHERE idx = ?
            """,
            (idx,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_notice(row)


def create_notice(
    database_path: str | Path,
    *,
    writer: str,
    write_date: str,
    from_date: str,
    until_date: str,
    title: str,
    notice: str,
    welcome_popup: bool = False,
) -> Notice:
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO notice_board (
                writer,
                write_date,
                from_date,
                until_date,
                title,
                notice,
                welcome_popup
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                writer.strip(),
                write_date.strip(),
                from_date.strip(),
                until_date.strip(),
                title.strip(),
                notice,
                1 if welcome_popup else 0,
            ),
        )
        connection.commit()
        idx = int(cursor.lastrowid)

    created = get_notice_by_idx(database_path, idx)
    if created is None:
        raise RuntimeError("Failed to load created notice")
    return created


def update_notice(
    database_path: str | Path,
    idx: int,
    *,
    writer: str,
    write_date: str,
    from_date: str,
    until_date: str,
    title: str,
    notice: str,
    welcome_popup: bool,
) -> Notice | None:
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE notice_board
            SET writer = ?,
                write_date = ?,
                from_date = ?,
                until_date = ?,
                title = ?,
                notice = ?,
                welcome_popup = ?
            WHERE idx = ?
            """,
            (
                writer.strip(),
                write_date.strip(),
                from_date.strip(),
                until_date.strip(),
                title.strip(),
                notice,
                1 if welcome_popup else 0,
                idx,
            ),
        )
        connection.commit()
        if cursor.rowcount == 0:
            return None
    return get_notice_by_idx(database_path, idx)


def update_notice_welcome_popup(
    database_path: str | Path,
    idx: int,
    *,
    welcome_popup: bool,
) -> Notice | None:
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE notice_board
            SET welcome_popup = ?
            WHERE idx = ?
            """,
            (1 if welcome_popup else 0, idx),
        )
        connection.commit()
        if cursor.rowcount == 0:
            return None
    return get_notice_by_idx(database_path, idx)


def delete_notices(database_path: str | Path, idx_list: list[int]) -> int:
    if not idx_list:
        return 0
    placeholders = ", ".join("?" for _ in idx_list)
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            f"DELETE FROM notice_board WHERE idx IN ({placeholders})",
            idx_list,
        )
        connection.commit()
        return int(cursor.rowcount)
