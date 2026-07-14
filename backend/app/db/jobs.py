from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection

JOB_STATE_RECEIVED = 0
JOB_STATE_PLAN_COMPLETED = 1
JOB_STATE_UNDER_REVIEW = 2
JOB_STATE_PENDING = 3
JOB_STATE_REJECTED = 4
JOB_STATE_APPROVED = 5
JOB_STATE_COMPLETED = 6
JOB_STATE_FAILED = 7

JOB_STATE_LABELS: dict[int, str] = {
    JOB_STATE_RECEIVED: "접수",
    JOB_STATE_PLAN_COMPLETED: "계획수립완료",
    JOB_STATE_UNDER_REVIEW: "검토중",
    JOB_STATE_PENDING: "보류",
    JOB_STATE_REJECTED: "반려",
    JOB_STATE_APPROVED: "승인",
    JOB_STATE_COMPLETED: "완료",
    JOB_STATE_FAILED: "실패",
}

JOB_SELECT_COLUMNS = """
    idx,
    request_date,
    job_title,
    request_depart,
    requester,
    requester_email,
    completion_request_date,
    job_description,
    approver,
    state,
    notify_channel,
    job_plan,
    original_job_plan,
    execution_result
"""


def job_state_label(state: int) -> str:
    return JOB_STATE_LABELS.get(state, f"unknown({state})")


@dataclass(frozen=True)
class Job:
    idx: int
    request_date: str
    job_title: str
    request_depart: str
    requester: str
    requester_email: str
    completion_request_date: str
    job_description: str
    approver: str
    state: int
    notify_channel: str
    job_plan: str | None
    original_job_plan: str | None
    execution_result: str | None


def _row_to_job(row) -> Job:
    keys = row.keys()
    return Job(
        idx=int(row["idx"]),
        request_date=str(row["request_date"]),
        job_title=str(row["job_title"]),
        request_depart=str(row["request_depart"]),
        requester=str(row["requester"]),
        requester_email=str(row["requester_email"]),
        completion_request_date=str(row["completion_request_date"]),
        job_description=str(row["job_description"]),
        approver=str(row["approver"]),
        state=int(row["state"]),
        notify_channel=str(row["notify_channel"]) if "notify_channel" in keys else "integrated_chat",
        job_plan=str(row["job_plan"]) if row["job_plan"] is not None else None,
        original_job_plan=(
            str(row["original_job_plan"])
            if "original_job_plan" in keys and row["original_job_plan"] is not None
            else None
        ),
        execution_result=str(row["execution_result"]) if row["execution_result"] is not None else None,
    )


def list_jobs(database_path: str | Path) -> list[Job]:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT {JOB_SELECT_COLUMNS}
            FROM jobs
            ORDER BY idx
            """
        ).fetchall()
    return [_row_to_job(row) for row in rows]


def list_jobs_by_state(database_path: str | Path, state: int) -> list[Job]:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT {JOB_SELECT_COLUMNS}
            FROM jobs
            WHERE state = ?
            ORDER BY idx
            """,
            (state,),
        ).fetchall()
    return [_row_to_job(row) for row in rows]


def list_jobs_by_states(database_path: str | Path, states: list[int]) -> list[Job]:
    if not states:
        return []

    placeholders = ", ".join("?" for _ in states)
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT {JOB_SELECT_COLUMNS}
            FROM jobs
            WHERE state IN ({placeholders})
            ORDER BY idx
            """,
            states,
        ).fetchall()
    return [_row_to_job(row) for row in rows]


def get_job_by_idx(database_path: str | Path, idx: int) -> Job | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            f"""
            SELECT {JOB_SELECT_COLUMNS}
            FROM jobs
            WHERE idx = ?
            """,
            (idx,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_job(row)


def create_job(
    database_path: str | Path,
    *,
    request_date: str,
    job_title: str,
    request_depart: str,
    requester: str,
    requester_email: str,
    completion_request_date: str,
    job_description: str,
    approver: str,
    state: int = JOB_STATE_RECEIVED,
    notify_channel: str = "integrated_chat",
) -> Job:
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO jobs (
                request_date,
                job_title,
                request_depart,
                requester,
                requester_email,
                completion_request_date,
                job_description,
                approver,
                state,
                notify_channel
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_date,
                job_title.strip(),
                request_depart.strip(),
                requester.strip(),
                requester_email.strip(),
                completion_request_date,
                job_description,
                approver.strip(),
                state,
                notify_channel,
            ),
        )
        connection.commit()
        idx = int(cursor.lastrowid)

    job = get_job_by_idx(database_path, idx)
    if job is None:
        raise RuntimeError("Failed to load created job")
    return job


def update_job_state(database_path: str | Path, idx: int, state: int) -> Job | None:
    with get_connection(database_path) as connection:
        connection.execute(
            """
            UPDATE jobs
            SET state = ?
            WHERE idx = ?
            """,
            (state, idx),
        )
        connection.commit()

    return get_job_by_idx(database_path, idx)


def update_job_plan(database_path: str | Path, idx: int, job_plan: str, state: int) -> Job | None:
    with get_connection(database_path) as connection:
        connection.execute(
            """
            UPDATE jobs
            SET job_plan = ?,
                original_job_plan = COALESCE(original_job_plan, ?),
                state = ?
            WHERE idx = ?
            """,
            (job_plan, job_plan, state, idx),
        )
        connection.commit()

    return get_job_by_idx(database_path, idx)


def save_job_plan_edit(database_path: str | Path, idx: int, job_plan: str) -> Job | None:
    with get_connection(database_path) as connection:
        connection.execute(
            """
            UPDATE jobs
            SET job_plan = ?,
                original_job_plan = COALESCE(original_job_plan, job_plan)
            WHERE idx = ?
            """,
            (job_plan, idx),
        )
        connection.commit()

    return get_job_by_idx(database_path, idx)


def restore_job_plan(database_path: str | Path, idx: int) -> Job | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            "SELECT original_job_plan FROM jobs WHERE idx = ?",
            (idx,),
        ).fetchone()
        if row is None:
            return None
        original = row["original_job_plan"]
        if original is None:
            return get_job_by_idx(database_path, idx)
        connection.execute(
            """
            UPDATE jobs
            SET job_plan = ?
            WHERE idx = ?
            """,
            (str(original), idx),
        )
        connection.commit()

    return get_job_by_idx(database_path, idx)


def update_job_execution_result(
    database_path: str | Path,
    idx: int,
    execution_result: str,
    state: int,
) -> Job | None:
    with get_connection(database_path) as connection:
        connection.execute(
            """
            UPDATE jobs
            SET execution_result = ?, state = ?
            WHERE idx = ?
            """,
            (execution_result, state, idx),
        )
        connection.commit()

    return get_job_by_idx(database_path, idx)
