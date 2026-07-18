import sqlite3
import json
from typing import List, Optional
from core.proto.trilith_pb2 import ContextItem, Tier, Scope
from google.protobuf.timestamp_pb2 import Timestamp

class SQLiteBackend:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        # check_same_thread=False: REST + gRPC share one connection via ThreadSafeBackend
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

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
                subtask_id TEXT
            )
        """)
        # Create indexing to speed up queries
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_tier_scope ON context_items(tier, scope)")
        self._conn.commit()

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
            (id, tier, content, scope, provenance, created_at_sec, created_at_nanosec, expires_at_sec, expires_at_nanosec, embedding, subtask_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                subtask_id
            )
        )
        self._conn.commit()
        return True

    def get(self, item_id: str) -> Optional[ContextItem]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT id, tier, content, scope, provenance, created_at_sec, created_at_nanosec, expires_at_sec, expires_at_nanosec, embedding FROM context_items WHERE id = ?",
            (item_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_item(row)

    def query(self, tier: Tier, scope: Optional[Scope] = None, subtask_id: Optional[str] = None) -> List[ContextItem]:
        query_str = "SELECT id, tier, content, scope, provenance, created_at_sec, created_at_nanosec, expires_at_sec, expires_at_nanosec, embedding FROM context_items WHERE tier = ?"
        params = [int(tier)]
        
        if scope is not None:
            query_str += " AND scope = ?"
            params.append(int(scope))
            
        if subtask_id is not None:
            query_str += " AND subtask_id = ?"
            params.append(subtask_id)
            
        cursor = self._conn.cursor()
        cursor.execute(query_str, params)
        rows = cursor.fetchall()
        return [self._row_to_item(row) for row in rows]

    def delete(self, item_id: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM context_items WHERE id = ?", (item_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def delete_by_scope(self, scope: Scope, tier: Optional[Tier] = None) -> int:
        query_str = "DELETE FROM context_items WHERE scope = ?"
        params = [int(scope)]
        if tier is not None:
            query_str += " AND tier = ?"
            params.append(int(tier))
            
        cursor = self._conn.cursor()
        cursor.execute(query_str, params)
        self._conn.commit()
        return cursor.rowcount

    def _row_to_item(self, row) -> ContextItem:
        val_id, val_tier, val_content, val_scope, val_provenance, c_sec, c_nano, e_sec, e_nano, val_emb = row
        
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
            embedding=emb_list
        )

    def __del__(self):
        try:
            self._conn.close()
        except Exception:
            pass
