"""Whatap webhook integration constants (not an AI agent)."""

WHATAP_EVENT_LOG_SOURCE = "whatap-events"

# Legacy agent-style ids kept for log/API compatibility only.
LEGACY_WHATAP_LOG_AGENT_IDS: frozenset[str] = frozenset({
    "sys-whatap-events",
    "whatap-event",
})

LEGACY_WHATAP_LOCAL_AGENT_IDS: frozenset[str] = frozenset(LEGACY_WHATAP_LOG_AGENT_IDS)

WHATAP_LOG_AGENT_IDS: frozenset[str] = frozenset({WHATAP_EVENT_LOG_SOURCE}) | LEGACY_WHATAP_LOG_AGENT_IDS


def is_whatap_log_agent_id(agent_id: str) -> bool:
    return agent_id.strip() in WHATAP_LOG_AGENT_IDS


def expand_whatap_log_filter_ids(agent_ids: frozenset[str]) -> frozenset[str]:
    if WHATAP_EVENT_LOG_SOURCE in agent_ids:
        return frozenset(agent_ids | WHATAP_LOG_AGENT_IDS)
    return agent_ids
