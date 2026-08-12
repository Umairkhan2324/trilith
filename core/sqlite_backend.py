import json
import sqlite3
import time
from typing import List, Optional

from google.protobuf.timestamp_pb2 import Timestamp

from core.identity import DEFAULT_TENANT, normalize_tenant
from core.proto.trilith_pb2 import ContextItem, Scope, Tier

# Columns added after v0.1. `_migrate` adds any that a pre-existing database is
# missing, so an old trilith.db keeps working without being recreated.
_TENANCY_COLUMNS = {
    "tenant_id": "TEXT",
    "owner_id": "TEXT",
    "session_id": "TEXT",
}

_SELECT_COLS = (
    "id, tier, content, scope, provenance, created_at_sec, created_at_nanosec, "
    "expires_at_sec, expires_at_nanosec, embedding, tenant_id, owner_id, session_id"
)


class SQLiteBackend:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        # check_same_thread=False: REST + gRPC share one connection via ThreadSafeBackend
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        """Underlying connection, shared with the API-key store."""
        return self._conn

    def _init_db(self):
        # We add a subtask_id text field for ProceduralStore folding.
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS context_items (
                id TEXT PRIMARY KEY,
                tier INTEGER,
                content TEXT,
                scope INTEGER,
                provenance TEXT,
                created_at_sec INTEGER,
                created_at_nanosec INTEGER,
                expires_at_sec INTEGER,
                expires_at_nanosec INTEGER,
                embedding TEXT,
                subtask_id TEXT,
                tenant_id TEXT DEFAULT 'default',
                owner_id TEXT DEFAULT '',
                session_id TEXT DEFAULT ''
            )
        """)
        self._migrate()
        # Tenant leads every index: it is the first predicate of every query.
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tenant_tier_scope "
            "ON context_items(tenant_id, tier, scope)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tenant_subtask "
            "ON context_items(tenant_id, subtask_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_expires ON context_items(expires_at_sec)"
        )
        self._conn.commit()

    def _migrate(self):
        """Bring a pre-multi-tenancy database up to the current schema.

        Adds any missing tenancy columns and backfills existing rows into the
        default tenant, so v0.1 data stays readable.
        """
        cursor = self._conn.cursor()
        cursor.execute("PRAGMA table_info(context_items)")
        existing = {row[1] for row in cursor.fetchall()}

        added = []
        for column, sql_type in _TENANCY_COLUMNS.items():
            if column not in existing:
                self._conn.execute(
                    f"ALTER TABLE context_items ADD COLUMN {column} {sql_type}"
                )
                added.append(column)

        # Backfill: NULL/'' tenant is meaningless — everything lands in 'default'.
        self._conn.execute(
            "UPDATE context_items SET tenant_id = ? "
            "WHERE tenant_id IS NULL OR tenant_id = ''",
            (DEFAULT_TENANT,),
        )
        self._conn.execute(
            "UPDATE context_items SET owner_id = '' WHERE owner_id IS NULL"
        )
        self._conn.execute(
            "UPDATE context_items SET session_id = '' WHERE session_id IS NULL"
        )
        self._conn.commit()
        return added

    def save(self, item: ContextItem, subtask_id: Optional[str] = None) -> bool:
        created_sec = item.created_at.seconds if item.HasField("created_at") else 0
        created_nanosec = item.created_at.nanos if item.HasField("created_at") else 0

        expires_sec = item.expires_at.seconds if item.HasField("expires_at") else None
        expires_nanosec = item.expires_at.nanos if item.HasField("expires_at") else None

        embedding_str = json.dumps(list(item.embedding)) if item.embedding else None

        # Use our persistent connection
        self._conn.execute(
            """
            INSERT OR REPLACE INTO context_items
            (id, tier, content, scope, provenance, created_at_sec, created_at_nanosec,
             expires_at_sec, expires_at_nanosec, embedding, subtask_id,
             tenant_id, owner_id, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                int(item.tier),
                item.content,
                int(item.scope),
                item.provenance,
                created_sec,
                created_nanosec,
                expires_sec,
                expires_nanosec,
                embedding_str,
                subtask_id,
                normalize_tenant(item.tenant_id),
                item.owner_id or "",
                item.session_id or "",
            )
        )
        self._conn.commit()
        return True

    def get(self, item_id: str, tenant_id: Optional[str] = None) -> Optional[ContextItem]:
        query_str = f"SELECT {_SELECT_COLS} FROM context_items WHERE id = ?"
        params: list = [item_id]
        if tenant_id is not None:
            query_str += " AND tenant_id = ?"
            params.append(normalize_tenant(tenant_id))

        cursor = self._conn.cursor()
        cursor.execute(query_str, params)
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_item(row)

    def query(
        self,
        tier: Tier,
        scope: Optional[Scope] = None,
        subtask_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        include_global: bool = False,
        limit: Optional[int] = None,
    ) -> List[ContextItem]:
        """Fetch candidates for one tier.

        Args:
            tenant_id: restrict to this tenant. `include_global` additionally
                lets Scope.GLOBAL items through, since those are cross-tenant.
            limit: cap the number of rows returned, newest first. The Governor
                uses this so assembly cost stays bounded on a large store.
        """
        query_str = f"SELECT {_SELECT_COLS} FROM context_items WHERE tier = ?"
        params: list = [int(tier)]

        if tenant_id is not None:
            if include_global:
                query_str += " AND (tenant_id = ? OR scope = ?)"
                params.extend([normalize_tenant(tenant_id), int(Scope.GLOBAL)])
            else:
                query_str += " AND tenant_id = ?"
                params.append(normalize_tenant(tenant_id))

        if scope is not None:
            query_str += " AND scope = ?"
            params.append(int(scope))

        if subtask_id is not None:
            query_str += " AND subtask_id = ?"
            params.append(subtask_id)

        # Newest first, so a limit keeps the most recent context rather than
        # whatever SQLite happens to return.
        query_str += " ORDER BY created_at_sec DESC, created_at_nanosec DESC"

        if limit is not None and limit > 0:
            query_str += " LIMIT ?"
            params.append(int(limit))

        cursor = self._conn.cursor()
        cursor.execute(query_str, params)
        rows = cursor.fetchall()
        return [self._row_to_item(row) for row in rows]

    def count(self, tier: Tier, tenant_id: Optional[str] = None, include_global: bool = False) -> int:
        query_str = "SELECT COUNT(*) FROM context_items WHERE tier = ?"
        params: list = [int(tier)]
        if tenant_id is not None:
            if include_global:
                query_str += " AND (tenant_id = ? OR scope = ?)"
                params.extend([normalize_tenant(tenant_id), int(Scope.GLOBAL)])
            else:
                query_str += " AND tenant_id = ?"
                params.append(normalize_tenant(tenant_id))
        cursor = self._conn.cursor()
        cursor.execute(query_str, params)
        return int(cursor.fetchone()[0])

    def delete(self, item_id: str, tenant_id: Optional[str] = None) -> bool:
        query_str = "DELETE FROM context_items WHERE id = ?"
        params: list = [item_id]
        if tenant_id is not None:
            query_str += " AND tenant_id = ?"
            params.append(normalize_tenant(tenant_id))
        cursor = self._conn.cursor()
        cursor.execute(query_str, params)
        self._conn.commit()
        return cursor.rowcount > 0

    def delete_by_scope(
        self,
        scope: Scope,
        tier: Optional[Tier] = None,
        tenant_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> int:
        query_str = "DELETE FROM context_items WHERE scope = ?"
        params: list = [int(scope)]
        if tier is not None:
            query_str += " AND tier = ?"
            params.append(int(tier))
        if tenant_id is not None:
            query_str += " AND tenant_id = ?"
            params.append(normalize_tenant(tenant_id))
        if owner_id:
            query_str += " AND owner_id = ?"
            params.append(owner_id)
        if session_id:
            query_str += " AND session_id = ?"
            params.append(session_id)

        cursor = self._conn.cursor()
        cursor.execute(query_str, params)
        self._conn.commit()
        return cursor.rowcount

    def delete_tenant(self, tenant_id: str) -> int:
        """Physically remove every item belonging to a tenant."""
        cursor = self._conn.cursor()
        cursor.execute(
            "DELETE FROM context_items WHERE tenant_id = ?",
            (normalize_tenant(tenant_id),),
        )
        self._conn.commit()
        return cursor.rowcount

    def purge_expired(self, now: Optional[float] = None, tenant_id: Optional[str] = None) -> int:
        """Physically delete items past their `expires_at`.

        The PolicyEngine already hides expired items from results; this reaps
        them so they stop consuming disk and scan time.
        """
        cutoff = int(now if now is not None else time.time())
        query_str = (
            "DELETE FROM context_items "
            "WHERE expires_at_sec IS NOT NULL AND expires_at_sec <= ?"
        )
        params: list = [cutoff]
        if tenant_id is not None:
            query_str += " AND tenant_id = ?"
            params.append(normalize_tenant(tenant_id))

        cursor = self._conn.cursor()
        cursor.execute(query_str, params)
        self._conn.commit()
        return cursor.rowcount

    def list_tenants(self) -> List[str]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT DISTINCT tenant_id FROM context_items ORDER BY tenant_id")
        return [row[0] for row in cursor.fetchall()]

    def _row_to_item(self, row) -> ContextItem:
        (
            val_id, val_tier, val_content, val_scope, val_provenance,
            c_sec, c_nano, e_sec, e_nano, val_emb,
            val_tenant, val_owner, val_session,
        ) = row

        created = Timestamp(seconds=c_sec, nanos=c_nano)
        expires = None
        if e_sec is not None:
            expires = Timestamp(seconds=e_sec, nanos=e_nano)

        emb_list = json.loads(val_emb) if val_emb else []

        return ContextItem(
            id=val_id,
            tier=Tier.Name(val_tier),
            content=val_content,
            scope=Scope.Name(val_scope),
            provenance=val_provenance,
            created_at=created,
            expires_at=expires,
            embedding=emb_list,
            tenant_id=normalize_tenant(val_tenant),
            owner_id=val_owner or "",
            session_id=val_session or "",
        )

    def __del__(self):
        try:
            self._conn.close()
        except Exception:
            pass
