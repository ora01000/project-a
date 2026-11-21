-- PostgreSQL core schema (Phase 1). Dynamic inventory tables are created at runtime.
-- Apply via init_database when DATABASE_URL is postgresql://...

CREATE TABLE IF NOT EXISTS users (
    idx BIGSERIAL PRIMARY KEY,
    userid TEXT NOT NULL,
    email TEXT NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    userid_bidx VARCHAR(64) NOT NULL DEFAULT '',
    email_bidx VARCHAR(64) NOT NULL DEFAULT '',
    depart VARCHAR(100) NOT NULL,
    role INTEGER NOT NULL,
    band INTEGER NOT NULL DEFAULT 1,
    agents VARCHAR(200) NOT NULL DEFAULT '',
    last_login TEXT,
    request_reason VARCHAR(200) NOT NULL DEFAULT '',
    whatap_event_sub INTEGER NOT NULL DEFAULT 0,
    prod_auth INTEGER NOT NULL DEFAULT 0,
    current_prod_mode INTEGER NOT NULL DEFAULT 1,
    theme_for_dev_mode INTEGER NOT NULL DEFAULT 1,
    theme_for_prod_mode INTEGER NOT NULL DEFAULT 1
);

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS prod_auth INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS current_prod_mode INTEGER NOT NULL DEFAULT 1;
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS theme_for_dev_mode INTEGER NOT NULL DEFAULT 1;
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS theme_for_prod_mode INTEGER NOT NULL DEFAULT 1;

-- users field crypto: widen plaintext columns for AES-GCM tokens; blind indexes for lookup
ALTER TABLE users ALTER COLUMN userid TYPE TEXT;
ALTER TABLE users ALTER COLUMN email TYPE TEXT;
ALTER TABLE users ALTER COLUMN username TYPE TEXT;
ALTER TABLE users ALTER COLUMN password TYPE TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS userid_bidx VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_bidx VARCHAR(64) NOT NULL DEFAULT '';
-- Drop legacy UNIQUE(userid) if present; uniqueness moves to userid_bidx.
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_userid_key;
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_userid_bidx
    ON users (userid_bidx)
    WHERE userid_bidx <> '';
-- email is not unique in this product (e.g. root/isyun share an address).
DROP INDEX IF EXISTS ux_users_email_bidx;
CREATE INDEX IF NOT EXISTS ix_users_email_bidx
    ON users (email_bidx)
    WHERE email_bidx <> '';

CREATE TABLE IF NOT EXISTS agentruntime (
    idx BIGSERIAL PRIMARY KEY,
    type INTEGER NOT NULL,
    agent_name VARCHAR(50) NOT NULL,
    agent_id VARCHAR(50) NOT NULL,
    local_agent_id VARCHAR(50) NOT NULL DEFAULT '',
    description VARCHAR(255) NOT NULL,
    registered_date TEXT NOT NULL,
    service_id VARCHAR(20) NOT NULL,
    talkable INTEGER NOT NULL DEFAULT 1,
    is_orchestrator INTEGER NOT NULL DEFAULT 0,
    is_prod INTEGER NOT NULL DEFAULT 1
);

ALTER TABLE agentruntime
    ADD COLUMN IF NOT EXISTS is_prod INTEGER NOT NULL DEFAULT 1;
-- Allow DEV/PROD pairs with the same AXIT agent_id.
ALTER TABLE agentruntime DROP CONSTRAINT IF EXISTS agentruntime_type_agent_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS ux_agentruntime_type_agent_id_is_prod
    ON agentruntime (type, agent_id, is_prod);

CREATE TABLE IF NOT EXISTS notice_board (
    idx BIGSERIAL PRIMARY KEY,
    writer_idx BIGINT NOT NULL,
    write_date TEXT NOT NULL,
    from_date TEXT NOT NULL,
    until_date TEXT NOT NULL,
    title VARCHAR(100) NOT NULL,
    notice TEXT NOT NULL,
    welcome_popup INTEGER NOT NULL DEFAULT 0
);

-- notice_board: writer (userid string) -> writer_idx (users.idx)
ALTER TABLE notice_board ADD COLUMN IF NOT EXISTS writer_idx BIGINT;
DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = current_schema() AND table_name = 'notice_board' AND column_name = 'writer'
  ) THEN
    UPDATE notice_board n
    SET writer_idx = COALESCE((SELECT u.idx FROM users u WHERE u.userid = n.writer), 1)
    WHERE n.writer_idx IS NULL;
  END IF;
END $$;
UPDATE notice_board SET writer_idx = 1 WHERE writer_idx IS NULL;
ALTER TABLE notice_board ALTER COLUMN writer_idx SET NOT NULL;
ALTER TABLE notice_board DROP COLUMN IF EXISTS writer;

CREATE TABLE IF NOT EXISTS jobs (
    idx BIGSERIAL PRIMARY KEY,
    srnum VARCHAR(20) NOT NULL UNIQUE,
    status_code INTEGER NOT NULL DEFAULT 0,
    job_type INTEGER NOT NULL DEFAULT 1,
    approver_registered_date TEXT,
    approver_idx BIGINT,
    job_title VARCHAR(300) NOT NULL,
    requester_email VARCHAR(100) NOT NULL,
    requester_depart VARCHAR(100) NOT NULL,
    job_content TEXT NOT NULL,
    request_date TEXT NOT NULL,
    requester_idx BIGINT NOT NULL DEFAULT 1,
    team_id VARCHAR(50) NOT NULL,
    channel_id VARCHAR(120) NOT NULL,
    message_id VARCHAR(120) NOT NULL,
    received_at TEXT NOT NULL,
    reject_reason VARCHAR(200) NOT NULL DEFAULT '',
    drop_reason VARCHAR(200) NOT NULL DEFAULT '',
    ai_audit_comment TEXT,
    ai_audit_date TEXT,
    ai_audit_cnt INTEGER NOT NULL DEFAULT 0,
    is_scheduled INTEGER NOT NULL DEFAULT 0,
    scheduled_at TEXT
);

-- jobs: user string columns (madang_id / approver / requester_name) -> users.idx
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS requester_idx BIGINT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS approver_idx BIGINT;
-- backfill from legacy columns if they exist
DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = current_schema() AND table_name = 'jobs' AND column_name = 'madang_id'
  ) THEN
    -- Existing deployments: make sure hidden system users exist before backfill
    -- (fresh DBs are seeded by init_database after the initial users).
    INSERT INTO users (userid, email, username, password, depart, role, band)
    SELECT v.userid, v.email, v.username, v.password, v.depart, v.role, v.band
    FROM (VALUES
      ('auto_approve', 'auto_approve@admin.io', 'auto_approve', 'system-no-login-auto-approve', 'System', 5, 1),
      ('whatap', 'whatap@admin.io', 'Whatap', 'system-no-login-whatap', 'Whatap', 5, 1),
      ('external', 'external@admin.io', 'External', 'system-no-login-external', 'External', 5, 1)
    ) AS v(userid, email, username, password, depart, role, band)
    WHERE EXISTS (SELECT 1 FROM users)
      AND NOT EXISTS (SELECT 1 FROM users u WHERE u.userid = v.userid);

    UPDATE jobs j SET requester_idx = COALESCE((SELECT u.idx FROM users u WHERE u.userid = j.madang_id), 1)
    WHERE requester_idx IS NULL;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = current_schema() AND table_name = 'jobs' AND column_name = 'approver'
  ) THEN
    UPDATE jobs j SET approver_idx = (SELECT u.idx FROM users u WHERE u.userid = j.approver)
    WHERE approver IS NOT NULL AND TRIM(approver) <> '' AND approver_idx IS NULL;
  END IF;
END $$;
UPDATE jobs SET requester_idx = 1 WHERE requester_idx IS NULL;
ALTER TABLE jobs ALTER COLUMN requester_idx SET DEFAULT 1;
ALTER TABLE jobs ALTER COLUMN requester_idx SET NOT NULL;
ALTER TABLE jobs DROP COLUMN IF EXISTS madang_id;
ALTER TABLE jobs DROP COLUMN IF EXISTS approver;
ALTER TABLE jobs DROP COLUMN IF EXISTS requester_name;

CREATE TABLE IF NOT EXISTS jobs_scheduled (
    idx BIGSERIAL PRIMARY KEY,
    job_idx BIGINT NOT NULL UNIQUE REFERENCES jobs(idx) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS jobs_result (
    srnum VARCHAR(20) NOT NULL PRIMARY KEY,
    result TEXT NOT NULL,
    complete_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mynotes (
    idx BIGSERIAL PRIMARY KEY,
    user_idx BIGINT NOT NULL,
    note_name VARCHAR(200) NOT NULL,
    create_date TEXT NOT NULL,
    origin_file VARCHAR(200) NOT NULL,
    last_update TEXT NOT NULL
);

-- mynotes: userid (string) -> user_idx (users.idx)
ALTER TABLE mynotes ADD COLUMN IF NOT EXISTS user_idx BIGINT;
DO $$ BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = current_schema() AND table_name = 'mynotes' AND column_name = 'userid'
  ) THEN
    UPDATE mynotes m
    SET user_idx = COALESCE((SELECT u.idx FROM users u WHERE u.userid = m.userid), 1)
    WHERE m.user_idx IS NULL;
  END IF;
END $$;
UPDATE mynotes SET user_idx = 1 WHERE user_idx IS NULL;
ALTER TABLE mynotes ALTER COLUMN user_idx SET NOT NULL;
ALTER TABLE mynotes DROP COLUMN IF EXISTS userid;
CREATE INDEX IF NOT EXISTS ix_mynotes_user_idx ON mynotes (user_idx);

CREATE TABLE IF NOT EXISTS mynote_contents (
    note_idx BIGINT PRIMARY KEY REFERENCES mynotes(idx) ON DELETE CASCADE,
    content TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

-- Suggested chat prompts for the interactive terminal (질의어 추천).
CREATE TABLE IF NOT EXISTS prompt_offer (
    idx SERIAL PRIMARY KEY,
    prompt VARCHAR(300) NOT NULL
);

CREATE TABLE IF NOT EXISTS infra_cluster (
    idx BIGSERIAL PRIMARY KEY,
    cluster_name VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL DEFAULT '',
    last_update TEXT,
    cron INTEGER NOT NULL DEFAULT 0,
    cron_expr VARCHAR(20) NOT NULL DEFAULT '0 23 * * 6',
    infra_type VARCHAR(20) NOT NULL DEFAULT 'k8s',
    is_prod INTEGER NOT NULL DEFAULT 1
);

ALTER TABLE infra_cluster
    ADD COLUMN IF NOT EXISTS display_name VARCHAR(100) NOT NULL DEFAULT '';
ALTER TABLE infra_cluster
    ADD COLUMN IF NOT EXISTS is_prod INTEGER NOT NULL DEFAULT 1;

-- vSphere credentials linked to infra_cluster.idx (infra_type = 'vSphere')
CREATE TABLE IF NOT EXISTS vsphere_infra_info (
    vsphere_idx BIGINT PRIMARY KEY REFERENCES infra_cluster(idx) ON DELETE CASCADE,
    vsphere_url TEXT NOT NULL DEFAULT '',
    vsphere_id VARCHAR(200) NOT NULL DEFAULT '',
    vsphere_pw TEXT NOT NULL DEFAULT ''
);

-- SMTP/IMAP mail server settings (singleton row; replaces EMAIL_* env / yaml)
CREATE TABLE IF NOT EXISTS mailserver_config (
    idx BIGSERIAL PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    smtp_host VARCHAR(200) NOT NULL DEFAULT '',
    smtp_port INTEGER NOT NULL DEFAULT 587,
    smtp_username VARCHAR(200) NOT NULL DEFAULT '',
    smtp_password TEXT NOT NULL DEFAULT '',
    from_address VARCHAR(200) NOT NULL DEFAULT '',
    smtp_auth INTEGER NOT NULL DEFAULT 1,
    use_tls INTEGER NOT NULL DEFAULT 1,
    use_ssl INTEGER NOT NULL DEFAULT 0,
    timeout_seconds DOUBLE PRECISION NOT NULL DEFAULT 30,
    receive_enabled INTEGER NOT NULL DEFAULT 0,
    imap_host VARCHAR(200) NOT NULL DEFAULT '',
    imap_port INTEGER NOT NULL DEFAULT 993,
    imap_use_ssl INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT ''
);

-- Inbound mail captured by IMAP/POP3 poller (worker / BACKEND_ROLE=all).
-- Column/index drift for existing DBs is applied once in init_database via
-- ensure_received_mail_table (not on every poll — concurrent DDL deadlocks).
CREATE TABLE IF NOT EXISTS received_mail (
    idx BIGSERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL UNIQUE,
    decision_type INTEGER NOT NULL DEFAULT 0,
    message_id VARCHAR(500) NOT NULL DEFAULT '',
    imap_uid BIGINT,
    pop3_uidl VARCHAR(500) NOT NULL DEFAULT '',
    mailbox VARCHAR(100) NOT NULL DEFAULT 'INBOX',
    subject TEXT NOT NULL DEFAULT '',
    from_address VARCHAR(500) NOT NULL DEFAULT '',
    to_addresses TEXT NOT NULL DEFAULT '',
    cc_addresses TEXT NOT NULL DEFAULT '',
    body_text TEXT NOT NULL DEFAULT '',
    received_at TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL DEFAULT '',
    attachment_count INTEGER NOT NULL DEFAULT 0,
    attachment_names TEXT NOT NULL DEFAULT '[]',
    unreadable_attachment_names TEXT NOT NULL DEFAULT '[]'
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_received_mail_mailbox_uid
    ON received_mail (mailbox, imap_uid)
    WHERE imap_uid IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_received_mail_message_id
    ON received_mail (message_id)
    WHERE message_id <> '';

CREATE INDEX IF NOT EXISTS ix_received_mail_pop3_uidl
    ON received_mail (pop3_uidl)
    WHERE pop3_uidl <> '';

CREATE INDEX IF NOT EXISTS ix_received_mail_fetched_at
    ON received_mail (fetched_at DESC);

ALTER TABLE received_mail
    ADD COLUMN IF NOT EXISTS pop3_uidl VARCHAR(500) NOT NULL DEFAULT '';

ALTER TABLE received_mail
    ADD COLUMN IF NOT EXISTS unreadable_attachment_names TEXT NOT NULL DEFAULT '[]';

-- Workflow designer (PLAN 260903)
-- work_node / workflow are keyed by uuid. Converting a legacy idx-keyed table
-- (backfill uuids, rewrite workflow expressions, drop idx, repoint the primary
-- key) happens in ensure_workflow_tables() because the expression rewrite needs
-- the idx -> uuid mapping in Python.
CREATE TABLE IF NOT EXISTS work_node (
    idx SERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL UNIQUE,
    owner INTEGER NOT NULL DEFAULT 1,
    work_name VARCHAR(100) NOT NULL,
    work_description VARCHAR(500) NOT NULL DEFAULT '',
    target_agent INTEGER NOT NULL DEFAULT 0,
    work_script TEXT NOT NULL DEFAULT '',
    script_type VARCHAR(20) NOT NULL DEFAULT '',
    test_result INTEGER NOT NULL DEFAULT 0,
    files VARCHAR(300) NOT NULL DEFAULT '',
    create_date TEXT NOT NULL DEFAULT '',
    validate_date TEXT NOT NULL DEFAULT ''
);

ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS uuid VARCHAR(36) NOT NULL DEFAULT '';
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS owner INTEGER NOT NULL DEFAULT 1;
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS work_description VARCHAR(500) NOT NULL DEFAULT '';
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS work_script TEXT NOT NULL DEFAULT '';
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS script_type VARCHAR(20) NOT NULL DEFAULT '';
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS create_date TEXT NOT NULL DEFAULT '';
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS validate_date TEXT NOT NULL DEFAULT '';
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS work_report VARCHAR(400) NOT NULL DEFAULT '';
ALTER TABLE work_node
    ALTER COLUMN work_report TYPE VARCHAR(400);
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS cron INTEGER NOT NULL DEFAULT 0;
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS cron_expr VARCHAR(20) NOT NULL DEFAULT '0 9 * * *';
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS schedule_wait INTEGER NOT NULL DEFAULT 0;
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS worker VARCHAR(10) NOT NULL DEFAULT 'agent';
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS upload INTEGER NOT NULL DEFAULT 0;
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS upload_path VARCHAR(500) NOT NULL DEFAULT '';
-- work_node: approver_userid (string) -> approver_idx (users.idx; 0 = none/unmatched)
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS approver_idx INTEGER NOT NULL DEFAULT 0;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'work_node'
          AND column_name = 'approver_userid'
    ) THEN
        UPDATE work_node w
        SET approver_idx = COALESCE(
            (SELECT u.idx FROM users u WHERE u.userid = w.approver_userid LIMIT 1),
            0
        )
        WHERE w.approver_userid IS NOT NULL
          AND btrim(w.approver_userid) <> ''
          AND w.approver_idx = 0;
        ALTER TABLE work_node DROP COLUMN IF EXISTS approver_userid;
    END IF;
END $$;
UPDATE work_node SET approver_idx = 0 WHERE approver_idx IS NULL;
ALTER TABLE work_node ALTER COLUMN approver_idx SET DEFAULT 0;
ALTER TABLE work_node ALTER COLUMN approver_idx SET NOT NULL;
-- Legacy column cleanup (agent_response → work_script, drop user_prompt)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'work_node'
          AND column_name = 'agent_response'
    ) THEN
        UPDATE work_node
        SET work_script = agent_response
        WHERE btrim(COALESCE(work_script, '')) = ''
          AND btrim(COALESCE(agent_response, '')) <> '';
        ALTER TABLE work_node DROP COLUMN IF EXISTS agent_response;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'work_node'
          AND column_name = 'user_prompt'
    ) THEN
        ALTER TABLE work_node DROP COLUMN IF EXISTS user_prompt;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS workflow (
    idx SERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL UNIQUE,
    owner INTEGER NOT NULL DEFAULT 1,
    distribute BOOLEAN NOT NULL DEFAULT FALSE,
    workflow_name VARCHAR(100) NOT NULL,
    workflow_description VARCHAR(500) NOT NULL DEFAULT '',
    workflow TEXT NOT NULL DEFAULT '',
    create_date TEXT NOT NULL DEFAULT '',
    test_result INTEGER NOT NULL DEFAULT 0,
    validate_date TEXT NOT NULL DEFAULT '',
    cron INTEGER NOT NULL DEFAULT 0,
    cron_expr VARCHAR(20) NOT NULL DEFAULT '0 9 * * *',
    merge_work_result VARCHAR(2000) NOT NULL DEFAULT ''
);

ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS uuid VARCHAR(36) NOT NULL DEFAULT '';
ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS owner INTEGER NOT NULL DEFAULT 1;
ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS distribute BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS create_date TEXT NOT NULL DEFAULT '';
ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS test_result INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS validate_date TEXT NOT NULL DEFAULT '';
ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS cron INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS cron_expr VARCHAR(20) NOT NULL DEFAULT '0 9 * * *';
ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS merge_work_result VARCHAR(2000) NOT NULL DEFAULT '';
-- Legacy checkin columns (owner/distribute model); drop if present
ALTER TABLE workflow DROP COLUMN IF EXISTS checkin_user;
ALTER TABLE workflow DROP COLUMN IF EXISTS checkin_time;

CREATE TABLE IF NOT EXISTS workflow_history (
    idx SERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL,
    start_date TEXT NOT NULL DEFAULT '',
    end_date TEXT NOT NULL DEFAULT '',
    finish_success INTEGER NOT NULL DEFAULT 0,
    result_file VARCHAR(1000) NOT NULL DEFAULT '',
    user_idx INTEGER NOT NULL DEFAULT 1
);
ALTER TABLE workflow_history
    ADD COLUMN IF NOT EXISTS user_idx INTEGER NOT NULL DEFAULT 1;
UPDATE workflow_history
SET user_idx = 1
WHERE user_idx IS NULL OR user_idx <= 0;
CREATE INDEX IF NOT EXISTS ix_workflow_history_uuid ON workflow_history (uuid);

CREATE TABLE IF NOT EXISTS workflow_template (
    idx SERIAL PRIMARY KEY,
    template_name VARCHAR(70) NOT NULL UNIQUE,
    template_filename VARCHAR(200) NOT NULL UNIQUE,
    update_date TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_workflow_template_name ON workflow_template (template_name);
CREATE INDEX IF NOT EXISTS ix_workflow_template_filename ON workflow_template (template_filename);

-- inventory / inventory_api metadata is managed by the remote inventory-api service.
DROP TABLE IF EXISTS inventory_api CASCADE;
DROP TABLE IF EXISTS inventory CASCADE;
