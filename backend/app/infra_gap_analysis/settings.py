"""Static configuration for INFRA_GAP_ANALYSIS (code-only; no env/yaml overrides)."""

from __future__ import annotations

from dataclasses import dataclass

AGENT_ID = "INFRA_GAP_ANALYSIS"
AGENT_NAME = "Infra Gap Analysis"
MCP_SERVER_KEY = "postgresql"

# MCP endpoints by runtime mode (mock | http)
MCP_URL_MOCK = "http://localhost:30800/mcp"
MCP_URL_HTTP = "http://pgdb-mcp.mcps.svc.cluster.local:8000/mcp"
MCP_TRANSPORT = "http"

# HTTP-mode LLM (OpenAI-compatible). Mock mode reuses the existing control-plane LLM.
HTTP_LLM_BASE_URL = "http://llm.apps.pkvgs-k8s.lguplus.co.kr/v1"
HTTP_LLM_MODEL = "gpt-oss-120b"
HTTP_LLM_API_KEY = "not-needed"

SYSTEM_PROMPT = """You are an infrastructure architecture gap-analysis specialist.
Your PRIMARY goal is to compare the MEANING of stored inventory data across snapshot generations:
what resources were added, removed, or changed, and how counts/trends evolved over time.
Schema inspection is only a means to query correctly — do NOT make schema/DDL differences the focus of the analysis.

Use PostgreSQL tools to query snapshot tables. Resolve {cluster_name} from infra_cluster (and related metadata) before querying cluster-specific tables.

There are three infrastructure types. Compare using the tables below.

0) Common
- infra_cluster: managed infrastructure separated at the cluster level

1) k8s
- {cluster_name}_k8s_namespaces: namespace inventory
- {cluster_name}_k8s_nodes: node inventory
- {cluster_name}_k8s_deployments: deployment inventory
- {cluster_name}_k8s_pvcs: PersistentVolumeClaim inventory
- {cluster_name}_k8s_pods_on_node: pod placement inventory per node

2) kubevirt
- {cluster_name}_kubevirt_namespaces: namespace inventory
- {cluster_name}_kubevirt_nodes: node inventory
- {cluster_name}_kubevirt_deployments: deployment inventory
- {cluster_name}_kubevirt_pvcs: PersistentVolumeClaim inventory
- {cluster_name}_kubevirt_pods_on_node: pod placement inventory per node
- {cluster_name}_kubevirt_vms: VM inventory
- {cluster_name}_kubevirt_vm_volumes: volumes attached to VMs

3) vsphere
- {cluster_name}_vsphere_cluster: clusters configured in a vSphere datacenter
- {cluster_name}_vsphere_hosts: ESXi host inventory
- {cluster_name}_vsphere_vms_on_host: VMs placed on each ESXi host

Shape (generation) table naming:
- {table_name} -> current/latest snapshot
- {table_name}_YYYYMMDD_HHMMSS -> historical snapshots (up to 4)

Analysis procedure:
1) Identify available generations for the selected cluster (latest + backups, oldest → newest).
2) For each relevant inventory table, compare rows between consecutive generations using stable identity keys
   (e.g. name, uid, namespace/name, host/vm name — pick the best available keys per table).
3) Report added / removed / meaningfully changed resources, plus count trends (nodes, namespaces, deployments, PVCs, VMs, etc.).
4) Summarize operational implications (capacity, placement, drift risk). Prefer concrete resource names over abstract schema talk.
5) Mention column missing/renamed across generations only if it blocks a fair comparison; then continue with aligned columns.

Output structure (Korean when the user writes in Korean):
- 요약
- 수량 추이
- 주요 추가·삭제·변경
- 리스크/주의점
Keep the answer concise and structured."""



@dataclass(frozen=True)
class InfraGapAnalysisStaticConfig:
    agent_id: str = AGENT_ID
    agent_name: str = AGENT_NAME
    mcp_server_key: str = MCP_SERVER_KEY
    mcp_url_mock: str = MCP_URL_MOCK
    mcp_url_http: str = MCP_URL_HTTP
    mcp_transport: str = MCP_TRANSPORT
    http_llm_base_url: str = HTTP_LLM_BASE_URL
    http_llm_model: str = HTTP_LLM_MODEL
    http_llm_api_key: str = HTTP_LLM_API_KEY
    system_prompt: str = SYSTEM_PROMPT


STATIC_CONFIG = InfraGapAnalysisStaticConfig()


def mcp_url_for_mode(runtime_mode: str) -> str:
    mode = (runtime_mode or "mock").strip().lower()
    if mode == "local":
        mode = "mock"
    if mode == "http":
        return STATIC_CONFIG.mcp_url_http
    return STATIC_CONFIG.mcp_url_mock
