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
    last_login TEXT
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

CREATE TABLE IF NOT EXISTS k8s_cluster (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_name VARCHAR(50) NOT NULL UNIQUE,
    last_update TEXT
);

CREATE TABLE IF NOT EXISTS k8s_nodes (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER NOT NULL,
    node_name VARCHAR(50) NOT NULL,
    node_cpu INTEGER,
    node_mem INTEGER,
    node_os VARCHAR(50),
    node_k8s_ver VARCHAR(50),
    FOREIGN KEY (cluster_id) REFERENCES k8s_cluster(idx)
);

CREATE TABLE IF NOT EXISTS k8s_namespaces (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER NOT NULL,
    namespace VARCHAR(50) NOT NULL,
    okd_display_name VARCHAR(100),
    resource_quota_cpu_limit REAL,
    resource_quota_mem_limit INTEGER,
    resource_quota_pod_limit INTEGER,
    okd_egressip1 VARCHAR(20),
    okd_egressip2 VARCHAR(20),
    FOREIGN KEY (cluster_id) REFERENCES k8s_cluster(idx)
);

CREATE TABLE IF NOT EXISTS k8s_deployments (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER NOT NULL,
    namespace_id INTEGER NOT NULL,
    name VARCHAR(50) NOT NULL,
    type VARCHAR(20) NOT NULL,
    replicas INTEGER,
    resource_cpu_request REAL,
    resource_mem_request INTEGER,
    resource_cpu_limit REAL,
    resource_mem_limit INTEGER,
    containers_cnt INTEGER,
    containers_name VARCHAR(300),
    containers_image VARCHAR(500),
    FOREIGN KEY (cluster_id) REFERENCES k8s_cluster(idx),
    FOREIGN KEY (namespace_id) REFERENCES k8s_namespaces(idx)
);

CREATE TABLE IF NOT EXISTS k8s_pvcs (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER NOT NULL,
    namespace_id INTEGER NOT NULL,
    deployment_id INTEGER,
    name VARCHAR(50) NOT NULL,
    storage_class VARCHAR(20),
    capacity INTEGER,
    used INTEGER,
    access_mode VARCHAR(20),
    FOREIGN KEY (cluster_id) REFERENCES k8s_cluster(idx),
    FOREIGN KEY (namespace_id) REFERENCES k8s_namespaces(idx),
    FOREIGN KEY (deployment_id) REFERENCES k8s_deployments(idx)
);

CREATE TABLE IF NOT EXISTS k8s_pods (
    idx INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER NOT NULL,
    namespace_id INTEGER NOT NULL,
    deployment_id INTEGER,
    name VARCHAR(50) NOT NULL,
    scheduled_node INTEGER,
    FOREIGN KEY (cluster_id) REFERENCES k8s_cluster(idx),
    FOREIGN KEY (namespace_id) REFERENCES k8s_namespaces(idx),
    FOREIGN KEY (deployment_id) REFERENCES k8s_deployments(idx),
    FOREIGN KEY (scheduled_node) REFERENCES k8s_nodes(idx)
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
