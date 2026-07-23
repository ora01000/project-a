"""User approval gate before regular agents query inventory in integrated chat."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable
from uuid import uuid4

from backend.app.agents.inventory_tool import INVENTORY_AGENT_ID

logger = logging.getLogger(__name__)

ApprovalCallback = Callable[[dict[str, Any]], Awaitable[None]]

_approval_callback: ContextVar[ApprovalCallback | None] = ContextVar(
    "inventory_approval_callback",
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


async def wait_for_inventory_approval(
    *,
    caller_agent_id: str,
    caller_agent_name: str,
    query: str,
) -> bool:
    callback = _approval_callback.get()
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
