"""Parse JOB_REQUEST_HELPER JSON payload ({title, form})."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JobRequestHelperDraft:
    title: str
    form: str


def parse_job_request_helper_content(content: str) -> JobRequestHelperDraft:
    text = (content or "").strip()
    if not text:
        raise ValueError("empty JOB_REQUEST_HELPER response")

    decoder = json.JSONDecoder()
    payload: dict[str, Any] | None = None
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and ("title" in parsed or "form" in parsed):
            payload = parsed
            break

    if payload is None:
        # Fallback: treat whole response as form body when JSON is missing.
        return JobRequestHelperDraft(title="", form=text)

    title = str(payload.get("title") or "").strip()
    form = str(payload.get("form") or "").strip()
    if not title and not form:
        raise ValueError("JOB_REQUEST_HELPER JSON missing title/form")
    return JobRequestHelperDraft(title=title, form=form)
