# 제거·비활성 에이전트

Control Plane에서 **명시적으로 차단된 에이전트 ID**와, 그와 함께 사라진 구형 기능을 정리합니다.  
mock 모드의 런타임 API 제한은 [MOCK_RUNTIME.md](MOCK_RUNTIME.md), 실행 경로는 [BACKEND_AGENT_INTERFACE.md](BACKEND_AGENT_INTERFACE.md)를 참고하세요.

소스: `backend/app/disabled_features.py` (`REMOVED_AGENT_IDS`).

---

## 차단된 에이전트 ID

채팅·로컬 invoke·정의 로드 시 아래 ID는 거부됩니다 (HTTP 503 / 필터 제외).

| ID | 과거 역할 |
|----|-----------|
| `inventory` | ChromaDB/SQLite 인벤토리 질의 에이전트 |
| `sys-inventory` | 시스템 인벤토리 메타 에이전트 |

그 외 `sys-*` ID는 `REMOVED_AGENT_IDS`에 **포함되지 않습니다**. 다만 Control Plane **시스템 에이전트 등록 목록은 비어 있습니다** (`SYSTEM_AGENTS = []` in `system_agents.py`). 헬프데스크·작업 오케스트레이션은 mock 플랫폼 로컬 ID(`helpdesk` 등) 또는 외부 AXIT/`agentruntime`으로 대체되었습니다.

---

## 함께 제거된 구형 기능

| 영역 | 상태 |
|------|------|
| `/api/inventory/*` (인벤토리 CSV) | 라우터 없음 |
| 채팅 인벤토리 승인(HITL) | API·UI 없음 |
| `query_inventory` MCP/도구 | 일반 에이전트 도구 목록에 없음 |
| ChromaDB 인벤토리 서비스 기동 | Control Plane lifespan에서 미사용 |
| Control Plane `sys-*` 시스템 에이전트 타일 | `SYSTEM_AGENTS` / `DASHBOARD_SYSTEM_AGENTS` 빈 목록 |

---

## 비활성이 아닌 것 (문서 혼동 주의)

이전 문서에서 “제거”로 적혀 있던 항목 중 **현재는 정상 동작**합니다.

| 영역 | 현재 |
|------|------|
| `/api/jobs/*` | 라우터 등록·사용 (작업 접수·검토·결과 등) |
| Whatap webhook | `/api/webhooks/whatap` 등 등록 |
| 통합 채팅 | 할당 에이전트 `invoke` |
| 작업 노트 UI | 작업 검토 / 나의 결과 / 반려 / 작업 진행·관리 탭 |
| 인프라 형상 | k8s·kubevirt·vSphere 수집·추이·**AI갭분석** (`INFRA_GAP_ANALYSIS`) |

mock에서만 막히는 작업 단계 실행·도구 목록 등은 **에이전트 제거가 아니라** 런타임 capabilities 제한입니다 → [MOCK_RUNTIME.md](MOCK_RUNTIME.md).
