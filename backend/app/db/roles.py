ROLE_ADMIN = 0
ROLE_USER = 1
ROLE_PENDING = 5
ROLE_SUPERADMIN = 100

ROOT_USERID = "root"


def is_admin_role(role: int) -> bool:
    return role == ROLE_ADMIN or role == ROLE_SUPERADMIN


def is_hidden_system_user(userid: str, role: int | None = None) -> bool:
    normalized = userid.strip()
    if normalized == ROOT_USERID:
        return True
    if role is not None and role == ROLE_SUPERADMIN:
        return True
    return False
