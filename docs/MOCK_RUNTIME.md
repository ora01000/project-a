# Mock Runtime 제한 사항

`AGENT_RUNTIME_MODE=mock` 일 때 Control Plane ↔ runtime client 간 **지원 API**는 아래와 같습니다.  
모드·카탈로그·invoke 경로의 전체 계약은 [BACKEND_AGENT_INTERFACE.md](BACKEND_AGENT_INTERFACE.md)를 참고하세요.

| API | `http` (외부 AXIT) | `mock` |
|-----|--------------------|--------|
| 질의/응답 (`invoke`) | ✅ | ✅ |
| 작업 단계 실행 (`invoke_planned_step`) | ❌ (클라이언트 미구현) | ❌ |
| 런타임 헬스 (`get_runtime_summary`) | ✅ (연결 상태 기반) | ❌ |
| 에이전트 도구 목록 (`list_agent_tools`) | ✅ (AXIT 측) | ❌ |
| 에이전트 정의 동기화 (`reload_definitions`) | no-op | ❌ |

`/api/health` 응답의 `runtime_capabilities` 필드로 프론트엔드가 기능 활성 여부를 판단합니다.

---

## Mock에서 동작하는 기능

| 기능 | 설명 |
|------|------|
| **통합 채팅** | `POST /api/agents/{id}/chat` → `agent_runtime.invoke` (로컬 LangGraph 또는 AXIT mock 레코드) |
| **대시보드·에이전트 타일** | 로컬/카탈로그 상태 |
| **작업 목록·검토/보류/반려** | DB 기반 (런타임 planned_step 불필요 경로) |
| **에이전트 런타임 카탈로그** | `agentruntime` CRUD (`type=0`) |
| **사용자·공지·메일·인프라 형상** | Control Plane 로컬 기능 |
| **AI갭분석** | `INFRA_GAP_ANALYSIS` (런타임 모드와 독립) |

---

## Mock에서 비활성화된 기능

| 기능 | 비활성 사유 | 백엔드 | 프론트엔드 |
|------|------------|--------|-----------|
| **작업 생성·승인·재실행 중 런타임 단계** | `invoke_planned_step` / `list_agent_tools` 등 | 해당 API → 503 | 관련 컨트롤 비활성 |
| **에이전트 도구 조회** | `list_agent_tools` 미제공 | `GET .../tools` → 503 | 도구 드롭다운 미로드 |
| **MCP/런타임 헬스 요약** | `get_runtime_summary` 미제공 | StatusBar 일부 항목 없음 | — |
| **런타임 정의 reload** | `reload_definitions` 미제공 | CRUD 후 reload 생략 | — |

정확한 503 메시지는 `MOCK_RUNTIME_UNAVAILABLE_DETAIL` (`agent_runtime_client.py`)를 따릅니다.

---

## 전체 기능에 가까운 실행

로컬 sandbox `:8090`을 띄우는 방식이 **아닙니다**. `http` 모드는 **외부 AXIT**로 위임합니다.

```bash
AGENT_RUNTIME_MODE=http \
DATABASE_URL=postgresql://... \
REDIS_URL=redis://localhost:6379/0 \
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8080 --reload
```

AXIT 엔드포인트·자격 증명은 `agentruntime`(type=1) 레코드와 환경/설정(`ORCHESTRATOR_URL` 등)을 사용합니다. 자세한 설정은 [PLAN_AXIT_PLATFORM.md](../PLAN_AXIT_PLATFORM.md)와 `.env`를 참고하세요.
