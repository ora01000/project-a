"""KubeVirt inventory collector (DynamicClient) — reuses K8s base collectors."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.app.config import K8sCollectorSettings, load_k8s_collector_settings
from backend.app.db.kubevirt_inventory import (
    KubevirtClusterSnapshot,
    KubevirtVmRow,
    KubevirtVmVolumeRow,
    replace_kubevirt_snapshot,
)
from backend.app.services.k8s_collector import (
    _attr,
    _collect_deployments,
    _collect_namespaces,
    _collect_nodes,
    _collect_pods,
    _collect_pvcs,
    _index_replicaset_owners,
    _safe_list,
    build_dynamic_client,
    is_excluded_system_namespace,
    parse_cpu_cores,
    parse_mem_gi,
    resolve_kubeconfig_path,
    DEFAULT_K8S_KUBECONFIG_PATH,
)
from backend.app.services.agent_runtime_client import normalize_runtime_mode

logger = logging.getLogger(__name__)


def _primary_vmi_ip(vmi: Any) -> str | None:
    interfaces = _attr(vmi, "status", "interfaces", default=[]) or []
    for iface in interfaces:
        ip = _attr(iface, "ipAddress") or _attr(iface, "ip")
        if ip and str(ip).strip():
            return str(ip).strip()[:45]
    return None


def _vm_cpu_cores(domain: Any) -> float | None:
    cores = _attr(domain, "cpu", "cores")
    if cores is not None:
        try:
            return float(cores)
        except (TypeError, ValueError):
            pass
    sockets = _attr(domain, "cpu", "sockets")
    threads = _attr(domain, "cpu", "threads")
    try:
        if sockets is not None:
            s = float(sockets)
            t = float(threads) if threads is not None else 1.0
            c = float(cores) if cores is not None else 1.0
            return s * t * c
    except (TypeError, ValueError):
        pass
    request = _attr(domain, "resources", "requests", "cpu")
    return parse_cpu_cores(str(request) if request is not None else None)


def _vm_memory_gi(domain: Any) -> int | None:
    guest = _attr(domain, "memory", "guest")
    parsed = parse_mem_gi(str(guest) if guest is not None else None)
    if parsed is not None:
        return parsed
    request = _attr(domain, "resources", "requests", "memory")
    return parse_mem_gi(str(request) if request is not None else None)


def _volume_pvc_name(volume: Any) -> str | None:
    for key in ("persistentVolumeClaim", "dataVolume"):
        claim = _attr(volume, key)
        if claim is None:
            continue
        claim_name = _attr(claim, "claimName") or _attr(claim, "name")
        if claim_name:
            return str(claim_name).strip()
    return None


def _collect_vms_and_volumes(
    dyn,
    pvc_capacity: dict[tuple[str, str], int | None],
) -> tuple[list[KubevirtVmRow], list[KubevirtVmVolumeRow]]:
    vm_items = _safe_list(dyn, "kubevirt.io/v1", "VirtualMachine")
    vmi_items = _safe_list(dyn, "kubevirt.io/v1", "VirtualMachineInstance")
    vmi_by_key: dict[tuple[str, str], Any] = {}
    for vmi in vmi_items:
        ns = str(_attr(vmi, "metadata", "namespace", default="") or "")
        name = str(_attr(vmi, "metadata", "name", default="") or "")
        if ns and name:
            vmi_by_key[(ns, name)] = vmi

    vms: list[KubevirtVmRow] = []
    volumes: list[KubevirtVmVolumeRow] = []

    for vm in vm_items:
        ns = str(_attr(vm, "metadata", "namespace", default="") or "")
        name = str(_attr(vm, "metadata", "name", default="") or "")
        if not ns or not name or is_excluded_system_namespace(ns):
            continue

        run_strategy = _attr(vm, "spec", "runStrategy")
        if run_strategy is None:
            running = _attr(vm, "spec", "running")
            if running is True:
                run_strategy = "Always"
            elif running is False:
                run_strategy = "Halted"

        printable = _attr(vm, "status", "printableStatus")
        ready = _attr(vm, "status", "ready")
        if ready is not None and not isinstance(ready, bool):
            ready = str(ready).lower() in {"1", "true", "yes"}

        domain = _attr(vm, "spec", "template", "spec", "domain", default=None)
        disks = _attr(domain, "devices", "disks", default=[]) or []
        networks = _attr(vm, "spec", "template", "spec", "networks", default=[]) or []
        template_volumes = (
            _attr(vm, "spec", "template", "spec", "volumes", default=[]) or []
        )

        volume_names: list[str] = []
        for volume in template_volumes:
            vol_name = str(_attr(volume, "name", default="") or "").strip()
            if vol_name:
                volume_names.append(vol_name)
            pvc_name = _volume_pvc_name(volume)
            volumes.append(
                KubevirtVmVolumeRow(
                    namespace=ns,
                    vm_name=name,
                    volume_name=vol_name or (pvc_name or "volume"),
                    pvc_name=pvc_name,
                    capacity_gi=(
                        pvc_capacity.get((ns, pvc_name)) if pvc_name else None
                    ),
                )
            )

        vmi = vmi_by_key.get((ns, name))
        vmi_phase = None
        node_name = None
        ip_address = None
        os_info = None
        if vmi is not None:
            vmi_phase = _attr(vmi, "status", "phase")
            node_name = _attr(vmi, "status", "nodeName")
            ip_address = _primary_vmi_ip(vmi)
            guest = _attr(vmi, "status", "guestOSInfo", default=None)
            if guest is not None:
                pretty = _attr(guest, "prettyName") or _attr(guest, "name")
                if pretty:
                    os_info = str(pretty).strip()[:100]

        created = _attr(vm, "metadata", "creationTimestamp")
        vms.append(
            KubevirtVmRow(
                namespace=ns,
                name=name,
                run_strategy=str(run_strategy)[:20] if run_strategy else None,
                printable_status=str(printable)[:30] if printable else None,
                ready=ready if isinstance(ready, bool) else None,
                vmi_phase=str(vmi_phase)[:20] if vmi_phase else None,
                node_name=str(node_name)[:50] if node_name else None,
                ip_address=ip_address,
                cpu_cores=_vm_cpu_cores(domain),
                memory_gi=_vm_memory_gi(domain),
                disk_count=len(disks) if disks else len(volume_names) or None,
                network_count=len(networks) if networks else None,
                volume_names=volume_names,
                os_info=os_info,
                created_at=str(created) if created else None,
            )
        )

    return vms, volumes


def collect_kubevirt_snapshot(
    cluster_name: str,
    settings: K8sCollectorSettings | None = None,
    *,
    runtime_mode: str | None = None,
) -> KubevirtClusterSnapshot:
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
        "Collecting kubevirt inventory cluster=%s context=%s resolved=%s "
        "kubeconfig=%s mode=%s",
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
    pvc_capacity = {
        (pvc.namespace, pvc.name): pvc.capacity for pvc in pvcs
    }
    vms, vm_volumes = _collect_vms_and_volumes(dyn, pvc_capacity)

    return KubevirtClusterSnapshot(
        cluster_name=cluster_name,
        nodes=nodes,
        namespaces=namespaces,
        deployments=deployments,
        pvcs=pvcs,
        vms=vms,
        vm_volumes=vm_volumes,
    )


def collect_and_persist_kubevirt(
    database_path: Path | str,
    *,
    cluster_idx: int,
    cluster_name: str,
    settings: K8sCollectorSettings | None = None,
    runtime_mode: str | None = None,
) -> dict[str, Any]:
    collector = settings or load_k8s_collector_settings()
    snapshot = collect_kubevirt_snapshot(
        cluster_name,
        collector,
        runtime_mode=runtime_mode,
    )
    return replace_kubevirt_snapshot(
        database_path,
        snapshot,
        cluster_idx=cluster_idx,
    )
