"""User approval gate before regular agents query inventory in integrated chat."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable
from uuid import uuid4

import httpx

from backend.app.agents.inventory_tool import INVENTORY_AGENT_ID

logger = logging.getLogger(__name__)

ApprovalCallback = Callable[[dict[str, Any]], Awaitable[None]]

_approval_callback: ContextVar[ApprovalCallback | None] = ContextVar(
    "inventory_approval_callback",
    default=None,
)
_remote_approval_context: ContextVar[tuple[str, str] | None] = ContextVar(
    "remote_inventory_approval_context",
    default=None,
)


@dataclass
class _PendingApproval:
    caller_agent_id: str
    caller_agent_name: str
    query: str
    decision_event: asyncio.Event
    approved: bool = False


_pending: dict[str, _PendingApproval] = {}
_pending_lock = asyncio.Lock()
_runtime_sessions: dict[str, "_RuntimeApprovalSession"] = {}


@dataclass
class _RuntimeApprovalSession:
    callback: ApprovalCallback
    decision_event: asyncio.Event
    approved: bool = False


def requires_inventory_approval(caller_agent_id: str | None) -> bool:
    if not caller_agent_id:
        return False
    if caller_agent_id == INVENTORY_AGENT_ID:
        return False
    if caller_agent_id.startswith("sys-"):
        return False
    return True


@asynccontextmanager
async def inventory_approval_session(
    callback: ApprovalCallback,
) -> AsyncIterator[None]:
    token = _approval_callback.set(callback)
    try:
        yield
    finally:
        _approval_callback.reset(token)


@asynccontextmanager
async def runtime_inventory_approval_session(
    trace_id: str,
    callback: ApprovalCallback,
) -> AsyncIterator[None]:
    session = _RuntimeApprovalSession(
        callback=callback,
        decision_event=asyncio.Event(),
    )
    _runtime_sessions[trace_id] = session
    try:
        yield
    finally:
        _runtime_sessions.pop(trace_id, None)


@asynccontextmanager
async def remote_inventory_approval_context(
    control_plane: tuple[str, str] | None,
) -> AsyncIterator[None]:
    token = _remote_approval_context.set(control_plane)
    try:
        yield
    finally:
        _remote_approval_context.reset(token)


async def wait_for_inventory_approval(
    *,
    caller_agent_id: str,
    caller_agent_name: str,
    query: str,
) -> bool:
    callback = _approval_callback.get()
    remote_ctx = _remote_approval_context.get()
    if callback is None and remote_ctx is not None:
        return await _wait_for_remote_inventory_approval(
            control_plane_base_url=remote_ctx[0],
            trace_id=remote_ctx[1],
            caller_agent_id=caller_agent_id,
            caller_agent_name=caller_agent_name,
            query=query,
        )
    if callback is None:
        return True

    approval_id = uuid4().hex
    pending = _PendingApproval(
        caller_agent_id=caller_agent_id,
        caller_agent_name=caller_agent_name,
        query=query,
        decision_event=asyncio.Event(),
    )

    async with _pending_lock:
        _pending[approval_id] = pending

    try:
        await callback(
            {
                "approval_id": approval_id,
                "caller_agent_id": caller_agent_id,
                "caller_agent_name": caller_agent_name,
                "query": query,
            }
        )
        await pending.decision_event.wait()
        return pending.approved
    finally:
        async with _pending_lock:
            _pending.pop(approval_id, None)


def resolve_inventory_approval(approval_id: str, *, approved: bool) -> bool:
    pending = _pending.get(approval_id)
    if pending is None:
        return False
    pending.approved = approved
    pending.decision_event.set()
    logger.info(
        "Inventory approval %s for caller=%s",
        "granted" if approved else "denied",
        pending.caller_agent_id,
    )
    return True


def reject_all_pending() -> None:
    for pending in list(_pending.values()):
        pending.approved = False
        pending.decision_event.set()
    for session in list(_runtime_sessions.values()):
        session.approved = False
        session.decision_event.set()


async def request_runtime_inventory_approval(
    *,
    trace_id: str,
    caller_agent_id: str,
    caller_agent_name: str,
    query: str,
) -> bool:
    session = _runtime_sessions.get(trace_id)
    if session is None:
        logger.warning("Runtime inventory approval requested for unknown trace_id=%s", trace_id)
        return False

    approval_id = uuid4().hex
    pending = _PendingApproval(
        caller_agent_id=caller_agent_id,
        caller_agent_name=caller_agent_name,
        query=query,
        decision_event=asyncio.Event(),
    )

    async with _pending_lock:
        _pending[approval_id] = pending

    try:
        await session.callback(
            {
                "approval_id": approval_id,
                "caller_agent_id": caller_agent_id,
                "caller_agent_name": caller_agent_name,
                "query": query,
            }
        )
        await pending.decision_event.wait()
        return pending.approved
    finally:
        async with _pending_lock:
            _pending.pop(approval_id, None)


async def _wait_for_remote_inventory_approval(
    *,
    control_plane_base_url: str,
    trace_id: str,
    caller_agent_id: str,
    caller_agent_name: str,
    query: str,
) -> bool:
    url = f"{control_plane_base_url.rstrip('/')}/api/internal/runtime/inventory-approvals/request"
    headers: dict[str, str] = {}
    try:
        from backend.app.config import load_settings

        _, server_settings, _, _ = load_settings()
        if server_settings.agent_runtime_api_key:
            headers["X-Runtime-Api-Key"] = server_settings.agent_runtime_api_key
    except Exception:
        logger.exception("Failed to load runtime API key for inventory approval callback")
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                url,
                json={
                    "trace_id": trace_id,
                    "caller_agent_id": caller_agent_id,
                    "caller_agent_name": caller_agent_name,
                    "query": query,
                },
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            return bool(payload.get("approved"))
    except Exception:
        logger.exception(
            "Remote inventory approval failed (trace_id=%s caller=%s)",
            trace_id,
            caller_agent_id,
        )
        return False
