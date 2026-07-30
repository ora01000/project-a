import type { HealthInfo, RuntimeCapabilities } from "../types/agent";

export const TOKEN_MANAGEMENT_DISABLED_MESSAGE =
  "토큰 사용량 조회·관리 기능이 비활성화되었습니다.";

export const AGENT_MANAGEMENT_DISABLED_MESSAGE =
  "에이전트 시스템프롬프트·도구 할당은 UI에서 제공하지 않습니다. Runtime(mock) 정적 정의를 사용합니다.";

export const MOCK_RUNTIME_UNAVAILABLE_MESSAGE =
  "Mock runtime은 질의/응답(invoke) API만 제공합니다. AGENT_RUNTIME_MODE=http 로 샌드박스 런타임을 연결하세요.";

const FULL_RUNTIME_CAPABILITIES: RuntimeCapabilities = {
  invoke: true,
  planned_step: true,
  health_summary: true,
  agent_tools: true,
  reload_definitions: true,
  job_submission: true,
};

const MOCK_RUNTIME_CAPABILITIES: RuntimeCapabilities = {
  invoke: true,
  planned_step: false,
  health_summary: false,
  agent_tools: false,
  reload_definitions: false,
  job_submission: false,
};

export function getRuntimeCapabilities(health: HealthInfo | null): RuntimeCapabilities {
  if (health?.runtime_capabilities) {
    return health.runtime_capabilities;
  }
  if (health?.runtime_mode === "mock" || health?.runtime_mode === "local") {
    return MOCK_RUNTIME_CAPABILITIES;
  }
  return FULL_RUNTIME_CAPABILITIES;
}

export function isInvokeOnlyRuntime(health: HealthInfo | null): boolean {
  const capabilities = getRuntimeCapabilities(health);
  return capabilities.invoke && !capabilities.planned_step;
}
