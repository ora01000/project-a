"""JSON contracts for Control Plane ↔ Agent Runtime HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.agents.base import AgentDefinition, AgentInvokeResult, ToolUsage


class ToolUsagePayload(BaseModel):
    name: str
    mcp_server: str | None = None


class AgentInvokeResultPayload(BaseModel):
    content: str
    tools_used: list[ToolUsagePayload] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class AgentDefinitionPayload(BaseModel):
    agent_id: str
    name: str
    role: str
    mcp_server_keys: list[str] = Field(default_factory=list)
    system_prompt: str


class RuntimeInvokeBody(BaseModel):
    message: str = Field(min_length=1)
    caller_agent_id: str | None = None
    trace_id: str | None = None
    control_plane_base_url: str | None = None


class RuntimePlannedStepBody(BaseModel):
    message: str = Field(min_length=1)
    tool_name: str | None = None
    tool_params: dict[str, Any] | None = None
    caller_agent_id: str | None = None
    trace_id: str | None = None
    control_plane_base_url: str | None = None


class ReloadAgentsBody(BaseModel):
    definitions: list[AgentDefinitionPayload] = Field(default_factory=list)


class RuntimeHealthResponse(BaseModel):
    agent_id: str
    status: str


def definition_to_payload(definition: AgentDefinition) -> AgentDefinitionPayload:
    return AgentDefinitionPayload(
        agent_id=definition.agent_id,
        name=definition.name,
        role=definition.role,
        mcp_server_keys=list(definition.mcp_server_keys),
        system_prompt=definition.system_prompt,
    )


def payload_to_definition(payload: AgentDefinitionPayload) -> AgentDefinition:
    return AgentDefinition(
        agent_id=payload.agent_id,
        name=payload.name,
        role=payload.role,
        mcp_server_keys=list(payload.mcp_server_keys),
        system_prompt=payload.system_prompt,
    )


def result_to_payload(result: AgentInvokeResult) -> AgentInvokeResultPayload:
    return AgentInvokeResultPayload(
        content=result.content,
        tools_used=[
            ToolUsagePayload(name=tool.name, mcp_server=tool.mcp_server)
            for tool in result.tools_used
        ],
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


def payload_to_result(payload: AgentInvokeResultPayload) -> AgentInvokeResult:
    return AgentInvokeResult(
        content=payload.content,
        tools_used=[
            ToolUsage(name=tool.name, mcp_server=tool.mcp_server)
            for tool in payload.tools_used
        ],
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
    )
