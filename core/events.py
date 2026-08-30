"""In-memory activity log — what Trilith actually did, in order.

Every mutating operation and every assembly appends an `Event`. Consoles read
the log with a cursor (`since(after=seq)`), so a dashboard can show live
traffic from *any* client — REST, gRPC, MCP, or in-process — not only its own
actions.

Two deliberate limits:

* **Not persisted.** The log lives in the process and is capped at
  `capacity` events. It is an operational view, not an audit record; a restart
  starts a fresh log. Anything that must survive belongs in the store.
* **Tenant-scoped on read.** `since()` requires the caller's tenant and never
  returns another tenant's activity, matching the boundary the query layer
  enforces everywhere else.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List, Optional

from core.identity import Principal, normalize_tenant

DEFAULT_CAPACITY = 500


@dataclass(frozen=True)
class Event:
    """One thing that happened, addressable by a monotonic sequence number."""

    seq: int
    at: float
    kind: str
    tenant_id: str
    actor: str
    summary: str
    detail: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "at": self.at,
            "kind": self.kind,
            "tenant_id": self.tenant_id,
            "actor": self.actor,
            "summary": self.summary,
            "detail": self.detail,
        }


class EventLog:
    """Bounded, thread-safe ring buffer of recent operations."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY):
        self._events: deque[Event] = deque(maxlen=capacity)
        self._lock = Lock()
        self._seq = 0

    def record(
        self,
        kind: str,
        principal: Optional[Principal] = None,
        summary: str = "",
        **detail: Any,
    ) -> Event:
        with self._lock:
            self._seq += 1
            event = Event(
                seq=self._seq,
                at=time.time(),
                kind=kind,
                tenant_id=principal.tenant_id if principal else normalize_tenant(None),
                actor=principal.describe() if principal else "anonymous",
                summary=summary,
                detail=detail,
            )
            self._events.append(event)
            return event

    def since(
        self,
        after: int = 0,
        tenant_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Event]:
        """Events newer than `after`, oldest first, for one tenant.

        `after=0` returns the tail of the log — how a console cold-starts.
        """
        tenant = normalize_tenant(tenant_id) if tenant_id is not None else None
        with self._lock:
            matched = [
                event
                for event in self._events
                if event.seq > after and (tenant is None or event.tenant_id == tenant)
            ]
        if limit > 0:
            # Newest wins when the caller has fallen behind the buffer.
            matched = matched[-limit:]
        return matched

    @property
    def latest_seq(self) -> int:
        with self._lock:
            return self._seq

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
