"""Synchronous OpenShift/Kubernetes inventory collector (DynamicClient)."""

from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kubernetes import config as k8s_config
from kubernetes.client import ApiClient
from kubernetes.config import ConfigException
from openshift.dynamic import DynamicClient

from backend.app.config import K8sCollectorSettings, load_k8s_collector_settings
from backend.app.db.k8s_inventory import (
    K8sClusterSnapshot,
    K8sDeploymentRow,
    K8sNamespaceRow,
    K8sNodeRow,
    K8sPodOnNodeRow,
    K8sPodRow,
    K8sPvcRow,
)
from backend.app.services.agent_runtime_client import normalize_runtime_mode

logger = logging.getLogger(__name__)

# Deployed (http) environments mount kubeconfig here.
DEFAULT_K8S_KUBECONFIG_PATH = "/etc/k8s/kubeconfig"

# (connect timeout seconds, read timeout seconds) for kubernetes API calls
_K8S_REQUEST_TIMEOUT = (5, 60)
# kubelet stats/summary is per node (not per PVC); cap parallel proxy calls
_NODE_STATS_WORKERS = 6

_CPU_RE = re.compile(r"^(\d+(?:\.\d+)?)(m|)$")
_MEM_RE = re.compile(r"^(\d+(?:\.\d+)?)(Ei|Pi|Ti|Gi|Mi|Ki|E|P|T|G|M|K|)$", re.IGNORECASE)

_WORKLOAD_KIND_TO_TYPE = {
    "Deployment": "deployment",
    "StatefulSet": "statefulset",
    "DaemonSet": "daemonset",
    "DeploymentConfig": "deploymentconfig",
}

# System namespaces excluded from inventory scrape (k8s / kubevirt).
_EXCLUDED_NAMESPACE_EXACT = frozenset({"default"})


def is_excluded_system_namespace(namespace: str | None) -> bool:
    """True for openshift-*, kube-*, and default (PLAN system NS skip)."""
    name = (namespace or "").strip()
    if not name:
        return True
    if name in _EXCLUDED_NAMESPACE_EXACT:
        return True
    if name.startswith("openshift-") or name.startswith("kube-"):
        return True
    return False



class KubeconfigRequiredError(RuntimeError):
    """Raised when http mode requires a mounted kubeconfig that is missing."""


def parse_cpu_cores(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    match = _CPU_RE.match(text)
    if not match:
        return None
    value = float(match.group(1))
    if match.group(2) == "m":
        return value / 1000.0
    return value


def parse_mem_gi(raw: str | None) -> int | None:
    value = parse_mem_gi_float(raw)
    if value is None:
        return None
    return int(round(value))


def parse_mem_gi_float(raw: str | None) -> float | None:
    """Parse Kubernetes memory quantity to Gi as float (keeps Mi-level precision)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    match = _MEM_RE.match(text)
    if not match:
        try:
            return int(text) / (1024**3)
        except ValueError:
            return None
    value = float(match.group(1))
    unit = (match.group(2) or "B").lower()
    multipliers = {
        "": 1 / (1024**3),
        "ki": 1 / (1024**2),
        "mi": 1 / 1024,
        "gi": 1,
        "ti": 1024,
        "pi": 1024**2,
        "ei": 1024**3,
        "k": 1000 / (1024**3),
        "m": (1000**2) / (1024**3),
        "g": (1000**3) / (1024**3),
        "t": (1000**4) / (1024**3),
        "p": (1000**5) / (1024**3),
        "e": (1000**6) / (1024**3),
    }
    factor = multipliers.get(unit)
    if factor is None:
        return None
    return value * factor


def _attr(obj: Any, *path: str, default: Any = None) -> Any:
    current = obj
    for key in path:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            current = getattr(current, key, default)
    return current


def _bytes_to_gi(raw_bytes: Any) -> int | None:
    try:
        value = int(raw_bytes)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return int(round(value / (1024**3)))


def _as_nonneg_int(raw: Any) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value


def _dir_used_bytes(path: str) -> int | None:
    """Directory size in bytes. None if the path is not a local directory."""
    text = path.strip()
    if not text or not os.path.isabs(text) or not os.path.isdir(text):
        return None
    total = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(text, followlinks=False):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    if os.path.islink(filepath):
                        continue
                    total += os.path.getsize(filepath)
                except OSError:
                    continue
    except OSError:
        return None
    return total


def _sane_pvc_used_gi(
    used_bytes: int | None,
    *,
    pvc_capacity_gi: int | None,
    stats_capacity_bytes: int | None = None,
    allow_host_fs: bool = False,
) -> int | None:
    """Drop kubelet host-disk df stats that exceed the PVC claim size."""
    if used_bytes is None:
        return None
    pvc_cap_bytes = None if pvc_capacity_gi is None else pvc_capacity_gi * (1024**3)
    if (
        not allow_host_fs
        and pvc_cap_bytes is not None
        and stats_capacity_bytes is not None
        and stats_capacity_bytes > pvc_cap_bytes * 2
    ):
        return None
    if pvc_cap_bytes is not None and used_bytes > int(pvc_cap_bytes * 1.1):
        return None
    return _bytes_to_gi(used_bytes)


def _fetch_node_stats_summary(api_client: ApiClient, node_name: str) -> dict[str, Any] | None:
    """GET /api/v1/nodes/{node}/proxy/stats/summary (one call per node).

    Must go through ``call_api`` so kubeconfig BearerToken is attached.
    ``ApiClient.request`` skips ``update_params_for_auth`` and is sent as
    ``system:anonymous``. ``CoreV1Api.connect_get_node_proxy_with_path``
    authenticates but returns ``str(dict)`` (Python quotes).
    """
    host = (getattr(getattr(api_client, "configuration", None), "host", None) or "").rstrip("/")
    if not host:
        return None
    try:
        data = api_client.call_api(
            "/api/v1/nodes/{name}/proxy/{path}",
            "GET",
            path_params={"name": node_name, "path": "stats/summary"},
            header_params={"Accept": "application/json"},
            auth_settings=["BearerToken"],
            response_types_map={200: "object"},
            _return_http_data_only=True,
            _request_timeout=_K8S_REQUEST_TIMEOUT,
        )
    except Exception as exc:
        logger.warning("Skip kubelet stats/summary node=%s (%s)", node_name, exc)
        return None

    if isinstance(data, dict):
        return data
    if isinstance(data, (bytes, bytearray)):
        try:
            data = data.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(data, str):
        try:
            loaded = json.loads(data)
        except json.JSONDecodeError:
            return None
        return loaded if isinstance(loaded, dict) else None
    return None


def _pvc_used_from_stats(summary: dict[str, Any]) -> dict[tuple[str, str], tuple[int, int | None]]:
    """Map (namespace, pvc_name) -> (usedBytes, capacityBytes) from one node."""
    used_by_pvc: dict[tuple[str, str], tuple[int, int | None]] = {}
    pods = summary.get("pods") or []
    if not isinstance(pods, list):
        return used_by_pvc
    for pod_stats in pods:
        volumes = _attr(pod_stats, "volume", default=[]) or []
        if not isinstance(volumes, list):
            continue
        for volume in volumes:
            pvc_name = str(_attr(volume, "pvcRef", "name", default="") or "").strip()
            pvc_ns = str(_attr(volume, "pvcRef", "namespace", default="") or "").strip()
            if not pvc_name or not pvc_ns:
                continue
            used_bytes = _as_nonneg_int(_attr(volume, "usedBytes"))
            if used_bytes is None:
                continue
            stats_cap = _as_nonneg_int(_attr(volume, "capacityBytes"))
            key = (pvc_ns, pvc_name)
            previous = used_by_pvc.get(key)
            if previous is None or used_bytes > previous[0]:
                used_by_pvc[key] = (used_bytes, stats_cap)
    return used_by_pvc


def _collect_pvc_kubelet_stats(
    dyn: DynamicClient, node_names: set[str]
) -> dict[tuple[str, str], tuple[int, int | None]]:
    """Fill PVC fs stats via kubelet stats/summary — O(nodes), not O(PVCs)."""
    names = {name.strip() for name in node_names if name and str(name).strip()}
    if not names:
        return {}

    api_client = getattr(dyn, "client", None)
    if api_client is None:
        return {}

    used_by_pvc: dict[tuple[str, str], tuple[int, int | None]] = {}
    workers = min(_NODE_STATS_WORKERS, len(names))

    def _one(node_name: str) -> dict[tuple[str, str], tuple[int, int | None]]:
        summary = _fetch_node_stats_summary(api_client, node_name)
        if not summary:
            return {}
        return _pvc_used_from_stats(summary)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_one, node_name): node_name for node_name in sorted(names)}
        for future in as_completed(futures):
            node_name = futures[future]
            try:
                chunk = future.result()
            except Exception as exc:
                logger.warning("Skip kubelet stats/summary node=%s (%s)", node_name, exc)
                continue
            for key, (used_bytes, stats_cap) in chunk.items():
                previous = used_by_pvc.get(key)
                if previous is None or used_bytes > previous[0]:
                    used_by_pvc[key] = (used_bytes, stats_cap)
    return used_by_pvc


def _collect_pv_path_used_bytes(dyn: DynamicClient) -> dict[tuple[str, str], int]:
    """If a local/hostPath PV directory is readable on this host, use its size."""
    used: dict[tuple[str, str], int] = {}
    for item in _safe_list(dyn, "v1", "PersistentVolume"):
        claim_ns = str(_attr(item, "spec", "claimRef", "namespace", default="") or "").strip()
        claim_name = str(_attr(item, "spec", "claimRef", "name", default="") or "").strip()
        if not claim_ns or not claim_name or is_excluded_system_namespace(claim_ns):
            continue
        path = str(
            _attr(item, "spec", "local", "path") or _attr(item, "spec", "hostPath", "path") or ""
        ).strip()
        if not path:
            continue
        size = _dir_used_bytes(path)
        if size is None:
            continue
        used[(claim_ns, claim_name)] = size
    return used


def _safe_list(dyn: DynamicClient, api_version: str, kind: str) -> list[Any]:
    try:
        resource = dyn.resources.get(api_version=api_version, kind=kind)
        result = resource.get(_request_timeout=_K8S_REQUEST_TIMEOUT)
        items = _attr(result, "items", default=[]) or []
        return list(items)
    except Exception as exc:
        logger.info("Skip API %s kind=%s (%s)", api_version, kind, exc)
        return []


def resolve_kubeconfig_path(
    configured: str | None,
    *,
    runtime_mode: str,
) -> str | None:
    """Resolve kubeconfig path by runtime mode.

    - http: mounted kubeconfig is required
    - mock/local: missing mount falls back to local KUBECONFIG/~/.kube/config
    """
    mode = normalize_runtime_mode(runtime_mode)
    candidate = (configured or "").strip() or DEFAULT_K8S_KUBECONFIG_PATH
    path = Path(candidate)
    if path.is_file():
        return str(path)

    if mode == "http":
        raise KubeconfigRequiredError(
            f"http 모드에서는 kubeconfig가 필요합니다: {candidate}"
        )

    logger.info(
        "kubeconfig not found at %s; mock/local mode uses default "
        "(KUBECONFIG/~/.kube/config)",
        candidate,
    )
    return None


def build_dynamic_client(
    *,
    kubeconfig: str | None,
    context: str | None,
    fallback_to_current_context: bool,
    runtime_mode: str,
) -> tuple[DynamicClient, str | None]:
    """Load kubeconfig and return (client, resolved_context_name)."""
    from kubernetes.client import Configuration

    config_file = resolve_kubeconfig_path(kubeconfig, runtime_mode=runtime_mode)
    tried_context = context
    configuration = Configuration()

    def _load(selected_context: str | None) -> None:
        kwargs: dict[str, Any] = {"client_configuration": configuration}
        if config_file:
            kwargs["config_file"] = config_file
        if selected_context:
            kwargs["context"] = selected_context
        k8s_config.load_kube_config(**kwargs)

    try:
        _load(tried_context)
        return DynamicClient(ApiClient(configuration=configuration)), tried_context
    except ConfigException as exc:
        if not fallback_to_current_context or not tried_context:
            raise
        logger.warning(
            "kubeconfig context '%s' unavailable (%s); falling back to current-context",
            tried_context,
            exc,
        )
        _load(None)
        return DynamicClient(ApiClient(configuration=configuration)), None


def _sum_container_resources(containers: list[Any]) -> tuple[
    float | None,
    int | None,
    float | None,
    int | None,
    list[str],
    list[str],
]:
    cpu_req = 0.0
    mem_req = 0
    cpu_lim = 0.0
    mem_lim = 0
    has_cpu_req = False
    has_mem_req = False
    has_cpu_lim = False
    has_mem_lim = False
    names: list[str] = []
    images: list[str] = []

    for container in containers:
        name = str(_attr(container, "name", default="") or "")
        image = str(_attr(container, "image", default="") or "")
        if name:
            names.append(name)
        if image:
            images.append(image)
        resources = _attr(container, "resources", default={}) or {}
        requests = _attr(resources, "requests", default={}) or {}
        limits = _attr(resources, "limits", default={}) or {}
        cpu_r = parse_cpu_cores(_attr(requests, "cpu"))
        mem_r = parse_mem_gi(_attr(requests, "memory"))
        cpu_l = parse_cpu_cores(_attr(limits, "cpu"))
        mem_l = parse_mem_gi(_attr(limits, "memory"))
        if cpu_r is not None:
            cpu_req += cpu_r
            has_cpu_req = True
        if mem_r is not None:
            mem_req += mem_r
            has_mem_req = True
        if cpu_l is not None:
            cpu_lim += cpu_l
            has_cpu_lim = True
        if mem_l is not None:
            mem_lim += mem_l
            has_mem_lim = True

    return (
        cpu_req if has_cpu_req else None,
        mem_req if has_mem_req else None,
        cpu_lim if has_cpu_lim else None,
        mem_lim if has_mem_lim else None,
        names,
        images,
    )


def _node_role_from_labels(labels: Any) -> str | None:
    """Derive a short role string from kubernetes node labels.

    DynamicClient returns metadata.labels as ResourceField (not dict);
    normalize via _as_mapping before reading role keys.
    """
    mapped = _as_mapping(labels)
    if not mapped:
        return None
    roles: set[str] = set()
    for key, value in mapped.items():
        key_text = str(key or "")
        if key_text.startswith("node-role.kubernetes.io/"):
            role = key_text.split("/", 1)[-1].strip()
            if role:
                roles.add(role)
        elif key_text in {"kubernetes.io/role", "node.kubernetes.io/role"}:
            role = str(value or "").strip()
            if role:
                roles.add(role)
    if not roles:
        return None
    return ",".join(sorted(roles))[:30]


def _collect_nodes(dyn: DynamicClient) -> list[K8sNodeRow]:
    rows: list[K8sNodeRow] = []
    for item in _safe_list(dyn, "v1", "Node"):
        name = str(_attr(item, "metadata", "name", default="") or "")
        if not name:
            continue
        capacity = _attr(item, "status", "capacity", default={}) or {}
        node_info = _attr(item, "status", "nodeInfo", default={}) or {}
        labels = _attr(item, "metadata", "labels", default=None)
        cpu = parse_cpu_cores(_attr(capacity, "cpu"))
        rows.append(
            K8sNodeRow(
                node_name=name,
                node_cpu=int(round(cpu)) if cpu is not None else None,
                node_mem=parse_mem_gi(_attr(capacity, "memory")),
                node_os=str(
                    _attr(node_info, "osImage")
                    or _attr(node_info, "operatingSystem")
                    or ""
                )
                or None,
                node_k8s_ver=str(_attr(node_info, "kubeletVersion") or "") or None,
                node_role=_node_role_from_labels(labels),
            )
        )
    return rows


def _collect_quotas_by_namespace(dyn: DynamicClient) -> dict[str, dict[str, float | int]]:
    quotas: dict[str, dict[str, float | int]] = {}
    for item in _safe_list(dyn, "v1", "ResourceQuota"):
        namespace = str(_attr(item, "metadata", "namespace", default="") or "")
        if not namespace:
            continue
        hard = _attr(item, "status", "hard", default=None) or _attr(
            item, "spec", "hard", default={}
        ) or {}
        bucket = quotas.setdefault(namespace, {})
        cpu = parse_cpu_cores(_attr(hard, "limits.cpu") or _attr(hard, "cpu"))
        mem = parse_mem_gi(_attr(hard, "limits.memory") or _attr(hard, "memory"))
        pods_raw = _attr(hard, "pods")
        if cpu is not None:
            bucket["cpu"] = float(bucket.get("cpu", 0.0)) + cpu
        if mem is not None:
            bucket["mem"] = int(bucket.get("mem", 0)) + mem
        if pods_raw is not None:
            try:
                bucket["pods"] = int(bucket.get("pods", 0)) + int(pods_raw)
            except (TypeError, ValueError):
                pass
    return quotas


def _merge_unique_ips(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for ip in group:
            text = str(ip).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged


_EGRESS_IP_SELECTOR_KEY = "egressIPSelector"


@dataclass
class NamespaceEgressInfo:
    ips: list[str] = field(default_factory=list)
    using_egressip: str | None = None
    egressip_assigned_node: str | None = None


def _as_mapping(value: Any) -> dict[str, Any]:
    """Normalize DynamicClient ResourceField / dict-like objects to a plain dict."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)

    items_fn = getattr(value, "items", None)
    if callable(items_fn):
        try:
            return {str(key): item for key, item in items_fn()}
        except Exception:
            pass

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            converted = to_dict()
            if isinstance(converted, dict):
                return dict(converted)
        except Exception:
            pass

    keys_fn = getattr(value, "keys", None)
    if callable(keys_fn):
        try:
            return {str(key): getattr(value, str(key), None) for key in keys_fn()}
        except Exception:
            pass

    try:
        return {str(key): item for key, item in dict(value).items()}
    except Exception:
        pass
    return {}


def _spec_egress_ips(item: Any) -> list[str]:
    """Return .spec.egressIPs as-is (1 or 2 entries used downstream)."""
    return [
        str(ip).strip()
        for ip in (_attr(item, "spec", "egressIPs", default=[]) or [])
        if ip is not None and str(ip).strip()
    ]


def _egress_ip_selector_value(item: Any) -> str | None:
    """Read EgressIP.spec.namespaceSelector.matchLabels.egressIPSelector."""
    selector = _attr(item, "spec", "namespaceSelector", default=None)
    if selector is None:
        return None
    match_labels_raw = _attr(selector, "matchLabels", default=None)
    if match_labels_raw is None and isinstance(selector, dict):
        match_labels_raw = selector.get("matchLabels")
    match_labels = _as_mapping(match_labels_raw)
    if not match_labels:
        return None
    raw = match_labels.get(_EGRESS_IP_SELECTOR_KEY)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _status_egress_assignment(item: Any) -> tuple[str | None, str | None]:
    """Return (using_egressip, egressip_assigned_node) from status.items[0]."""
    status_items = _attr(item, "status", "items", default=[]) or []
    if not status_items:
        return None, None
    status_item = status_items[0]
    ip = _attr(status_item, "egressIP")
    node = _attr(status_item, "node")
    ip_text = str(ip).strip() if ip is not None else ""
    node_text = str(node).strip() if node is not None else ""
    return (
        ip_text[:20] if ip_text else None,
        node_text[:50] if node_text else None,
    )


def _merge_egress_info(
    current: NamespaceEgressInfo | None,
    *,
    ips: list[str],
    using_egressip: str | None = None,
    egressip_assigned_node: str | None = None,
) -> NamespaceEgressInfo:
    base = current or NamespaceEgressInfo()
    merged_ips = _merge_unique_ips(base.ips, ips)
    return NamespaceEgressInfo(
        ips=merged_ips,
        using_egressip=using_egressip or base.using_egressip,
        egressip_assigned_node=egressip_assigned_node or base.egressip_assigned_node,
    )


def _collect_egress_ips(
    dyn: DynamicClient,
    namespace_labels: dict[str, dict[str, str]],
) -> dict[str, NamespaceEgressInfo]:
    """Best-effort OKD/OCP egress IP lookup; empty on plain Kubernetes.

    Dual path:
    - Legacy OpenShift SDN: NetNamespace.egressIPs keyed by namespace name
    - OVN-Kubernetes: match
        EgressIP.spec.namespaceSelector.matchLabels.egressIPSelector
        == Namespace.metadata.labels.egressIPSelector
      IPs come from EgressIP.spec.egressIPs (1 or 2 values).
      using_egressip = status.items[0].egressIP
      egressip_assigned_node = status.items[0].node
    """
    by_namespace: dict[str, NamespaceEgressInfo] = {}

    ns_with_selector = {
        name: str(labels.get(_EGRESS_IP_SELECTOR_KEY) or "").strip()
        for name, labels in namespace_labels.items()
        if str(labels.get(_EGRESS_IP_SELECTOR_KEY) or "").strip()
    }

    for item in _safe_list(dyn, "network.openshift.io/v1", "NetNamespace"):
        name = str(_attr(item, "netName") or _attr(item, "metadata", "name") or "")
        if not name:
            continue
        egress = _attr(item, "egressIPs", default=[]) or []
        ips = [str(ip).strip() for ip in egress if ip is not None and str(ip).strip()]
        if ips:
            by_namespace[name] = _merge_egress_info(by_namespace.get(name), ips=ips)

    for item in _safe_list(dyn, "k8s.ovn.org/v1", "EgressIP"):
        selector_value = _egress_ip_selector_value(item)
        if not selector_value:
            continue
        ips = _spec_egress_ips(item)
        if not ips:
            continue
        # Inventory columns hold at most two IPs.
        ips = ips[:2]
        using_ip, assigned_node = _status_egress_assignment(item)
        for ns_name, ns_selector in ns_with_selector.items():
            if ns_selector != selector_value:
                continue
            by_namespace[ns_name] = _merge_egress_info(
                by_namespace.get(ns_name),
                ips=ips,
                using_egressip=using_ip,
                egressip_assigned_node=assigned_node,
            )

    return by_namespace


def _collect_namespaces(dyn: DynamicClient) -> list[K8sNamespaceRow]:
    quotas = _collect_quotas_by_namespace(dyn)
    namespace_items = _safe_list(dyn, "v1", "Namespace")
    namespace_labels: dict[str, dict[str, str]] = {}
    for item in namespace_items:
        name = str(_attr(item, "metadata", "name", default="") or "")
        if not name or is_excluded_system_namespace(name):
            continue
        raw_labels = _attr(item, "metadata", "labels", default={}) or {}
        mapped = _as_mapping(raw_labels)
        namespace_labels[name] = {
            str(key): str(value) for key, value in mapped.items()
        }

    egress_map = _collect_egress_ips(dyn, namespace_labels)
    rows: list[K8sNamespaceRow] = []
    for item in namespace_items:
        name = str(_attr(item, "metadata", "name", default="") or "")
        if not name or is_excluded_system_namespace(name):
            continue
        annotations = _attr(item, "metadata", "annotations", default={}) or {}
        if not isinstance(annotations, dict):
            annotations = _as_mapping(annotations)
        display = (
            annotations.get("openshift.io/display-name")
            or annotations.get("openshift.io/description")
            or None
        )
        quota = quotas.get(name, {})
        egress = egress_map.get(name) or NamespaceEgressInfo()
        rows.append(
            K8sNamespaceRow(
                namespace=name,
                okd_display_name=str(display)[:100] if display else None,
                resource_quota_cpu_limit=float(quota["cpu"]) if "cpu" in quota else None,
                resource_quota_mem_limit=int(quota["mem"]) if "mem" in quota else None,
                resource_quota_pod_limit=int(quota["pods"]) if "pods" in quota else None,
                okd_egressip1=egress.ips[0][:20] if len(egress.ips) >= 1 else None,
                okd_egressip2=egress.ips[1][:20] if len(egress.ips) >= 2 else None,
                using_egressip=egress.using_egressip,
                egressip_assigned_node=egress.egressip_assigned_node,
            )
        )
    return rows


def _parse_int(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _status_ready_replicas(item: Any, kind: str) -> int | None:
    if kind == "DaemonSet":
        return _parse_int(_attr(item, "status", "numberReady"))
    return _parse_int(_attr(item, "status", "readyReplicas"))


def _workload_rows(
    dyn: DynamicClient, api_version: str, kind: str, type_name: str
) -> list[K8sDeploymentRow]:
    rows: list[K8sDeploymentRow] = []
    for item in _safe_list(dyn, api_version, kind):
        namespace = str(_attr(item, "metadata", "namespace", default="") or "")
        name = str(_attr(item, "metadata", "name", default="") or "")
        if not namespace or not name or is_excluded_system_namespace(namespace):
            continue
        if kind == "DaemonSet":
            replicas_int = _parse_int(_attr(item, "status", "desiredNumberScheduled"))
        else:
            replicas_int = _parse_int(_attr(item, "spec", "replicas"))
        readyreplicas_int = _status_ready_replicas(item, kind)
        containers = (
            _attr(item, "spec", "template", "spec", "containers", default=[]) or []
        )
        cpu_req, mem_req, cpu_lim, mem_lim, names, images = _sum_container_resources(
            list(containers)
        )
        rows.append(
            K8sDeploymentRow(
                namespace=namespace,
                name=name,
                type=type_name,
                replicas=replicas_int,
                readyreplicas=readyreplicas_int,
                resource_cpu_request=cpu_req,
                resource_mem_request=mem_req,
                resource_cpu_limit=cpu_lim,
                resource_mem_limit=mem_lim,
                containers_cnt=len(names),
                containers_name=names,
                containers_image=images,
            )
        )
    return rows


def _collect_deployments(dyn: DynamicClient) -> list[K8sDeploymentRow]:
    rows: list[K8sDeploymentRow] = []
    rows.extend(_workload_rows(dyn, "apps/v1", "Deployment", "deployment"))
    rows.extend(_workload_rows(dyn, "apps/v1", "StatefulSet", "statefulset"))
    rows.extend(_workload_rows(dyn, "apps/v1", "DaemonSet", "daemonset"))
    rows.extend(
        _workload_rows(dyn, "apps.openshift.io/v1", "DeploymentConfig", "deploymentconfig")
    )
    return rows


def _index_replicaset_owners(dyn: DynamicClient) -> dict[tuple[str, str], tuple[str, str]]:
    """Map (namespace, replicaset_name) -> (deployment_name, type)."""
    mapping: dict[tuple[str, str], tuple[str, str]] = {}
    for item in _safe_list(dyn, "apps/v1", "ReplicaSet"):
        namespace = str(_attr(item, "metadata", "namespace", default="") or "")
        rs_name = str(_attr(item, "metadata", "name", default="") or "")
        if not namespace or not rs_name or is_excluded_system_namespace(namespace):
            continue
        owners = _attr(item, "metadata", "ownerReferences", default=[]) or []
        for owner in owners:
            if str(_attr(owner, "kind", default="")) == "Deployment":
                dep_name = str(_attr(owner, "name", default="") or "")
                if namespace and rs_name and dep_name:
                    mapping[(namespace, rs_name)] = (dep_name, "deployment")
                break
    return mapping


def _owner_workload(
    owners: list[Any],
    namespace: str,
    rs_map: dict[tuple[str, str], tuple[str, str]],
) -> tuple[str | None, str | None]:
    for owner in owners:
        kind = str(_attr(owner, "kind", default="") or "")
        name = str(_attr(owner, "name", default="") or "")
        if not kind or not name:
            continue
        if kind == "ReplicaSet":
            return rs_map.get((namespace, name), (None, None))
        type_name = _WORKLOAD_KIND_TO_TYPE.get(kind)
        if type_name:
            return name, type_name
    return None, None


def _format_pod_age(creation_timestamp: Any) -> str | None:
    """Format creationTimestamp as a short kubectl-like age string."""
    if creation_timestamp is None:
        return None
    text = str(creation_timestamp).strip()
    if not text:
        return None
    try:
        from datetime import datetime, timezone

        normalized = text.replace("Z", "+00:00")
        created = datetime.fromisoformat(normalized)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        seconds = max(0, int((now - created).total_seconds()))
    except Exception:
        return text[:20]

    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    if days < 365:
        return f"{days}d"
    years = days // 365
    return f"{years}y"


def _sum_pod_container_resources(
    containers: list[Any],
) -> tuple[float | None, float | None, float | None, float | None]:
    cpu_req = 0.0
    mem_req = 0.0
    cpu_lim = 0.0
    mem_lim = 0.0
    has_cpu_req = False
    has_mem_req = False
    has_cpu_lim = False
    has_mem_lim = False

    for container in containers:
        resources = _attr(container, "resources", default={}) or {}
        requests = _attr(resources, "requests", default={}) or {}
        limits = _attr(resources, "limits", default={}) or {}
        cpu_r = parse_cpu_cores(_attr(requests, "cpu"))
        mem_r = parse_mem_gi_float(_attr(requests, "memory"))
        cpu_l = parse_cpu_cores(_attr(limits, "cpu"))
        mem_l = parse_mem_gi_float(_attr(limits, "memory"))
        if cpu_r is not None:
            cpu_req += cpu_r
            has_cpu_req = True
        if mem_r is not None:
            mem_req += mem_r
            has_mem_req = True
        if cpu_l is not None:
            cpu_lim += cpu_l
            has_cpu_lim = True
        if mem_l is not None:
            mem_lim += mem_l
            has_mem_lim = True

    return (
        cpu_req if has_cpu_req else None,
        cpu_lim if has_cpu_lim else None,
        mem_req if has_mem_req else None,
        mem_lim if has_mem_lim else None,
    )


def _collect_pods_on_nodes(dyn: DynamicClient) -> list[K8sPodOnNodeRow]:
    """Collect non-terminated pods per node (excludes system namespaces)."""
    rows: list[K8sPodOnNodeRow] = []
    for item in _safe_list(dyn, "v1", "Pod"):
        namespace = str(_attr(item, "metadata", "namespace", default="") or "")
        name = str(_attr(item, "metadata", "name", default="") or "")
        node_name = str(_attr(item, "spec", "nodeName", default="") or "")
        if (
            not namespace
            or not name
            or not node_name
            or is_excluded_system_namespace(namespace)
        ):
            continue
        phase = str(_attr(item, "status", "phase", default="") or "").strip()
        if phase in {"Succeeded", "Failed"}:
            continue
        containers = (
            _attr(item, "spec", "containers", default=[]) or []
        )
        cpu_req, cpu_lim, mem_req, mem_lim = _sum_pod_container_resources(
            list(containers)
        )
        age = _format_pod_age(_attr(item, "metadata", "creationTimestamp"))
        rows.append(
            K8sPodOnNodeRow(
                node_name=node_name,
                namespace=namespace,
                pod_name=name,
                cpu_request=cpu_req,
                cpu_limit=cpu_lim,
                mem_request=mem_req,
                mem_limit=mem_lim,
                age=age,
            )
        )
    return rows


def _collect_pods(
    dyn: DynamicClient,
    rs_map: dict[tuple[str, str], tuple[str, str]],
) -> list[K8sPodRow]:
    rows: list[K8sPodRow] = []
    for item in _safe_list(dyn, "v1", "Pod"):
        namespace = str(_attr(item, "metadata", "namespace", default="") or "")
        name = str(_attr(item, "metadata", "name", default="") or "")
        if not namespace or not name or is_excluded_system_namespace(namespace):
            continue
        owners = _attr(item, "metadata", "ownerReferences", default=[]) or []
        dep_name, dep_type = _owner_workload(list(owners), namespace, rs_map)
        node_name = str(_attr(item, "spec", "nodeName", default="") or "") or None
        rows.append(
            K8sPodRow(
                namespace=namespace,
                name=name,
                deployment_name=dep_name,
                deployment_type=dep_type,
                scheduled_node_name=node_name,
            )
        )
    return rows


def _pvc_to_workload(
    pods: list[K8sPodRow],
    dyn: DynamicClient,
) -> tuple[dict[tuple[str, str], tuple[str, str]], set[str]]:
    """Map (namespace, pvc_name) -> (deployment_name, type) via pod volume mounts.

    Also returns node names that mount at least one PVC (for stats/summary).
    """
    mapping: dict[tuple[str, str], tuple[str, str]] = {}
    nodes: set[str] = set()
    for item in _safe_list(dyn, "v1", "Pod"):
        namespace = str(_attr(item, "metadata", "namespace", default="") or "")
        pod_name = str(_attr(item, "metadata", "name", default="") or "")
        if (
            not namespace
            or not pod_name
            or is_excluded_system_namespace(namespace)
        ):
            continue
        node_name = str(_attr(item, "spec", "nodeName", default="") or "").strip()
        owners = next(
            (
                (pod.deployment_name, pod.deployment_type)
                for pod in pods
                if pod.namespace == namespace and pod.name == pod_name
            ),
            (None, None),
        )
        volumes = _attr(item, "spec", "volumes", default=[]) or []
        for volume in volumes:
            claim = _attr(volume, "persistentVolumeClaim", "claimName")
            if not claim:
                continue
            if node_name:
                nodes.add(node_name)
            if owners[0] and owners[1]:
                mapping[(namespace, str(claim))] = (owners[0], owners[1])
    return mapping, nodes


def _collect_pvcs(
    dyn: DynamicClient,
    pods: list[K8sPodRow],
) -> list[K8sPvcRow]:
    pvc_owners, pvc_nodes = _pvc_to_workload(pods, dyn)
    kubelet_stats = _collect_pvc_kubelet_stats(dyn, pvc_nodes)
    path_used = _collect_pv_path_used_bytes(dyn)
    rows: list[K8sPvcRow] = []
    for item in _safe_list(dyn, "v1", "PersistentVolumeClaim"):
        namespace = str(_attr(item, "metadata", "namespace", default="") or "")
        name = str(_attr(item, "metadata", "name", default="") or "")
        if not namespace or not name or is_excluded_system_namespace(namespace):
            continue
        storage_class = _attr(item, "spec", "storageClassName")
        requests = _attr(item, "spec", "resources", "requests", default={}) or {}
        capacity_status = _attr(item, "status", "capacity", default={}) or {}
        access_modes = _attr(item, "spec", "accessModes", default=[]) or []
        dep = pvc_owners.get((namespace, name))
        capacity = parse_mem_gi(
            _attr(capacity_status, "storage") or _attr(requests, "storage")
        )
        key = (namespace, name)
        path_bytes = path_used.get(key)
        used = None
        if path_bytes is not None:
            used = _sane_pvc_used_gi(path_bytes, pvc_capacity_gi=capacity, allow_host_fs=True)
        else:
            stats = kubelet_stats.get(key)
            if stats is not None:
                used = _sane_pvc_used_gi(
                    stats[0],
                    pvc_capacity_gi=capacity,
                    stats_capacity_bytes=stats[1],
                )
        rows.append(
            K8sPvcRow(
                namespace=namespace,
                name=name,
                deployment_name=dep[0] if dep else None,
                deployment_type=dep[1] if dep else None,
                storage_class=str(storage_class) if storage_class else None,
                capacity=capacity,
                used=used,
                access_mode=str(access_modes[0]) if access_modes else None,
            )
        )
    return rows


def collect_cluster_snapshot(
    cluster_name: str,
    settings: K8sCollectorSettings | None = None,
    *,
    runtime_mode: str | None = None,
) -> K8sClusterSnapshot:
    collector = settings or load_k8s_collector_settings()
    mode = runtime_mode or collector.runtime_mode
    context_name = collector.contexts.get(cluster_name, cluster_name)
    resolved_kubeconfig = resolve_kubeconfig_path(
        collector.kubeconfig or None,
        runtime_mode=mode,
    )
    dyn, resolved = build_dynamic_client(
        kubeconfig=collector.kubeconfig or None,
        context=context_name,
        fallback_to_current_context=collector.fallback_to_current_context,
        runtime_mode=mode,
    )
    logger.info(
        "Collecting k8s inventory cluster=%s context=%s resolved=%s kubeconfig=%s mode=%s",
        cluster_name,
        context_name,
        resolved or "current-context",
        resolved_kubeconfig or f"(local default; missing {DEFAULT_K8S_KUBECONFIG_PATH})",
        normalize_runtime_mode(mode),
    )

    nodes = _collect_nodes(dyn)
    namespaces = _collect_namespaces(dyn)
    deployments = _collect_deployments(dyn)
    rs_map = _index_replicaset_owners(dyn)
    pods = _collect_pods(dyn, rs_map)
    pvcs = _collect_pvcs(dyn, pods)
    pods_on_nodes = _collect_pods_on_nodes(dyn)

    return K8sClusterSnapshot(
        cluster_name=cluster_name,
        nodes=nodes,
        namespaces=namespaces,
        deployments=deployments,
        pvcs=pvcs,
        pods=pods,
        pods_on_nodes=pods_on_nodes,
    )


def collect_and_persist_cluster(
    database_path: Path | str,
    *,
    cluster_idx: int,
    cluster_name: str,
    settings: K8sCollectorSettings | None = None,
    runtime_mode: str | None = None,
) -> dict[str, Any]:
    from backend.app.db.k8s_inventory import replace_cluster_snapshot

    collector = settings or load_k8s_collector_settings()
    snapshot = collect_cluster_snapshot(
        cluster_name,
        collector,
        runtime_mode=runtime_mode,
    )
    return replace_cluster_snapshot(
        database_path,
        snapshot,
        cluster_idx=cluster_idx,
    )
