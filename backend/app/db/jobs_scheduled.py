"""Queue of approved jobs waiting for scheduled_at before processing."""

from __future__ import annotations

from pathlib import Path

from backend.app.db.database import get_connection
from backend.app.db.job_datetime import now_job_datetime


def ensure_jobs_scheduled_table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs_scheduled (
            idx BIGSERIAL PRIMARY KEY,
            job_idx BIGINT NOT NULL UNIQUE REFERENCES jobs(idx) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        ALTER TABLE jobs
        ADD COLUMN IF NOT EXISTS is_scheduled INTEGER NOT NULL DEFAULT 0
        """
    )
    connection.execute(
        """
        ALTER TABLE jobs
        ADD COLUMN IF NOT EXISTS scheduled_at TEXT
        """
    )
    connection.commit()


def enqueue_scheduled_job(connection, job_idx: int) -> None:
    ensure_jobs_scheduled_table(connection)
    connection.execute(
        """
        INSERT INTO jobs_scheduled (job_idx)
        VALUES (?)
        ON CONFLICT (job_idx) DO NOTHING
        """,
        (job_idx,),
    )


def dequeue_scheduled_job(connection, job_idx: int) -> None:
    ensure_jobs_scheduled_table(connection)
    connection.execute(
        "DELETE FROM jobs_scheduled WHERE job_idx = ?",
        (job_idx,),
    )


def list_scheduled_job_idxs(database_path: str | Path) -> set[int]:
    with get_connection(database_path) as connection:
        ensure_jobs_scheduled_table(connection)
        rows = connection.execute("SELECT job_idx FROM jobs_scheduled").fetchall()
    return {int(row["job_idx"]) for row in rows}


def release_due_scheduled_jobs(database_path: str | Path) -> list[int]:
    """Remove due rows from jobs_scheduled so the job processor can pick them up.

    Returns released job_idx values.
    """
    now = now_job_datetime()
    with get_connection(database_path) as connection:
        ensure_jobs_scheduled_table(connection)
        rows = connection.execute(
            """
            SELECT js.job_idx AS job_idx
            FROM jobs_scheduled js
            INNER JOIN jobs j ON j.idx = js.job_idx
            WHERE j.is_scheduled = 1
              AND j.scheduled_at IS NOT NULL
              AND TRIM(j.scheduled_at) <> ''
              AND j.scheduled_at <= ?
            """,
            (now,),
        ).fetchall()
        released = [int(row["job_idx"]) for row in rows]
        if released:
            connection.executemany(
                "DELETE FROM jobs_scheduled WHERE job_idx = ?",
                [(job_idx,) for job_idx in released],
            )
            connection.commit()
    return released
