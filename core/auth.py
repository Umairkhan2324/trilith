"""API-key authentication, binding a caller to a tenant.

Multi-tenancy is only real if a caller cannot choose their own `tenant_id`.
This module is what makes the boundary enforceable:

* Keys look like ``tri_<43 url-safe chars>`` and are shown exactly once. Only a
  SHA-256 hash is stored, so a leaked database does not leak usable keys.
* Each key pins a `tenant_id`, and optionally an `owner_id`. When a key pins a
  value, a client-supplied value for it is ignored rather than merged.
* **Auth is off until you turn it on.** With no keys minted and no explicit
  requirement, `AuthEnforcer.enabled` is False and Trilith behaves exactly as
  it did in v0.1 — the local quickstart needs no credentials. Minting the first
  key (or passing ``--require-auth`` / ``TRILITH_REQUIRE_AUTH=1``) flips it on.

That single switch is the difference between the local dev deployment and a
shared/cloud one; the binary is the same.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from typing import List, Optional

from core.identity import Principal, normalize_tenant

KEY_PREFIX = "tri_"
# Shown in listings so a key is identifiable without revealing it.
_FINGERPRINT_LEN = 12


class AuthError(Exception):
    """Raised when a request cannot be attributed to a valid principal."""


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def fingerprint(raw_key: str) -> str:
    """Stable public identifier for a key (first bytes of its hash)."""
    return hash_key(raw_key)[:_FINGERPRINT_LEN]


def generate_key() -> str:
    return f"{KEY_PREFIX}{secrets.token_urlsafe(32)}"


@dataclass(frozen=True)
class ApiKeyRecord:
    fingerprint: str
    tenant_id: str
    owner_id: str
    name: str
    created_at: int
    revoked: bool


class ApiKeyStore:
    """Persists API keys alongside context data in the same SQLite file."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._init_db()

    def _init_db(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_hash TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                owner_id TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id)"
        )
        self._conn.commit()

    def create(
        self,
        tenant_id: str,
        owner_id: str = "",
        name: str = "",
    ) -> tuple[str, ApiKeyRecord]:
        """Mint a key. Returns (raw_key, record) — the raw key is never stored."""
        raw = generate_key()
        record = ApiKeyRecord(
            fingerprint=fingerprint(raw),
            tenant_id=normalize_tenant(tenant_id),
            owner_id=owner_id or "",
            name=name or "",
            created_at=int(time.time()),
            revoked=False,
        )
        self._conn.execute(
            """
            INSERT INTO api_keys
            (key_hash, fingerprint, tenant_id, owner_id, name, created_at, revoked)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (
                hash_key(raw),
                record.fingerprint,
                record.tenant_id,
                record.owner_id,
                record.name,
                record.created_at,
            ),
        )
        self._conn.commit()
        return raw, record

    def lookup(self, raw_key: str) -> Optional[ApiKeyRecord]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT fingerprint, tenant_id, owner_id, name, created_at, revoked "
            "FROM api_keys WHERE key_hash = ?",
            (hash_key(raw_key),),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return ApiKeyRecord(
            fingerprint=row[0],
            tenant_id=row[1],
            owner_id=row[2],
            name=row[3],
            created_at=row[4],
            revoked=bool(row[5]),
        )

    def list(self, tenant_id: Optional[str] = None) -> List[ApiKeyRecord]:
        query = (
            "SELECT fingerprint, tenant_id, owner_id, name, created_at, revoked "
            "FROM api_keys"
        )
        params: list = []
        if tenant_id:
            query += " WHERE tenant_id = ?"
            params.append(normalize_tenant(tenant_id))
        query += " ORDER BY created_at DESC"

        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return [
            ApiKeyRecord(
                fingerprint=r[0],
                tenant_id=r[1],
                owner_id=r[2],
                name=r[3],
                created_at=r[4],
                revoked=bool(r[5]),
            )
            for r in cursor.fetchall()
        ]

    def revoke(self, fingerprint_prefix: str) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            "UPDATE api_keys SET revoked = 1 "
            "WHERE fingerprint LIKE ? AND revoked = 0",
            (f"{fingerprint_prefix}%",),
        )
        self._conn.commit()
        return cursor.rowcount

    def active_count(self) -> int:
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM api_keys WHERE revoked = 0")
        return int(cursor.fetchone()[0])

    def total_count(self) -> int:
        """Every key ever minted, revoked ones included.

        Auth keys off this rather than `active_count`: revoking your last key
        must not silently reopen the instance to unauthenticated callers.
        """
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM api_keys")
        return int(cursor.fetchone()[0])


def parse_authorization(header: Optional[str]) -> Optional[str]:
    """Extract the raw key from an Authorization header.

    Accepts ``Bearer tri_...``, ``ApiKey tri_...``, or a bare ``tri_...``.
    """
    if not header:
        return None
    value = header.strip()
    lowered = value.lower()
    for prefix in ("bearer ", "apikey ", "token "):
        if lowered.startswith(prefix):
            return value[len(prefix):].strip() or None
    return value or None


class AuthEnforcer:
    """Turns an inbound credential into the Principal a request runs as."""

    def __init__(self, store: ApiKeyStore, require_auth: Optional[bool] = None):
        self._store = store
        if require_auth is None:
            require_auth = os.environ.get("TRILITH_REQUIRE_AUTH", "").lower() in (
                "1", "true", "yes", "on",
            )
        self._require_auth = bool(require_auth)

    @property
    def store(self) -> ApiKeyStore:
        return self._store

    @property
    def enabled(self) -> bool:
        """Auth is live once any key has been minted, or when explicitly required.

        Keeping this dynamic means `trilith key create` secures a running
        server without a restart, and a fresh install stays open for local use.

        It is deliberately a one-way door: revoking every key leaves auth on,
        so an instance can never be reopened to the world by a revocation. To
        genuinely go back to open mode, delete the `api_keys` rows yourself.
        """
        return self._require_auth or self._store.total_count() > 0

    def resolve(
        self,
        authorization: Optional[str],
        tenant_id: str = "",
        owner_id: str = "",
        session_id: str = "",
        legacy_scope: str = "",
    ) -> Principal:
        """Build the request's Principal.

        Open mode (auth disabled): the caller's own values are trusted, which
        is what makes the zero-config local path work.

        Enforced mode: the key decides `tenant_id` (and `owner_id` if pinned).
        Client-supplied values for those are discarded, not merged — a caller
        cannot read another tenant by asking nicely.
        """
        if not self.enabled:
            return Principal(
                tenant_id=tenant_id,
                owner_id=owner_id,
                session_id=session_id,
                legacy_scope=legacy_scope,
            )

        raw_key = parse_authorization(authorization)
        if not raw_key:
            raise AuthError(
                "Missing API key. Send 'Authorization: Bearer tri_...' "
                "(mint one with: trilith key create --tenant <id>)."
            )

        record = self._store.lookup(raw_key)
        if record is None:
            raise AuthError("Invalid API key.")
        if record.revoked:
            raise AuthError("API key has been revoked.")

        return Principal(
            tenant_id=record.tenant_id,
            owner_id=record.owner_id or owner_id,
            session_id=session_id,
            legacy_scope=legacy_scope,
        )
