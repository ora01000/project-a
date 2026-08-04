"""HTTP client for AXIT platform agent runtime APIs."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pathlib import Path

import httpx

from backend.app.config import resolve_agent_runtime_mode
from backend.app.db.agentruntime import (
    AGENTRUNTIME_TYPE_EXTERNAL,
    StoredAgentRuntime,
    axit_runtime_api_family,
    build_axit_invoke_url,
    build_axit_invocations_url,
    get_agentruntime_by_agent_id,
    runtime_mode_for_type,
)
from backend.app.services.axit_config import (
    AXIT_ACCESS_TOKEN_TTL_SECONDS,
    resolve_axit_client_id,
    resolve_axit_client_secret,
    resolve_axit_credential_source,
    resolve_axit_service_id,
    resolve_axit_token_url,
)

logger = logging.getLogger(__name__)

_UUID_SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _normalize_axit_session_id(session_id: str | None) -> str:
    candidate = (session_id or "").strip()
    if _UUID_SESSION_ID_RE.match(candidate):
        return candidate
    if candidate:
        logger.warning(
            "AXIT session_id is not UUID format; generating new id (received=%r)",
            candidate,
        )
    return str(uuid4())

DEFAULT_AXIT_HTTP_TIMEOUT_SECONDS = 3600.0
DEFAULT_AXIT_TOKEN_TIMEOUT_SECONDS = 60.0
DEFAULT_AXIT_POLL_INTERVAL_SECONDS = 3.0
DEFAULT_AXIT_POLL_MAX_ATTEMPTS = 100  # 3s × 100 ≈ 5분

_PENDING_INVOCATION_STATUSES = frozenset({"running", "pending"})


def _invocation_status(payload: dict[str, Any]) -> str:
    raw = (
        payload.get("agent_invocation_status")
        or payload.get("orchestrator_invocation_status")
        or ""
    )
    return str(raw).strip().lower()


def _invocation_id(payload: dict[str, Any]) -> str:
    raw = (
        payload.get("agent_invocation_id")
        or payload.get("orchestrator_invocation_id")
        or ""
    )
    return str(raw).strip()


def build_axit_http_timeout(timeout_seconds: float) -> httpx.Timeout:
    """Long read timeout for AXIT agent invoke; keep connect/write bounded."""
    read_timeout = max(1.0, float(timeout_seconds))
    return httpx.Timeout(connect=30.0, read=read_timeout, write=60.0, pool=30.0)


def build_axit_token_http_timeout(timeout_seconds: float = DEFAULT_AXIT_TOKEN_TIMEOUT_SECONDS) -> httpx.Timeout:
    read_timeout = max(5.0, float(timeout_seconds))
    return httpx.Timeout(connect=15.0, read=read_timeout, write=15.0, pool=15.0)


class AxitInvokeError(RuntimeError):
    """AXIT invoke failed before a successful completion payload was parsed."""

    def __init__(
        self,
        message: str,
        *,
        elapsed_seconds: float,
        invoke_url: str = "",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.elapsed_seconds = elapsed_seconds
        self.invoke_url = invoke_url
        self.status_code = status_code


class AxitGatewayTimeoutError(AxitInvokeError):
    """AXIT API gateway returned 504 while upstream agent work may still be running."""


class AxitInvokeTimeoutError(AxitInvokeError):
    """Backend httpx client timed out waiting for AXIT invoke response."""


class AxitInvocationPollTimeoutError(AxitInvokeError):
    """Polling for invocation completion exceeded max attempts."""


def format_axit_invoke_error(exc: Exception) -> str:
    if isinstance(exc, AxitInvocationPollTimeoutError):
        return (
            "AXIT 에이전트 응답 폴링 시간이 초과되었습니다 "
            f"({exc.elapsed_seconds:.0f}초). 잠시 후 다시 시도해 주세요."
        )
    if isinstance(exc, AxitGatewayTimeoutError):
        return (
            "AXIT 플랫폼 게이트웨이가 응답 대기 중 504 Gateway Timeout을 반환했습니다. "
            f"경과 {exc.elapsed_seconds:.0f}초. 에이전트는 백그라운드에서 계속 처리 중일 수 있습니다."
        )
    if isinstance(exc, AxitInvokeTimeoutError):
        return (
            "AXIT invoke 응답 대기 시간이 초과되었습니다 "
            f"({exc.elapsed_seconds:.0f}초). AGENT_RUNTIME_HTTP_TIMEOUT_SECONDS 설정을 확인하세요."
        )
    if isinstance(exc, AxitInvokeError):
        status = f" HTTP {exc.status_code}" if exc.status_code is not None else ""
        return f"AXIT invoke 실패{status}: {exc} (경과 {exc.elapsed_seconds:.0f}초)"
    return str(exc)


class AxitTokenError(RuntimeError):
    """Raised when AXIT platform token issuance fails."""


@dataclass(frozen=True)
class AxitPlatformInvokeRequest:
    axit_agent_id: str
    message: str
    service_id: str | None = None
    session_id: str | None = None
    session_attributes: dict[str, Any] | None = None
    prompt_session_attributes: dict[str, Any] | None = None
    enable_trace: bool = False


@dataclass(frozen=True)
class AxitPlatformInvokeResult:
    session_id: str
    service_id: str
    completion: str
    retrieval_results: list[Any]
    trace: Any | None = None


@dataclass
class _CachedAccessToken:
    access_token: str
    expires_at: float


@dataclass(frozen=True)
class _InvokeContext:
    record: StoredAgentRuntime
    service_id: str
    session_id: str
    runtime_mode: str
    access_token: str
    invoke_url: str
    invocations_url: str
    body: dict[str, Any]


class AxitPlatformClient:
    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout_seconds: float = DEFAULT_AXIT_HTTP_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_AXIT_POLL_INTERVAL_SECONDS,
        poll_max_attempts: int = DEFAULT_AXIT_POLL_MAX_ATTEMPTS,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout_seconds = max(1.0, float(timeout_seconds))
        self._invoke_http_timeout = build_axit_http_timeout(self._timeout_seconds)
        self._token_http_timeout = build_axit_token_http_timeout()
        self._poll_http_timeout = build_axit_token_http_timeout(60.0)
        self._poll_interval_seconds = max(0.5, float(poll_interval_seconds))
        self._poll_max_attempts = max(1, int(poll_max_attempts))
        self._token_cache: dict[str, _CachedAccessToken] = {}

    def _resolve_client_id(self, runtime_mode: str) -> str:
        if self._client_id:
            return self._client_id
        return resolve_axit_client_id(runtime_mode=runtime_mode)

    def _resolve_client_secret(self, runtime_mode: str) -> str:
        if self._client_secret:
            return self._client_secret
        return resolve_axit_client_secret(runtime_mode=runtime_mode)

    def _basic_auth_header(self, runtime_mode: str) -> str:
        client_id = self._resolve_client_id(runtime_mode)
        client_secret = self._resolve_client_secret(runtime_mode)
        encoded = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
        return f"Basic {encoded}"

    async def _fetch_access_token(self, token_url: str, *, runtime_mode: str) -> str:
        cached = self._token_cache.get(token_url)
        now = time.time()
        if cached is not None and cached.expires_at > now:
            logger.info(
                "AXIT token cache hit: method=POST url=%s runtime_mode=%s expires_in_sec=%.0f",
                token_url,
                runtime_mode,
                cached.expires_at - now,
            )
            return cached.access_token

        client_id = self._resolve_client_id(runtime_mode)
        credential_source = resolve_axit_credential_source()
        request_body = {"grant_type": "client_credentials"}
        logger.info(
            "AXIT token request start: method=POST url=%s runtime_mode=%s client_id=%s "
            "credential_source=%s grant_type=%s content_type=application/x-www-form-urlencoded",
            token_url,
            runtime_mode,
            client_id,
            credential_source,
            request_body["grant_type"],
        )

        async with httpx.AsyncClient(timeout=self._token_http_timeout) as client:
            response = await client.post(
                token_url,
                headers={
                    "Authorization": self._basic_auth_header(runtime_mode),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=request_body,
            )
            logger.info(
                "AXIT token response received: method=POST url=%s status=%s reason=%s",
                token_url,
                response.status_code,
                response.reason_phrase,
            )
            if response.status_code >= 400:
                body_preview = response.text.strip()[:500]
                logger.error(
                    "AXIT token request failed: method=POST url=%s status=%s client_id=%s "
                    "credential_source=%s body=%s",
                    token_url,
                    response.status_code,
                    client_id,
                    credential_source,
                    body_preview,
                )
                raise AxitTokenError(
                    f"Token issuance failed ({response.status_code}) for {token_url}: {body_preview or response.reason_phrase}"
                ) from None
            payload = response.json()

        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected token response from {token_url}")

        access_token = str(payload.get("access_token", "")).strip()
        if not access_token or access_token.lower() == "null":
            logger.error(
                "AXIT token response missing access_token: method=POST url=%s payload_keys=%s",
                token_url,
                sorted(payload.keys()),
            )
            raise RuntimeError(f"Token issuance failed: access_token missing from {token_url}")

        expires_in_raw = payload.get("expires_in", AXIT_ACCESS_TOKEN_TTL_SECONDS)
        try:
            expires_in = int(expires_in_raw)
        except (TypeError, ValueError):
            expires_in = AXIT_ACCESS_TOKEN_TTL_SECONDS
        expires_at = now + max(60, min(expires_in, AXIT_ACCESS_TOKEN_TTL_SECONDS))

        self._token_cache[token_url] = _CachedAccessToken(
            access_token=access_token,
            expires_at=expires_at,
        )
        logger.info(
            "AXIT token request success: method=POST url=%s expires_in=%s token_type=%s",
            token_url,
            expires_in,
            payload.get("token_type", "Bearer"),
        )
        return access_token

    @staticmethod
    def _extract_completion(payload: dict[str, Any]) -> str:
        completion = str(payload.get("text") or payload.get("completion") or "").strip()
        if not completion and isinstance(payload.get("result"), dict):
            completion = str(payload["result"].get("text") or "").strip()
        return completion

    @staticmethod
    def _extract_trace(payload: dict[str, Any]) -> Any | None:
        trace = payload.get("trace")
        if trace is None and isinstance(payload.get("result"), dict):
            trace = payload["result"].get("trace")
        if trace is None:
            return None
        if isinstance(trace, (dict, list)):
            return trace
        return None

    @staticmethod
    def _extract_retrieval_results(payload: dict[str, Any]) -> list[Any]:
        retrieval_results = payload.get("retrieval_results")
        if not isinstance(retrieval_results, list):
            retrieval_results = []
        return retrieval_results

    def _result_from_payload(
        self,
        payload: dict[str, Any],
        *,
        session_id: str,
        service_id: str,
    ) -> AxitPlatformInvokeResult:
        completion = self._extract_completion(payload)
        if not completion:
            raise RuntimeError("Invoke response missing text")

        return AxitPlatformInvokeResult(
            session_id=str(payload.get("session_id") or session_id),
            service_id=str(payload.get("service_id") or service_id),
            completion=completion,
            retrieval_results=self._extract_retrieval_results(payload),
            trace=self._extract_trace(payload),
        )

    async def _prepare_invoke_context(
        self,
        database_path: str | Path,
        request: AxitPlatformInvokeRequest,
        *,
        runtime_record: StoredAgentRuntime | None = None,
    ) -> _InvokeContext:
        if runtime_record is None:
            record = get_agentruntime_by_agent_id(
                database_path,
                request.axit_agent_id,
                runtime_mode=resolve_agent_runtime_mode(),
            )
        else:
            record = runtime_record
        if record is None:
            raise ValueError(f"agentruntime record not found for agent_id={request.axit_agent_id!r}")

        service_id = (request.service_id or record.service_id or resolve_axit_service_id()).strip()
        if not service_id:
            raise ValueError(
                f"service_id is required for AXIT invoke (agent_id={request.axit_agent_id!r})",
            )
        session_id = _normalize_axit_session_id(request.session_id)
        record_runtime_mode = runtime_mode_for_type(record.type)
        token_url = resolve_axit_token_url(runtime_mode=record_runtime_mode)
        access_token = await self._fetch_access_token(token_url, runtime_mode=record_runtime_mode)

        body = {
            "service_id": service_id,
            "session_id": session_id,
            "session_attributes": request.session_attributes or {},
            "prompt_session_attributes": request.prompt_session_attributes or {},
            "enable_trace": request.enable_trace,
            "text": request.message,
        }
        return _InvokeContext(
            record=record,
            service_id=service_id,
            session_id=session_id,
            runtime_mode=record_runtime_mode,
            access_token=access_token,
            invoke_url=build_axit_invoke_url(record),
            invocations_url=build_axit_invocations_url(record),
            body=body,
        )

    async def _fetch_invocation_latest(
        self,
        client: httpx.AsyncClient,
        *,
        invocations_url: str,
        access_token: str,
        session_id: str,
        service_id: str,
    ) -> dict[str, Any] | None:
        response = await client.get(
            invocations_url,
            params={
                "service_id": service_id,
                "session_id": session_id,
                "latest": "true",
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        if response.status_code >= 400:
            body_preview = response.text.strip()[:300]
            logger.warning(
                "AXIT invocation latest failed: url=%s status=%s body=%s",
                invocations_url,
                response.status_code,
                body_preview,
            )
            return None

        try:
            payload = response.json()
        except ValueError:
            logger.warning("AXIT invocation latest returned non-JSON: url=%s", invocations_url)
            return None

        if not isinstance(payload, dict):
            return None
        return payload

    async def _fetch_invocation_info(
        self,
        client: httpx.AsyncClient,
        *,
        invocations_url: str,
        access_token: str,
        agent_invocation_id: str,
        service_id: str,
    ) -> dict[str, Any]:
        detail_url = f"{invocations_url.rstrip('/')}/{agent_invocation_id.strip()}"
        response = await client.get(
            detail_url,
            params={"service_id": service_id},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        if response.status_code >= 400:
            body_preview = response.text.strip()[:500]
            raise AxitInvokeError(
                f"Invocation detail failed with HTTP {response.status_code}: {body_preview or response.reason_phrase}",
                elapsed_seconds=0.0,
                invoke_url=detail_url,
                status_code=response.status_code,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Unexpected non-JSON invocation detail from {detail_url}") from exc

        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected invocation detail from {detail_url}")
        return payload

    async def _poll_invocation_until_complete(
        self,
        context: _InvokeContext,
        *,
        started_at: float,
    ) -> AxitPlatformInvokeResult:
        logger.info(
            "AXIT invoke polling start: agent_id=%s api=%s service_id=%s session_id=%s url=%s "
            "interval=%ss max_attempts=%s",
            context.record.agent_id,
            axit_runtime_api_family(context.record),
            context.service_id,
            context.session_id,
            context.invocations_url,
            self._poll_interval_seconds,
            self._poll_max_attempts,
        )

        async with httpx.AsyncClient(timeout=self._poll_http_timeout) as client:
            for attempt in range(1, self._poll_max_attempts + 1):
                if attempt > 1:
                    await asyncio.sleep(self._poll_interval_seconds)

                latest = await self._fetch_invocation_latest(
                    client,
                    invocations_url=context.invocations_url,
                    access_token=context.access_token,
                    session_id=context.session_id,
                    service_id=context.service_id,
                )
                if latest is None:
                    logger.info("AXIT poll attempt %s/%s: no invocation record yet", attempt, self._poll_max_attempts)
                    continue

                status = _invocation_status(latest)
                if not status:
                    logger.info("AXIT poll attempt %s/%s: empty invocation status", attempt, self._poll_max_attempts)
                    continue

                if status in _PENDING_INVOCATION_STATUSES:
                    logger.info(
                        "AXIT poll attempt %s/%s: status=%s (waiting)",
                        attempt,
                        self._poll_max_attempts,
                        status,
                    )
                    continue

                invocation_id = _invocation_id(latest)
                if not invocation_id:
                    logger.warning(
                        "AXIT poll attempt %s/%s: status=%s but invocation id missing",
                        attempt,
                        self._poll_max_attempts,
                        status,
                    )
                    continue

                detail = await self._fetch_invocation_info(
                    client,
                    invocations_url=context.invocations_url,
                    access_token=context.access_token,
                    agent_invocation_id=invocation_id,
                    service_id=context.service_id,
                )
                elapsed = time.monotonic() - started_at
                logger.info(
                    "AXIT invoke completed via polling: agent_id=%s invocation_id=%s "
                    "status=%s attempts=%s elapsed=%.1fs",
                    context.record.agent_id,
                    invocation_id,
                    status,
                    attempt,
                    elapsed,
                )
                return self._result_from_payload(
                    detail,
                    session_id=context.session_id,
                    service_id=context.service_id,
                )

        elapsed = time.monotonic() - started_at
        raise AxitInvocationPollTimeoutError(
            (
                f"AXIT invocation polling timed out after {self._poll_max_attempts} attempts "
                f"(interval={self._poll_interval_seconds:.0f}s)"
            ),
            elapsed_seconds=elapsed,
            invoke_url=context.invocations_url,
        )

    async def invoke(
        self,
        database_path: str | Path,
        request: AxitPlatformInvokeRequest,
        *,
        runtime_record: StoredAgentRuntime | None = None,
    ) -> AxitPlatformInvokeResult:
        context = await self._prepare_invoke_context(
            database_path,
            request,
            runtime_record=runtime_record,
        )
        started_at = time.monotonic()
        logger.info(
            "AXIT invoke start: agent_id=%s api=%s is_orchestrator=%s url=%s runtime_mode=%s "
            "read_timeout=%ss service_id=%s session_id=%s",
            context.record.agent_id,
            axit_runtime_api_family(context.record),
            context.record.is_orchestrator,
            context.invoke_url,
            context.runtime_mode,
            self._timeout_seconds,
            context.service_id,
            context.session_id,
        )

        try:
            async with httpx.AsyncClient(timeout=self._invoke_http_timeout) as client:
                response = await client.post(
                    context.invoke_url,
                    headers={
                        "Authorization": f"Bearer {context.access_token}",
                        "Content-Type": "application/json",
                    },
                    json=context.body,
                )
        except httpx.TimeoutException as exc:
            elapsed = time.monotonic() - started_at
            logger.error(
                "AXIT invoke client timeout: url=%s elapsed=%.1fs read_timeout=%ss error=%s",
                context.invoke_url,
                elapsed,
                self._timeout_seconds,
                exc,
            )
            raise AxitInvokeTimeoutError(
                f"AXIT invoke timed out after {elapsed:.1f}s (read_timeout={self._timeout_seconds:.0f}s)",
                elapsed_seconds=elapsed,
                invoke_url=context.invoke_url,
            ) from exc
        except httpx.RequestError as exc:
            elapsed = time.monotonic() - started_at
            logger.error(
                "AXIT invoke transport error: url=%s elapsed=%.1fs error=%s",
                context.invoke_url,
                elapsed,
                exc,
            )
            raise AxitInvokeError(
                f"AXIT invoke transport error: {exc}",
                elapsed_seconds=elapsed,
                invoke_url=context.invoke_url,
            ) from exc

        elapsed = time.monotonic() - started_at
        if response.status_code == 504:
            body_preview = response.text.strip()[:500]
            logger.warning(
                "AXIT invoke gateway timeout (504): url=%s elapsed=%.1fs body=%s — starting polling",
                context.invoke_url,
                elapsed,
                body_preview,
            )
            return await self._poll_invocation_until_complete(context, started_at=started_at)

        if response.status_code >= 400:
            body_preview = response.text.strip()[:500]
            logger.error(
                "AXIT invoke HTTP error: url=%s status=%s elapsed=%.1fs body=%s",
                context.invoke_url,
                response.status_code,
                elapsed,
                body_preview,
            )
            raise AxitInvokeError(
                f"AXIT invoke failed with HTTP {response.status_code}: {body_preview or response.reason_phrase}",
                elapsed_seconds=elapsed,
                invoke_url=context.invoke_url,
                status_code=response.status_code,
            )

        logger.info(
            "AXIT invoke success: agent_id=%s status=%s elapsed=%.1fs",
            context.record.agent_id,
            response.status_code,
            elapsed,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Unexpected non-JSON invoke response from {context.invoke_url}") from exc

        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected invoke response from {context.invoke_url}")

        return self._result_from_payload(
            payload,
            session_id=context.session_id,
            service_id=context.service_id,
        )


def is_mockup_runtime(record: StoredAgentRuntime) -> bool:
    from backend.app.db.agentruntime import AGENTRUNTIME_TYPE_MOCKUP

    return record.type == AGENTRUNTIME_TYPE_MOCKUP


def is_external_runtime(record: StoredAgentRuntime) -> bool:
    return record.type == AGENTRUNTIME_TYPE_EXTERNAL
