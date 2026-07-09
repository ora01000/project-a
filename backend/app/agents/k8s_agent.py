from backend.app.agents.base import AgentDefinition

K8S_CLUSTER_SPECS: list[tuple[str, str]] = [
    ("dprv6-k8s", "구 PaaS 대개체 개발기(6층)"),
    ("pcicd-k8s", "빌드팜(6층)"),
    ("dprv-k8s", "IT공통 개발기"),
    ("dprsv-k8s", "UCube 서비스/청구/수미납 개발기"),
    ("dprmn-k8s", "UCube 공통 개발기"),
    ("dprrt-k8s", "UCube 과금 개발기"),
    ("dpvs-k8s", "Provisioning 개발기"),
    ("dtest-k8s", "테스트 클러스터"),
]


def _build_k8s_system_prompt(cluster_id: str, display_name: str) -> str:
    return (
        f"You are a Kubernetes cluster information specialist for cluster `{cluster_id}` ({display_name}). "
        f"Always scope queries and answers to this cluster only. "
        "Use kubernetes-mcp-server and kubectl-ai MCP tools to query cluster resources such as "
        "namespaces, pods, nodes, deployments, services, and events. "
        "Provide concise, structured answers in Korean when possible. "
        "Do not perform destructive operations; read-only queries only."
    )


def create_k8s_cluster_agent(cluster_id: str, display_name: str) -> AgentDefinition:
    return AgentDefinition(
        agent_id=cluster_id,
        name=display_name,
        role=f"{display_name} Kubernetes 클러스터 정보 조회",
        mcp_server_keys=["kubernetes", "kubectl_ai"],
        system_prompt=_build_k8s_system_prompt(cluster_id, display_name),
    )


K8S_CLUSTER_AGENTS: list[AgentDefinition] = [
    create_k8s_cluster_agent(cluster_id, display_name)
    for cluster_id, display_name in K8S_CLUSTER_SPECS
]
