# AX 인프라 운영 콘솔 — Release Notes

프로젝트 최초 개발일(2026-07-08) 이후 변경 이력을 **최근순**으로 요약합니다.  
출처: git 커밋, `ADDITIONAL_PLAN.md`, 워킹 트리 반영분(2026-07-15~18).

**현재 버전:** 1.7 / 릴리즈 `260814`

---

## 2026-08-14 — 인프라 형상 용량·PVC used·vSphere 데이터스토어 (`260814` / `pg260814`)

### 인프라 형상 탭
- 작업 노트에서 **인프라 형상을 맨 앞 탭**으로 두고 기본 진입 탭으로 사용
- 요약 아래 **클러스터 용량 | 노드(호스트)별 용량 | 저장소 용량** (1:1:1), 그 아래 형상 추이
- 클러스터 용량: worker(목업은 전체 노드) vs deploy request/limit 도넛, 가상화비율(k8s는 Limit)
- kubevirt: Running VM cpu/mem을 request에 합산
- vSphere: 호스트 cpu/mem 합 vs POWERED_ON VM, MEM MiB→Gi
- 노드/호스트별 용량: 2단 가로 바, CPU/MEM 정렬 토글(기본 CPU 내림차순), Top 5, 긴 이름 truncate+툴팁
- 저장소 용량
  - k8s/kubevirt: PVC 가로 바 `used/capacity`, used 없으면 `용량: {capacity}`(NFS 등), 툴팁 `ns/deploy/sc/accessMode`, 비율 Top 5
  - vSphere: 데이터스토어 가로 바 `free_bytes/capacity_bytes`, 툴팁 `datacenter/type/accessible`, 비율 Top 5
- 상세정보: k8s/kubevirt 기본 탭 **네임스페이스**, vSphere 탭 순서 **ESXi호스트 → 클러스터**(기본 ESXi호스트)

### 수집
- vSphere 호스트 CPU/MEM: SOAP `RetrievePropertiesEx` 100대 청크 + Continue token
- PVC used: kubelet `nodes/proxy/stats/summary`를 `call_api`(BearerToken)로 호출 — `request()` 익명 403 수정
- kubelet host-disk df는 PVC 청구 대비 비정상 값으로 폐기, local/hostPath는 디렉터리 `du`
- NFS PVC used는 kubelet df(공유 전체)라 수집하지 않음
- vSphere 데이터스토어: 데이터센터별 REST 목록 → `{cluster_name}_vsphere_datastores` (`capacity_bytes`/`free_bytes` BIGINT)
- INFRA_GAP_ANALYSIS 시스템 프롬프트에 데이터스토어 갭분석 규칙 추가

### 기타
- 가입 승인 메일·SR 시퀀스, role=1 IP 화면 마스킹

### 릴리즈
- About: 버전 **1.7**, 릴리즈 **260814**
- Docker 이미지 태그: `pg260814` (`linux/amd64`)

---

## 2026-08-13 — 메일 수신·JOB_DECISION·작업 관리 (`260813` / `pg260813`)

### 메일 수발신
- 리포트 메일: 미등록 이메일 직접 입력(칩, `;`/`,`/공백)
- 메일 서버 설정: **메일 수신 활성화** + IMAP 호스트/포트/SSL
- IMAP 폴링(기본 30초, worker/`BACKEND_ROLE=all`): `received_mail` 저장, 텍스트·인증서 첨부만 `{RECEIVED_MAIL_ATTACHMENT_HOME}/{uuid}/`
- `decision_type`: `0` 대기, `5` 자료부족, `10` 작업 대상, `11` 비작업
- API: `GET /api/received-mail`, `GET /api/received-mail/{uuid}`, `GET .../attachments/{filename}` (관리자)
- 관리자 디버깅: 환경설정 → 관리자 작업 → **수신메일 목록(디버깅)**
- 정적 에이전트 **`JOB_DECISION_AGENT`**: INFRA_GAP_ANALYSIS와 동일 LLM, AXIT 미사용, skill=`job_scope.md`
  - `GET/POST /api/job-decision-agent/{status,invoke,evaluate}` — received_mail → decision_type(5/10/11)

### 상세정보·작업 관리
- 역할 기반 **작업 관리** 탭: 작업 목록·AI검토내용 패널·행 클릭 상세
- `AI검토내용` 버튼이 테이블 행 높이를 키우지 않도록 축소

### 나의 노트·대시보드 UX
- 노트 저장 시 `mynote_contents` 즉시 반영(Redis 재기동 유실 완화), INSERT/LASTVAL 오류 수정
- database 모드 빈 md 파일 생성 중단, 밝은 테마 hover·미리보기 기본 선택 보정
- 에이전트 노드 목록·상세정보 패널 접기, 채팅 history 버튼 세로 배치
- 공지 없을 때 WelcomeBack 생략

### 문서
- Control Plane/UI/mock/disabled 에이전트 docs 현행화, 미사용 `lib/hsqldb.jar` 제거

### 릴리즈
- About: 버전 **1.6**, 릴리즈 **260813**
- Docker 이미지 태그: `pg260813` (`linux/amd64`)

---

## 2026-08-11 — SMTP·리포트 메일 전송 (`260811` / `pg260811`)

### 메일 서버 설정
- SMTP 환경변수 제거 → **`mailserver_config` DB 테이블** + 관리자 UI
- 환경설정 > 관리자 작업: **메일 서버 설정** 팝업, **테스트 메일 발송** 팝업

### 리포트 메일 전송
- 작업·노트 **Markdown 리포트** 메일 API (`multipart/alternative` plain + HTML)
- 메일 본문의 **D2 다이어그램**을 PNG 이미지로 변환해 HTML에 임베딩 (백엔드 `d2` + `rsvg-convert`)
- 메일 전송 UI: **Whatap 이벤트 리포트**, **나의 작업결과**, **반려된 작업**, **나의 노트** 탭
- 수신자 선택: **SR 기안자** / **등록된 사용자** (`조직/이름(id)` pill), `role=5`(보류) 제외
- **수신자·참조·숨은참조** 컬럼 선택 후 등록 사용자 추가, **제목 수정**, **추가 내용**(리포트 상단, 기본 문구 포함)
- 반려 작업은 결과 없이도 작업 내용·반려 사유로 메일 본문 생성

### 자동 알림 메일
- **Whatap 이벤트 리포트** 완료(`job_type=2`, status 10) 시 `users.whatap_event_sub` 구독자에게 결과 메일 자동 발송
- **신규 가입 신청** 접수(`job_type=10`, status 0) 시 관리자(`role=0`)에게 신청 사유 메일 자동 발송
- **일반 작업 요청서**(`job_type=1`) 상태 변경 시 요청자(`requester_email`) 자동 메일, 승인자는 참조
  - 처리완료 성공/실패(10|11): `[작업처리결과]`, 본문 `jobs_result.result`
  - 작업반려(12): `[작업반려]`, 본문 `reject_reason`
  - 작업취소(13): `[작업취소]`, 본문 `drop_reason`
- 반려 사유 저장 컬럼을 **`reject_reason`** 으로 통일 (표시·메일은 기존 `drop_reason` fallback 유지)

### 작업 노트·상세 패널 UX
- 작업 노트·작업 진행 목록 **클라이언트 페이징**(기본 10, 10/20/30/50)
- 페이징·표시개수를 **동일 행**에 배치 (왼쪽 페이징 / 오른쪽 표시개수)
- 상세정보 패널 타이틀 제거·최소화 버튼 탭 행 배치, 관리자용 **작업 관리** 탭(TBD)
- 사용자 관리 > **이벤트 리포트 구독** 팝업

### 인프라 형상 GAP 분석
- 독립 에이전트 **`INFRA_GAP_ANALYSIS`** (AXIT runtime·목업 카탈로그와 분리, 코드 static 설정)
  - mock: 기존 LLM + MCP `http://localhost:30800/mcp`
  - http: `openai/gpt-oss-120b` + MCP `http://pgdb-mcp.mcps.svc.cluster.local:8000/mcp`
- API: `GET/POST /api/infra-gap-analysis/{status,invoke}`
- 인프라 형상 탭: **형상 변경 추이 → 형상 추이**, 우측 상단 **AI갭분석** 버튼
- 갭분석 Q/A는 **대화로그**(`logs/agents/INFRA_GAP_ANALYSIS.log`)에 기록

### 문서
- [README.md](README.md)를 현재 구현(Postgres·Redis·mock/http·로컬 기동·주요 기능)에 맞춰 온보딩 중심으로 전면 개편

### 릴리즈
- About: 버전 **1.5**, 릴리즈 **260811** (유지)
- Docker 이미지 태그: `pg260811` (`linux/amd64`)

---

## 2026-08-10 — Postgres 전용 multipod·형상/채팅 UX (`260810` / `pg260810`)

### PostgreSQL 전용 (dev-axplatform-multi-pod)
- 목업(로컬)·http(서버) 모두 **`DATABASE_URL`(PostgreSQL) 필수** — SQLite 폴백 제거
- 관리자 **SQLite → PostgreSQL 마이그레이션** 메뉴·API·CLI 스크립트 삭제
- Docker 이미지 태그 규칙 **`pgYYMMDD`** (`scripts/docker-build-push.sh` 기본값)
- OKD 매니페스트 이미지 참조를 Postgres 태그 체계에 맞춤

### 인프라 형상
- 네임스페이스·노드·VM 상세를 **표 중심** UI로 정리, 탭 순서에서 **인프라 형상을 나의 노트 앞**으로 배치
- `node_role`, deployments **`readyreplicas`**, 노드별 **`pods_on_nodes`**(요청/제한 CPU·Mem) 반영
- 인프라 목록 버튼을 pill → **둥근 모서리 사각형**으로 변경

### 관리 화면 팝업
- **에이전트 연결 / 사용자 조회 / 공지사항**을 대시보드 위 모달로 전환(에이전트 할당과 동일 패턴)
- 에이전트 연결 팝업 가로 폭 확대

### 대화형 터미널
- 응답 중지 시 `응답 생성 중...` 대신 **「요청이 취소되었습니다.」** 표시
- 입력창 **↓ 키/버튼**으로 명령 히스토리 다음 항목 이동(최신에서 한 번 더 누르면 빈 입력)

### 릴리즈
- About: 버전 **1.4**, 릴리즈 **260810**
- Docker 이미지 태그: `pg260810` (`linux/amd64`)

---

## 2026-08-07 — KubeVirt scrape·인프라 형상 상세 (`260807`)

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
- About: 버전 **1.3B**, 릴리즈 **260807**
- Docker 이미지 태그: `260807` (`linux/amd64`)

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
| 버전 | 1.7 |
| 릴리즈 | 260814 |
| 백엔드 이미지 | `ora01000/project-a-backend:<tag>` |
| 프론트 이미지 | `ora01000/project-a-frontend:<tag>` |
| 최근 태그 예 | `260805`, `260806`, `260807` |
| multi-pod(Postgres) 태그 | `pgYYMMDD` (예: `pg260814`) — `dev-axplatform-multi-pod` 배포용 |

---

## 참고

- 상세 요구사항·미구현 메모는 `ADDITIONAL_PLAN.md`, `PLAN_AXIT_PLATFORM.md`를 참고하세요.
