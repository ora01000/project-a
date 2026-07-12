CREATE TABLE IF NOT EXISTS users (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    userid VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(50) NOT NULL,
    username VARCHAR(50) NOT NULL,
    password VARCHAR(50) NOT NULL,
    depart VARCHAR(100) NOT NULL,
    role INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL,
    role VARCHAR(200) NOT NULL,
    system_prompt TEXT NOT NULL,
    mcp_server_keys VARCHAR(200) NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    request_date DATE NOT NULL,
    job_title VARCHAR(200) NOT NULL,
    request_depart VARCHAR(50) NOT NULL,
    requester VARCHAR(50) NOT NULL,
    requester_email VARCHAR(50) NOT NULL,
    completion_request_date DATE NOT NULL,
    job_description TEXT NOT NULL,
    approver VARCHAR(50) NOT NULL,
    state INTEGER NOT NULL DEFAULT 0,
    notify_channel VARCHAR(30) NOT NULL DEFAULT 'integrated_chat',
    job_plan TEXT,
    execution_result TEXT
);

CREATE TABLE IF NOT EXISTS job_notifications (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    job_idx INTEGER NOT NULL,
    target_user VARCHAR(50) NOT NULL,
    notification_type VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_idx) REFERENCES jobs(idx)
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
