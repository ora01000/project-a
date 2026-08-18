# Backend ↔ Agent 인터페이스

Control Plane과 에이전트 실행 경로의 **현재 계약**만 정리합니다.  
배포·멀티 파드는 [ARCHITECTURE_MULTIPOD.md](ARCHITECTURE_MULTIPOD.md), mock 기능 제한 표는 [MOCK_RUNTIME.md](MOCK_RUNTIME.md), 온보딩·토폴로지는 [README.md](../README.md)를 참고하세요.

---

## 1. 역할 분리

```
Frontend
   │  /api/agents/{id}/chat  (SSE)
   ▼
Control Plane (FastAPI, backend/app/main.py)
   │  app.state.agent_manager   — 카탈로그·헬스·마커
   │  app.state.agent_runtime  — 실행 위임 (factory)
   ├─ mock → MockAgentRuntimeClient
   │           ├─ agentruntime(type=0) 있으면 AXIT mock HTTP
   │           └─ 없으면 LocalAgentRuntimeClient (in-process LangGraph)
   └─ http → ExternalAxitRuntimeClient → 외부 AXIT
```

| 구성 | 책임 |
|------|------|
| **AgentManager** | 정의/카탈로그 로드, operation·health 상태, mock에서 LangGraph 빌드, http에서 `REMOTE_AGENT_MARKER` |
| **agent_runtime** | `invoke` 등 실행 API. `create_agent_runtime_client(AGENT_RUNTIME_MODE)` |
| **agentruntime 테이블** | AXIT 연결 카탈로그 (`type` 0=mock, 1=http) |
| **INFRA_GAP_ANALYSIS** | 카탈로그·채팅 경로 **밖**. 별도 `/api/infra-gap-analysis/*` |

Control Plane은 채팅·작업 등에서 **직접 LangGraph를 부르지 않고** `app.state.agent_runtime.invoke(...)`로 위임합니다.

---

## 2. 모드 매트릭스 (`AGENT_RUNTIME_MODE`)

| | `mock` (`local` 별칭) | `http` |
|--|----------------------|--------|
| Client | `MockAgentRuntimeClient` | `ExternalAxitRuntimeClient` |
| 실행 | AXIT mock 레코드 우선, 없으면 in-process LangGraph | 외부 AXIT만 (`AxitPlatformClient`) |
| 카탈로그 `type` | `0` | `1` |
| LangGraph in CP | 있음 (로컬 폴백·정적 에이전트) | 없음 (`REMOTE_AGENT_MARKER`) |
| capabilities | `invoke`만 | 전체(헬스·도구 목록 등; planned_step은 클라이언트에서 미지원일 수 있음) |

상세 제한·UI 비활성: [MOCK_RUNTIME.md](MOCK_RUNTIME.md).

---

## 3. 카탈로그 (`agentruntime`)

Postgres (SQLite `agents` 테이블·`/api/agent-records` 없음).

| 필드 | 의미 |
|------|------|
| `type` | `0` mock / `1` external(http) |
| `agent_id` | AXIT(또는 mock) 측 ID |
| `local_agent_id` | Control Plane/로컬 매핑 ID (빈 값 가능) |
| `talkable` | 통합 채팅 대상 여부 |
| `is_orchestrator` | 오케스트레이터 여부 |
| `service_id` | AXIT 서비스 식별 |

관리 API: `/api/agentruntime` (`backend/app/api/agentruntime_records.py`).  
목록·타일용 메타는 `/api/agents` (`AgentManager`).

mock 오케스트레이터 로컬 ID 예: `helpdesk`, `job-scheduler`, `archi-analysis`, `job_auditor` (`ORCHESTRATOR_LOCAL_AGENT_IDS`).

---

## 4. Invoke 경로

### 4.1 통합 채팅

```
POST /api/agents/{agent_id}/chat
  → 권한(할당 에이전트) 검사
  → agent_runtime.invoke(AgentInvokeRequest)
  → SSE: tools → token(×80) → done | error
```

구현: `backend/app/api/chat.py`.  
공통 결과: `AgentInvokeResult(content, tools_used, ...)`.

### 4.2 mock 내부

1. `build_axit_agent_id` + `agentruntime(type=0)` 조회  
2. 있으면 `AxitPlatformClient.invoke` (mock AXIT HTTP)  
3. 없으면 `LocalAgentRuntimeClient` → `invoke_agent_by_id` / LangGraph·마커

마커:

| 마커 | 의미 |
|------|------|
| `REMOTE_AGENT_MARKER` | http 카탈로그 에이전트 (로컬 실행 없음) |
| `ORCHESTRATOR_MARKER` | mock 플랫폼 오케스트레이터 |

### 4.3 http (외부 AXIT)

`resolve_agentruntime_for_invoke(..., runtime_mode="http")` → `AxitPlatformClient.invoke`.  
레코드 없으면 오류.

### 4.4 INFRA_GAP_ANALYSIS (독립)

- 패키지: `backend/app/infra_gap_analysis/`
- API: `GET/POST /api/infra-gap-analysis/{status,invoke}`
- AXIT·`agentruntime`·통합 채팅과 **무관**. MCP/LLM은 해당 모듈 설정 사용.
- http LLM: `http://llmgateway.apps.pkvgs-k8s.lguplus.co.kr/v1` · `openai/gpt-oss-120b` · API key `PRIVATE_LLM_API_KEY`
- UI: 인프라 형상(형상 추이) **AI갭분석**.

---

## 5. 잔존·비권장 코드

| 항목 | 상태 |
|------|------|
| `backend/app/agent_runtime/` (sandbox `:8090`) | 레거시. factory는 사용하지 않음 |
| `HttpAgentRuntimeClient` | 파일에 남을 수 있으나 `create_agent_runtime_client`는 mock/AXIT만 생성 |
| SQLite `agents` / system `sys-*` 표 / Job plan JSON 상세 | 구 문서 내용. 현재 계약 아님 |

`http` 모드는 **외부 AXIT**이지 로컬 sandbox `:8090`이 아닙니다.

---

## 6. 관련 문서

| 문서 | 범위 |
|------|------|
| [README.md](../README.md) | 온보딩·모드 요약 |
| [MOCK_RUNTIME.md](MOCK_RUNTIME.md) | mock capabilities·비활성 기능 |
| [ARCHITECTURE_MULTIPOD.md](ARCHITECTURE_MULTIPOD.md) | PG + Redis + api/worker |
| [DISABLED_AGENTS.md](DISABLED_AGENTS.md) | 제거된 에이전트 ID (일부 서술 구형일 수 있음) |
| [PLAN_AXIT_PLATFORM.md](../PLAN_AXIT_PLATFORM.md) | 요구·구현 계획 |
