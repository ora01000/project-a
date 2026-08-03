"""Job request intake API (Teams / Power Automate inbound)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.db.jobs import JOB_STATUS_RECEIVED, JobRecord
from backend.app.services.job_intake import receive_job_request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


class JobIntakeRequest(BaseModel):
    job_title: str = Field(min_length=1, max_length=300)
    requester_name: str = Field(min_length=1, max_length=100)
    requester_email: str = Field(min_length=1, max_length=100)
    requester_depart: str = Field(min_length=1, max_length=100)
    job_content: str = Field(min_length=1)
    request_date: str = Field(min_length=1)
    madang_id: str = Field(min_length=1, max_length=50)
    team_id: str = Field(min_length=1, max_length=50)
    channel_id: str = Field(min_length=1, max_length=120)
    message_id: str = Field(min_length=1, max_length=50)


class JobIntakeResponse(BaseModel):
    idx: int
    srnum: str
    status_code: int
    received_at: str

    @classmethod
    def from_record(cls, record: JobRecord) -> "JobIntakeResponse":
        return cls(
            idx=record.idx,
            srnum=record.srnum,
            status_code=record.status_code,
            received_at=record.received_at,
        )


@router.post("/jobs", response_model=JobIntakeResponse, status_code=201)
async def submit_job_request(
    request: Request,
    body: JobIntakeRequest,
) -> JobIntakeResponse:
    database_path = request.app.state.database_path
    try:
        record = receive_job_request(database_path, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Job intake failed")
        raise HTTPException(status_code=500, detail="Failed to store job request") from exc

    if record.status_code != JOB_STATUS_RECEIVED:
        raise HTTPException(status_code=500, detail="Invalid job status after intake")

    return JobIntakeResponse.from_record(record)
