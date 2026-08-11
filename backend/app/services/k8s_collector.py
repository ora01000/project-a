"""Synchronous OpenShift/Kubernetes inventory collector (DynamicClient)."""

from __future__ import annotations

import logging
import re
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


def _as_mapping(value: Any) -> dict[str, Any]:
    """Normalize DynamicClient ResourceField / dict-like objects to a plain dict."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)

    items_method = getattr(value, "items", None)
    if callable(items_method):
        try:
            return {str(key): item for key, item in items_method()}
        except Exception:
            pass

    keys_method = getattr(value, "keys", None)
    if callable(keys_method):
        try:
            return {
                str(key): getattr(value, str(key), None)
                for key in keys_method()
            }
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
    try:
        return {str(key): item for key, item in dict(value).items()}
    except Exception:
        pass
    return {}


def _node_label_candidates(item: Any) -> list[tuple[str, Any]]:
    """Collect node label payloads from common DynamicClient / dict shapes."""
    candidates: list[tuple[str, Any]] = [
        ("metadata.labels", _attr(item, "metadata", "labels")),
        ("metadata.labels.dot", _attr(item, "metadata.labels")),
    ]
    if isinstance(item, dict):
        metadata = item.get("metadata") or {}
        if isinstance(metadata, dict):
            candidates.append(("dict.metadata.labels", metadata.get("labels")))

    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        try:
            converted = to_dict()
            if isinstance(converted, dict):
                metadata = converted.get("metadata") or {}
                if isinstance(metadata, dict):
                    candidates.append(("item.to_dict.metadata.labels", metadata.get("labels")))
        except Exception as exc:
            candidates.append(("item.to_dict", f"<error: {exc}>"))

    return candidates


def _role_related_label_keys(labels: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in labels.items()
        if str(key).startswith("node-role.kubernetes.io/")
        or str(key) in {"kubernetes.io/role", "node.kubernetes.io/role"}
    }


def _node_role_from_labels(labels: Any, *, node_name: str | None = None) -> str | None:
    """Derive a short role string from kubernetes node labels.

    DynamicClient returns metadata.labels as ResourceField (not dict);
    normalize via _as_mapping before reading role keys.
    """
    mapped = _as_mapping(labels)
    if not mapped:
        if node_name:
            logger.warning(
                "k8s node role labels empty after normalize: node=%s labels_type=%s labels_repr=%r",
                node_name,
                type(labels).__name__,
                labels,
            )
        return None

    roles: set[str] = set()
    matched_keys: list[str] = []
    for key, value in mapped.items():
        key_text = str(key or "")
        if key_text.startswith("node-role.kubernetes.io/"):
            role = key_text.split("/", 1)[-1].strip()
            if role:
                roles.add(role)
                matched_keys.append(key_text)
        elif key_text in {"kubernetes.io/role", "node.kubernetes.io/role"}:
            role = str(value or "").strip()
            if role:
                roles.add(role)
                matched_keys.append(key_text)

    if not roles:
        if node_name:
            logger.warning(
                "k8s node role not derived: node=%s label_count=%d role_related_labels=%s all_label_keys=%s",
                node_name,
                len(mapped),
                _role_related_label_keys(mapped),
                sorted(str(key) for key in mapped.keys()),
            )
        return None

    node_role = ",".join(sorted(roles))[:30]
    logger.info(
        "k8s node role derived: node=%s role=%s matched_keys=%s",
        node_name or "-",
        node_role,
        matched_keys,
    )
    return node_role


def _resolve_node_labels(item: Any, *, node_name: str) -> dict[str, Any]:
    """Resolve node labels with fallbacks and detailed logging for http-mode diagnostics."""
    attempts: list[tuple[str, Any, dict[str, Any]]] = []
    for source, raw_labels in _node_label_candidates(item):
        mapped = _as_mapping(raw_labels)
        attempts.append((source, raw_labels, mapped))
        if mapped:
            if len(attempts) > 1 or source != "metadata.labels":
                logger.info(
                    "k8s node labels resolved: node=%s source=%s label_count=%d",
                    node_name,
                    source,
                    len(mapped),
                )
            return mapped

    logger.warning(
        "k8s node labels unresolved: node=%s attempts=%s",
        node_name,
        [
            {
                "source": source,
                "raw_type": type(raw_labels).__name__,
                "raw_repr": repr(raw_labels)[:500],
                "mapped_keys": sorted(mapped.keys()),
            }
            for source, raw_labels, mapped in attempts
        ],
    )
    return {}


def _collect_nodes(dyn: DynamicClient) -> list[K8sNodeRow]:
    rows: list[K8sNodeRow] = []
    for item in _safe_list(dyn, "v1", "Node"):
        name = str(_attr(item, "metadata", "name", default="") or "")
        if not name:
            continue
        capacity = _attr(item, "status", "capacity", default={}) or {}
        node_info = _attr(item, "status", "nodeInfo", default={}) or {}
        labels = _resolve_node_labels(item, node_name=name)
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
                node_role=_node_role_from_labels(labels, node_name=name),
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


def _extract_node_labels(item: Any, *, node_name: str) -> dict[str, str]:
    """Read node metadata.labels with fallbacks for http DynamicClient payloads."""
    sources: list[tuple[str, Any]] = [
        ("metadata.labels", _attr(item, "metadata", "labels")),
        ("metadata.labels.dot", _attr(item, "metadata.labels")),
    ]
    item_to_dict = getattr(item, "to_dict", None)
    if callable(item_to_dict):
        try:
            payload = item_to_dict()
            if isinstance(payload, dict):
                meta = payload.get("metadata")
                if isinstance(meta, dict):
                    sources.append(("item.to_dict.metadata.labels", meta.get("labels")))
        except Exception as exc:
            logger.info(
                "K8s node %s: item.to_dict() failed while reading labels (%s)",
                node_name,
                exc,
            )

    for source, raw in sources:
        mapped = _as_mapping(raw)
        if mapped:
            if source != "metadata.labels":
                logger.info(
                    "K8s node %s: labels resolved via fallback source=%s key_count=%d",
                    node_name,
                    source,
                    len(mapped),
                )
            return {str(key): "" if val is None else str(val) for key, val in mapped.items()}

        if raw is not None:
            logger.info(
                "K8s node %s: labels source=%s did not normalize type=%s repr=%s",
                node_name,
                source,
                type(raw).__name__,
                repr(raw)[:500],
            )

    logger.warning(
        "K8s node %s: could not extract metadata.labels from any source; node_role will be empty",
        node_name,
    )
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
) -> dict[tuple[str, str], tuple[str, str]]:
    """Map (namespace, pvc_name) -> (deployment_name, type) via pod volume mounts."""
    mapping: dict[tuple[str, str], tuple[str, str]] = {}
    for item in _safe_list(dyn, "v1", "Pod"):
        namespace = str(_attr(item, "metadata", "namespace", default="") or "")
        pod_name = str(_attr(item, "metadata", "name", default="") or "")
        if (
            not namespace
            or not pod_name
            or is_excluded_system_namespace(namespace)
        ):
            continue
        owners = next(
            (
                (pod.deployment_name, pod.deployment_type)
                for pod in pods
                if pod.namespace == namespace and pod.name == pod_name
            ),
            (None, None),
        )
        if not owners[0] or not owners[1]:
            continue
        volumes = _attr(item, "spec", "volumes", default=[]) or []
        for volume in volumes:
            claim = _attr(volume, "persistentVolumeClaim", "claimName")
            if claim:
                mapping[(namespace, str(claim))] = (owners[0], owners[1])
    return mapping


def _collect_pvcs(
    dyn: DynamicClient,
    pods: list[K8sPodRow],
) -> list[K8sPvcRow]:
    pvc_owners = _pvc_to_workload(pods, dyn)
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
        rows.append(
            K8sPvcRow(
                namespace=namespace,
                name=name,
                deployment_name=dep[0] if dep else None,
                deployment_type=dep[1] if dep else None,
                storage_class=str(storage_class) if storage_class else None,
                capacity=parse_mem_gi(
                    _attr(capacity_status, "storage") or _attr(requests, "storage")
                ),
                used=None,
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
