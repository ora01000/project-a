"""Static mock-platform orchestrator agents (mock runtime only)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.agents.base import AgentDefinition
from backend.app.agents.infra_diagram_prompt import (
    INFRA_D2_ANALYSIS_GUIDELINES,
    INFRA_D2_MANIFEST_SHAPE_MAPPING,
    INFRA_D2_NODE_LABEL_RULE,
)
from backend.app.db.agentruntime import ORCHESTRATOR_LOCAL_AGENT_IDS, MockAgentRuntimePreset

CALLABLE_INFRA_AGENT_IDS: tuple[str, ...] = (
    "dprv-k8s",
    "dprv6-k8s",
    "pcicd-k8s",
    "dprmn-k8s",
    "dtest-k8s",
    "dpvs-k8s",
    "dprsv-k8s",
    "dprrt-k8s",
    "dkvrt-k8s",
)

# Plan lists dkvrt-k8s; catalog uses kubevirt.
CALLABLE_AGENT_ID_ALIASES: dict[str, str] = {
    "dkvrt-k8s": "kubevirt",
}


@dataclass(frozen=True)
class MockPlatformAgentSpec:
    agent_id: str
    agent_name: str
    description: str
    system_prompt: str
    callable_agent_ids: tuple[str, ...] = CALLABLE_INFRA_AGENT_IDS

    def to_agent_definition(self) -> AgentDefinition:
        return AgentDefinition(
            agent_id=self.agent_id,
            name=self.agent_name,
            role=self.description,
            mcp_server_keys=[],
            system_prompt=self.system_prompt,
        )

    def to_runtime_preset(self) -> MockAgentRuntimePreset:
        return MockAgentRuntimePreset(
            agent_name=self.agent_name,
            local_agent_id=self.agent_id,
            description=self.description,
        )


MOCK_PLATFORM_AGENT_SPECS: tuple[MockPlatformAgentSpec, ...] = (
    MockPlatformAgentSpec(
        agent_id="job-scheduler",
        agent_name="작업 접수/계획",
        description="채널을 통해 작업 요청을 수신/계획 수립",
        system_prompt="You receive and plan tasks via a channel. Analyze the user's request and plan the task.",
    ),
    MockPlatformAgentSpec(
        agent_id="archi-analysis",
        agent_name="아키텍처 분석",
        description="인프라의 설계 구성 분석/도식화",
        system_prompt=(
            "You are an agent that analyzes and visualizes infrastructure architecture.\n"
            "1. Select an appropriate agent capable of extracting information about the requested "
            "infrastructure and delegate to that agent.\n"
            "2. Do not answer directly; the delegated infra agent will query resources and "
            "produce the final response including a D2 diagram when applicable.\n"
            "3. When a D2 diagram is produced, the infra agent must use these manifest-specific "
            "node shapes:\n"
            f"{INFRA_D2_MANIFEST_SHAPE_MAPPING}\n"
            f"4. {INFRA_D2_NODE_LABEL_RULE}\n"
            "5. When delegating diagram work, ensure the infra agent follows these analysis "
            "guidelines:\n"
            f"{INFRA_D2_ANALYSIS_GUIDELINES}"
        ),
    ),
    MockPlatformAgentSpec(
        agent_id="helpdesk",
        agent_name="헬프데스크",
        description="문의응대",
        system_prompt="You are an agent that handles infrastructure inquiries. When you receive a user request, identify the infrastructure and call the appropriate agent to provide a correct answer.",
    ),
)

MOCK_PLATFORM_AGENT_SPECS_BY_ID: dict[str, MockPlatformAgentSpec] = {
    spec.agent_id: spec for spec in MOCK_PLATFORM_AGENT_SPECS
}

MOCK_PLATFORM_AGENT_IDS: frozenset[str] = frozenset(MOCK_PLATFORM_AGENT_SPECS_BY_ID.keys())

MOCK_AGENTRUNTIME_EXTRA_PRESETS: list[MockAgentRuntimePreset] = [
    spec.to_runtime_preset() for spec in MOCK_PLATFORM_AGENT_SPECS
]


def is_mock_platform_orchestrator_agent(agent_id: str) -> bool:
    return agent_id.strip() in ORCHESTRATOR_LOCAL_AGENT_IDS


def get_mock_platform_agent_spec(agent_id: str) -> MockPlatformAgentSpec | None:
    return MOCK_PLATFORM_AGENT_SPECS_BY_ID.get(agent_id.strip())


def resolve_callable_catalog_agent_ids(
    spec: MockPlatformAgentSpec,
    *,
    available_agent_ids: set[str],
) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for raw_agent_id in spec.callable_agent_ids:
        mapped_id = CALLABLE_AGENT_ID_ALIASES.get(raw_agent_id, raw_agent_id)
        if mapped_id in available_agent_ids and mapped_id not in seen:
            resolved.append(mapped_id)
            seen.add(mapped_id)
    return resolved


def load_mock_platform_agent_definitions() -> list[AgentDefinition]:
    return [spec.to_agent_definition() for spec in MOCK_PLATFORM_AGENT_SPECS]
