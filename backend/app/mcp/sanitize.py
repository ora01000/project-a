import logging
import types
from typing import Any

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

_KNOWN_PARAMETER_KEYS = {
    "namespace",
    "command",
    "name",
    "context",
    "resource",
    "field_selector",
    "label_selector",
    "modifies_resource",
}

_VALUE_PREFIXES_AFTER_NE = (
    "kubectl",
    "default",
    "kube-",
    "get ",
    "list ",
    "describe ",
    "{",
    "[",
)


def _should_strip_ne_prefix(original: str, candidate: str) -> bool:
    if not candidate:
        return False
    if candidate.startswith(_VALUE_PREFIXES_AFTER_NE):
        return True
    if candidate in {"default", "yes", "no", "unknown"}:
        return True
    return False


def sanitize_tool_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Remove a leading 'ne' corruption prefix from MCP tool arguments."""
    sanitized: dict[str, Any] = {}

    for key, value in arguments.items():
        clean_key = key
        if isinstance(key, str) and key.startswith("ne"):
            candidate_key = key[2:]
            if candidate_key in _KNOWN_PARAMETER_KEYS:
                clean_key = candidate_key
                logger.warning("Sanitized corrupted tool parameter key: %s -> %s", key, clean_key)

        if isinstance(value, str) and value.startswith("ne"):
            candidate_value = value[2:]
            if _should_strip_ne_prefix(value, candidate_value):
                logger.warning(
                    "Sanitized corrupted tool parameter value for %s: %s -> %s",
                    clean_key,
                    value,
                    candidate_value,
                )
                value = candidate_value

        sanitized[clean_key] = value

    return sanitized


def wrap_tool_with_argument_sanitizer(tool: BaseTool) -> BaseTool:
    original_parse_input = tool._parse_input

    def sanitized_parse_input(
        self: BaseTool,
        tool_input: str | dict[str, Any],
        tool_call_id: str | None = None,
    ) -> str | dict[str, Any]:
        if isinstance(tool_input, dict):
            tool_input = sanitize_tool_arguments(tool_input)
        return original_parse_input(tool_input, tool_call_id)

    object.__setattr__(tool, "_parse_input", types.MethodType(sanitized_parse_input, tool))
    return tool
