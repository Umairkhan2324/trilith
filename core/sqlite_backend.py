from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

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


@dataclass(frozen=True)
class StoredItem:
    """A row as it exists on disk.

    `ContextItem` has no `subtask_id` — folding groups steps by a column the
    proto does not carry. Anything that has to round-trip a row (an editor
    saving a change) needs both halves, so read paths for humans return this
    instead of a bare item.
    """

    item: ContextItem
    subtask_id: Optional[str] = None


class SQLiteBackend:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._transaction_depth = 0
        # check_same_thread=False: REST + gRPC share one connection via ThreadSafeBackend
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA secure_delete = ON")
        self._conn.execute("PRAGMA recursive_triggers = ON")
        self._init_db()

    def _commit(self):
        if not self._transaction_depth:
            self._conn.commit()

    @contextmanager
    def transaction(self):
        self._conn.execute("SAVEPOINT trilith_operation")
        self._transaction_depth += 1
        try:
            yield
            self._conn.execute("RELEASE SAVEPOINT trilith_operation")
        except BaseException:
            self._conn.execute("ROLLBACK TO SAVEPOINT trilith_operation")
            self._conn.execute("RELEASE SAVEPOINT trilith_operation")
            raise
        finally:
            self._transaction_depth -= 1

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
        self._conn.execute("""CREATE TABLE IF NOT EXISTS derived_sources (
            tenant_id TEXT NOT NULL, source_id TEXT NOT NULL, summary_id TEXT NOT NULL,
            PRIMARY KEY (tenant_id, source_id, summary_id))""")
        self._conn.execute(
            """CREATE TRIGGER IF NOT EXISTS erase_derived AFTER DELETE ON context_items
            BEGIN
                DELETE FROM context_items WHERE tenant_id = OLD.tenant_id AND id IN
                    (SELECT summary_id FROM derived_sources WHERE tenant_id = OLD.tenant_id AND source_id = OLD.id);
                DELETE FROM derived_sources WHERE tenant_id = OLD.tenant_id AND
                    (source_id = OLD.id OR summary_id = OLD.id);
            END"""
        )
        # Tenant leads every index: it is the first predicate of every query.
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tenant_tier_scope "
            "ON context_items(tenant_id, tier, scope)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tenant_subtask ON context_items(tenant_id, subtask_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_expires ON context_items(expires_at_sec)"
        )
        self._commit()

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
                self._conn.execute(f"ALTER TABLE context_items ADD COLUMN {column} {sql_type}")
                added.append(column)

        # Backfill: NULL/'' tenant is meaningless — everything lands in 'default'.
        self._conn.execute(
            "UPDATE context_items SET tenant_id = ? WHERE tenant_id IS NULL OR tenant_id = ''",
            (DEFAULT_TENANT,),
        )
        self._conn.execute("UPDATE context_items SET owner_id = '' WHERE owner_id IS NULL")
        self._conn.execute("UPDATE context_items SET session_id = '' WHERE session_id IS NULL")
        # SQLite cannot alter a primary key. Rebuild transactionally, retaining
        # every column (including subtask metadata) and recreating indexes below.
        info = self._conn.execute("PRAGMA table_info(context_items)").fetchall()
        primary = [r[1] for r in sorted(info, key=lambda r: r[5]) if r[5]]
        if primary != ["tenant_id", "id"]:
            columns = ", ".join(r[1] for r in info)
            definitions = ", ".join(
                f"{r[1]} {r[2]}" + (" NOT NULL" if r[1] in ("tenant_id", "id") else "")
                for r in info
            )
            self._conn.execute(
                f"CREATE TABLE context_items_v2 ({definitions}, PRIMARY KEY (tenant_id, id))"
            )
            self._conn.execute(
                f"INSERT INTO context_items_v2 ({columns}) SELECT {columns} FROM context_items"
            )
            self._conn.execute("DROP TABLE context_items")
            self._conn.execute("ALTER TABLE context_items_v2 RENAME TO context_items")
        self._commit()
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
            ),
        )
        self._commit()
        return True

    def get(self, item_id: str, tenant_id: Optional[str] = None) -> Optional[ContextItem]:
        query_str = f"SELECT {_SELECT_COLS} FROM context_items WHERE id = ?"
        params: list = [item_id]
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

    def lineage(self, item_id: str, tenant_id: str) -> set[str]:
        """Transitive tenant-local source closure, including the item itself."""
        rows = self._conn.execute(
            """WITH RECURSIVE ancestors(id) AS (
                SELECT ? UNION SELECT d.source_id FROM derived_sources d
                JOIN ancestors a ON d.summary_id = a.id WHERE d.tenant_id = ?
            ) SELECT id FROM ancestors""",
            (item_id, normalize_tenant(tenant_id)),
        ).fetchall()
        return {row[0] for row in rows}

    def count(
        self, tier: Tier, tenant_id: Optional[str] = None, include_global: bool = False
    ) -> int:
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

    def stored(self, item_id: str, tenant_id: Optional[str] = None) -> Optional["StoredItem"]:
        """One row, including the columns `ContextItem` cannot carry."""
        query_str = f"SELECT {_SELECT_COLS}, subtask_id FROM context_items WHERE id = ?"
        params: list = [item_id]
        query_str += " AND tenant_id = ?"
        params.append(normalize_tenant(tenant_id))

        cursor = self._conn.cursor()
        cursor.execute(query_str, params)
        row = cursor.fetchone()
        if not row:
            return None
        return StoredItem(item=self._row_to_item(row[:-1]), subtask_id=row[-1])

    def search(
        self,
        tenant_id: Optional[str] = None,
        global_tiers: Sequence[Tier] = (),
        tiers: Optional[Sequence[Tier]] = None,
        scope: Optional[Scope] = None,
        text: str = "",
        owner_id: str = "",
        session_id: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List["StoredItem"], int]:
        """Browse a tenant's rows across tiers, newest first.

        This is the read path a console needs and `query` is not: it spans
        tiers, matches free text, and pages. The tenant predicate is identical
        to `query`'s — `global_tiers` names the tiers whose GLOBAL items are
        cross-tenant (episodic is deliberately not one of them).

        Returns (page, total_matching).
        """
        clauses: List[str] = []
        params: list = []

        if tenant_id is not None:
            if global_tiers:
                placeholders = ", ".join("?" for _ in global_tiers)
                clauses.append(f"(tenant_id = ? OR (scope = ? AND tier IN ({placeholders})))")
                params.append(normalize_tenant(tenant_id))
                params.append(int(Scope.GLOBAL))
                params.extend(int(tier) for tier in global_tiers)
            else:
                clauses.append("tenant_id = ?")
                params.append(normalize_tenant(tenant_id))

        if tiers:
            placeholders = ", ".join("?" for _ in tiers)
            clauses.append(f"tier IN ({placeholders})")
            params.extend(int(tier) for tier in tiers)

        if scope is not None:
            clauses.append("scope = ?")
            params.append(int(scope))

        if owner_id:
            clauses.append("owner_id = ?")
            params.append(owner_id)

        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)

        needle = text.strip().lower()
        if needle:
            like = f"%{needle}%"
            clauses.append(
                "(LOWER(content) LIKE ? OR LOWER(id) LIKE ? "
                "OR LOWER(IFNULL(provenance, '')) LIKE ? OR LOWER(IFNULL(subtask_id, '')) LIKE ?)"
            )
            params.extend([like, like, like, like])

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        cursor = self._conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM context_items{where}", params)
        total = int(cursor.fetchone()[0])

        page_sql = (
            f"SELECT {_SELECT_COLS}, subtask_id FROM context_items{where}"
            " ORDER BY created_at_sec DESC, created_at_nanosec DESC, id DESC"
            " LIMIT ? OFFSET ?"
        )
        cursor.execute(page_sql, [*params, max(1, int(limit)), max(0, int(offset))])
        rows = cursor.fetchall()
        page = [StoredItem(item=self._row_to_item(row[:-1]), subtask_id=row[-1]) for row in rows]
        return page, total

    def list_subtasks(self, tenant_id: Optional[str] = None) -> List[Tuple[str, int]]:
        """Procedural sub-tasks with more than nothing in them: (subtask_id, steps).

        A console needs this to offer `fold` on something real rather than
        asking an operator to remember identifiers.
        """
        query_str = (
            "SELECT subtask_id, COUNT(*) FROM context_items "
            "WHERE tier = ? AND subtask_id IS NOT NULL AND subtask_id != ''"
        )
        params: list = [int(Tier.PROCEDURAL)]
        if tenant_id is not None:
            query_str += " AND tenant_id = ?"
            params.append(normalize_tenant(tenant_id))
        query_str += " GROUP BY subtask_id ORDER BY COUNT(*) DESC, subtask_id"

        cursor = self._conn.cursor()
        cursor.execute(query_str, params)
        return [(row[0], int(row[1])) for row in cursor.fetchall()]

    def delete(self, item_id: str, tenant_id: Optional[str] = None) -> bool:
        query_str = "DELETE FROM context_items WHERE id = ?"
        params: list = [item_id]
        query_str += " AND tenant_id = ?"
        params.append(normalize_tenant(tenant_id))
        cursor = self._conn.cursor()
        cursor.execute(query_str, params)
        self._commit()
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
        self._commit()
        return cursor.rowcount

    def delete_tenant(self, tenant_id: str) -> int:
        """Physically remove every item belonging to a tenant."""
        cursor = self._conn.cursor()
        cursor.execute(
            "DELETE FROM context_items WHERE tenant_id = ?",
            (normalize_tenant(tenant_id),),
        )
        self._commit()
        return cursor.rowcount

    def purge_expired(self, now: Optional[float] = None, tenant_id: Optional[str] = None) -> int:
        """Physically delete items past their `expires_at`.

        The PolicyEngine already hides expired items from results; this reaps
        them so they stop consuming disk and scan time.
        """
        cutoff = int(now if now is not None else time.time())
        query_str = (
            "DELETE FROM context_items WHERE expires_at_sec IS NOT NULL AND expires_at_sec <= ?"
        )
        params: list = [cutoff]
        if tenant_id is not None:
            query_str += " AND tenant_id = ?"
            params.append(normalize_tenant(tenant_id))

        cursor = self._conn.cursor()
        cursor.execute(query_str, params)
        self._commit()
        return cursor.rowcount

    def list_tenants(self) -> List[str]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT DISTINCT tenant_id FROM context_items ORDER BY tenant_id")
        return [row[0] for row in cursor.fetchall()]

    def _row_to_item(self, row) -> ContextItem:
        (
            val_id,
            val_tier,
            val_content,
            val_scope,
            val_provenance,
            c_sec,
            c_nano,
            e_sec,
            e_nano,
            val_emb,
            val_tenant,
            val_owner,
            val_session,
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
