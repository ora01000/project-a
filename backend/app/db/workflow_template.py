"""CRUD for diagram workflow templates stored under ``{UPLOAD_HOME}/workflow_template``."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from backend.app.config import docs_workflow_template_dir, workflow_template_dir
from backend.app.db.database import get_connection
from backend.app.db.job_datetime import now_job_datetime

logger = logging.getLogger(__name__)

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_TEMPLATE_NAME_MAX = 70
_TEMPLATE_FILENAME_MAX = 200

_SELECT = """
    idx, template_name, template_filename, update_date, created_by
"""


@dataclass(frozen=True)
class WorkflowTemplateRecord:
    idx: int
    template_name: str
    template_filename: str
    update_date: str
    created_by: int


def ensure_workflow_template_table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_template (
            idx SERIAL PRIMARY KEY,
            template_name VARCHAR(70) NOT NULL UNIQUE,
            template_filename VARCHAR(200) NOT NULL UNIQUE,
            update_date TEXT NOT NULL DEFAULT '',
            created_by INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_template_name
        ON workflow_template (template_name)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_template_filename
        ON workflow_template (template_filename)
        """
    )


def _row_to_record(row) -> WorkflowTemplateRecord:
    return WorkflowTemplateRecord(
        idx=int(row["idx"] or 0),
        template_name=str(row["template_name"] or ""),
        template_filename=str(row["template_filename"] or ""),
        update_date=str(row["update_date"] or ""),
        created_by=int(row["created_by"] or 1) or 1,
    )


def sanitize_template_filename(raw: str) -> str:
    """Return a safe ``*.md`` basename or raise ``ValueError``."""
    name = Path((raw or "").strip()).name.strip()
    if not name:
        raise ValueError("파일명이 비어 있습니다.")
    if _INVALID_FILENAME_CHARS.search(name) or ".." in name:
        raise ValueError("파일명에 사용할 수 없는 문자가 포함되어 있습니다.")
    if not name.lower().endswith(".md"):
        name = f"{name}.md"
    if len(name) > _TEMPLATE_FILENAME_MAX:
        raise ValueError(f"파일명은 {_TEMPLATE_FILENAME_MAX}자를 넘을 수 없습니다.")
    if name.startswith("."):
        raise ValueError("파일명이 올바르지 않습니다.")
    return name


def sanitize_template_name(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        raise ValueError("양식 이름을 입력하세요.")
    if len(name) > _TEMPLATE_NAME_MAX:
        raise ValueError(f"양식 이름은 {_TEMPLATE_NAME_MAX}자를 넘을 수 없습니다.")
    if _INVALID_FILENAME_CHARS.search(name):
        raise ValueError("양식 이름에 사용할 수 없는 문자가 포함되어 있습니다.")
    return name


def list_workflow_templates(database_path: str | Path) -> list[WorkflowTemplateRecord]:
    with get_connection(database_path) as connection:
        ensure_workflow_template_table(connection)
        rows = connection.execute(
            f"""
            SELECT {_SELECT}
            FROM workflow_template
            ORDER BY template_name ASC, idx ASC
            """
        ).fetchall()
    return [_row_to_record(row) for row in rows]


def get_workflow_template_by_idx(
    database_path: str | Path, idx: int
) -> WorkflowTemplateRecord | None:
    with get_connection(database_path) as connection:
        ensure_workflow_template_table(connection)
        row = connection.execute(
            f"""
            SELECT {_SELECT}
            FROM workflow_template
            WHERE idx = ?
            """,
            (int(idx),),
        ).fetchone()
    return _row_to_record(row) if row is not None else None


def get_workflow_template_by_name(
    database_path: str | Path, template_name: str
) -> WorkflowTemplateRecord | None:
    key = (template_name or "").strip()
    if not key:
        return None
    with get_connection(database_path) as connection:
        ensure_workflow_template_table(connection)
        row = connection.execute(
            f"""
            SELECT {_SELECT}
            FROM workflow_template
            WHERE template_name = ?
            """,
            (key,),
        ).fetchone()
    return _row_to_record(row) if row is not None else None


def get_workflow_template_by_filename(
    database_path: str | Path, template_filename: str
) -> WorkflowTemplateRecord | None:
    try:
        key = sanitize_template_filename(template_filename)
    except ValueError:
        return None
    with get_connection(database_path) as connection:
        ensure_workflow_template_table(connection)
        row = connection.execute(
            f"""
            SELECT {_SELECT}
            FROM workflow_template
            WHERE template_filename = ?
            """,
            (key,),
        ).fetchone()
    return _row_to_record(row) if row is not None else None


def create_workflow_template(
    database_path: str | Path,
    *,
    template_name: str,
    template_filename: str,
    created_by: int,
    content: str,
) -> WorkflowTemplateRecord:
    name = sanitize_template_name(template_name)
    filename = sanitize_template_filename(template_filename)
    body = content if isinstance(content, str) else ""
    stamp = now_job_datetime()
    owner = int(created_by or 0) or 1

    directory = workflow_template_dir()
    target = (directory / filename).resolve()
    try:
        target.relative_to(directory.resolve())
    except ValueError as exc:
        raise ValueError("파일 경로가 올바르지 않습니다.") from exc
    if target.exists():
        raise ValueError(f"이미 존재하는 파일명입니다: {filename}")

    with get_connection(database_path) as connection:
        ensure_workflow_template_table(connection)
        existing_name = connection.execute(
            "SELECT idx FROM workflow_template WHERE template_name = ?",
            (name,),
        ).fetchone()
        if existing_name is not None:
            raise ValueError(f"이미 존재하는 양식 이름입니다: {name}")
        existing_file = connection.execute(
            "SELECT idx FROM workflow_template WHERE template_filename = ?",
            (filename,),
        ).fetchone()
        if existing_file is not None:
            raise ValueError(f"이미 존재하는 파일명입니다: {filename}")
        row = connection.execute(
            """
            INSERT INTO workflow_template (
                template_name, template_filename, update_date, created_by
            )
            VALUES (?, ?, ?, ?)
            RETURNING idx
            """,
            (name, filename, stamp, owner),
        ).fetchone()
        idx = int(row["idx"])

    try:
        target.write_text(body, encoding="utf-8")
    except OSError as exc:
        with get_connection(database_path) as connection:
            ensure_workflow_template_table(connection)
            connection.execute("DELETE FROM workflow_template WHERE idx = ?", (idx,))
        raise ValueError(f"템플릿 파일 저장에 실패했습니다: {exc}") from exc

    record = get_workflow_template_by_idx(database_path, idx)
    if record is None:
        raise ValueError("템플릿 저장 후 조회에 실패했습니다.")
    return record


def read_workflow_template_content(record: WorkflowTemplateRecord) -> str:
    directory = workflow_template_dir()
    path = (directory / record.template_filename).resolve()
    try:
        path.relative_to(directory.resolve())
    except ValueError as exc:
        raise ValueError("템플릿 파일 경로가 올바르지 않습니다.") from exc
    if not path.is_file():
        raise FileNotFoundError(f"템플릿 파일이 없습니다: {record.template_filename}")
    return path.read_text(encoding="utf-8")


def update_workflow_template(
    database_path: str | Path,
    idx: int,
    *,
    template_name: str,
    template_filename: str,
    content: str,
) -> WorkflowTemplateRecord:
    existing = get_workflow_template_by_idx(database_path, idx)
    if existing is None:
        raise ValueError("템플릿을 찾을 수 없습니다.")

    name = sanitize_template_name(template_name)
    filename = sanitize_template_filename(template_filename)
    body = content if isinstance(content, str) else ""
    stamp = now_job_datetime()

    conflict_name = get_workflow_template_by_name(database_path, name)
    if conflict_name is not None and conflict_name.idx != existing.idx:
        raise ValueError(f"이미 존재하는 양식 이름입니다: {name}")
    conflict_file = get_workflow_template_by_filename(database_path, filename)
    if conflict_file is not None and conflict_file.idx != existing.idx:
        raise ValueError(f"이미 존재하는 파일명입니다: {filename}")

    directory = workflow_template_dir()
    old_path = (directory / existing.template_filename).resolve()
    new_path = (directory / filename).resolve()
    try:
        old_path.relative_to(directory.resolve())
        new_path.relative_to(directory.resolve())
    except ValueError as exc:
        raise ValueError("파일 경로가 올바르지 않습니다.") from exc

    if filename != existing.template_filename and new_path.exists():
        raise ValueError(f"이미 존재하는 파일명입니다: {filename}")

    try:
        if filename != existing.template_filename:
            if old_path.is_file():
                old_path.replace(new_path)
            else:
                new_path.write_text(body, encoding="utf-8")
        new_path.write_text(body, encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"템플릿 파일 저장에 실패했습니다: {exc}") from exc

    with get_connection(database_path) as connection:
        ensure_workflow_template_table(connection)
        connection.execute(
            """
            UPDATE workflow_template
            SET template_name = ?, template_filename = ?, update_date = ?
            WHERE idx = ?
            """,
            (name, filename, stamp, int(existing.idx)),
        )

    record = get_workflow_template_by_idx(database_path, existing.idx)
    if record is None:
        raise ValueError("템플릿 수정 후 조회에 실패했습니다.")
    return record


def sync_disk_templates_to_db(database_path: str | Path) -> int:
    """Register ``*.md`` files under UPLOAD_HOME that are missing from the DB."""
    directory = workflow_template_dir()
    if not directory.is_dir():
        return 0
    created = 0
    for path in sorted(directory.glob("*.md")):
        if not path.is_file():
            continue
        try:
            filename = sanitize_template_filename(path.name)
        except ValueError:
            continue
        if get_workflow_template_by_filename(database_path, filename) is not None:
            continue
        name = path.stem.strip()[:_TEMPLATE_NAME_MAX] or filename
        if get_workflow_template_by_name(database_path, name) is not None:
            name = f"{name}_{path.stat().st_mtime_ns}"[:_TEMPLATE_NAME_MAX]
        try:
            # File already on disk — insert DB row only (avoid recreate write collision).
            stamp = now_job_datetime()
            with get_connection(database_path) as connection:
                ensure_workflow_template_table(connection)
                connection.execute(
                    """
                    INSERT INTO workflow_template (
                        template_name, template_filename, update_date, created_by
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, filename, stamp, 1),
                )
            created += 1
        except Exception as exc:
            logger.warning("workflow template disk sync skipped %s: %s", path.name, exc)
    return created


def seed_workflow_templates_from_docs(database_path: str | Path) -> int:
    """Copy bundled docs templates into UPLOAD_HOME and register missing DB rows.

    Returns the number of newly registered templates.
    """
    source_dir = docs_workflow_template_dir()
    if not source_dir.is_dir():
        return 0

    created = 0
    for path in sorted(source_dir.glob("*.md")):
        if not path.is_file():
            continue
        try:
            filename = sanitize_template_filename(path.name)
        except ValueError:
            continue
        name = path.stem.strip()[:_TEMPLATE_NAME_MAX] or filename
        if get_workflow_template_by_filename(database_path, filename) is not None:
            continue
        if get_workflow_template_by_name(database_path, name) is not None:
            continue
        try:
            content = path.read_text(encoding="utf-8")
            create_workflow_template(
                database_path,
                template_name=name,
                template_filename=filename,
                created_by=1,
                content=content,
            )
            created += 1
        except (OSError, ValueError) as exc:
            logger.warning("workflow template seed skipped %s: %s", path.name, exc)
    return created
