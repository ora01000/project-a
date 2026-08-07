# AX 인프라 운영 콘솔 — Release Notes

프로젝트 최초 개발일(2026-07-08) 이후 변경 이력을 **최근순**으로 요약합니다.  
출처: git 커밋, `ADDITIONAL_PLAN.md`, 워킹 트리 반영분(2026-07-15~18).

**현재 버전:** 1.3B / 릴리즈 `270807`

---

## 2026-08-07 — KubeVirt scrape·인프라 형상 상세 (`270807`)

### 인프라 레지스트리
- `k8s_cluster` → **`infra_cluster`** 이관, `infra_type`(`k8s` | `kubevirt`) 컬럼
- 관리자 메뉴 **인프라 구성**, 클러스터별 유형 선택·수집

### KubeVirt 수집
- `infra_type=kubevirt` 클러스터 수집 → `{cluster}_kubevirt_*` 동적 테이블
  (nodes / namespaces / deployments / pvcs / vms / vm_volumes)
- K8S와 동일 백업·4세대 prune, DynamicClient·kubeconfig(http) 규칙 공유
- 수동 수집·cron 스케줄러가 k8s·kubevirt 모두 지원

### 시스템 네임스페이스 제외
- k8s·kubevirt 수집 시 `default`, `openshift-*`, `kube-*` 네임스페이스 및 하위 리소스 제외

### 인프라 형상 분석
- 목록에 **infra_type** 표시, kubevirt 요약·추이에 **VM / Volumes** 추가
- 오른쪽 **상세정보** 패널(~40%): 네임스페이스·노드(·VM) 탐색
  - 네임스페이스: 상세 + deployment·PVC
  - 노드: 노드 상세
  - VM(kubevirt): VM 상세 + 연결 볼륨
- 카테고리 전환 시 이전 선택으로 잘못된 상세 요청하던 오류 수정
- 밝은 테마에서 상세 항목 버튼 hover 색상 보정

### 기타
- 사용자 목록 **최근 로그인 시각** 표시

### 릴리즈
- About: 버전 **1.3B**, 릴리즈 **270807**
- Docker 이미지 태그: `270807` (`linux/amd64`)

---

## 2026-08-07 — K8S 인프라 scrape·스케줄·형상 분석 (`260807`)

### K8S 인프라 수집
- 관리자 **K8S 인프라 구성** UI·API로 클러스터 등록·수동 수집 재도입
- 수집 결과를 클러스터별 동적 테이블(`{cluster}_k8s_*`)에 저장, 수집 전 백업(`_{YYYYMMDD_HHMMSS}`)
- 백업 테이블은 stamp 기준 **최근 4세대만 유지** 후 나머지 drop
- OVN-Kubernetes **EgressIP** ↔ Namespace `egressIPSelector` 매칭, NetNamespace(레거시) 병행
- DynamicClient **ResourceField → dict 정규화**로 http 모드 수집 누락 수정
- 네임스페이스 컬럼 `using_egressip` / `egressip_assigned_node` 추가

### 스케줄(cron)
- `k8s_cluster.cron` / `cron_expr` 컬럼, UI 스케줄 ON/OFF·cron 표현식(기본 `0 23 * * 6`)
- 백엔드 스케줄러가 `cron=true` 클러스터를 표현식 시각에 자동 수집

### 인프라 형상 분석
- 작업 노트 **인프라 형상** 탭: 클러스터 목록·요약(버전·개수)·형상 변경 추이 차트
- latest + 백업(최대 4) 시점의 nodes/namespaces/deployments/pvcs 개수 추이

### 기타
- 테이블 디버그 API: 하이픈 포함 클러스터 테이블명 조회 허용
- 의존성: `croniter`, `openshift`(기존 수집 경로)

### 릴리즈
- About: 버전 **1.2B**, 릴리즈 **260807**
- Docker 이미지 태그: `260807` (`linux/amd64`)

---

## 2026-08-06 — 작업 진행·작업접수·세션·UI 정리 (`260806`)

### AI 작업 검토
- `jobs.ai_audit_comment` **TEXT** 타입, `ai_audit_date`·`ai_audit_cnt` 컬럼 추가
- 작업 검토·나의 검토작업 패널 **AI 검토결과** 표시(MD 렌더링), 검토 차수·완료 시각
- AI 검토결과 **나의 노트로 복사** 버튼

### 작업 진행(워크플로우)
- 상세 정보 **작업 진행** 탭: 본인 승인·요청 작업의 `status_code` 단계 시각·담당자 워크플로우
- `GET /api/jobs/workflow` API, 10초 폴링·로컬 액션 후 즉시 갱신
- 로그인 후 상세정보 기본 탭 **작업 진행**, 탭 순서: 작업 진행 | Whatap | 대화로그

### 대화형 터미널
- **대화창 | 작업접수** 탭, `JobIntakePanel`(`POST /api/jobs`, 수동 접수)
- 작업접수 **초기화**(확인)·접수 완료 **알림**

### 세션·Welcome Back
- 메뉴바 **세션 연장** 버튼(만료 5분 전 활성), 현재시각 **요일** 표시
- Welcome Back **오늘 하루 보지 않기**(기본 체크, `localStorage`)

### 메뉴·백엔드 정리
- 미사용 **에이전트 관리**·**토큰관리** 메뉴 및 `/api/agents/token-usage` API 제거

### 릴리즈
- About: 버전 **1.1B**, 릴리즈 **260806**
- Docker 이미지 태그: `260806` (`linux/amd64`)

---

## 2026-08-05 — 입력 히스토리·릴리즈 (`26805`)

- 대화형 터미널 **입력 히스토리**(최대 10개) **Redis** 저장·API 연동
- About: 제품명 **AX 인프라 운영 콘솔**, 버전 **1.0B**, 릴리즈 **26805**
- Docker 이미지 태그: `260805` (`linux/amd64`)

---

## 2026-08-04 — madang·Redis·작업 노트 고도화 (`260804`)

### 인증·세션
- **madang IDP** OAuth 연동·신규 가입 승인 흐름 (`job_type=10`)
- **Redis Bearer 세션** (쿠키·TTL 연장)

### 작업·AXIT
- HTTP 모드 안정화: helpdesk 위임, **AXIT 타임아웃·504** 로그, `srnum` 일별 시퀀스
- 작업 노트 **AXIT 폴링** 보완, 통합 채팅 **알림 제거**
- **반려된 작업** 탭·반려 사유 표시, 작업 검토 `status_code=0` 필터
- 신규 가입 job 승인 시 `users.role=1`, 에이전트 전송 제외
- 에이전트 노드 **동시 작업 다중 표시** (`operation_details`, `task_id`)
- 나의 노트 **Redis** 편집 캐시, 작업 패널 UI 개선

### 기타
- `orchestratorApi.js`·롱폴링 클라이언트 샘플
- D2 렌더 오류 수정

---

## 2026-08-03 — 작업요청서·작업 노트

### AXIT / jobs
- 협업 에이전트 **orchestrator invoke API** 경로 분리 (`/orchestrators/v1/...`)
- **작업요청서 수신 API**·`jobs` 테이블·job 요청서 포맷
- `agentruntime` 자동 시드 제거, HTTP **session_id** 보완
- helpdesk / archi-analysis 시스템 프롬프트 참조 문서

### 작업 노트
- **작업 노트 패널**(검토·보류·완료·나의 노트)
- **jobs 처리 데몬**(승인·위임·상태 전이)
- **나의 노트** CRUD·파일 연동

---

## 2026-08-02 — 다이어그램·archi-analysis

- 통합 채팅 **D2 / Mermaid** 렌더링
- **archi-analysis** 시스템 에이전트 위임·목업 LLM 선택
- archi-analysis D2 shape·라벨·분석 가이드 프롬프트 보강

---

## 2026-08-01 — AXIT 대시보드·오케스트레이터

- AXIT 대시보드 동기화·UI 정리, 계획서 복원
- 목업 **오케스트레이터** 에이전트
- `agentruntime` **talkable** / **is_orchestrator** 컬럼·API 지원

---

## 2026-07-30 — AXIT HTTP 연동

- **AXIT 플랫폼 HTTP 연동** 및 `agentruntime` 기반 에이전트 관리 전환
- 서버 에러 로그 보강

---

## 2026-07-29 — Mock 런타임·라이트 테마

- 전 에이전트 **샌드박스 위임**·**mock 런타임** 도입
- 라이트 테마 UI 추가
- 프론트엔드 화면 구성 문서·샘플 파일 정리

---

## 2026-07-25 — Agent Runtime 분리 (Phase 1~3)

- `AgentRuntimeClient` 추상화로 에이전트 실행 경로 분리
- Agent Runtime **HTTP 모드** 분리 및 Control Plane 최적화
- Power Automate 수신 샘플 JSON 포맷 정리

---

## 2026-07-23 — Teams·인벤토리 (`260723-1`)

- **Teams / Power Automate** 수신 디버그(프론트 팝업·백엔드 in-memory 큐)
- 인벤토리 승인 워크플로 보강
- Power Automate 수신 JSON 샘플·포맷 문서 정리

---

## 2026-07-19~20 — 운영 패치 (`260719`, `260719-1`)

- Kubernetes 수집·에이전트 운영 관련 안정화 및 릴리즈 이미지 태그 반영

---

## 2026-07-18 — Kubernetes 주기 수집·릴리즈 (`260718`)

### Kubernetes 클러스터 인벤토리 수집
- 저장 테이블: `k8s_cluster`, `k8s_nodes`, `k8s_namespaces`, `k8s_deployments`, `k8s_pvcs`, `k8s_pods`
- `cluster_id`는 `k8s_cluster.idx`(int FK), 수집 완료 시 `last_update` 시각 갱신
- **openshift DynamicClient**(동기) 수집, kubeconfig=`KUBECONFIG`/`~/.kube/config`
- OCP/OKD 전용 API(DeploymentConfig, EgressIP 등) 없으면 스킵 후 계속(로컬 OrbStack 대응)
- API connect/read 타임아웃 적용
- 스케줄: **기동 시 전체 1회 수집**, 이후 매일 **00:10**부터 에이전트 등록 순서 **5분 간격**
  - 예: `dprv6-k8s` 00:10 → `pcicd-k8s` 00:15 → … → `dtest-k8s` 00:45

### 버전
- About: 버전 **0.3** / 릴리즈 **260718**

---

## 2026-07-16 — 할당·권한·인벤토리·채팅 (`260716` / `260716-2`)

### 통합 채팅 / 대시보드
- 통합 채팅 패널 가로 폭 확대(약 +30%, 500→650px)
- 통합 채팅 하단 에이전트: **할당된 일반 에이전트** + 헬프데스크(시스템)
- 에이전트 노드 목록: **시스템 에이전트는 전원 표시**, 일반 에이전트는 할당분만 표시
- 긴 대화 렌더링 부하 완화: 화면에 **최근 질의/응답 10쌍**만 유지(파일 로그는 전체 보존)
- 사용자 통신 로그(`data/user_comm_logs`) 기반 당일 히스토리 복원

### 테이블 조회(디버깅)
- 레코드 **수정** 버튼·테이블 컬럼 기반 수정 팝업
- 업데이트 성공 시 팝업 종료 (`POST /api/debug/tables/{table}/update`)

### 사용자·세션
- `users.agents` 컬럼·**에이전트 할당** UI(다중 선택, Ctrl/Cmd+A, 드래그 앤 드롭)
- 로그인 패스워드 visible/hidden 토글
- `users.last_login` 기록, Welcome Back 팝업(승인자 작업 요약)
- 프론트 로그인 세션 TTL **1시간**

### 인벤토리 에이전트
- 업로드 한도 **100MB**(nginx/프론트/백엔드), Embedding 실패 stdout 진단 로깅
- Chroma 배치 크기 제한 대응(`CHROMA_ADD_BATCH_SIZE`)
- 샘플 인벤토리 자동 시드 제거
- `chunk_overlap`(기본 50), `n_results`(기본 100) 컬럼·폼 반영
- `db_type`(`table`|`vector`): table 모드는 동적 SQLite 테이블 import, Embedding 비활성
- table 타입 질의: LLM SQL 생성 → 검증·실행
  - 문자열 검색 시 사용자 파라미터 포함 강제
  - `SELECT *` 금지, 핵심 컬럼(+WHERE 컬럼) 최대 10개 선별

### Docker
- 이미지 태그 예: `260716-2` (backend/frontend, amd64/arm64)

---

## 2026-07-15 — 헬프데스크·계획/수행 고도화 (`260715`)

### 헬프데스크 시스템 에이전트
- `sys-helpdesk` 추가: 카탈로그 에이전트 라우팅 후 사용자 메시지 그대로 전달
- 통합 채팅 기본 선택, 응답 decoration(JSON pretty 등)
- 라우팅 프롬프트: 최대 3에이전트 사고 제한, 인프라 외 질의는 직접 일반 응답
- 프롬프트 디버깅 탭(admin): LLM prompt/response·오케스트레이션 관측

### 작업 분석/계획·수행
- 계획 단계: 에이전트 선택 → 해당 에이전트에 도구 추천 문의
- 수행 단계: 계획된 에이전트·도구만 위임 호출, 빈 결과도 정상 처리
- `request_date` / `completion_request_date` 시분초, `actual_completion_time` 기록

### Docker
- 멀티아키(`amd64`/`arm64`) 이미지 태그 예: `260715-2`, `260716-1`

---

## 2026-07-14~15 — UI·작업·인증·테스트 (`260714`)

### UI / UX
- 제품명 **AX 인프라 운영 콘솔**로 변경
- About 팝업, 통합 채팅 User 메시지 fold/unfold, 대화창 통합·에이전트 레이블 선택
- 통합 채팅 대화/에이전트 영역 세로 리사이즈
- Topology 맵 배치·폰트·타일 크기 조정, 노드 고정 크기·줌
- 환경설정(테스트 작업 발송, 테이블 조회) **admin 전용** 노출

### 작업 프로세스
- 작업 계획 검토 UI에서 단계 추가/삭제/수정·원복, 도구 dropdown 수정
- 승인 API 비동기 처리, 실패 알림(해제/재작업)
- 알림 중복 insert 정리(target_user=userid)
- 완료 작업 테이블 컬럼에 **실제작업완료시간** 반영

### 인증
- `AUTH_PROVIDER_TYPE=db|madang` 인증 프로바이더 분기 (madang OAuth 프록시 연동 로직)

### 테스트 / 디버깅
- 테스트 작업 발송 모달(샘플 양식 선택·수정 발송)
- 테이블 조회(디버깅): SQLite 전체 테이블 조회·선택 삭제
- 작업요청자 주기 발송 샘플(READ 전용) 및 데몬 중지 방향

---

## 2026-07-13 — 중간 업데이트 (`260713`)

- 시스템 에이전트·알림·헬스체크·인벤토리 등 운영 기능 확장
- Whatap 이벤트 수신 시스템 에이전트, Chroma 기반 인벤토리 에이전트
- 에이전트 working/idle/error 상태 표시, 로그 탭, 주기적 헬스체크

---

## 2026-07-12 — 중간 업데이트 (`260712`)

- 작업 프로세스·대시보드·에이전트 운영 기능 보강

---

## 2026-07-10 — 로그인·에이전트 DB·작업 프로세스 (`260710`)

- SQLite `users` 기반 **로그인/로그아웃**, 사용자 CRUD(조회·추가·수정·삭제)
- 메뉴바 실사용자 표시(`조직/이름`), 역할(admin/user)
- 에이전트 정보 DB화(`agents`) 및 **에이전트 관리** 메뉴(추가/수정/삭제)
- KubeVirt MCP 연동, 통합 채팅 Stop/Cancel, 상세 정보 작업 탭(검토/보류/완료) 골격
- **시스템 에이전트** 도입 시작: 작업 분석/계획, 작업 수행
- jobs DB·통합 채팅 알림(검토/승인/보류/반려) 워크플로 기반 구축
- JumpDesktop 관련 부가 반영

---

## 2026-07-09 — UI 재구성·통합 채팅

- 개별 타일 채팅 중심에서 **통합 채팅 패널**(우측) 구조로 UI 전환
- **에이전트 노드 목록** 패널, **상세 정보** 멀티탭(Topology / 디버깅→로그) 도입
- Topology 맵과 에이전트 노드 레이어 분리·배치 개선
- Kubernetes 클러스터별 에이전트 세분화 계획 반영

---

## 2026-07-08 — 최초 개발

- LangGraph 기반 멀티 에이전트 백엔드·React 프론트엔드 초기 구성
- 로컬 LLM(OpenAI 호환) 및 MCP(streamable HTTP) 연동
- Kubernetes / KubeVirt / VMware(vCenter) 조회용 에이전트 타일 UI
- 에이전트 타일 채팅(메시지 이력·마크다운·자동 스크롤 등) 기본 UX
- Docker 이미지 빌드·Docker Hub 푸시 체계 (`ora01000/project-a-*`)
- Ansible 에이전트 슬롯 및 서비스 호스트/포트 환경변수화

---

## 버전 / 이미지 참고

| 항목 | 내용 |
|------|------|
| 제품명 | AX 인프라 운영 콘솔 |
| 버전 | 1.3B |
| 릴리즈 | 270807 |
| 백엔드 이미지 | `ora01000/project-a-backend:<tag>` |
| 프론트 이미지 | `ora01000/project-a-frontend:<tag>` |
| 최근 태그 예 | `260806`, `260807`, `270807` |

---

## 참고

- 상세 요구사항·미구현 메모는 `ADDITIONAL_PLAN.md`, `PLAN_AXIT_PLATFORM.md`를 참고하세요.
