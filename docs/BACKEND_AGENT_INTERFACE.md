# Backend ↔ Agent 인터페이스

FastAPI 백엔드와 LangGraph ReAct 에이전트 간의 정의·호출·데이터 계약을 정리한 문서입니다.

---

## 1. 개요

```
┌──────────────────────────────────────────────────────────────────┐
│                     FastAPI (backend/app/main.py)                │
│  app.state.agent_manager  │  app.state.database_path             │
└────────────┬──────────────────────────────┬──────────────────────┘
             │                              │
    ┌────────▼────────┐            ┌────────▼────────┐
    │  AgentManager   │            │  SQLite DB      │
    │  agents{}       │◄───────────│  agents, jobs   │
    │  definitions    │            └─────────────────┘
    │  mcp_manager    │
    └────────┬────────┘
             │
   ┌─────────┼──────────────┬─────────────────┐
   │         │              │                 │
   ▼         ▼              ▼                 ▼
 LangGraph  MCPClient    InventoryService   System Agents
 ReAct      Manager      (ChromaDB)         (마커 객체)
```

| 구성 요소 | 역할 |
|-----------|------|
| **AgentManager** | 에이전트 정의 로드, LangGraph 인스턴스 보관, MCP·LLM 헬스, 작업 상태 추적 |
| **AgentDefinition** | 에이전트 메타데이터 (ID, 이름, 역할, MCP 서버 키, 시스템 프롬프트) |
| **agent_invocation** | 채팅·작업 실행 등 모든 에이전트 호출의 단일 진입점 |
| **MCPClientManager** | MCP 서버 연결 및 도구 목록 제공 |
| **LLM** | OpenAI 호환 API (`get_llm()`, `streaming=False`) |

---

## 2. 에이전트 종류

### 2.1 DB 에이전트 (일반 에이전트)

- **저장소**: SQLite `agents` 테이블
- **런타임**: LangGraph `create_react_agent` (MCP 도구 + `query_inventory` 도구)
- **예외**: `inventory` 에이전트는 `INVENTORY_AGENT_MARKER` → ChromaDB 직접 조회
- **채팅**: `chat_enabled = true` (항상)

```sql
CREATE TABLE agents (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL,
    role VARCHAR(200) NOT NULL,
    system_prompt TEXT NOT NULL,
    mcp_server_keys VARCHAR(200) NOT NULL  -- 쉼표 구분
);
```

초기 시드 템플릿은 `backend/app/agents/registry.py`의 `AGENT_DEFINITIONS`에 정의되어 있으며, 런타임에는 `load_agent_definitions(database_path)`로 DB에서 로드합니다.

### 2.2 시스템 에이전트

코드에 정의된 오케스트레이션 전용 에이전트 (`backend/app/agents/system_agents.py`). LangGraph 인스턴스가 아니라 `SYSTEM_AGENT_MARKER` 객체로 등록됩니다.

| agent_id | 이름 | 역할 | chat_enabled | 대시보드 |
|----------|------|------|:------------:|:--------:|
| `sys-job-planning` | 작업 분석/계획 | 작업 요청 접수·계획 수립 | false | yes |
| `sys-job-execution` | 작업 수행 | 승인된 작업 단계별 실행 | false | yes |
| `sys-inventory` | 인벤토리 | ChromaDB 인벤토리 (DB `inventory`와 별개) | false | no |
| `sys-whatap-events` | Whatap 이벤트 수신 | webhook 수신 | false | yes |
| `sys-helpdesk` | 헬프데스크 | 사용자 질의를 일반 에이전트에 중계 | **true** | yes |

---

## 3. 핵심 데이터 모델

### 3.1 AgentDefinition

```python
@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    name: str
    role: str
    mcp_server_keys: list[str]
    system_prompt: str
```

### 3.2 AgentInvokeResult (모든 호출 경로의 공통 반환)

```python
@dataclass(frozen=True)
class AgentInvokeResult:
    content: str
    tools_used: list[ToolUsage]   # ToolUsage(name, mcp_server?)
    input_tokens: int = 0
    output_tokens: int = 0
```

### 3.3 ToolUsage

```python
@dataclass(frozen=True)
class ToolUsage:
    name: str
    mcp_server: str | None = None   # MCP 서버 키 또는 "inventory"
```

### 3.4 Job Plan JSON (`jobs.job_plan`)

```json
{
  "summary": "작업 요약",
  "steps": [
    {
      "agent_id": "dprv-k8s",
      "agent_name": "IT공통 개발기",
      "description": "단계별 지시 (최대 200자)",
      "tool_name": "kubectl_get",
      "tool_params": { "namespace": "default", "resource": "pods" }
    }
  ]
}
```

| 필드 | 생성 시점 | 설명 |
|------|-----------|------|
| `agent_id`, `agent_name`, `description` | Planning 1단계 | Job Planning LLM이 에이전트 선택 |
| `tool_name`, `tool_params` | Tool Consult 2단계 | 대상 에이전트별 도구 상담 LLM이 결정 |
| `tool_name = "agent_invoke"` | — | MCP 도구 없이 역할 지식만으로 응답 |

### 3.5 Execution Result JSON (`jobs.execution_result`)

```json
{
  "summary": "실행 요약",
  "results": [
    {
      "agent_id": "dprv-k8s",
      "agent_name": "IT공통 개발기",
      "tool_name": "kubectl_get",
      "tool_params": {},
      "status": "completed",
      "content": "에이전트 응답 또는 오류 메시지"
    }
  ]
}
```

`status` 값: `completed` | `failed` | `skipped`

### 3.6 Job 상태

| state | label |
|-------|-------|
| 0 | 접수 |
| 1 | 계획수립완료 |
| 2 | 검토중 |
| 3 | 보류 |
| 4 | 반려 |
| 5 | 승인 |
| 6 | 완료 |
| 7 | 실패 |

---

## 4. AgentManager 생명주기

**파일**: `backend/app/main.py`

### 4.1 초기화 (`initialize`)

1. `MCPClientManager` 생성 및 MCP 서버 연결
2. DB에서 `agent_definitions` 로드
3. 각 DB 에이전트:
   - `inventory` → `INVENTORY_AGENT_MARKER`
   - 그 외 → `build_agent(definition, mcp_manager)` (LangGraph ReAct)
4. `_register_system_agents()` — 시스템 에이전트를 `SYSTEM_AGENT_MARKER`로 등록
5. LLM/MCP 헬스 체크

### 4.2 리로드 (`reload_agents`)

`/api/agent-records` CRUD 후 호출. 삭제된 에이전트 제거, 변경된 정의로 ReAct 에이전트 재빌드.

### 4.3 작업 상태 추적

| 필드 | 값 | 의미 |
|------|-----|------|
| `agent_operation_status` | `idle` / `working` / `error` | 현재 작업 여부 |
| `agent_operation_details` | 문자열 | 작업 중 라벨 (예: `"채팅 응답"`, `"작업실행: …"`) |
| `agent_health_status` | `connected` / `partial` / `disabled` / `ready` / `unavailable` | MCP 연결 또는 인벤토리 상태 |
| `agent_active_counts` | int | 동시 작업 카운터 (0이 되면 idle) |

```python
manager.mark_agent_working(agent_id, "채팅 응답")
# ... invoke ...
manager.mark_agent_idle(agent_id)
# 또는
manager.mark_agent_error(agent_id, reason, input_message=...)
```

---

## 5. 에이전트 호출 인터페이스

**파일**: `backend/app/services/agent_invocation.py`

### 5.1 `invoke_agent_by_id` — 채팅·일반 호출

```python
async def invoke_agent_by_id(
    agent_manager,
    agent_id: str,
    message: str,
    *,
    caller_agent_id: str | None = None,
) -> AgentInvokeResult
```

| agent_id | 동작 |
|----------|------|
| `sys-helpdesk` | `handle_helpdesk_query()` — LLM 라우팅 후 대상 에이전트 호출 |
| `inventory` | `inventory_service.query(message)` |
| `SYSTEM_AGENT_MARKER` / 대시보드 시스템 에이전트 | "직접 질의 불가" 안내 메시지 반환 |
| 그 외 | `invoke_agent()` — LangGraph ReAct (LLM + MCP 도구 루프) |

### 5.2 `invoke_agent_for_planned_step` — 작업 실행 전용

```python
async def invoke_agent_for_planned_step(
    agent_manager,
    agent_id: str,
    message: str,
    *,
    tool_name: str | None = None,
    tool_params: dict | None = None,
    caller_agent_id: str | None = None,
) -> AgentInvokeResult
```

- Job Execution이 단계별로 호출
- `build_planned_step_agent()`로 **계획된 단일 MCP 도구만** 바인딩한 일회성 ReAct 에이전트 생성
- 시스템 에이전트는 호출 불가 (`AgentInvocationError`)
- `tool_params`는 호출자가 `message`에 이미 인코딩 (파라미터 자체는 미사용)

### 5.3 `invoke_agent` — LangGraph 실행

**파일**: `backend/app/agents/base.py`

```python
async def invoke_agent(
    agent,
    message: str,
    mcp_manager: MCPClientManager | None = None,
    *,
    agent_id: str | None = None,
    agent_name: str | None = None,
) -> AgentInvokeResult
```

```python
result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
```

응답 메시지에서 `tools_used`, `content`, 토큰 사용량을 추출합니다.

### 5.4 `build_agent` / `build_planned_step_agent`

| 함수 | 용도 | 도구 바인딩 |
|------|------|-------------|
| `build_agent` | 일반 채팅 | MCP 전체 + `query_inventory` (인벤토리 에이전트 제외) |
| `build_planned_step_agent` | 작업 단계 실행 | 계획된 `tool_name` 1개만 (또는 `agent_invoke` 시 도구 없음) |

작업 단계 실행 시 `JOB_STEP_EXECUTION_POLICY` 프롬프트가 추가되어, 계획 외 도구 호출을 구조적으로 제한합니다.

---

## 6. REST API 계약

### 6.1 에이전트 목록·헬스

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/agents` | DB + 시스템 에이전트 목록 |
| `GET` | `/api/agents/{agent_id}/tools` | 에이전트별 MCP + inventory 도구 목록 |
| `GET` | `/api/health` | LLM/MCP/에이전트 헬스 |

**`GET /api/agents` 응답 필드** (프론트 `AgentInfo`와 1:1 대응):

```json
{
  "id": "dprv-k8s",
  "name": "IT공통 개발기",
  "role": "Kubernetes 클러스터 조회",
  "mcp_servers": ["kubernetes", "kubectl_ai"],
  "mcp_status": { "kubernetes": "connected", "kubectl_ai": "connected" },
  "status": "connected",
  "operation_status": "idle",
  "operation_error": null,
  "operation_detail": null,
  "input_tokens": 0,
  "output_tokens": 0,
  "is_system": false,
  "chat_enabled": true
}
```

`chat_enabled` 규칙:
- DB 에이전트: 항상 `true`
- 시스템 에이전트: `sys-helpdesk`만 `true`

### 6.2 채팅 (SSE)

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/agents/{agent_id}/chat` | 에이전트 호출 → SSE 스트리밍 |
| `GET` | `/api/chat/logs/{userid}?date=YYYY-MM-DD` | 사용자별 채팅 로그 |

**요청** (`ChatRequest`):

```json
{
  "message": "질의 내용 (min 1자)",
  "userid": "선택 — 권한 검사용"
}
```

**권한**: `userid`가 있으면 DB 사용자의 `agents` 필드에 할당된 에이전트만 호출 가능. `chat_enabled` 시스템 에이전트(`sys-helpdesk`)는 할당 없이 허용.

**SSE 이벤트** (LLM 전체 응답을 80자 청크로 재전송):

| event | data |
|-------|------|
| `tools` | `{"tools": [{"name": "...", "mcp_server": "..."}]}` |
| `token` | `{"content": "chunk"}` |
| `done` | `{"content": "", "tools": [...]}` |

**처리 흐름**:

```
POST /api/agents/{agent_id}/chat
  → mark_agent_working
  → invoke_agent_by_id
  → token_tracker.record, log_agent_interaction, log_user_communication
  → mark_agent_idle
  → EventSourceResponse: tools → token×N → done
```

### 6.3 DB 에이전트 CRUD

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/agent-records` | DB 에이전트 레코드 |
| `POST` | `/api/agent-records` | 생성 + `reload_agents` |
| `PUT` | `/api/agent-records/{idx}` | 수정 + reload |
| `DELETE` | `/api/agent-records` | 삭제 + reload |
| `GET` | `/api/mcp-servers` | MCP 서버 옵션 목록 |

### 6.4 작업 (에이전트 오케스트레이션)

| Method | Path | 트리거 서비스 |
|--------|------|---------------|
| `POST` | `/api/jobs` | `submit_job_request` (Job Planning) |
| `POST` | `/api/jobs/{idx}/actions/approve` | `accept_and_schedule_job_execution` (202) |
| `POST` | `/api/jobs/{idx}/actions/retry` | 실패 작업 재시도 |
| `PUT` | `/api/jobs/{idx}/plan` | 계획 수동 편집 |

---

## 7. 호출 경로별 흐름

### 7.1 통합 채팅

```
Client
  POST /api/agents/{agent_id}/chat { message, userid? }
        │
        ▼
  invoke_agent_by_id
        │
        ├─ sys-helpdesk
        │     ├─ LLM 라우팅 → agent_id 선택 (또는 직접 응답)
        │     └─ invoke_agent_by_id(target, 원문 message)
        │
        ├─ inventory
        │     └─ inventory_service.query(message)
        │
        ├─ system marker
        │     └─ "직접 질의 불가" 안내
        │
        └─ 일반 에이전트
              └─ invoke_agent(langgraph_react)
                    ├─ LLM + MCP tool calls (ReAct loop)
                    └─ AgentInvokeResult
```

### 7.2 작업 계획 (Job Planning)

**파일**: `backend/app/services/job_planning.py`

```
submit_job_request()
  ├─ create_job (state=접수)
  ├─ Planning LLM → plan { summary, steps[agent_id, description] }
  ├─ 각 step: Tool Consult LLM → tool_name, tool_params
  ├─ update_job_plan (state=계획수립완료)
  └─ 승인자 알림 발송
```

Planning/Consult 단계는 **LLM을 직접 호출**하며 MCP 도구를 실행하지 않습니다.

### 7.3 작업 실행 (Job Execution)

**파일**: `backend/app/services/job_execution.py`

```
POST /api/jobs/{idx}/actions/approve
  ├─ accept_job_execution → state=승인 (동기, 202 반환)
  └─ asyncio.create_task(run_approved_job)
        │
        for each step in plan.steps:
          ├─ _build_step_message(step) → 실행 지시 메시지
          ├─ mark_agent_working(target_agent)
          ├─ invoke_agent_for_planned_step(agent_id, message, tool_name)
          │     └─ build_planned_step_agent (단일 도구만)
          ├─ mark_agent_idle / mark_agent_error
          └─ results[]에 단계 결과 추가
        │
        update_job_execution_result → 완료 또는 실패
        send_job_notifications
```

| 단계 | 호출 방식 | 도구 실행 |
|------|-----------|-----------|
| Planning | `get_llm().ainvoke` | 없음 (상담만) |
| Execution | `invoke_agent_for_planned_step` | 실제 MCP 도구 1개만 |

---

## 8. MCP 도구 바인딩

**파일**: `backend/app/mcp/client.py`, `config/mcp_servers.yaml`

- `MCPClientManager.get_tools_for_servers(server_keys)` — 에이전트별 도구 필터링
- `MCPClientManager.get_tool_server(tool_name)` — 도구 사용 추적용 MCP 서버 키 반환
- `mcp/sanitize.py` — MCP 도구 호출 시 인자 정제 (`ne` 접두사 오염 제거)

**에이전트별 MCP 바인딩 예**:

| agent_id | mcp_server_keys |
|----------|-----------------|
| K8s 클러스터들 | `["kubernetes", "kubectl_ai"]` |
| `ansible` | `["ansible"]` |
| `vcenter` | `["vcenter"]` |
| `kubevirt` | `["kubevirt"]` |
| `inventory` | `[]` (ChromaDB 직접) |

**추가 도구**: 인벤토리 에이전트가 아닌 모든 ReAct 에이전트에 `query_inventory` StructuredTool 자동 주입 (`inventory_tool.py`).

---

## 9. 헬프데스크 라우팅

**파일**: `backend/app/services/helpdesk.py`

```python
async def handle_helpdesk_query(agent_manager, message) -> AgentInvokeResult
```

1. 호출 가능한 에이전트 카탈로그 구성 (시스템 에이전트·헬프데스크 제외)
2. LLM이 `agent_id` 선택 (인프라 외 주제는 직접 응답)
3. 선택된 에이전트에 `invoke_agent_by_id(target, 원문 message)` — **메시지 변형 없이 전달**
4. `tools_used`에 `route:{agent_id}` 추가

---

## 10. 주요 파일 맵

| 경로 | 역할 |
|------|------|
| `backend/app/main.py` | `AgentManager`, lifespan, 라우터 등록 |
| `backend/app/agents/base.py` | `AgentDefinition`, `build_agent`, `invoke_agent`, ReAct 생성 |
| `backend/app/agents/registry.py` | 코드 템플릿, `load_agent_definitions()` |
| `backend/app/agents/system_agents.py` | 시스템 에이전트 메타데이터, `chat_enabled` |
| `backend/app/agents/inventory_agent.py` | 인벤토리 에이전트 + `INVENTORY_AGENT_MARKER` |
| `backend/app/agents/inventory_tool.py` | `query_inventory` LangChain 도구 |
| `backend/app/db/agents.py` | DB CRUD, `StoredAgent` ↔ `AgentDefinition` |
| `backend/app/db/jobs.py` | Job 모델·상태·plan/result 저장 |
| `backend/app/services/agent_invocation.py` | 통합 호출 진입점 |
| `backend/app/services/job_planning.py` | 작업 계획 LLM + tool consult |
| `backend/app/services/job_execution.py` | 승인 후 단계별 에이전트 실행 |
| `backend/app/services/helpdesk.py` | 헬프데스크 라우팅 |
| `backend/app/mcp/client.py` | MCP 서버 연결·도구 목록 |
| `backend/app/api/chat.py` | 채팅 SSE API |
| `backend/app/api/agents.py` | 에이전트 목록·도구·헬스 API |
| `backend/app/api/agent_records.py` | DB 에이전트 CRUD + reload |
| `backend/app/api/jobs.py` | 작업 API |
| `frontend/src/types/agent.ts` | 프론트 API 계약 타입 |

---

## 11. 설계 참고 사항

1. **SSE는 의사 스트리밍**: LLM은 `streaming=False`로 전체 응답을 받은 뒤 80자 단위로 `token` 이벤트를 쪼개 전송합니다.
2. **시스템 에이전트는 마커 객체**: LangGraph 인스턴스가 아니며, Job Planning/Execution은 전용 서비스에서 LLM을 직접 호출합니다.
3. **작업 단계는 단일 도구 제한**: `JOB_STEP_EXECUTION_POLICY` + `build_planned_step_agent`로 계획 외 도구 호출을 구조적으로 제한합니다.
4. **인벤토리 이중 경로**: 독립 `inventory` 에이전트(ChromaDB) + 모든 ReAct 에이전트의 `query_inventory` 도구.
5. **권한**: 채팅 시 `userid`가 있으면 DB 사용자의 `agents` 필드에 할당된 에이전트만 호출 가능 (`chat_enabled` 시스템 에이전트는 예외).

---

## 12. 토큰 누적 및 귀속 규칙

에이전트 타일의 입력/출력 토큰은 `TokenTracker`가 **서버 기동 후 누적**합니다.  
집계 지점: `wrap_llm_for_prompt_debug` → `record_llm_exchange` → `TokenTracker.record()` (통합 채팅 API에서의 별도 집계 없음).

산출 방식:
1. LLM `response_metadata.token_usage` 우선
2. 없으면 `format_messages_as_prompt(messages)` 전체(system/human/ai/tool_calls) + 응답 문자열을 `len//4`로 추정

| 호출 경로 | `wrap_llm` agent_id | 타일 누적 대상 |
|-----------|---------------------|----------------|
| 통합 채팅 → 일반 에이전트 | 해당 `agent_id` | 해당 에이전트 |
| ReAct 다회 호출 | 동일 `agent_id` | 호출마다 해당 에이전트 |
| 헬프데스크 라우팅 LLM | `sys-helpdesk` | 헬프데스크 |
| 헬프데스크 → 위임 실행 | 대상 `agent_id` | 대상 에이전트 |
| 작업 계획 LLM | `sys-job-planning` | 작업 분석/계획 |
| Tool consult (계획 단계) | `sys-job-planning` | 작업 분석/계획 (대상 에이전트 아님) |
| 작업 실행 step | 대상 `agent_id` | 해당 에이전트 |
| 인벤토리 분류/요약 LLM | `inventory` | 인벤토리 |

`record_orchestration`의 `estimate_tokens`는 Prompt Debug용이며 **TokenTracker에 반영하지 않습니다** (LLM 미호출 메타 로그).

### API

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/api/agents/token-usage` | 서버 기동 후 누적 (TokenTracker, 에이전트 타일과 동일) |
| `GET` | `/api/agents/token-usage/period?since=&until=&agent_id=` | Prompt Debug LLM 기록 기간 합산 (`since`/`until`: ISO 8601) |
| `POST` | `/api/agents/token-usage/reset` | 누적 초기화 (관리자, body: `{ "viewer_role": 1 }`) |

기간 조회는 `kind=llm` 항목만 합산하며, Prompt Debug 메모리 상한(500건) 내 데이터만 포함합니다.
