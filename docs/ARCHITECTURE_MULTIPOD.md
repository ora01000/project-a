# OKD 멀티 파드 아키텍처

## 목표

http(OKD) 배포에서 frontend/backend replica를 늘려 부하에 대비한다.  
embedded SQLite·로컬 파일·인메모리 스케줄러를 **공유 DB + Redis + worker 분리**로 교체한다.

## 목표 토폴로지

```
Ingress/Route
  ├─ frontend (Deployment, replicas N, HPA)     # 정적 nginx
  └─ backend-api (Deployment, replicas N, HPA) # FastAPI only
backend-worker (Deployment, replicas 1)        # scrape / job / mynote flush
PostgreSQL  ← API + worker
Redis       ← 세션·노트 버퍼·입력 히스토리·(선택) 분산 락
```

환경변수:

| 변수 | 용도 |
|------|------|
| `BACKEND_ROLE` | `all`(기본, 로컬) / `api` / `worker` |
| `DATABASE_URL` | `postgresql://...` 이면 Postgres, 비어 있으면 `DATABASE_PATH` SQLite |
| `DATABASE_PATH` | SQLite 파일 경로 (로컬/mock 기본) |
| `REDIS_URL` | 공유 Redis |
| `MY_NOTES_CONTENT_BACKEND` | `file` \| `database` |
| `USER_COMM_LOG_BACKEND` | `file` \| `stdout` |

## Phase 1 — PostgreSQL 접속·스키마 이식

### 접속

- [`backend/app/db/engine.py`](../backend/app/db/engine.py): dialect 감지 (`sqlite` / `postgresql`)
- [`get_connection()`](../backend/app/db/database.py): dialect에 따라 sqlite3 또는 psycopg 연결
- Postgres 스키마 초안: [`backend/app/db/schema.postgres.sql`](../backend/app/db/schema.postgres.sql)

### 마이그레이션 원칙

1. 로컬/mock은 기본 SQLite 유지 (회귀 비용 최소화).
2. http(OKD)는 `DATABASE_URL` 필수.
3. `init_database`는 **idempotent**. 멀티 파드 동시 기동 시 Postgres `pg_advisory_lock`로 직렬화.
4. 동적 inventory (`{cluster}_k8s_*` / `{cluster}_kubevirt_*`):
   - 단기: PG에서도 동일 테이블명 허용 (identifier quote).
   - 중기: `inventory_*` 고정 테이블 + `cluster_id` 정규화 (백업은 `as_of` 컬럼 또는 별도 snapshot 테이블).

### SQLite → PG SQL 차이 (이식 체크리스트)

| SQLite | PostgreSQL |
|--------|------------|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGSERIAL PRIMARY KEY` |
| `?` placeholder | `%s` (psycopg) — engine이 변환 또는 dialect별 SQL |
| `PRAGMA table_info` | `information_schema.columns` |
| `INSERT OR IGNORE` | `ON CONFLICT DO NOTHING` |
| `TEXT` datetime | `TIMESTAMPTZ` 권장 (단기 TEXT 유지 가능) |

전체 쿼리 일괄 치환은 단계적 PR로 진행한다. 엔진·스키마·락이 선행 인프라다.

### SQLite → PG 데이터 이관 (검토용)

일회성 스크립트: [`scripts/migrate_sqlite_to_postgres.py`](../scripts/migrate_sqlite_to_postgres.py)

- **기본은 dry-run** (계획·건수만 출력). 실제 쓰기는 `--execute` 필요.
- 코어 테이블 FK 순서 이관, `k8s_cluster` → `infra_cluster` 매핑.
- 동적 inventory 테이블은 컬럼 introspect 후 PG에 CREATE·INSERT (백업 세대 포함).
- 선택: `--import-mynote-files`로 `data/mynotes` 파일을 `mynote_contents`에 적재.
- 권장 순서: dry-run 검토 → 대상 PG에 `--apply-schema` 또는 앱 `init_database` → `--execute` (필요 시 `--truncate-target`).

```bash
uv run scripts/migrate_sqlite_to_postgres.py \
  --sqlite data/app.db \
  --database-url 'postgresql://user:pass@host:5432/db'

uv run scripts/migrate_sqlite_to_postgres.py \
  --sqlite data/app.db \
  --database-url 'postgresql://...' \
  --apply-schema --truncate-target --import-mynote-files --execute
```

PostgreSQL 버전은 별도 고정하지 않으나 운영은 **14/15+** 권장.

## Phase 2 — Worker 분리

- `BACKEND_ROLE=api`: job processor / mynote flush / k8s scrape **미기동**
- `BACKEND_ROLE=worker`: 위 루프만 기동 + `/healthz` (프로브용 최소 앱)
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
