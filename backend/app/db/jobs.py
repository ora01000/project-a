from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection
from backend.app.db.job_datetime import build_sr_num, normalize_job_datetime, now_job_datetime

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
    sr_num,
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
    execution_result,
    actual_completion_time,
    approval_date,
    pending_date,
    reject_date
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
    actual_completion_time: str | None
    sr_num: str | None = None
    approval_date: str | None = None
    pending_date: str | None = None
    reject_date: str | None = None


def _optional_job_datetime(row, key: str) -> str | None:
    if key not in row.keys() or row[key] is None:
        return None
    value = str(row[key])
    try:
        return normalize_job_datetime(value)
    except ValueError:
        return value


def _row_to_job(row) -> Job:
    keys = row.keys()
    request_date = str(row["request_date"])
    completion_request_date = str(row["completion_request_date"])
    try:
        request_date = normalize_job_datetime(request_date)
    except ValueError:
        pass
    try:
        completion_request_date = normalize_job_datetime(completion_request_date)
    except ValueError:
        pass

    actual_completion_time = _optional_job_datetime(row, "actual_completion_time")

    sr_num = None
    if "sr_num" in keys and row["sr_num"] is not None:
        value = str(row["sr_num"]).strip()
        sr_num = value or None

    return Job(
        idx=int(row["idx"]),
        request_date=request_date,
        job_title=str(row["job_title"]),
        request_depart=str(row["request_depart"]),
        requester=str(row["requester"]),
        requester_email=str(row["requester_email"]),
        completion_request_date=completion_request_date,
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
        actual_completion_time=actual_completion_time,
        sr_num=sr_num,
        approval_date=_optional_job_datetime(row, "approval_date"),
        pending_date=_optional_job_datetime(row, "pending_date"),
        reject_date=_optional_job_datetime(row, "reject_date"),
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


def list_jobs_by_approver(
    database_path: str | Path,
    *,
    userid: str,
    username: str,
) -> list[Job]:
    """Jobs where approver matches userid (username kept for legacy rows)."""
    candidates = [value.strip() for value in (userid, username) if value and value.strip()]
    if not candidates:
        return []

    unique_candidates = list(dict.fromkeys(candidates))
    placeholders = ", ".join("?" for _ in unique_candidates)
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT {JOB_SELECT_COLUMNS}
            FROM jobs
            WHERE approver IN ({placeholders})
            ORDER BY idx DESC
            """,
            unique_candidates,
        ).fetchall()
    return [_row_to_job(row) for row in rows]


def list_jobs_for_participant(
    database_path: str | Path,
    *,
    userid: str,
    username: str = "",
) -> list[Job]:
    """Jobs where the user is requester or approver (userid; username for legacy rows)."""
    candidates = [value.strip() for value in (userid, username) if value and value.strip()]
    if not candidates:
        return []

    unique_candidates = list(dict.fromkeys(candidates))
    placeholders = ", ".join("?" for _ in unique_candidates)
    params = [*unique_candidates, *unique_candidates]
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT {JOB_SELECT_COLUMNS}
            FROM jobs
            WHERE requester IN ({placeholders})
               OR approver IN ({placeholders})
            ORDER BY idx DESC
            """,
            params,
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
    actual_completion_time: str | None = None,
) -> Job:
    normalized_request_date = normalize_job_datetime(request_date)
    normalized_completion_request_date = normalize_job_datetime(completion_request_date)
    normalized_actual = (
        normalize_job_datetime(actual_completion_time) if actual_completion_time else None
    )
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
                notify_channel,
                actual_completion_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_request_date,
                job_title.strip(),
                request_depart.strip(),
                requester.strip(),
                requester_email.strip(),
                normalized_completion_request_date,
                job_description,
                approver.strip(),
                state,
                notify_channel,
                normalized_actual,
            ),
        )
        idx = int(cursor.lastrowid)
        sr_num = build_sr_num(normalized_request_date, idx)
        connection.execute(
            """
            UPDATE jobs
            SET sr_num = ?
            WHERE idx = ?
            """,
            (sr_num, idx),
        )
        connection.commit()

    job = get_job_by_idx(database_path, idx)
    if job is None:
        raise RuntimeError("Failed to load created job")
    return job


def update_job_state(database_path: str | Path, idx: int, state: int) -> Job | None:
    set_parts = ["state = ?"]
    params: list[object] = [state]

    if state == JOB_STATE_APPROVED:
        set_parts.append("approval_date = ?")
        params.append(now_job_datetime())
    elif state == JOB_STATE_PENDING:
        set_parts.append("pending_date = ?")
        params.append(now_job_datetime())
    elif state == JOB_STATE_REJECTED:
        set_parts.append("reject_date = ?")
        params.append(now_job_datetime())

    params.append(idx)
    with get_connection(database_path) as connection:
        connection.execute(
            f"""
            UPDATE jobs
            SET {", ".join(set_parts)}
            WHERE idx = ?
            """,
            tuple(params),
        )
        connection.commit()

    return get_job_by_idx(database_path, idx)


def get_job_notification_times(
    database_path: str | Path,
    job_idxs: list[int],
) -> dict[int, dict[str, str | None]]:
    if not job_idxs:
        return {}

    unique_idxs = sorted({int(value) for value in job_idxs})
    placeholders = ", ".join("?" for _ in unique_idxs)
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT idx, request_date, actual_completion_time
            FROM jobs
            WHERE idx IN ({placeholders})
            """,
            tuple(unique_idxs),
        ).fetchall()

    result: dict[int, dict[str, str | None]] = {}
    for row in rows:
        job_idx = int(row["idx"])
        request_date = str(row["request_date"])
        try:
            request_date = normalize_job_datetime(request_date)
        except ValueError:
            pass
        result[job_idx] = {
            "request_date": request_date,
            "actual_completion_time": _optional_job_datetime(row, "actual_completion_time"),
        }
    return result


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
    *,
    actual_completion_time: str | None = None,
) -> Job | None:
    """Persist execution payload/state. Sets actual_completion_time when provided or on COMPLETED."""
    completion_time = actual_completion_time
    if completion_time is None and state == JOB_STATE_COMPLETED:
        completion_time = now_job_datetime()
    elif completion_time is not None:
        completion_time = normalize_job_datetime(completion_time)

    with get_connection(database_path) as connection:
        if completion_time is not None:
            connection.execute(
                """
                UPDATE jobs
                SET execution_result = ?,
                    state = ?,
                    actual_completion_time = ?
                WHERE idx = ?
                """,
                (execution_result, state, completion_time, idx),
            )
        else:
            connection.execute(
                """
                UPDATE jobs
                SET execution_result = ?,
                    state = ?
                WHERE idx = ?
                """,
                (execution_result, state, idx),
            )
        connection.commit()

    return get_job_by_idx(database_path, idx)


def delete_job_by_idx(database_path: str | Path, idx: int) -> bool:
    with get_connection(database_path) as connection:
        cursor = connection.execute("DELETE FROM jobs WHERE idx = ?", (idx,))
        connection.commit()
        return int(cursor.rowcount) > 0
