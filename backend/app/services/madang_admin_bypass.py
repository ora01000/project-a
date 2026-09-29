"""Madang auth mode: admin bypass login via DB credentials + source passkey."""

from __future__ import annotations

import re
import secrets

# 소스코드에서만 관리 — xxxx-xxxx-xxxx-xxxx (영문 대·소문자·특수문자)
MADANG_ADMIN_BYPASS_PASSKEY = "k9Lm-P2xQ-7nRw-B4t!"
MADANG_ADMIN_BYPASS_USERID = "root"

_PASSKEY_PATTERN = re.compile(
    r"^[A-Za-z0-9!@#$%^&*\-_=+]{4}-[A-Za-z0-9!@#$%^&*\-_=+]{4}-[A-Za-z0-9!@#$%^&*\-_=+]{4}-[A-Za-z0-9!@#$%^&*\-_=+]{4}$"
)


def is_valid_admin_bypass_passkey_format(passkey: str) -> bool:
    return bool(_PASSKEY_PATTERN.match(passkey.strip()))


def verify_admin_bypass_passkey(passkey: str) -> bool:
    candidate = passkey.strip()
    if not is_valid_admin_bypass_passkey_format(candidate):
        return False
    return secrets.compare_digest(candidate, MADANG_ADMIN_BYPASS_PASSKEY)
