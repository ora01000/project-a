"""Parse raw HTTP request text and execute it for admin Postman debugging."""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

_REQUEST_LINE_RE = re.compile(
    r"^(?P<method>[A-Za-z]+)\s+(?P<target>\S+)(?:\s+HTTP/\d(?:\.\d)?)?\s*$"
)


class PostmanDebugError(ValueError):
    """Raised when call info cannot be parsed or sent."""


def parse_raw_http_request(raw: str) -> tuple[str, str, dict[str, str], str]:
    text = raw.replace("\r\n", "\n").strip()
    if not text:
        raise PostmanDebugError("호출정보가 비어 있습니다.")

    head, separator, body = text.partition("\n\n")
    if not separator:
        head, separator, body = text.partition("\n\r\n")
    if not separator:
        body = ""

    lines = [line for line in head.split("\n") if line.strip()]
    if not lines:
        raise PostmanDebugError("요청 첫 줄이 없습니다.")

    request_match = _REQUEST_LINE_RE.match(lines[0].strip())
    if request_match is None:
        raise PostmanDebugError(
            "첫 줄은 'METHOD URL' 또는 'METHOD URL HTTP/1.1' 형식이어야 합니다."
        )

    method = request_match.group("method").upper()
    target = request_match.group("target")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            raise PostmanDebugError(f"잘못된 헤더 형식입니다: {line}")
        name, value = line.split(":", 1)
        headers[name.strip()] = value.strip()

    if target.startswith("http://") or target.startswith("https://"):
        url = target
    else:
        host = headers.pop("Host", headers.pop("host", "")).strip()
        if not host:
            raise PostmanDebugError("상대 경로 URL인 경우 Host 헤더가 필요합니다.")
        path = target if target.startswith("/") else f"/{target}"
        scheme = "https" if host.endswith(":443") else "http"
        url = f"{scheme}://{host}{path}"

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PostmanDebugError(f"유효하지 않은 URL입니다: {url}")

    return method, url, headers, body


def format_http_response(
    *,
    status_code: int,
    reason: str,
    headers: dict[str, str],
    body: str,
    elapsed_ms: float,
) -> str:
    lines = [f"HTTP/1.1 {status_code} {reason}".strip(), f"Elapsed: {elapsed_ms:.0f}ms", ""]
    for key, value in headers.items():
        lines.append(f"{key}: {value}")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)


async def execute_raw_http_request(
    raw: str,
    *,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    method, url, headers, body = parse_raw_http_request(raw)
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            response = await client.request(
                method,
                url,
                headers=headers,
                content=body.encode("utf-8") if body else b"",
            )
    except httpx.TimeoutException as exc:
        raise PostmanDebugError(f"요청 시간이 초과되었습니다 ({timeout_seconds:.0f}s).") from exc
    except httpx.RequestError as exc:
        raise PostmanDebugError(f"요청 전송에 실패했습니다: {exc}") from exc

    elapsed_ms = (time.perf_counter() - started) * 1000
    response_text = response.text
    response_headers = {key: value for key, value in response.headers.items()}
    raw_response = format_http_response(
        status_code=response.status_code,
        reason=response.reason_phrase or "",
        headers=response_headers,
        body=response_text,
        elapsed_ms=elapsed_ms,
    )
    return {
        "status_code": response.status_code,
        "reason": response.reason_phrase or "",
        "headers": response_headers,
        "body": response_text,
        "elapsed_ms": round(elapsed_ms, 2),
        "raw_response": raw_response,
    }
