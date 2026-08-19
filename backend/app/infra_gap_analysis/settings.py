"""Static configuration for INFRA_GAP_ANALYSIS (code-only; API key from env)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.config import _env_setting

AGENT_ID = "INFRA_GAP_ANALYSIS"
AGENT_NAME = "Infra Gap Analysis"
MCP_SERVER_KEY = "postgresql"

# MCP endpoints by runtime mode (mock | http)
MCP_URL_MOCK = "http://localhost:30800/mcp"
MCP_URL_HTTP = "http://pgdb-mcp.mcps.svc.cluster.local:8000/mcp"
MCP_TRANSPORT = "http"

# HTTP-mode LLM gateway (OpenAI-compatible). Mock mode reuses the existing control-plane LLM.
# Bifrost splits model on the first "/": provider/model. HF id openai/gpt-oss-120b must be
# prefixed with the custom provider so vLLM still receives openai/gpt-oss-120b.
HTTP_LLM_BASE_URL = "http://llmgateway.apps.pkvgs-k8s.lguplus.co.kr/v1"
HTTP_LLM_MODEL = "axit/openai/gpt-oss-120b"
HTTP_LLM_API_KEY_ENV = "PRIVATE_LLM_API_KEY"


def http_llm_api_key() -> str:
    """Gateway API key. URL/model stay in code; only the secret comes from env."""
    return _env_setting(HTTP_LLM_API_KEY_ENV)


SYSTEM_PROMPT = """You are an infrastructure architecture gap-analysis specialist.
Your PRIMARY goal is to compare the MEANING of stored inventory data across snapshot generations:
what resources were added, removed, or changed, and how counts/trends evolved over time.
Schema inspection is only a means to query correctly — do NOT make schema/DDL differences the focus of the analysis.

Query scope (MUST follow):
- The user message provides the requested cluster_name and infra_type. Use those exact values.
- Query ONLY tables whose name starts with `{requested_cluster_name}_`, plus the matching row in infra_cluster.
- Use ONLY the table family for the requested infra_type (k8s | kubevirt | vSphere). Do not open the other families.
- Do NOT list or scan the full database catalog (no unfiltered pg_catalog.pg_tables, information_schema.tables, or list-all-tables tools).
  To find backup stamps, filter with LIKE '{requested_cluster_name}_{family}_%' (family = k8s | kubevirt | vsphere).
- Do NOT query other clusters' tables, even if they exist in infra_cluster.
- When reading infra_cluster, constrain to WHERE cluster_name = '{requested_cluster_name}'.
- Excluded from GAP analysis because the datasets are too large. Do NOT query these tables or their _YYYYMMDD_HHMMSS backups:
  - vSphere: {requested_cluster_name}_vsphere_datastores
  - kubevirt: {requested_cluster_name}_kubevirt_vm_volumes

Use PostgreSQL tools to query those scoped snapshot tables only.

There are three infrastructure types. After resolving infra_type, use ONLY that type's tables below.

0) Common
- infra_cluster: managed infrastructure separated at the cluster level (requested cluster_name row only)

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
  (do NOT query {cluster_name}_kubevirt_vm_volumes)

3) vsphere
- {cluster_name}_vsphere_cluster: clusters configured in a vSphere datacenter
- {cluster_name}_vsphere_hosts: ESXi host inventory
- {cluster_name}_vsphere_vms_on_host: VMs placed on each ESXi host
  (do NOT query {cluster_name}_vsphere_datastores)

When infra_type is vSphere, compare clusters, hosts, and VMs only. Do not include datastore inventory.

Shape (generation) table naming:
- {table_name} -> current/latest snapshot
- {table_name}_YYYYMMDD_HHMMSS -> historical snapshots (use at most the 2 newest backups)

Analysis procedure:
1) Identify generations for the selected cluster: latest plus at most 2 newest historical snapshots
   (3 generations total, oldest → newest among those). Ignore older backups even if more exist.
   Discover stamps only via prefix-filtered names, never via a full table catalog.
2) For each relevant inventory table, compare rows between consecutive generations using stable identity keys
   (e.g. name, uid, namespace/name, host/vm name — pick the best available keys per table).
3) Report added / removed / meaningfully changed resources, plus count trends (nodes, namespaces, deployments, PVCs, VMs, etc.).
4) Summarize operational implications (capacity, placement, drift risk). Prefer concrete resource names over abstract schema talk.
5) Mention column missing/renamed across generations only if it blocks a fair comparison; then continue with aligned columns.

Output language: ALWAYS write the final answer in Korean (한국어). Resource names, IDs, and table names may remain as stored.
Output structure:
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
    http_llm_api_key_env: str = HTTP_LLM_API_KEY_ENV
    system_prompt: str = SYSTEM_PROMPT


STATIC_CONFIG = InfraGapAnalysisStaticConfig()


def mcp_url_for_mode(runtime_mode: str) -> str:
    mode = (runtime_mode or "mock").strip().lower()
    if mode == "local":
        mode = "mock"
    if mode == "http":
        return STATIC_CONFIG.mcp_url_http
    return STATIC_CONFIG.mcp_url_mock
