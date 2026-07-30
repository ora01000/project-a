# Mock Runtime 제한 사항

`AGENT_RUNTIME_MODE=mock` 일 때 Control Plane ↔ Mock Runtime 간 통신은 **단일 API**만 제공합니다.

| API | HTTP (http 모드) | Mock |
|-----|------------------|------|
| 질의/응답 (`invoke`) | `POST /runtime/agents/{id}/invoke` | ✅ |
| 작업 단계 실행 (`invoke_planned_step`) | `POST .../invoke-planned-step` | ❌ |
| 런타임 헬스 (`get_runtime_summary`) | `GET /runtime/health` | ❌ |
| 에이전트 도구 목록 (`list_agent_tools`) | `GET .../tools` | ❌ |
| 에이전트 정의 동기화 (`reload_definitions`) | `POST /runtime/agents/reload` | ❌ |

`/api/health` 응답의 `runtime_capabilities` 필드로 프론트엔드가 기능 활성 여부를 판단합니다.

---

## Mock에서 동작하는 기능

| 기능 | 설명 |
|------|------|
| **통합 채팅** | `POST /api/agents/{id}/chat` → mock `invoke` 스텁 응답 |
| **헬프데스크 라우팅** | 대상 에이전트로 `invoke` 위임 (스텁) |
| **대시보드·에이전트 타일** | 로컬 fallback 상태 (`mock` / `ready`) |
| **작업 목록 조회** | DB 기반 읽기 전용 |
| **검토/보류/반려** | Control Plane DB 처리 (런타임 미사용) |
| **에이전트 CRUD** | DB 저장 (런타임 reload 생략) |
| **사용자·공지·인벤토리 CSV** | Control Plane 로컬 기능 |

---

## Mock에서 비활성화된 기능

| 기능 | 비활성 사유 | 백엔드 | 프론트엔드 |
|------|------------|--------|-----------|
| **작업 생성** | 계획 수립 시 `list_agent_tools` 필요 | `POST /api/jobs` → 503 | 메뉴·폼 비활성 |
| **테스트 작업 발송** | 작업 생성과 동일 | `POST /api/jobs/test-samples/send` → 503 | 관리자 메뉴 비활성 |
| **작업 승인** | `invoke_planned_step` 필요 | `POST .../approve` → 503 | 알림 카드 승인 버튼 비활성 |
| **작업 재실행** | `invoke_planned_step` 필요 | `POST .../retry` → 503 | 알림 카드 재작업 버튼 비활성 |
| **에이전트 도구 조회** | `list_agent_tools` 미제공 | `GET .../tools` → 503 | 작업 상세 도구 드롭다운 미로드 |
| **MCP 연결 상태** | `get_runtime_summary` 미제공 | StatusBar MCP 항목 없음 | — |
| **런타임 에이전트 동기화** | `reload_definitions` 미제공 | CRUD 후 reload 생략 | — |
| **인벤토리 승인(HITL)** | mock가 콜백 미발생 | — | 채팅에서 승인 카드 미표시 |

---

## 전체 기능 사용

```bash
AGENT_RUNTIME_MODE=http \
AGENT_RUNTIME_HTTP_BASE_URL=http://localhost:8090 \
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8080 --reload

AGENT_RUNTIME_HOST=0.0.0.0 AGENT_RUNTIME_PORT=8090 \
uv run uvicorn backend.app.agent_runtime.main:app --host 0.0.0.0 --port 8090 --reload
```
