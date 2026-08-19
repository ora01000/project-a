# AX 인프라 운영 콘솔

인프라 운영을 위한 웹 콘솔입니다. 작업 요청·검토, 인프라 형상 조회, 통합 채팅, 메일 알림을 한곳에서 다룹니다.

**현재 버전:** 1.8 / 릴리즈 `260819` — 상세 변경 이력은 [RELEASE.md](RELEASE.md)를 참고하세요.

## 아키텍처 요약

| 구성 | 설명 |
|------|------|
| Frontend (`9001`) | React + Vite (개발) / nginx (이미지) |
| Backend (`8080`) | FastAPI Control Plane |
| PostgreSQL | **필수** (`DATABASE_URL`) — mock/http 공통, SQLite 폴백 없음 |
| Redis | 세션·노트 버퍼·채팅 입력 히스토리 (`REDIS_URL`) |

에이전트 실행 모드는 `AGENT_RUNTIME_MODE`로 전환합니다.

| 모드 | 동작 |
|------|------|
| `mock` | Control Plane 내부 LangGraph 에이전트 (로컬 개발 기본) |
| `http` | 외부 AXIT 런타임으로 위임 |

로컬은 보통 `BACKEND_ROLE=all`(API + 백그라운드 워커 단일 프로세스)입니다. OKD에서 API/worker 분리·멀티 파드는 [docs/ARCHITECTURE_MULTIPOD.md](docs/ARCHITECTURE_MULTIPOD.md)를 참고하세요.

```mermaid
flowchart LR
  FE[Frontend_9001] --> BE[Backend_8080]
  BE --> PG[(PostgreSQL)]
  BE --> RD[(Redis)]
  BE -->|mock| LocalAgents[InProcess_LangGraph]
  BE -->|http| Axit[External_AXIT_Runtime]
```

## 사전 요구사항

- Python **3.12** + [uv](https://docs.astral.sh/uv/)
- Node.js **18+**
- PostgreSQL (`DATABASE_URL`)
- Docker (로컬 Redis 권장)
- (선택) OpenAI 호환 LLM, MCP 서버 — mock 채팅·도구 연동용

## 설치

```bash
# 저장소 루트에서
uv sync

cd frontend
npm install
cd ..
```

## 필수 설정

프로젝트 루트 `.env` (gitignored) 예시:

```bash
AGENT_RUNTIME_MODE=mock
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DBNAME
REDIS_URL=redis://localhost:6379/0
BACKEND_ROLE=all
MY_NOTES_CONTENT_BACKEND=database
USER_COMM_LOG_BACKEND=file
```

추가 설정 파일:

| 파일 | 용도 |
|------|------|
| [config/settings.yaml](config/settings.yaml) | LLM, 서버 포트, 작업 프로세서, Redis 기본값 등 |
| [config/mcp_servers.yaml](config/mcp_servers.yaml) | mock 모드 MCP 엔드포인트 |

환경변수는 yaml보다 우선합니다. SMTP는 DB 테이블 `mailserver_config`(관리자 UI)에서 관리합니다.

## 로컬 실행

```bash
# 1) Redis
docker rm -f project-a-redis 2>/dev/null || true
docker run -d --name project-a-redis -p 6379:6379 redis:7-alpine

# 2) Backend
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8080 --reload

# 3) Frontend
cd frontend && npm run dev
```

브라우저: [http://localhost:9001](http://localhost:9001)  
헬스 체크: [http://localhost:8080/healthz](http://localhost:8080/healthz)

## 주요 기능

- **인증·사용자**: 로그인/세션, 가입 신청, 역할·에이전트 할당, 이벤트 리포트 구독
- **작업 노트**: 작업 검토·나의 검토/결과, Whatap 이벤트 리포트, 반려 작업, 나의 노트 (목록 페이징)
- **인프라 형상**: k8s / kubevirt / vSphere 수집·요약·세대 추이, **AI갭분석** (`INFRA_GAP_ANALYSIS`)
- **통합 채팅·대화로그**: 에이전트 채팅(SSE), 상세정보 패널 로그
- **메일**: 리포트 수동 전송(Markdown + D2/FossFLOW 이미지), 작업 완료/반려/취소·가입·Whatap 구독 자동 알림
- **관리자**: 에이전트 연결, 인프라 구성, 메일 서버, 공지사항 등

mock 모드에서 제한되는 런타임 API는 [docs/MOCK_RUNTIME.md](docs/MOCK_RUNTIME.md)를 참고하세요.

## Docker 이미지

Postgres multipod 배포용 태그는 **`pgYYMMDD`** 형식입니다 (예: `pg260819`).

```bash
IMAGE_TAG=pg260819 PUSH=true PLATFORMS=linux/amd64 bash scripts/docker-build-push.sh
```

| 이미지 | 예시 태그 |
|--------|-----------|
| `ora01000/project-a-backend` | `pg260819` |
| `ora01000/project-a-frontend` | `pg260819` |

OKD 매니페스트 예시는 [`deploy/okd/`](deploy/okd/)을 참고하세요.

## 문서

| 문서 | 내용 |
|------|------|
| [RELEASE.md](RELEASE.md) | 릴리즈 노트·현재 버전 |
| [docs/ARCHITECTURE_MULTIPOD.md](docs/ARCHITECTURE_MULTIPOD.md) | Postgres + Redis + api/worker 멀티 파드 |
| [docs/MOCK_RUNTIME.md](docs/MOCK_RUNTIME.md) | mock vs http 런타임 차이 |
| [docs/BACKEND_AGENT_INTERFACE.md](docs/BACKEND_AGENT_INTERFACE.md) | Control Plane ↔ runtime·카탈로그·invoke 계약 |
| [docs/FRONTEND_UI.md](docs/FRONTEND_UI.md) | 프론트 화면·메뉴·패널 구성 |
| [docs/DISABLED_AGENTS.md](docs/DISABLED_AGENTS.md) | 제거된 에이전트 ID |
| [PLAN_AXIT_PLATFORM.md](PLAN_AXIT_PLATFORM.md) | 요구사항·구현 계획 |
