# 비활성화된 에이전트 및 관련 기능

시스템 에이전트(`sys-*`)와 인벤토리 에이전트(`inventory`)가 제거되었으며, 연관 기능은 백엔드·프론트엔드에서 비활성화되었습니다.

## 제거된 에이전트

| ID | 이름 |
|----|------|
| `sys-helpdesk` | 헬프데스크 |
| `sys-job-planning` | 작업 분석/계획 |
| `sys-job-execution` | 작업 수행 |
| `sys-inventory` | 시스템 인벤토리 (메타) |
| `sys-whatap-events` | Whatap 이벤트 수신 |
| `inventory` | 인벤토리 (ChromaDB/SQLite) |

`REMOVED_AGENT_IDS` — `backend/app/disabled_features.py`

---

## 비활성화된 백엔드 기능

| 영역 | API/기능 | 상태 |
|------|----------|------|
| 작업 관리 | `/api/jobs/*` 전체 | 503 |
| 인벤토리 CSV | `/api/inventory/*` | 라우터 미등록 |
| Whatap webhook | `/api/webhooks/whatap` | 라우터 미등록 |
| 인벤토리 승인(HITL) | `/api/chat/inventory-approvals/*` | 제거 |
| 런타임 내부 콜백 | `/api/internal/runtime/*` | 라우터 미등록 |
| `query_inventory` 도구 | 일반 에이전트 MCP 도구 목록 | 제거 |
| 인벤토리 서비스 | ChromaDB 초기화 | 미실행 |
| 시스템 에이전트 등록 | Control Plane / Runtime | 빈 목록 |
| 작업 단계 실행 | `invoke-planned-step` | 503 (런타임) |

---

## 비활성화된 프론트엔드 기능

| 메뉴/화면 | 상태 |
|-----------|------|
| 인벤토리 CSV | 메뉴 제거 |
| 작업관리 (목록/생성) | 메뉴 제거 |
| 테스트 작업 발송 | 관리자 메뉴 제거 |
| 검토/보류/완료 작업 탭 | DetailInfoPanel 제거 |
| 작업 알림 카드 | 통합 채팅 제거 |
| 인벤토리 승인 카드 | 통합 채팅 제거 |
| 헬프데스크 기본 선택 | 제거 (할당 에이전트만) |
| 시스템 에이전트 타일 | 대시보드 미표시 |

---

## 계속 사용 가능

- K8s / KubeVirt / vCenter / Ansible 일반 에이전트
- 할당된 에이전트와의 통합 채팅 (`invoke`)
- 에이전트 관리·할당·토큰관리
- 사용자·공지·가입 승인 알림
- Topology 맵·로그·디버깅(관리자)
