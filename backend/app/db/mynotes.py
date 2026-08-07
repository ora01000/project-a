from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from backend.app.config import PROJECT_ROOT
from backend.app.db.database import get_connection
from backend.app.db.job_datetime import now_job_datetime

MY_NOTES_ROOT = PROJECT_ROOT / "data" / "mynotes"
_USER_ID_PATTERN = re.compile(r"^[\w.-]+$")


@dataclass(frozen=True)
class MyNoteRecord:
    idx: int
    userid: str
    note_name: str
    create_date: str
    origin_file: str
    last_update: str


def _sanitize_user_id(userid: str) -> str:
    normalized = userid.strip()
    if not normalized or not _USER_ID_PATTERN.match(normalized):
        raise ValueError(f"Invalid userid for mynotes: {userid!r}")
    return normalized


def build_mynote_filename(create_date: str) -> str:
    safe = create_date.strip().replace(" ", "_").replace(":", "-")
    return f"{safe}.md"


def build_origin_file_relative(userid: str, create_date: str) -> str:
    safe_userid = _sanitize_user_id(userid)
    return f"data/mynotes/{safe_userid}/{build_mynote_filename(create_date)}"


def resolve_origin_file_path(origin_file: str) -> Path:
    path = Path(origin_file)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _row_to_mynote(row) -> MyNoteRecord:
    return MyNoteRecord(
        idx=int(row["idx"]),
        userid=str(row["userid"]),
        note_name=str(row["note_name"]),
        create_date=str(row["create_date"]),
        origin_file=str(row["origin_file"]),
        last_update=str(row["last_update"]),
    )


def list_mynotes(database_path: str | Path, *, userid: str) -> list[MyNoteRecord]:
    safe_userid = _sanitize_user_id(userid)
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT idx, userid, note_name, create_date, origin_file, last_update
            FROM mynotes
            WHERE userid = ?
            ORDER BY last_update DESC, idx DESC
            """,
            (safe_userid,),
        ).fetchall()
    return [_row_to_mynote(row) for row in rows]


def list_all_mynotes(database_path: str | Path) -> list[MyNoteRecord]:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT idx, userid, note_name, create_date, origin_file, last_update
            FROM mynotes
            ORDER BY idx ASC
            """
        ).fetchall()
    return [_row_to_mynote(row) for row in rows]


def get_mynote_by_idx(database_path: str | Path, idx: int) -> MyNoteRecord | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT idx, userid, note_name, create_date, origin_file, last_update
            FROM mynotes
            WHERE idx = ?
            """,
            (idx,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_mynote(row)


def create_mynote(
    database_path: str | Path,
    *,
    userid: str,
    note_name: str | None = None,
) -> MyNoteRecord:
    safe_userid = _sanitize_user_id(userid)
    create_date = now_job_datetime()
    last_update = create_date
    resolved_name = (note_name or "").strip() or create_date
    if len(resolved_name) > 50:
        resolved_name = resolved_name[:50]

    origin_file = build_origin_file_relative(safe_userid, create_date)
    file_path = resolve_origin_file_path(origin_file)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if not file_path.exists():
        file_path.write_text("", encoding="utf-8")

    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO mynotes (userid, note_name, create_date, origin_file, last_update)
            VALUES (?, ?, ?, ?, ?)
            """,
            (safe_userid, resolved_name, create_date, origin_file, last_update),
        )
        connection.commit()
        note_idx = int(cursor.lastrowid)

    created = get_mynote_by_idx(database_path, note_idx)
    if created is None:
        raise RuntimeError("Failed to load created mynote record")
    return created


def update_mynote_name(
    database_path: str | Path,
    idx: int,
    *,
    userid: str,
    note_name: str,
) -> MyNoteRecord:
    existing = get_mynote_by_idx(database_path, idx)
    if existing is None:
        raise ValueError("note not found")
    if existing.userid != _sanitize_user_id(userid):
        raise ValueError("note does not belong to this user")

    resolved_name = note_name.strip()
    if not resolved_name:
        raise ValueError("note_name is required")
    if len(resolved_name) > 50:
        resolved_name = resolved_name[:50]

    last_update = now_job_datetime()
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE mynotes
            SET note_name = ?, last_update = ?
            WHERE idx = ? AND userid = ?
            """,
            (resolved_name, last_update, idx, existing.userid),
        )
        connection.commit()
        if cursor.rowcount == 0:
            raise ValueError("note rename failed")

    updated = get_mynote_by_idx(database_path, idx)
    if updated is None:
        raise RuntimeError("Failed to load updated mynote record")
    return updated


def touch_mynote_last_update(
    database_path: str | Path,
    idx: int,
    *,
    userid: str,
) -> MyNoteRecord:
    existing = get_mynote_by_idx(database_path, idx)
    if existing is None:
        raise ValueError("note not found")
    if existing.userid != _sanitize_user_id(userid):
        raise ValueError("note does not belong to this user")

    last_update = now_job_datetime()
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE mynotes
            SET last_update = ?
            WHERE idx = ? AND userid = ?
            """,
            (last_update, idx, existing.userid),
        )
        connection.commit()
        if cursor.rowcount == 0:
            raise ValueError("note update failed")

    updated = get_mynote_by_idx(database_path, idx)
    if updated is None:
        raise RuntimeError("Failed to load updated mynote record")
    return updated


def write_mynote_content_file(record: MyNoteRecord, content: str) -> None:
    file_path = resolve_origin_file_path(record.origin_file)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


def write_mynote_content_db(
    database_path: str | Path,
    record: MyNoteRecord,
    content: str,
) -> None:
    updated_at = now_job_datetime()
    with get_connection(database_path) as connection:
        connection.execute(
            """
            INSERT INTO mynote_contents (note_idx, content, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(note_idx) DO UPDATE SET
                content = excluded.content,
                updated_at = excluded.updated_at
            """,
            (record.idx, content, updated_at),
        )
        connection.commit()


def read_mynote_content_db(database_path: str | Path, record: MyNoteRecord) -> str:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT content FROM mynote_contents WHERE note_idx = ?
            """,
            (record.idx,),
        ).fetchone()
    if row is None:
        return ""
    return str(row["content"] or "")


def _mynote_content_backend() -> str:
    from backend.app.config import load_mynotes_settings

    return load_mynotes_settings().content_backend


def persist_mynote_content(
    database_path: str | Path,
    record: MyNoteRecord,
    content: str,
) -> None:
    if _mynote_content_backend() == "database":
        write_mynote_content_db(database_path, record, content)
        return
    write_mynote_content_file(record, content)


def save_mynote_content(
    database_path: str | Path,
    idx: int,
    *,
    userid: str,
    content: str,
) -> MyNoteRecord:
    existing = get_mynote_by_idx(database_path, idx)
    if existing is None:
        raise ValueError("note not found")
    if existing.userid != _sanitize_user_id(userid):
        raise ValueError("note does not belong to this user")

    persist_mynote_content(database_path, existing, content)

    last_update = now_job_datetime()
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE mynotes
            SET last_update = ?
            WHERE idx = ? AND userid = ?
            """,
            (last_update, idx, existing.userid),
        )
        connection.commit()
        if cursor.rowcount == 0:
            raise ValueError("note content save failed")

    updated = get_mynote_by_idx(database_path, idx)
    if updated is None:
        raise RuntimeError("Failed to load updated mynote record")
    return updated


def read_mynote_content(
    record: MyNoteRecord,
    *,
    database_path: str | Path | None = None,
) -> str:
    if _mynote_content_backend() == "database":
        if database_path is None:
            raise ValueError("database_path is required for database content backend")
        content = read_mynote_content_db(database_path, record)
        if content:
            return content
        # Fallback: migrate from file once if present.
        file_path = resolve_origin_file_path(record.origin_file)
        if file_path.exists():
            file_content = file_path.read_text(encoding="utf-8")
            write_mynote_content_db(database_path, record, file_content)
            return file_content
        return ""

    file_path = resolve_origin_file_path(record.origin_file)
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")


def delete_mynote(
    database_path: str | Path,
    idx: int,
    *,
    userid: str,
) -> None:
    existing = get_mynote_by_idx(database_path, idx)
    if existing is None:
        raise ValueError("note not found")
    if existing.userid != _sanitize_user_id(userid):
        raise ValueError("note does not belong to this user")

    file_path = resolve_origin_file_path(existing.origin_file)
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            DELETE FROM mynotes
            WHERE idx = ? AND userid = ?
            """,
            (idx, existing.userid),
        )
        connection.commit()
        if cursor.rowcount == 0:
            raise ValueError("note delete failed")

    if file_path.exists():
        file_path.unlink()
