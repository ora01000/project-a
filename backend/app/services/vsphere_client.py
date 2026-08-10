"""Minimal vCenter REST client for inventory scrape (inspired by vsphere-mcp-pro)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class VsphereApiError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        path: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.path = path
        detail = message
        if status_code is not None:
            detail = f"{message} (HTTP {status_code}"
            if path:
                detail += f" on {path}"
            detail += ")"
        super().__init__(detail)


class VsphereConnectTimeoutError(Exception):
    """Raised when vCenter login/connect times out or is unreachable."""


class VsphereMockScrapeSkippedError(Exception):
    """Raised when mock/local mode probes vCenter but must not persist scrape data."""


@dataclass(frozen=True)
class VsphereConnectionConfig:
    base_url: str
    user: str
    password: str
    timeout_s: float = 20.0
    verify_ssl: bool = False
    api_mode: str = "api"  # "api" | "rest"


def normalize_vsphere_base_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        raise ValueError("vSphere URL이 비어 있습니다.")
    parsed = urlparse(text if "://" in text else f"https://{text}")
    scheme = parsed.scheme or "https"
    if scheme not in {"http", "https"}:
        raise ValueError(f"지원하지 않는 URL scheme 입니다: {scheme}")
    host = parsed.hostname
    if not host:
        raise ValueError(f"vSphere URL에서 호스트를 파싱할 수 없습니다: {url}")
    netloc = parsed.netloc  # keeps port
    return f"{scheme}://{netloc}".rstrip("/")


class VsphereRestClient:
    """Session-based vCenter inventory client (hosts / VMs by host)."""

    def __init__(self, cfg: VsphereConnectionConfig) -> None:
        self._cfg = cfg
        self._base = normalize_vsphere_base_url(cfg.base_url)
        self._timeout = float(cfg.timeout_s)
        self._api_mode = "api" if cfg.api_mode == "api" else "rest"
        self._session_id: str | None = None
        self._client = httpx.Client(
            timeout=httpx.Timeout(self._timeout),
            verify=cfg.verify_ssl,
            follow_redirects=True,
        )

    @property
    def base_url(self) -> str:
        return self._base

    def close(self) -> None:
        try:
            self.logout()
        finally:
            self._client.close()

    def __enter__(self) -> VsphereRestClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _auth_headers(self) -> dict[str, str]:
        if not self._session_id:
            return {}
        return {"vmware-api-session-id": self._session_id}

    def _path(self, rest: str, api: str) -> str:
        return api if self._api_mode == "api" else rest

    def _extract_value(self, response: httpx.Response) -> Any:
        data = response.json()
        if self._api_mode == "rest" and isinstance(data, dict) and "value" in data:
            return data["value"]
        return data

    def _raise_connect(self, exc: Exception, *, operation: str) -> None:
        if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
            raise VsphereConnectTimeoutError(
                f"vCenter {operation} 실패(타임아웃/연결불가): {self._base} ({exc})"
            ) from exc
        raise

    def login(self) -> None:
        if self._session_id:
            return
        auth = (self._cfg.user, self._cfg.password)
        if self._api_mode == "api":
            url = f"{self._base}/api/session"
            try:
                response = self._client.post(url, auth=auth)
            except Exception as exc:
                self._raise_connect(exc, operation="login")
                raise
            if response.is_success:
                token = self._parse_session_token(response)
                if token:
                    self._session_id = token
                    logger.info("vCenter login ok via /api/session base=%s", self._base)
                    return
            logger.debug(
                "/api/session failed status=%s, trying /rest",
                response.status_code,
            )

        url = f"{self._base}/rest/com/vmware/cis/session"
        try:
            response = self._client.post(url, auth=auth)
        except Exception as exc:
            self._raise_connect(exc, operation="login")
            raise
        if not response.is_success:
            raise VsphereApiError(
                "vCenter login failed",
                status_code=response.status_code,
                path=url,
            )
        try:
            token = response.json().get("value")
        except Exception as exc:
            raise VsphereApiError("vCenter login returned invalid JSON", path=url) from exc
        if not token:
            raise VsphereApiError("vCenter login returned no session token", path=url)
        self._session_id = str(token)
        logger.info("vCenter login ok via /rest/session base=%s", self._base)

    @staticmethod
    def _parse_session_token(response: httpx.Response) -> str | None:
        try:
            token = response.json()
            if isinstance(token, dict) and "value" in token:
                token = token["value"]
            elif isinstance(token, (list, dict)):
                token = None
        except Exception:
            token = (response.text or "").strip() or None
        if not token:
            token = response.headers.get("vmware-api-session-id")
        return str(token) if token else None

    def logout(self) -> None:
        if not self._session_id:
            return
        path = (
            "/api/session"
            if self._api_mode == "api"
            else "/rest/com/vmware/cis/session"
        )
        try:
            self._client.delete(
                f"{self._base}{path}",
                headers=self._auth_headers(),
            )
        except Exception as exc:
            logger.warning("vCenter logout failed base=%s: %s", self._base, exc)
        finally:
            self._session_id = None

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url = f"{self._base}{path}"
        try:
            response = self._client.request(
                method,
                url,
                headers=self._auth_headers(),
                params=params,
            )
        except Exception as exc:
            self._raise_connect(exc, operation=method)
            raise
        if response.status_code == 401:
            self._session_id = None
            self.login()
            try:
                response = self._client.request(
                    method,
                    url,
                    headers=self._auth_headers(),
                    params=params,
                )
            except Exception as exc:
                self._raise_connect(exc, operation=method)
                raise
        return response

    def _check(self, response: httpx.Response, path: str, operation: str) -> None:
        if response.is_success:
            return
        raise VsphereApiError(
            f"Failed to {operation}",
            status_code=response.status_code,
            path=path,
        )

    def list_hosts(self) -> list[dict[str, Any]]:
        path = self._path("/rest/vcenter/host", "/api/vcenter/host")
        response = self._request("GET", path)
        self._check(response, path, "list hosts")
        data = self._extract_value(response)
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def list_clusters(self) -> list[dict[str, Any]]:
        """GET /api/vcenter/cluster — cluster MoID, name, ha_enabled, drs_enabled."""
        path = self._path("/rest/vcenter/cluster", "/api/vcenter/cluster")
        response = self._request("GET", path)
        self._check(response, path, "list clusters")
        data = self._extract_value(response)
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def list_hosts_by_cluster(self, cluster_id: str) -> list[dict[str, Any]]:
        """Hosts belonging to a ClusterComputeResource (REST filter.clusters / clusters)."""
        cluster_id = (cluster_id or "").strip()
        if not cluster_id:
            raise ValueError("cluster_id is required")
        path = self._path("/rest/vcenter/host", "/api/vcenter/host")
        params = (
            {"clusters": cluster_id}
            if self._api_mode == "api"
            else {"filter.clusters.1": cluster_id}
        )
        response = self._request("GET", path, params=params)
        if (
            not response.is_success
            and self._api_mode == "rest"
            and response.status_code == 400
        ):
            response = self._request(
                "GET", path, params={"filter.clusters": cluster_id}
            )
        self._check(response, path, f"list hosts in cluster '{cluster_id}'")
        data = self._extract_value(response)
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def list_vms_by_host(self, host_id: str) -> list[dict[str, Any]]:
        host_id = (host_id or "").strip()
        if not host_id:
            raise ValueError("host_id is required")
        path = self._path("/rest/vcenter/vm", "/api/vcenter/vm")
        params = (
            {"hosts": host_id}
            if self._api_mode == "api"
            else {"filter.hosts.1": host_id}
        )
        response = self._request("GET", path, params=params)
        if not response.is_success and self._api_mode == "rest" and response.status_code == 400:
            response = self._request("GET", path, params={"filter.hosts": host_id})
        self._check(response, path, f"list VMs on host '{host_id}'")
        data = self._extract_value(response)
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]
