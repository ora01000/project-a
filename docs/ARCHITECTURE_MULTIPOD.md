# OKD 멀티 파드 아키텍처

## 목표

http(OKD) 배포에서 frontend/backend replica를 늘려 부하에 대비한다.  
embedded SQLite·로컬 파일·인메모리 스케줄러를 **공유 DB + Redis + worker 분리**로 교체한다.

## 목표 토폴로지

```
Ingress/Route
  ├─ frontend (Deployment, replicas N, HPA)     # 정적 nginx
  └─ backend-api (Deployment, replicas N, HPA) # FastAPI only
backend-worker (Deployment, replicas 1)        # scrape / job / mynote flush / mail receive
PostgreSQL  ← API + worker
Redis       ← 세션·노트 버퍼·입력 히스토리·(선택) 분산 락
Shared PVC  ← 수신 메일 첨부 (`RECEIVED_MAIL_ATTACHMENT_HOME`, api+worker 마운트)
```

환경변수:

| 변수 | 용도 |
|------|------|
| `BACKEND_ROLE` | `all`(기본, 로컬) / `api` / `worker` |
| `DATABASE_URL` | **필수** `postgresql://...` |
| `REDIS_URL` | 공유 Redis |
| `MY_NOTES_CONTENT_BACKEND` | `file` \| `database` |
| `USER_COMM_LOG_BACKEND` | `file` \| `stdout` |
| `RECEIVED_MAIL_ATTACHMENT_HOME` | 수신 메일 첨부 루트 (`{home}/{uuid}/…`) |
| `RECEIVED_MAIL_POLL_INTERVAL_SECONDS` | IMAP 폴링 주기(기본 30) |

## Phase 1 — PostgreSQL 접속·스키마

### 접속

- [`backend/app/db/engine.py`](../backend/app/db/engine.py): PostgreSQL only (`DATABASE_URL` 필수)
- [`get_connection()`](../backend/app/db/database.py): psycopg 연결
- 스키마: [`backend/app/db/schema.postgres.sql`](../backend/app/db/schema.postgres.sql)

### 운영 원칙

1. mock/http 모두 `DATABASE_URL` 필수 (SQLite 폴백 없음).
2. `init_database`는 **idempotent**. 멀티 파드 동시 기동 시 Postgres `pg_advisory_lock`로 직렬화.
3. 동적 inventory (`{cluster}_k8s_*` / `{cluster}_kubevirt_*`):
   - 단기: PG에서도 동일 테이블명 허용 (identifier quote).
   - 중기: `inventory_*` 고정 테이블 + `cluster_id` 정규화 (백업은 `as_of` 컬럼 또는 별도 snapshot 테이블).

PostgreSQL 버전은 별도 고정하지 않으나 운영은 **14/15+** 권장.

## Phase 2 — Worker 분리

- `BACKEND_ROLE=api`: job processor / mynote flush / k8s scrape **미기동**
- `BACKEND_ROLE=worker`: 위 루프만 기동 + `/healthz` (프로브용 최소 앱) — IMAP 수신 폴링 포함
- `BACKEND_ROLE=all`: 현행(단일 프로세스) — 로컬 개발 기본

이미지 엔트리포인트: `BACKEND_ROLE`에 따라 `backend.app.main:app` 또는 `backend.app.worker:app`.

## Phase 3 — 파일 상태 제거

- **mynotes**: `content_backend=database` 시 `mynote_contents` 테이블에 본문 저장. Redis 버퍼 → flush → DB.
- **user_comm_logs**: `backend=stdout` 시 JSON 한 줄 로그를 stdout으로 (클러스터 로깅 수집). `file`은 기존 동작.

## Phase 4 — OKD 매니페스트

[`deploy/okd/`](../deploy/okd/) 참고:

- `frontend-deployment.yaml` + HPA
- `backend-api-deployment.yaml` + HPA (`BACKEND_ROLE=api`)
- `backend-worker-deployment.yaml` (`BACKEND_ROLE=worker`, replicas=1)
- `secrets.example.yaml` / ConfigMap 예시
- readiness/liveness: `/healthz` (API·worker)

## 하지 말 것

- SQLite 파일을 RWX PVC에 두고 backend replicas>1
- 모든 API 파드에서 scrape/job 루프 활성 유지
