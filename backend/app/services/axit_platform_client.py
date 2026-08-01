"""HTTP client for AXIT platform agent runtime APIs."""

from __future__ import annotations

import base64
import logging
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
    build_agent_chat_url,
    get_agentruntime_by_agent_id,
    runtime_mode_for_type,
)
from backend.app.services.axit_config import (
    AXIT_ACCESS_TOKEN_TTL_SECONDS,
    resolve_axit_client_id,
    resolve_axit_client_secret,
    resolve_axit_credential_source,
    resolve_axit_token_url,
)

logger = logging.getLogger(__name__)


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


class AxitPlatformClient:
    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout_seconds = timeout_seconds
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

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
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
        if trace is None:
            return None
        if isinstance(trace, (dict, list)):
            return trace
        return None

    async def invoke(
        self,
        database_path: str | Path,
        request: AxitPlatformInvokeRequest,
        *,
        runtime_record: StoredAgentRuntime | None = None,
    ) -> AxitPlatformInvokeResult:
        runtime_mode = resolve_agent_runtime_mode()
        record = runtime_record or get_agentruntime_by_agent_id(
            database_path,
            request.axit_agent_id,
            runtime_mode=runtime_mode,
        )
        if record is None:
            raise ValueError(f"agentruntime record not found for agent_id={request.axit_agent_id!r}")

        service_id = (request.service_id or record.service_id).strip()
        session_id = (request.session_id or str(uuid4())).strip()
        runtime_mode = runtime_mode_for_type(record.type)
        token_url = resolve_axit_token_url(runtime_mode=runtime_mode)
        access_token = await self._fetch_access_token(token_url, runtime_mode=runtime_mode)

        invoke_url = build_agent_chat_url(record)
        body = {
            "service_id": service_id,
            "session_id": session_id,
            "session_attributes": request.session_attributes or {},
            "prompt_session_attributes": request.prompt_session_attributes or {},
            "enable_trace": request.enable_trace,
            "text": request.message,
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                invoke_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected invoke response from {invoke_url}")

        completion = self._extract_completion(payload)
        if not completion:
            raise RuntimeError(f"Invoke response missing text from {invoke_url}")

        retrieval_results = payload.get("retrieval_results")
        if not isinstance(retrieval_results, list):
            retrieval_results = []

        return AxitPlatformInvokeResult(
            session_id=str(payload.get("session_id") or session_id),
            service_id=str(payload.get("service_id") or service_id),
            completion=completion,
            retrieval_results=retrieval_results,
            trace=self._extract_trace(payload),
        )


def is_mockup_runtime(record: StoredAgentRuntime) -> bool:
    from backend.app.db.agentruntime import AGENTRUNTIME_TYPE_MOCKUP

    return record.type == AGENTRUNTIME_TYPE_MOCKUP


def is_external_runtime(record: StoredAgentRuntime) -> bool:
    return record.type == AGENTRUNTIME_TYPE_EXTERNAL
