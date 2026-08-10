"""vSphere inventory collector (vCenter REST) — http mode only persists."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from backend.app.db.k8s_inventory import get_vsphere_credentials
from backend.app.db.vsphere_inventory import (
    VsphereClusterSnapshot,
    VsphereHostRow,
    VsphereVmOnHostRow,
    replace_vsphere_snapshot,
)
from backend.app.services.agent_runtime_client import normalize_runtime_mode
from backend.app.services.vsphere_client import (
    VsphereApiError,
    VsphereConnectionConfig,
    VsphereConnectTimeoutError,
    VsphereMockScrapeSkippedError,
    VsphereRestClient,
)

logger = logging.getLogger(__name__)

# Mock/local probe should fail fast; http uses a longer default.
_MOCK_PROBE_TIMEOUT_S = float(os.getenv("VSPHERE_MOCK_PROBE_TIMEOUT_S", "5"))
_HTTP_TIMEOUT_S = float(os.getenv("VSPHERE_TIMEOUT_S", "20"))
_VERIFY_SSL = os.getenv("VSPHERE_VERIFY_SSL", "false").lower() in {
    "1",
    "true",
    "yes",
}


def _as_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_client(
    *,
    url: str,
    user: str,
    password: str,
    timeout_s: float,
) -> VsphereRestClient:
    return VsphereRestClient(
        VsphereConnectionConfig(
            base_url=url,
            user=user,
            password=password,
            timeout_s=timeout_s,
            verify_ssl=_VERIFY_SSL,
            api_mode=os.getenv("VSPHERE_API_MODE", "api").strip() or "api",
        )
    )


def collect_vsphere_snapshot(
    cluster_name: str,
    *,
    url: str,
    user: str,
    password: str,
    runtime_mode: str | None = None,
) -> VsphereClusterSnapshot:
    mode = normalize_runtime_mode(runtime_mode)
    timeout_s = _HTTP_TIMEOUT_S if mode == "http" else _MOCK_PROBE_TIMEOUT_S
    client = _build_client(
        url=url,
        user=user,
        password=password,
        timeout_s=timeout_s,
    )
    try:
        client.login()
        if mode != "http":
            raise VsphereMockScrapeSkippedError(
                "mock/local 모드에서는 vSphere URL 연결을 시도한 뒤 scrape를 수행하지 않습니다 "
                f"(base={client.base_url}). AGENT_RUNTIME_MODE=http 에서 수집하세요."
            )

        hosts_raw = client.list_hosts()
        hosts: list[VsphereHostRow] = []
        vms_on_host: list[VsphereVmOnHostRow] = []
        for entry in hosts_raw:
            host_id = str(entry.get("host") or "").strip()
            if not host_id:
                continue
            hosts.append(
                VsphereHostRow(
                    host_id=host_id,
                    host_name=str(entry.get("name") or "") or None,
                    connection_state=str(entry.get("connection_state") or "") or None,
                    power_state=str(entry.get("power_state") or "") or None,
                )
            )
            try:
                vms_raw = client.list_vms_by_host(host_id)
            except VsphereApiError as exc:
                logger.warning(
                    "list_vms_by_host failed host=%s cluster=%s: %s",
                    host_id,
                    cluster_name,
                    exc,
                )
                continue
            for vm_entry in vms_raw:
                vm_id = str(vm_entry.get("vm") or "").strip()
                if not vm_id:
                    continue
                vms_on_host.append(
                    VsphereVmOnHostRow(
                        vm_id=vm_id,
                        host_id=host_id,
                        vm_name=str(vm_entry.get("name") or "") or None,
                        power_state=str(vm_entry.get("power_state") or "") or None,
                        cpu_count=_as_optional_int(vm_entry.get("cpu_count")),
                        memory_mib=_as_optional_int(vm_entry.get("memory_size_MiB")),
                    )
                )

        logger.info(
            "Collected vsphere snapshot cluster=%s hosts=%s vms=%s",
            cluster_name,
            len(hosts),
            len(vms_on_host),
        )
        return VsphereClusterSnapshot(
            cluster_name=cluster_name,
            hosts=hosts,
            vms_on_host=vms_on_host,
        )
    finally:
        client.close()


def collect_and_persist_vsphere(
    database_path: Path | str,
    *,
    cluster_idx: int,
    cluster_name: str,
    runtime_mode: str | None = None,
) -> dict[str, Any]:
    creds = get_vsphere_credentials(database_path, cluster_idx)
    if creds is None:
        raise ValueError(
            f"vSphere 자격증명이 없습니다 (idx={cluster_idx}). "
            "인프라 구성에서 URL/계정/패스워드를 저장하세요."
        )
    url, user, password = creds
    snapshot = collect_vsphere_snapshot(
        cluster_name,
        url=url,
        user=user,
        password=password,
        runtime_mode=runtime_mode,
    )
    return replace_vsphere_snapshot(
        database_path,
        snapshot,
        cluster_idx=cluster_idx,
    )


__all__ = [
    "collect_and_persist_vsphere",
    "collect_vsphere_snapshot",
    "VsphereConnectTimeoutError",
    "VsphereMockScrapeSkippedError",
    "VsphereApiError",
]
