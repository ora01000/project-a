"""Synchronous OpenShift/Kubernetes inventory collector (DynamicClient)."""

from __future__ import annotations

import logging
import re
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
    K8sPodRow,
    K8sPvcRow,
)

logger = logging.getLogger(__name__)

# Deployed environments mount kubeconfig here; local test usually has no such file.
DEFAULT_K8S_KUBECONFIG_PATH = "/etc/k8s-kubeconfig/k8s-kubeconfig"

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
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    match = _MEM_RE.match(text)
    if not match:
        try:
            return int(round(int(text) / (1024**3)))
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
    return int(round(value * factor))


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


def resolve_kubeconfig_path(configured: str | None) -> str | None:
    """Prefer the configured/default mounted kubeconfig; else local kubernetes access.

    When ``/etc/k8s-kubeconfig/k8s-kubeconfig`` (or an override path) is missing,
    return None so client-python uses the local default (KUBECONFIG/~/.kube/config).
    """
    candidate = (configured or "").strip() or DEFAULT_K8S_KUBECONFIG_PATH
    path = Path(candidate)
    if path.is_file():
        return str(path)
    logger.info(
        "kubeconfig not found at %s; treating as local kubernetes access "
        "(default KUBECONFIG/~/.kube/config)",
        candidate,
    )
    return None


def build_dynamic_client(
    *,
    kubeconfig: str | None,
    context: str | None,
    fallback_to_current_context: bool,
) -> tuple[DynamicClient, str | None]:
    """Load kubeconfig and return (client, resolved_context_name)."""
    from kubernetes.client import Configuration

    config_file = resolve_kubeconfig_path(kubeconfig)
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


def _collect_nodes(dyn: DynamicClient) -> list[K8sNodeRow]:
    rows: list[K8sNodeRow] = []
    for item in _safe_list(dyn, "v1", "Node"):
        name = str(_attr(item, "metadata", "name", default="") or "")
        if not name:
            continue
        capacity = _attr(item, "status", "capacity", default={}) or {}
        node_info = _attr(item, "status", "nodeInfo", default={}) or {}
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


def _collect_egress_ips(dyn: DynamicClient) -> dict[str, list[str]]:
    """Best-effort OKD/OCP egress IP lookup; empty on plain Kubernetes."""
    by_namespace: dict[str, list[str]] = {}

    for item in _safe_list(dyn, "network.openshift.io/v1", "NetNamespace"):
        name = str(_attr(item, "netName") or _attr(item, "metadata", "name") or "")
        if not name:
            continue
        egress = _attr(item, "egressIPs", default=[]) or []
        ips = [str(ip) for ip in egress if str(ip).strip()]
        if ips:
            by_namespace[name] = ips

    for item in _safe_list(dyn, "k8s.ovn.org/v1", "EgressIP"):
        # OVN-Kubernetes style: assign to namespaces via spec.namespaceSelector — skip complex match;
        # also check status.items assigned.
        pass

    return by_namespace


def _collect_namespaces(dyn: DynamicClient) -> list[K8sNamespaceRow]:
    quotas = _collect_quotas_by_namespace(dyn)
    egress_map = _collect_egress_ips(dyn)
    rows: list[K8sNamespaceRow] = []
    for item in _safe_list(dyn, "v1", "Namespace"):
        name = str(_attr(item, "metadata", "name", default="") or "")
        if not name:
            continue
        annotations = _attr(item, "metadata", "annotations", default={}) or {}
        display = (
            annotations.get("openshift.io/display-name")
            or annotations.get("openshift.io/description")
            or None
        )
        quota = quotas.get(name, {})
        egress = egress_map.get(name, [])
        rows.append(
            K8sNamespaceRow(
                namespace=name,
                okd_display_name=str(display)[:100] if display else None,
                resource_quota_cpu_limit=float(quota["cpu"]) if "cpu" in quota else None,
                resource_quota_mem_limit=int(quota["mem"]) if "mem" in quota else None,
                resource_quota_pod_limit=int(quota["pods"]) if "pods" in quota else None,
                okd_egressip1=egress[0][:20] if len(egress) >= 1 else None,
                okd_egressip2=egress[1][:20] if len(egress) >= 2 else None,
            )
        )
    return rows


def _workload_rows(dyn: DynamicClient, api_version: str, kind: str, type_name: str) -> list[K8sDeploymentRow]:
    rows: list[K8sDeploymentRow] = []
    for item in _safe_list(dyn, api_version, kind):
        namespace = str(_attr(item, "metadata", "namespace", default="") or "")
        name = str(_attr(item, "metadata", "name", default="") or "")
        if not namespace or not name:
            continue
        if kind == "DaemonSet":
            replicas = _attr(item, "status", "desiredNumberScheduled")
            try:
                replicas_int = int(replicas) if replicas is not None else None
            except (TypeError, ValueError):
                replicas_int = None
        else:
            replicas = _attr(item, "spec", "replicas")
            try:
                replicas_int = int(replicas) if replicas is not None else None
            except (TypeError, ValueError):
                replicas_int = None
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


def _collect_pods(
    dyn: DynamicClient,
    rs_map: dict[tuple[str, str], tuple[str, str]],
) -> list[K8sPodRow]:
    rows: list[K8sPodRow] = []
    for item in _safe_list(dyn, "v1", "Pod"):
        namespace = str(_attr(item, "metadata", "namespace", default="") or "")
        name = str(_attr(item, "metadata", "name", default="") or "")
        if not namespace or not name:
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
        if not namespace or not pod_name:
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
        if not namespace or not name:
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
    cluster_id: str,
    settings: K8sCollectorSettings | None = None,
) -> K8sClusterSnapshot:
    collector = settings or load_k8s_collector_settings()
    context_name = collector.contexts.get(cluster_id, cluster_id)
    resolved_kubeconfig = resolve_kubeconfig_path(collector.kubeconfig or None)
    dyn, resolved = build_dynamic_client(
        kubeconfig=collector.kubeconfig or None,
        context=context_name,
        fallback_to_current_context=collector.fallback_to_current_context,
    )
    logger.info(
        "Collecting k8s inventory cluster_id=%s context=%s resolved=%s kubeconfig=%s",
        cluster_id,
        context_name,
        resolved or "current-context",
        resolved_kubeconfig or f"(local default; missing {DEFAULT_K8S_KUBECONFIG_PATH})",
    )

    nodes = _collect_nodes(dyn)
    namespaces = _collect_namespaces(dyn)
    deployments = _collect_deployments(dyn)
    rs_map = _index_replicaset_owners(dyn)
    pods = _collect_pods(dyn, rs_map)
    pvcs = _collect_pvcs(dyn, pods)

    return K8sClusterSnapshot(
        cluster_name=cluster_id,
        nodes=nodes,
        namespaces=namespaces,
        deployments=deployments,
        pvcs=pvcs,
        pods=pods,
    )
