"""Bidirectional field encryption for users.userid/email/password/username.

Envelope-style AES-256-GCM with versioned ciphertext (`v{n}:…`) and HMAC
blind indexes for equality search. KEK/blind keys live outside the DB.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import threading
from dataclasses import dataclass
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

LOGGER = logging.getLogger(__name__)

_CIPHER_RE = re.compile(r"^v(\d+):([A-Za-z0-9_-]+)$")
_VERSION_PREFIX = "v"


@dataclass(frozen=True)
class UsersFieldCryptoConfig:
    backend: str  # env | vault
    kek: bytes | None
    previous_kek: bytes | None
    blind_key: bytes | None
    key_version: int
    enabled: bool


def _b64url_decode(raw: str) -> bytes:
    padded = raw + "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_key_material(raw: str, *, label: str) -> bytes | None:
    text = (raw or "").strip()
    if not text:
        return None
    key: bytes | None = None
    for decoder in (base64.b64decode, _b64url_decode):
        try:
            candidate = decoder(text)
            if len(candidate) in (16, 24, 32):
                key = candidate
                break
        except Exception:
            continue
    if key is None:
        # Derive a 32-byte key from arbitrary secret material.
        key = hashlib.sha256(text.encode("utf-8")).digest()
        LOGGER.debug("Derived 32-byte %s via SHA-256", label)
    return key


def _load_vault_secret(path: str) -> dict[str, str]:
    """Load a KV secret from Vault (KV v2 data.data preferred)."""
    import httpx

    addr = (os.environ.get("VAULT_ADDR") or "").rstrip("/")
    token = (os.environ.get("VAULT_TOKEN") or "").strip()
    if not addr or not token:
        raise RuntimeError("USERS_FIELD_CRYPTO_BACKEND=vault requires VAULT_ADDR and VAULT_TOKEN")
    secret_path = path.strip().lstrip("/")
    if not secret_path:
        raise RuntimeError("USERS_FIELD_VAULT_KEK_PATH is empty")
    # Accept either "secret/data/foo" or "secret/foo"
    url = f"{addr}/v1/{secret_path}"
    response = httpx.get(url, headers={"X-Vault-Token": token}, timeout=10.0)
    response.raise_for_status()
    body = response.json()
    data = body.get("data") or {}
    if isinstance(data.get("data"), dict):
        data = data["data"]
    return {str(k): str(v) for k, v in data.items()}


def load_users_field_crypto_config() -> UsersFieldCryptoConfig:
    backend = (os.environ.get("USERS_FIELD_CRYPTO_BACKEND") or "env").strip().lower()
    if backend not in ("env", "vault"):
        backend = "env"
    key_version = 1
    try:
        key_version = max(1, int(os.environ.get("USERS_FIELD_KEY_VERSION") or "1"))
    except ValueError:
        key_version = 1

    kek_raw = ""
    prev_raw = ""
    blind_raw = ""
    if backend == "vault":
        path = os.environ.get("USERS_FIELD_VAULT_KEK_PATH") or "secret/data/project-a/users-field-crypto"
        try:
            secret = _load_vault_secret(path)
            kek_raw = secret.get("kek") or secret.get("USERS_FIELD_KEK") or ""
            prev_raw = secret.get("previous_kek") or secret.get("USERS_FIELD_PREVIOUS_KEK") or ""
            blind_raw = secret.get("blind_key") or secret.get("USERS_FIELD_BLIND_KEY") or ""
        except Exception:
            LOGGER.exception("Failed to load users-field crypto keys from Vault path=%s", path)
            raise
    else:
        kek_raw = os.environ.get("USERS_FIELD_KEK") or ""
        prev_raw = os.environ.get("USERS_FIELD_PREVIOUS_KEK") or ""
        blind_raw = os.environ.get("USERS_FIELD_BLIND_KEY") or ""

    kek = _decode_key_material(kek_raw, label="USERS_FIELD_KEK")
    previous_kek = _decode_key_material(prev_raw, label="USERS_FIELD_PREVIOUS_KEK")
    blind_key = _decode_key_material(blind_raw, label="USERS_FIELD_BLIND_KEY")
    enabled = kek is not None and blind_key is not None
    if not enabled and (kek_raw or blind_raw):
        LOGGER.warning("Users field crypto keys incomplete; encryption disabled")
    return UsersFieldCryptoConfig(
        backend=backend,
        kek=kek,
        previous_kek=previous_kek,
        blind_key=blind_key,
        key_version=key_version,
        enabled=enabled,
    )


_config_lock = threading.Lock()
_cached_config: UsersFieldCryptoConfig | None = None


def get_users_field_crypto_config(*, refresh: bool = False) -> UsersFieldCryptoConfig:
    global _cached_config
    with _config_lock:
        if _cached_config is None or refresh:
            _cached_config = load_users_field_crypto_config()
        return _cached_config


def is_users_field_crypto_enabled() -> bool:
    return get_users_field_crypto_config().enabled


def is_ciphertext(value: str | None) -> bool:
    text = (value or "").strip()
    return bool(_CIPHER_RE.match(text))


def encrypt_field(plaintext: str, *, aad: str = "") -> str:
    """Encrypt plaintext; passthrough when crypto disabled."""
    cfg = get_users_field_crypto_config()
    text = plaintext if plaintext is not None else ""
    if not cfg.enabled or cfg.kek is None:
        return text
    if is_ciphertext(text):
        return text
    aesgcm = AESGCM(cfg.kek)
    iv = os.urandom(12)
    ct = aesgcm.encrypt(iv, text.encode("utf-8"), aad.encode("utf-8") if aad else None)
    token = _b64url_encode(iv + ct)
    return f"{_VERSION_PREFIX}{cfg.key_version}:{token}"


def decrypt_field(stored: str, *, aad: str = "") -> str:
    """Decrypt ciphertext; passthrough plaintext / disabled mode."""
    text = stored if stored is not None else ""
    cfg = get_users_field_crypto_config()
    match = _CIPHER_RE.match(text.strip())
    if match is None:
        return text
    if not cfg.enabled:
        raise RuntimeError("Encrypted users field present but USERS_FIELD crypto is disabled")
    version = int(match.group(1))
    raw = _b64url_decode(match.group(2))
    if len(raw) < 12 + 16:
        raise ValueError("invalid users field ciphertext")
    iv, body = raw[:12], raw[12:]
    keys: list[bytes] = []
    if cfg.kek is not None:
        keys.append(cfg.kek)
    if cfg.previous_kek is not None and cfg.previous_kek not in keys:
        keys.append(cfg.previous_kek)
    aad_bytes = aad.encode("utf-8") if aad else None
    last_error: Exception | None = None
    for key in keys:
        try:
            return AESGCM(key).decrypt(iv, body, aad_bytes).decode("utf-8")
        except Exception as exc:  # noqa: BLE001 — try next key version
            last_error = exc
            continue
    raise RuntimeError(f"Failed to decrypt users field (key_version={version})") from last_error


def blind_index(plaintext: str, *, kind: str) -> str:
    """HMAC-SHA256 blind index (hex). Empty plaintext → empty index."""
    cfg = get_users_field_crypto_config()
    normalized = (plaintext or "").strip()
    if kind == "email":
        normalized = normalized.lower()
    if not normalized:
        return ""
    if not cfg.enabled or cfg.blind_key is None:
        # Dev/disabled: deterministic non-secret stand-in so UNIQUE columns still work.
        return hashlib.sha256(f"{kind}:{normalized}".encode("utf-8")).hexdigest()
    digest = hmac.new(
        cfg.blind_key,
        f"{kind}:{normalized}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def pack_user_secrets(
    *,
    userid: str,
    email: str,
    username: str,
    password: str,
) -> dict[str, str]:
    """Return DB-ready encrypted fields + blind indexes."""
    uid = (userid or "").strip()
    em = (email or "").strip()
    un = (username or "").strip()
    pw = password if password is not None else ""
    return {
        "userid": encrypt_field(uid, aad="userid"),
        "email": encrypt_field(em, aad="email"),
        "username": encrypt_field(un, aad="username"),
        "password": encrypt_field(pw, aad="password"),
        "userid_bidx": blind_index(uid, kind="userid"),
        "email_bidx": blind_index(em, kind="email"),
    }


def unpack_user_secrets(row_userid: str, row_email: str, row_username: str, row_password: str) -> dict[str, str]:
    return {
        "userid": decrypt_field(row_userid, aad="userid"),
        "email": decrypt_field(row_email, aad="email"),
        "username": decrypt_field(row_username, aad="username"),
        "password": decrypt_field(row_password, aad="password"),
    }
