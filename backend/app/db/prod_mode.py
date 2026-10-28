"""DEV/PROD platform mode constants and visibility helpers."""

from __future__ import annotations

# users.current_prod_mode / agentruntime.is_prod
PROD_MODE_DEV = 1
PROD_MODE_PROD = 2

# infra_cluster.is_prod (PLAN lists 1/2/3; integer despite "boolean" wording)
INFRA_PROD_DEV = 1
INFRA_PROD_PROD = 2
INFRA_PROD_BOTH = 3

# users.theme_for_*_mode — 1:dark 2:white(light) 3:homebrew 4:monochrome
THEME_ID_DARK = 1
THEME_ID_LIGHT = 2
THEME_ID_HOMEBREW = 3
THEME_ID_MONOCHROME = 4

VALID_PROD_MODES: frozenset[int] = frozenset({PROD_MODE_DEV, PROD_MODE_PROD})
VALID_INFRA_PROD_FLAGS: frozenset[int] = frozenset(
    {INFRA_PROD_DEV, INFRA_PROD_PROD, INFRA_PROD_BOTH}
)
VALID_THEME_IDS: frozenset[int] = frozenset(
    {THEME_ID_DARK, THEME_ID_LIGHT, THEME_ID_HOMEBREW, THEME_ID_MONOCHROME}
)


def normalize_prod_mode(value: int | None, *, default: int = PROD_MODE_DEV) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return parsed if parsed in VALID_PROD_MODES else default


def normalize_theme_id(value: int | None, *, default: int = THEME_ID_DARK) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return parsed if parsed in VALID_THEME_IDS else default


PROD_MODE_LABELS: dict[int, str] = {
    PROD_MODE_DEV: "개발",
    PROD_MODE_PROD: "운영",
}

INFRA_PROD_LABELS: dict[int, str] = {
    INFRA_PROD_DEV: "개발",
    INFRA_PROD_PROD: "운영",
    INFRA_PROD_BOTH: "개발+운영",
}


def prod_mode_label(value: int | None) -> str:
    return PROD_MODE_LABELS[normalize_prod_mode(value)]


def infra_prod_label(value: int | None) -> str:
    return INFRA_PROD_LABELS[normalize_infra_prod_flag(value)]


def normalize_infra_prod_flag(value: int | None, *, default: int = INFRA_PROD_DEV) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return parsed if parsed in VALID_INFRA_PROD_FLAGS else default


def is_vsphere_infra_type(infra_type: str | None) -> bool:
    key = (infra_type or "").strip().lower()
    return key in {"vsphere", "vcenter"}


def infra_cluster_visible_for_mode(
    *,
    is_prod: int,
    infra_type: str | None,
    current_prod_mode: int,
) -> bool:
    """Infra shape visibility for the selected management platform.

    - 운영(PROD) 선택: 개발+운영 모두 관리 → 전체 클러스터 표시
    - 개발(DEV) 선택: 개발 / 개발+운영 / vSphere 만 표시 (운영 전용 제외)
    """
    mode = normalize_prod_mode(current_prod_mode)
    if mode == PROD_MODE_PROD:
        return True
    if is_vsphere_infra_type(infra_type):
        return True
    flag = normalize_infra_prod_flag(is_prod)
    if flag == INFRA_PROD_BOTH:
        return True
    return flag == PROD_MODE_DEV


def agentruntime_visible_for_mode(*, is_prod: int, current_prod_mode: int) -> bool:
    return normalize_prod_mode(is_prod) == normalize_prod_mode(current_prod_mode)
