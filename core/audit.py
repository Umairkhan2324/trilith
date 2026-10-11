"""Durable decision records, separate from the ephemeral operational log.

No prompt text or item contents are stored. IDs are still personal metadata:
erase them alongside memory. This is not an immutable compliance certification.
"""

import json
import time


class AuditLog:
    def __init__(self, backend):
        self.backend = backend
        with backend.transaction():
            backend.inner.conn.execute("""CREATE TABLE IF NOT EXISTS audit_decisions (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                at REAL NOT NULL, tenant_id TEXT NOT NULL,
                owner_id TEXT NOT NULL, session_id TEXT NOT NULL,
                operation TEXT NOT NULL, decision TEXT NOT NULL, detail TEXT NOT NULL
            )""")

            backend.inner.conn.execute("""CREATE TRIGGER IF NOT EXISTS erase_item_audit
                AFTER DELETE ON context_items BEGIN
                DELETE FROM audit_decisions WHERE tenant_id = OLD.tenant_id
                    AND json_extract(detail, '$.item_id') = OLD.id;
                END""")

    def record(self, principal, operation, decision, **detail):
        from core.identity import Principal

        principal = principal or Principal()
        with self.backend.transaction():
            self.backend.inner.conn.execute(
                "INSERT INTO audit_decisions(at,tenant_id,owner_id,session_id,operation,decision,detail) VALUES (?,?,?,?,?,?,?)",
                (
                    time.time(),
                    principal.tenant_id,
                    principal.owner_id,
                    principal.session_id,
                    operation,
                    decision,
                    json.dumps(detail, sort_keys=True),
                ),
            )

    def erase(self, principal, scope):
        clauses, values = ["tenant_id = ?"], [principal.tenant_id]
        if scope.upper() == "USER":
            clauses.append("owner_id = ?")
            values.append(principal.owner_id)
        elif scope.upper() == "SESSION":
            clauses.append("session_id = ?")
            values.append(principal.session_id)
        with self.backend.transaction():
            self.backend.inner.conn.execute(
                "DELETE FROM audit_decisions WHERE " + " AND ".join(clauses), values
            )

    def read(self, principal, limit=100):
        if not principal.can("tenant_admin"):
            raise PermissionError("tenant_admin capability required")
        with self.backend.transaction():
            rows = self.backend.inner.conn.execute(
                "SELECT seq,at,operation,decision,detail FROM audit_decisions WHERE tenant_id=? ORDER BY seq DESC LIMIT ?",
                (principal.tenant_id, max(1, min(1000, limit))),
            ).fetchall()
        return [
            dict(seq=r[0], at=r[1], operation=r[2], decision=r[3], detail=json.loads(r[4]))
            for r in rows
        ]
