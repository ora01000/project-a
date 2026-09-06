-- PostgreSQL core schema (Phase 1). Dynamic inventory tables are created at runtime.
-- Apply via init_database when DATABASE_URL is postgresql://...

CREATE TABLE IF NOT EXISTS users (
    idx BIGSERIAL PRIMARY KEY,
    userid VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(50) NOT NULL,
    username VARCHAR(50) NOT NULL,
    password VARCHAR(50) NOT NULL,
    depart VARCHAR(100) NOT NULL,
    role INTEGER NOT NULL,
    band INTEGER NOT NULL DEFAULT 1,
    agents VARCHAR(200) NOT NULL DEFAULT '',
    last_login TEXT,
    request_reason VARCHAR(200) NOT NULL DEFAULT '',
    whatap_event_sub INTEGER NOT NULL DEFAULT 0
);

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
    UNIQUE(type, agent_id)
);

CREATE TABLE IF NOT EXISTS notice_board (
    idx BIGSERIAL PRIMARY KEY,
    writer VARCHAR(50) NOT NULL,
    write_date TEXT NOT NULL,
    from_date TEXT NOT NULL,
    until_date TEXT NOT NULL,
    title VARCHAR(100) NOT NULL,
    notice TEXT NOT NULL,
    welcome_popup INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS jobs (
    idx BIGSERIAL PRIMARY KEY,
    srnum VARCHAR(20) NOT NULL UNIQUE,
    status_code INTEGER NOT NULL DEFAULT 0,
    job_type INTEGER NOT NULL DEFAULT 1,
    approver_registered_date TEXT,
    approver VARCHAR(20),
    job_title VARCHAR(300) NOT NULL,
    requester_name VARCHAR(100) NOT NULL,
    requester_email VARCHAR(100) NOT NULL,
    requester_depart VARCHAR(100) NOT NULL,
    job_content TEXT NOT NULL,
    request_date TEXT NOT NULL,
    madang_id VARCHAR(50) NOT NULL,
    team_id VARCHAR(50) NOT NULL,
    channel_id VARCHAR(120) NOT NULL,
    message_id VARCHAR(50) NOT NULL,
    received_at TEXT NOT NULL,
    reject_reason VARCHAR(200) NOT NULL DEFAULT '',
    drop_reason VARCHAR(200) NOT NULL DEFAULT '',
    ai_audit_comment TEXT,
    ai_audit_date TEXT,
    ai_audit_cnt INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS jobs_result (
    srnum VARCHAR(20) NOT NULL PRIMARY KEY,
    result TEXT NOT NULL,
    complete_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mynotes (
    idx BIGSERIAL PRIMARY KEY,
    userid VARCHAR(50) NOT NULL,
    note_name VARCHAR(200) NOT NULL,
    create_date TEXT NOT NULL,
    origin_file VARCHAR(200) NOT NULL,
    last_update TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mynote_contents (
    note_idx BIGINT PRIMARY KEY REFERENCES mynotes(idx) ON DELETE CASCADE,
    content TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS infra_cluster (
    idx BIGSERIAL PRIMARY KEY,
    cluster_name VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL DEFAULT '',
    last_update TEXT,
    cron INTEGER NOT NULL DEFAULT 0,
    cron_expr VARCHAR(20) NOT NULL DEFAULT '0 23 * * 6',
    infra_type VARCHAR(20) NOT NULL DEFAULT 'k8s'
);

ALTER TABLE infra_cluster
    ADD COLUMN IF NOT EXISTS display_name VARCHAR(100) NOT NULL DEFAULT '';

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

-- Inbound mail captured by IMAP poller (worker / BACKEND_ROLE=all)
CREATE TABLE IF NOT EXISTS received_mail (
    idx BIGSERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL UNIQUE,
    decision_type INTEGER NOT NULL DEFAULT 0,
    message_id VARCHAR(500) NOT NULL DEFAULT '',
    imap_uid BIGINT,
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

CREATE INDEX IF NOT EXISTS ix_received_mail_fetched_at
    ON received_mail (fetched_at DESC);

ALTER TABLE received_mail
    ADD COLUMN IF NOT EXISTS unreadable_attachment_names TEXT NOT NULL DEFAULT '[]';

-- Workflow designer (PLAN 260903)
CREATE TABLE IF NOT EXISTS work_node (
    idx BIGSERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL UNIQUE,
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
    ADD COLUMN IF NOT EXISTS work_description VARCHAR(500) NOT NULL DEFAULT '';
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS work_script TEXT NOT NULL DEFAULT '';
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS script_type VARCHAR(20) NOT NULL DEFAULT '';
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS create_date TEXT NOT NULL DEFAULT '';
ALTER TABLE work_node
    ADD COLUMN IF NOT EXISTS validate_date TEXT NOT NULL DEFAULT '';
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
CREATE UNIQUE INDEX IF NOT EXISTS work_node_uuid_uidx ON work_node (uuid);

CREATE TABLE IF NOT EXISTS workflow (
    idx BIGSERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL UNIQUE,
    checkin_user INTEGER NOT NULL DEFAULT 0,
    checkin_time TEXT NOT NULL DEFAULT '',
    workflow_name VARCHAR(100) NOT NULL,
    workflow_description VARCHAR(500) NOT NULL DEFAULT '',
    workflow TEXT NOT NULL DEFAULT '',
    create_date TEXT NOT NULL DEFAULT '',
    test_result INTEGER NOT NULL DEFAULT 0,
    validate_date TEXT NOT NULL DEFAULT ''
);

ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS uuid VARCHAR(36) NOT NULL DEFAULT '';
ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS checkin_user INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS checkin_time TEXT NOT NULL DEFAULT '';
ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS create_date TEXT NOT NULL DEFAULT '';
ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS test_result INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workflow
    ADD COLUMN IF NOT EXISTS validate_date TEXT NOT NULL DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS workflow_uuid_uidx ON workflow (uuid);
