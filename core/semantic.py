from core.proto.trilith_pb2 import Tier
from core.store_base import BaseStore


class SemanticStore(BaseStore):
    """Durable facts. Visible tenant-wide (or globally, for Scope.GLOBAL)."""

    tier = Tier.SEMANTIC
    include_global = True
