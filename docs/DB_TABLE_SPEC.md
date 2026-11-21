# DB 테이블 명세서

작성 기준일: 2026-11-19  
DB: **PostgreSQL** (`DATABASE_URL` 필수)  
기준 소스:

- 코어 DDL: [`backend/app/db/schema.postgres.sql`](../backend/app/db/schema.postgres.sql)
- 런타임 보정: `backend/app/db/*.py` 의 `ensure_*` (특히 `workflow.py`, `received_mail.py`)

날짜/시각 컬럼은 대부분 **TEXT(ISO 문자열)** 로 저장한다.  
정수 플래그(`enabled`, `cron`, `talkable` 등)는 `0`/`1` 관례를 따른다.

### 사용자 참조 원칙

- 다른 테이블이 사용자를 참조할 때는 **`users.idx`만** 저장한다.
- `userid` / `username` 등 문자열 식별자는 타 테이블에 저장하지 않는다. 표시명은 조회 시 `users` JOIN/룩업으로 조립한다.
- API 응답의 `requester_name`, `approver_userid` 등은 **계산 필드**이며 DB 컬럼이 아니다.

---

## 1. 코어 테이블 목록

| 테이블 | 용도 |
|--------|------|
| `users` | 사용자·역할·에이전트 배정 |
| `agentruntime` | 에이전트 런타임 카탈로그(mock/http) |
| `notice_board` | 공지 |
| `jobs` | 작업(헬프데스크/Whatap/워크플로 등) |
| `jobs_scheduled` | 예약 작업 대기열 (`jobs.idx` FK) |
| `jobs_result` | 작업 완료 결과 |
| `mynotes` | 노트 메타데이터 |
| `mynote_contents` | 노트 본문(DB 백엔드) |
| `prompt_offer` | 질의어 추천 프롬프트 |
| `infra_cluster` | 인프라 클러스터 등록 |
| `vsphere_infra_info` | vSphere 접속 정보 |
| `mailserver_config` | SMTP/IMAP 설정(사실상 싱글톤) |
| `received_mail` | 수신 메일 |
| `work_node` | 워크플로 작업 노드 |
| `workflow` | 워크플로 정의 |
| `workflow_history` | 워크플로 실행 이력 |
| `work_node_history` | 작업 노드 실행 이력 |
| `workflow_template` | 워크플로 템플릿 메타 |

제거됨(원격 inventory-api로 이관): `inventory`, `inventory_api`.

---

## 2. 코드성 값 (공통)

### 2.1 `users.role`

| 값 | 의미 |
|----|------|
| `0` | admin |
| `1` | user |
| `2` | infraadmin |
| `5` | pending(가입 대기) |
| `100` | superadmin |

### 2.2 `users.band`

| 값 | 의미 |
|----|------|
| `1` | 사원 |
| `2` | 선임 |
| `3` | 책임 |

### 2.3 `agentruntime.type`

| 값 | 의미 |
|----|------|
| `0` | mock |
| `1` | external(http) |

### 2.4 `jobs.status_code`

| 값 | 의미 |
|----|------|
| `0` | 수신 |
| `1` | 승인자 지정 |
| `2` | 직결재(승인 후 진행) |
| `10` | 완료(성공) |
| `11` | 완료(실패) |
| `12` | 반려 |
| `13` | 취소 |

### 2.5 `jobs.job_type`

| 값 | 의미 |
|----|------|
| `1` | AX 인프라 작업 |
| `2` | Whatap 이벤트 |
| `3` | 워크플로 |
| `10` | 가입(signup) |

### 2.6 `infra_cluster.infra_type`

| 값 | 의미 |
|----|------|
| `k8s` | Kubernetes/OKD |
| `kubevirt` | KubeVirt |
| `vSphere` | VMware vSphere |

### 2.7 `received_mail.decision_type`

| 값 | 의미 |
|----|------|
| `0` | pending |
| `5` | 작업 후보이지만 자료 부족 |
| `10` | job으로 처리 |
| `11` | non-job |

### 2.8 `work_node.script_type`

`oc/kubectl/virtctl` | `ansible` | `cli` | `prompt`

### 2.9 `work_node.worker`

`agent` | `hitl`

### 2.10 `work_node.crud`

의도 문자 집합 문자열(최대 4자). 문자: `c`/`r`/`u`/`d`.

---

## 3. 테이블 상세

### 3.1 `users`

| 컬럼 | 타입 | NULL | 기본값 | 설명 |
|------|------|------|--------|------|
| `idx` | BIGSERIAL | PK | | 타 테이블 사용자 참조의 유일한 키 |
| `userid` | TEXT | | | 로그인 ID 암호문(`v{n}:…`) 또는 평문(키 미설정) |
| `email` | TEXT | | | 이메일 암호문/평문 |
| `username` | TEXT | | | 표시명 암호문/평문 |
| `password` | TEXT | | | 비밀번호 암호문/평문 (운영 인증은 미사용) |
| `userid_bidx` | VARCHAR(64) | | `''` | HMAC blind index (조회·UNIQUE) |
| `email_bidx` | VARCHAR(64) | | `''` | HMAC blind index (조회·UNIQUE) |
| `depart` | VARCHAR(100) | | | 부서 |
| `role` | INTEGER | | | §2.1 |
| `band` | INTEGER | | `1` | §2.2 |
| `agents` | VARCHAR(200) | | `''` | 배정 에이전트 목록(문자열) |
| `last_login` | TEXT | YES | | |
| `request_reason` | VARCHAR(200) | | `''` | 가입 사유 등 |
| `whatap_event_sub` | INTEGER | | `0` | Whatap 이벤트 메일 구독 |
| `prod_auth` | INTEGER | | `0` | PROD 모드 사용 권한 |
| `current_prod_mode` | INTEGER | | `1` | 현재 모드(DEV/PROD 등) |
| `theme_for_dev_mode` | INTEGER | | `1` | DEV 테마 |
| `theme_for_prod_mode` | INTEGER | | `1` | PROD 테마 |

UNIQUE INDEX `ux_users_userid_bidx` (`userid_bidx`) WHERE `userid_bidx <> ''`  
INDEX `ix_users_email_bidx` (`email_bidx`) WHERE `email_bidx <> ''` (이메일은 중복 허용)

필드 암호: AES-256-GCM 봉투 암호 + `USERS_FIELD_CRYPTO_BACKEND`=`env`\|`vault`. 키는 DB 밖(`USERS_FIELD_KEK`, `USERS_FIELD_BLIND_KEY`).

숨김 시스템 사용자(시드, 로그인 불가): `root`, `auto_approve`, `whatap`, `external`.

### 3.2 `agentruntime`

| 컬럼 | 타입 | NULL | 기본값 | 설명 |
|------|------|------|--------|------|
| `idx` | BIGSERIAL | PK | | |
| `type` | INTEGER | | | §2.3 |
| `agent_name` | VARCHAR(50) | | | 표시명 |
| `agent_id` | VARCHAR(50) | | | 외부/플랫폼 ID |
| `local_agent_id` | VARCHAR(50) | | `''` | 목업 로컬 ID |
| `description` | VARCHAR(255) | | | |
| `registered_date` | TEXT | | | |
| `service_id` | VARCHAR(20) | | | |
| `talkable` | INTEGER | | `1` | 대화 가능 |
| `is_orchestrator` | INTEGER | | `0` | 오케스트레이터 여부 |
| `is_prod` | INTEGER | | `1` | PROD(1)/DEV(0) 페어 구분 |

UNIQUE INDEX `ux_agentruntime_type_agent_id_is_prod` (`type`, `agent_id`, `is_prod`)

### 3.3 `notice_board`

| 컬럼 | 타입 | NULL | 기본값 | 설명 |
|------|------|------|--------|------|
| `idx` | BIGSERIAL | PK | | |
| `writer_idx` | BIGINT | NOT NULL | | 작성자 `users.idx` |
| `write_date` | TEXT | | | |
| `from_date` | TEXT | | | 게시 시작 |
| `until_date` | TEXT | | | 게시 종료 |
| `title` | VARCHAR(100) | | | |
| `notice` | TEXT | | | 본문 |
| `welcome_popup` | INTEGER | | `0` | 환영 팝업 |

제거됨: `writer` (userid 문자열) → `writer_idx`. API 계산 필드: `writer_name`.

### 3.4 `jobs`

| 컬럼 | 타입 | NULL | 기본값 | 설명 |
|------|------|------|--------|------|
| `idx` | BIGSERIAL | PK | | |
| `srnum` | VARCHAR(20) | UNIQUE | | SR 번호 |
| `status_code` | INTEGER | | `0` | §2.4 |
| `job_type` | INTEGER | | `1` | §2.5 |
| `approver_registered_date` | TEXT | YES | | |
| `approver_idx` | BIGINT | YES | | 승인자 `users.idx` (NULL=미지정) |
| `job_title` | VARCHAR(300) | | | |
| `requester_email` | VARCHAR(100) | | | 연락용(표시 보조) |
| `requester_depart` | VARCHAR(100) | | | 연락용(표시 보조) |
| `job_content` | TEXT | | | |
| `request_date` | TEXT | | | |
| `requester_idx` | BIGINT | NOT NULL | `1` | 요청자 `users.idx` |
| `team_id` | VARCHAR(50) | | | Teams |
| `channel_id` | VARCHAR(120) | | | |
| `message_id` | VARCHAR(120) | | | |
| `received_at` | TEXT | | | |
| `reject_reason` | VARCHAR(200) | | `''` | |
| `drop_reason` | VARCHAR(200) | | `''` | |
| `ai_audit_comment` | TEXT | YES | | AI 감사 코멘트 |
| `ai_audit_date` | TEXT | YES | | |
| `ai_audit_cnt` | INTEGER | | `0` | |
| `is_scheduled` | INTEGER | | `0` | 예약 실행 여부 |
| `scheduled_at` | TEXT | YES | | 예약 시각 |

제거됨(마이그레이션): `madang_id`, `approver`, `requester_name` → idx/조회 시 조립로 대체.

API 계산 필드(비저장): `requester_name`, `approver_name`, `requester_userid`, `approver_userid`.

### 3.5 `jobs_scheduled`

예약 대기 작업. `jobs.is_scheduled=1` 과 연동.

| 컬럼 | 타입 | NULL | 기본값 | 설명 |
|------|------|------|--------|------|
| `idx` | BIGSERIAL | PK | | |
| `job_idx` | BIGINT | UNIQUE, FK→`jobs.idx` CASCADE | | |

### 3.6 `jobs_result`

| 컬럼 | 타입 | NULL | 기본값 | 설명 |
|------|------|------|--------|------|
| `srnum` | VARCHAR(20) | PK | | `jobs.srnum` |
| `result` | TEXT | | | 결과 본문 |
| `complete_date` | TEXT | | | |

### 3.7 `mynotes` / `mynote_contents`

**mynotes**

| 컬럼 | 타입 | NULL | 기본값 | 설명 |
|------|------|------|--------|------|
| `idx` | BIGSERIAL | PK | | |
| `user_idx` | BIGINT | NOT NULL | | 소유자 `users.idx` |
| `note_name` | VARCHAR(200) | | | |
| `create_date` | TEXT | | | |
| `origin_file` | VARCHAR(200) | | | |
| `last_update` | TEXT | | | |

INDEX `ix_mynotes_user_idx` (`user_idx`)

제거됨: `userid` (문자열) → `user_idx`. Redis/파일 경로는 조회한 `users.userid`로만 조립.

**mynote_contents**

| 컬럼 | 타입 | NULL | 기본값 | 설명 |
|------|------|------|--------|------|
| `note_idx` | BIGINT | PK, FK→`mynotes.idx` CASCADE | | |
| `content` | TEXT | | `''` | 본문 |
| `updated_at` | TEXT | | | |

### 3.8 `prompt_offer`

대화 단말 질의어 추천.

| 컬럼 | 타입 | NULL | 기본값 | 설명 |
|------|------|------|--------|------|
| `idx` | SERIAL | PK | | |
| `prompt` | VARCHAR(300) | | | 추천 질의 문구 |

### 3.9 `infra_cluster` / `vsphere_infra_info`

**infra_cluster**

| 컬럼 | 타입 | NULL | 기본값 | 설명 |
|------|------|------|--------|------|
| `idx` | BIGSERIAL | PK | | |
| `cluster_name` | VARCHAR(50) | UNIQUE | | |
| `display_name` | VARCHAR(100) | | `''` | |
| `last_update` | TEXT | YES | | 스크랩 시각 |
| `cron` | INTEGER | | `0` | 스케줄 사용 |
| `cron_expr` | VARCHAR(20) | | `'0 23 * * 6'` | |
| `infra_type` | VARCHAR(20) | | `'k8s'` | §2.6 |
| `is_prod` | INTEGER | | `1` | PROD(1)/DEV(0) |

**vsphere_infra_info**

| 컬럼 | 타입 | NULL | 기본값 | 설명 |
|------|------|------|--------|------|
| `vsphere_idx` | BIGINT | PK, FK→`infra_cluster.idx` CASCADE | | |
| `vsphere_url` | TEXT | | `''` | |
| `vsphere_id` | VARCHAR(200) | | `''` | |
| `vsphere_pw` | TEXT | | `''` | |

### 3.10 `mailserver_config`

SMTP/IMAP 설정. 운영상 1행 사용을 가정.

| 컬럼 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `idx` | BIGSERIAL PK | | |
| `enabled` | INTEGER | `0` | |
| `smtp_host` | VARCHAR(200) | `''` | |
| `smtp_port` | INTEGER | `587` | |
| `smtp_username` | VARCHAR(200) | `''` | |
| `smtp_password` | TEXT | `''` | |
| `from_address` | VARCHAR(200) | `''` | |
| `smtp_auth` | INTEGER | `1` | |
| `use_tls` | INTEGER | `1` | |
| `use_ssl` | INTEGER | `0` | |
| `timeout_seconds` | DOUBLE PRECISION | `30` | |
| `receive_enabled` | INTEGER | `0` | IMAP 수신 |
| `imap_host` | VARCHAR(200) | `''` | |
| `imap_port` | INTEGER | `993` | |
| `imap_use_ssl` | INTEGER | `1` | |
| `updated_at` | TEXT | `''` | |

### 3.11 `received_mail`

| 컬럼 | 타입 | NULL | 기본값 | 설명 |
|------|------|------|--------|------|
| `idx` | BIGSERIAL | PK | | |
| `uuid` | VARCHAR(36) | UNIQUE | | 첨부 디렉터리 키 |
| `decision_type` | INTEGER | | `0` | §2.7 |
| `message_id` | VARCHAR(500) | | `''` | |
| `imap_uid` | BIGINT | YES | | |
| `pop3_uidl` | VARCHAR(500) | | `''` | |
| `mailbox` | VARCHAR(100) | | `'INBOX'` | |
| `subject` | TEXT | | `''` | |
| `from_address` | VARCHAR(500) | | `''` | |
| `to_addresses` | TEXT | | `''` | |
| `cc_addresses` | TEXT | | `''` | |
| `body_text` | TEXT | | `''` | |
| `received_at` | TEXT | | `''` | |
| `fetched_at` | TEXT | | `''` | |
| `attachment_count` | INTEGER | | `0` | |
| `attachment_names` | TEXT | | `'[]'` | JSON 배열 문자열 |
| `unreadable_attachment_names` | TEXT | | `'[]'` | JSON 배열 문자열 |

인덱스:

- UNIQUE(`mailbox`, `imap_uid`) WHERE `imap_uid IS NOT NULL`
- `message_id` (비어 있지 않을 때)
- `fetched_at DESC`

### 3.12 `work_node`

논리 키: `uuid`. `idx`는 SERIAL PK(레거시 호환).  
추가 컬럼·마이그레이션은 `ensure_workflow_tables()`에서도 보정한다.

| 컬럼 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `idx` | SERIAL PK | | |
| `uuid` | VARCHAR(36) UNIQUE | | |
| `owner` | INTEGER | `1` | 소유자 `users.idx` |
| `work_name` | VARCHAR(100) | | |
| `work_description` | VARCHAR(500) | `''` | |
| `target_agent` | INTEGER | `0` | agentruntime idx 등 |
| `work_script` | TEXT | `''` | |
| `script_type` | VARCHAR(20) | `''` | §2.8 |
| `test_result` | INTEGER | `0` | |
| `files` | VARCHAR(300) | `''` | |
| `create_date` | TEXT | `''` | |
| `validate_date` | TEXT | `''` | |
| `last_start_date` | TEXT | `''` | |
| `last_end_date` | TEXT | `''` | |
| `last_success` | INTEGER | `0` | |
| `last_fail_reason` | VARCHAR(200) | `''` | |
| `use_previous_work_result` | INTEGER | `0` | |
| `work_report` | VARCHAR(400) | `''` | 결과 메일 수신자 |
| `cron` | INTEGER | `0` | 노드 스케줄 |
| `cron_expr` | VARCHAR(20) | `'0 9 * * *'` | 당일 1회 시각 |
| `schedule_wait` | INTEGER | `0` | |
| `worker` | VARCHAR(10) | `'agent'` | §2.9 |
| `upload` | INTEGER | `0` | HITL 업로드 |
| `upload_path` | VARCHAR(500) | `''` | |
| `approver_idx` | INTEGER | `0` | HITL 승인자 `users.idx` (0=미지정) |
| `crud` | VARCHAR(4) | `''` | §2.10 |

제거됨: `approver_userid` (문자열) → `approver_idx`.  
API 계산 필드: `approver_userid` (`users.userid`). 워크플로 표현식 `H:{userid}` 포맷은 유지(경계에서 idx↔userid 변환).

### 3.13 `workflow`

| 컬럼 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `idx` | SERIAL PK | | |
| `uuid` | VARCHAR(36) UNIQUE | | |
| `owner` | INTEGER | `1` | 소유자 `users.idx` |
| `distribute` | BOOLEAN | FALSE | 배포/공유 |
| `workflow_name` | VARCHAR(100) | | |
| `workflow_description` | VARCHAR(500) | `''` | |
| `workflow` | TEXT | `''` | 흐름 JSON 문자열 |
| `create_date` | TEXT | `''` | |
| `test_result` | INTEGER | `0` | |
| `validate_date` | TEXT | `''` | |
| `last_start_date` | TEXT | `''` | |
| `last_end_date` | TEXT | `''` | |
| `cron` | INTEGER | `0` | 워크플로 스케줄 |
| `cron_expr` | VARCHAR(20) | `'0 9 * * *'` | |
| `merge_work_result` | VARCHAR(2000) | `''` | 취합 대상 work_node uuid CSV |

제거됨: `checkin_user`, `checkin_time` (owner/distribute 모델로 대체).

### 3.14 `workflow_history` / `work_node_history`

최종 스키마는 `ensure_workflow_tables()` 기준.  
(`schema.postgres.sql`의 `finish_success`/`result_file`은 기동 시 `success`로 이관·DROP)

**workflow_history**

| 컬럼 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `idx` | SERIAL PK | | |
| `uuid` | VARCHAR(36) | | workflow uuid |
| `start_date` | TEXT | `''` | |
| `end_date` | TEXT | `''` | |
| `success` | INTEGER | `0` | |
| `user_idx` | INTEGER | `1` | 실행자 `users.idx` |

INDEX `ix_workflow_history_uuid` (`uuid`)

**work_node_history**

| 컬럼 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `idx` | SERIAL PK | | |
| `uuid` | VARCHAR(36) | | work_node uuid |
| `start_date` | TEXT | `''` | |
| `end_date` | TEXT | `''` | |
| `success` | INTEGER | `0` | |
| `workflow_history_idx` | INTEGER | `0` | 소속 실행 |
| `user_idx` | INTEGER | `1` | 실행자 `users.idx` |

INDEX(`uuid`), INDEX(`workflow_history_idx`)

### 3.15 `workflow_template`

| 컬럼 | 타입 | NULL | 기본값 | 설명 |
|------|------|------|--------|------|
| `idx` | SERIAL | PK | | |
| `template_name` | VARCHAR(70) | UNIQUE | | |
| `template_filename` | VARCHAR(200) | UNIQUE | | |
| `update_date` | TEXT | | `''` | |
| `created_by` | INTEGER | | `1` | 작성자 `users.idx` |

---

## 4. 동적 인벤토리 테이블

`infra_cluster` 등록 후 scrape 시 **클러스터별 테이블**이 생성된다.  
백업: `{table}_{YYYYMMDD_HHMMSS}` (최근 스탬프 세트 유지).

### 4.1 `infra_type=k8s`

| 테이블 | 주요 컬럼 |
|--------|-----------|
| `{cluster}_k8s_nodes` | `node_name`, `node_cpu`, `node_mem`, `node_os`, `node_k8s_ver`, `node_role` |
| `{cluster}_k8s_namespaces` | `namespace`, `okd_display_name`, RQ/egress 관련 |
| `{cluster}_k8s_deployments` | `namespace_id` FK, `name`, `type`, replicas, resource, containers* |
| `{cluster}_k8s_pvcs` | `namespace_id`, `deployment_id`, `name`, storage |
| `{cluster}_k8s_pods_on_nodes` | 노드별 파드 요약 |

### 4.2 `infra_type=kubevirt`

| 테이블 |
|--------|
| `{cluster}_kubevirt_nodes` |
| `{cluster}_kubevirt_namespaces` |
| `{cluster}_kubevirt_deployments` |
| `{cluster}_kubevirt_pvcs` |
| `{cluster}_kubevirt_vms` |
| `{cluster}_kubevirt_vm_volumes` |
| `{cluster}_kubevirt_pods_on_nodes` |

### 4.3 `infra_type=vSphere`

| 테이블 | 주요 컬럼 |
|--------|-----------|
| `{cluster}_vsphere_cluster` | `cluster_id`, `cluster_name`, HA/DRS |
| `{cluster}_vsphere_hosts` | `host_id`, `host_name`, `cluster_id`, cpu/mem |
| `{cluster}_vsphere_vms_on_host` | `vm_id`, host 연계 |
| `{cluster}_vsphere_datastores` | datastore / datacenter |

상세 CREATE는 `backend/app/db/k8s_inventory.py`, `kubevirt_inventory.py`, `vsphere_inventory.py` 참고.

---

## 5. 관계 요약

```
users.idx ──┬── work_node.owner / workflow.owner / *_history.user_idx
            ├── work_node.approver_idx (0=미지정)
            ├── workflow_template.created_by
            ├── jobs.requester_idx / jobs.approver_idx
            ├── mynotes.user_idx
            └── notice_board.writer_idx

agentruntime.idx ≈ work_node.target_agent (정수 참조, DB FK 아님)

jobs.idx ── jobs_scheduled.job_idx (CASCADE)
jobs.srnum ── jobs_result.srnum

mynotes.idx ── mynote_contents.note_idx (CASCADE)

infra_cluster.idx ── vsphere_infra_info.vsphere_idx (CASCADE)

workflow.uuid ── workflow_history.uuid
work_node.uuid ── work_node_history.uuid
workflow_history.idx ≈ work_node_history.workflow_history_idx
```

---

## 6. 스키마 적용

- 기동 시 `init_database`가 `schema.postgres.sql` + 각 `ensure_*`를 **idempotent** 적용
- 멀티 파드: Postgres advisory lock으로 직렬화 ([`docs/ARCHITECTURE_MULTIPOD.md`](ARCHITECTURE_MULTIPOD.md))

스키마가 바뀌면 본 문서와 `schema.postgres.sql` / `ensure_*`를 함께 갱신한다.
