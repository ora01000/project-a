CREATE TABLE IF NOT EXISTS users (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    userid VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(50) NOT NULL,
    username VARCHAR(50) NOT NULL,
    password VARCHAR(50) NOT NULL,
    depart VARCHAR(100) NOT NULL,
    role INTEGER NOT NULL,
    band INTEGER NOT NULL DEFAULT 1,
    agents VARCHAR(200) NOT NULL DEFAULT '',
    last_login TEXT,
    request_reason VARCHAR(200) NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS agentruntime (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE IF NOT EXISTS signup_notifications (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    user_idx INTEGER NOT NULL,
    target_user VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_idx) REFERENCES users(idx)
);

CREATE TABLE IF NOT EXISTS notice_board (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    writer VARCHAR(50) NOT NULL,
    write_date TEXT NOT NULL,
    from_date TEXT NOT NULL,
    until_date TEXT NOT NULL,
    title VARCHAR(100) NOT NULL,
    notice TEXT NOT NULL,
    welcome_popup INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS jobs (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
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
    drop_reason VARCHAR(200) NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS jobs_result (
    srnum VARCHAR(20) NOT NULL PRIMARY KEY,
    result TEXT NOT NULL,
    complete_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mynotes (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    userid VARCHAR(50) NOT NULL,
    note_name VARCHAR(50) NOT NULL,
    create_date TEXT NOT NULL,
    origin_file VARCHAR(200) NOT NULL,
    last_update TEXT NOT NULL
);
