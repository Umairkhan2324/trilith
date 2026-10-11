import hashlib
import json
import re

from google.protobuf.timestamp_pb2 import Timestamp

from core.identity import Principal
from core.privacy import PolicyEngine
from core.proto.trilith_pb2 import ContextItem, Scope, Tier
from core.store_base import BaseStore


class ProceduralStore(BaseStore):
    """Conservative extractive distillation with retained source evidence."""

    tier = Tier.PROCEDURAL
    include_global = True

    def write(self, item, subtask_id=None):
        item.tier = self.tier
        return self.backend.save(item, subtask_id=subtask_id)

    def fold(self, subtask_id, principal=None):
        principal = principal or Principal()
        with self.backend.transaction():
            items = self.backend.query(
                self.tier, subtask_id=subtask_id, tenant_id=principal.tenant_id
            )
            items = [
                i
                for i in items
                if i.owner_id == principal.owner_id
                and i.session_id == principal.session_id
                and PolicyEngine().explain(i, principal)[0]
            ]
            if not items:
                return None
            if len({i.scope for i in items}) != 1:
                raise ValueError("Fold requires homogeneous scope")
            if any(i.scope == Scope.GLOBAL for i in items) and not principal.can("publish_global"):
                raise PermissionError("publish_global capability required")
            items.sort(key=lambda i: (i.created_at.seconds, i.created_at.nanos, i.id))
            strategies, outcomes = [], []
            for item in items:
                try:
                    record = json.loads(item.content)
                except (ValueError, TypeError):
                    record = None
                if isinstance(record, dict):
                    if isinstance(record.get("strategy"), str):
                        strategies.append(record["strategy"][:512])
                    if isinstance(record.get("outcome"), str):
                        outcomes.append(record["outcome"][:512])
                elif item.content:
                    sentence = re.split(r"(?<=[.!?])\s+|\n", item.content)[0]
                    strategies.append(sentence[:256])
            payload = {
                "method": "extractive-v1",
                "outcome": outcomes[-1] if outcomes else "Not explicitly recorded",
                "strategy": list(dict.fromkeys(strategies))[:4],
                "strategy_status": "source excerpts; reuse requires validation",
                "sources": [{"tenant_id": i.tenant_id, "id": i.id} for i in items],
            }
            digest = hashlib.sha256(
                json.dumps(
                    [
                        principal.tenant_id,
                        principal.owner_id,
                        principal.session_id,
                        subtask_id,
                        [i.id for i in items],
                    ]
                ).encode()
            ).hexdigest()[:24]
            created = Timestamp()
            created.GetCurrentTime()
            summary = ContextItem(
                id="folded-" + digest,
                tier=self.tier,
                content=json.dumps(payload, ensure_ascii=False),
                scope=items[0].scope,
                provenance="procedural_fold:extractive-v1",
                created_at=created,
                tenant_id=principal.tenant_id,
                owner_id=principal.owner_id,
                session_id=principal.session_id,
            )
            expiring = [i.expires_at for i in items if i.HasField("expires_at")]
            if expiring:
                summary.expires_at.CopyFrom(min(expiring, key=lambda t: (t.seconds, t.nanos)))
            self.backend.save(summary)
            backend = getattr(self.backend, "inner", self.backend)
            for source in items:
                backend.conn.execute(
                    "INSERT OR IGNORE INTO derived_sources VALUES (?,?,?)",
                    (principal.tenant_id, source.id, summary.id),
                )
            return summary
