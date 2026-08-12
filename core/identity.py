"""Principal — who is asking, and what they are allowed to see.

Trilith's isolation model has two layers:

1. **Tenant** (`tenant_id`) is a hard boundary. Items belonging to another
   tenant are never returned, ranked, or counted against a budget. The only
   exception is `Scope.GLOBAL`, which is explicitly cross-tenant.
2. **Scope kind** narrows visibility *within* a tenant: `TENANT` (everyone),
   `USER` (matching `owner_id`), `SESSION` (matching `session_id`).

`requester_scope` from v0.1 is still accepted. When a caller supplies only
that string and no identity fields, the Principal runs in *legacy mode*: scope
kinds are matched by name, exactly as they were before multi-tenancy existed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.proto.trilith_pb2 import ContextItem
from core.proto.trilith_pb2 import Principal as PrincipalPB

# Items written before multi-tenancy (and items written with no tenant at all)
# live here. The SQLite migration backfills existing rows to this value.
DEFAULT_TENANT = "default"


def normalize_tenant(tenant_id: Optional[str]) -> str:
    """Empty/None tenant means the default tenant, never 'no tenant'."""
    return (tenant_id or "").strip() or DEFAULT_TENANT


@dataclass(frozen=True)
class Principal:
    """The identity a request is evaluated against."""

    tenant_id: str = DEFAULT_TENANT
    owner_id: str = ""
    session_id: str = ""
    # v0.1 compatibility only. Set when the caller passed a bare scope name.
    legacy_scope: str = ""

    def __post_init__(self):
        object.__setattr__(self, "tenant_id", normalize_tenant(self.tenant_id))
        object.__setattr__(self, "owner_id", (self.owner_id or "").strip())
        object.__setattr__(self, "session_id", (self.session_id or "").strip())
        object.__setattr__(self, "legacy_scope", (self.legacy_scope or "").strip())

    @property
    def is_legacy(self) -> bool:
        """True when only a v0.1 scope string was supplied (no real identity)."""
        return not self.owner_id and not self.session_id

    @classmethod
    def from_pb(
        cls,
        pb: Optional[PrincipalPB],
        legacy_scope: str = "",
    ) -> "Principal":
        if pb is None:
            return cls(legacy_scope=legacy_scope)
        return cls(
            tenant_id=pb.tenant_id,
            owner_id=pb.owner_id,
            session_id=pb.session_id,
            legacy_scope=pb.requester_scope or legacy_scope,
        )

    def to_pb(self) -> PrincipalPB:
        return PrincipalPB(
            tenant_id=self.tenant_id,
            owner_id=self.owner_id,
            session_id=self.session_id,
            requester_scope=self.legacy_scope,
        )

    def stamp(self, item: ContextItem) -> None:
        """Fill an item's identity from this principal where it left them blank.

        A caller may not write into another tenant: `tenant_id` is always
        overwritten with the principal's own.
        """
        item.tenant_id = self.tenant_id
        if not item.owner_id:
            item.owner_id = self.owner_id
        if not item.session_id:
            item.session_id = self.session_id

    def describe(self) -> str:
        parts = [f"tenant={self.tenant_id}"]
        if self.owner_id:
            parts.append(f"owner={self.owner_id}")
        if self.session_id:
            parts.append(f"session={self.session_id}")
        if self.legacy_scope:
            parts.append(f"scope={self.legacy_scope}")
        return " ".join(parts)
