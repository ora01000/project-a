from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection


@dataclass(frozen=True)
class JobResultRecord:
    srnum: str
    result: str
    complete_date: str


def _row_to_job_result(row) -> JobResultRecord:
    return JobResultRecord(
        srnum=str(row["srnum"]),
        result=str(row["result"] or ""),
        complete_date=str(row["complete_date"]),
    )


def get_job_result_by_srnum(
    database_path: str | Path,
    srnum: str,
) -> JobResultRecord | None:
    normalized_srnum = srnum.strip()
    if not normalized_srnum:
        return None

    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT srnum, result, complete_date
            FROM jobs_result
            WHERE srnum = ?
            """,
            (normalized_srnum,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_job_result(row)


def upsert_job_result(
    database_path: str | Path,
    *,
    srnum: str,
    result: str,
    complete_date: str,
) -> JobResultRecord:
    normalized_srnum = srnum.strip()
    if not normalized_srnum:
        raise ValueError("srnum is required")

    with get_connection(database_path) as connection:
        connection.execute(
            """
            INSERT INTO jobs_result (srnum, result, complete_date)
            VALUES (?, ?, ?)
            ON CONFLICT(srnum) DO UPDATE SET
                result = excluded.result,
                complete_date = excluded.complete_date
            """,
            (normalized_srnum, result, complete_date),
        )
        connection.commit()

    record = get_job_result_by_srnum(database_path, normalized_srnum)
    if record is None:
        raise RuntimeError("Failed to load job result after upsert")
    return record
