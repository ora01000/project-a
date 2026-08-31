ROLE_ADMIN = 0
ROLE_USER = 1
ROLE_INFRAADMIN = 2
ROLE_PENDING = 5
ROLE_SUPERADMIN = 100

ROOT_USERID = "root"

ASSIGNABLE_ROLES = frozenset({ROLE_ADMIN, ROLE_USER, ROLE_INFRAADMIN, ROLE_PENDING})


def is_admin_role(role: int) -> bool:
    return role == ROLE_ADMIN or role == ROLE_SUPERADMIN


def can_run_gap_analysis(role: int) -> bool:
    return is_admin_role(role) or role == ROLE_INFRAADMIN


def is_assignable_role(role: int) -> bool:
    return role in ASSIGNABLE_ROLES


def should_mask_ips(role: int) -> bool:
    """IP masking applies only to ordinary users (role=1)."""
    return role == ROLE_USER


def is_hidden_system_user(userid: str, role: int | None = None) -> bool:
    normalized = userid.strip()
    if normalized == ROOT_USERID:
        return True
    if role is not None and role == ROLE_SUPERADMIN:
        return True
    return False
