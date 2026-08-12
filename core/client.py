"""Lean HTTP client for trilith serve (stdlib only — no extra deps)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional


class TrilithClient:
    """Plug-and-play client for the REST gateway (default http://127.0.0.1:8080).

    Identity:
        `api_key` authenticates the client and, when the server has auth
        enabled, determines the tenant — anything passed as `tenant_id` is
        ignored server-side in that case. On a local server with no keys
        minted, `tenant_id` is honoured directly and no key is needed.

        `owner_id` / `session_id` unlock USER- and SESSION-scoped items. Set
        them per client instance, or override them on individual calls.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        timeout: float = 30.0,
        api_key: Optional[str] = None,
        tenant_id: str = "",
        owner_id: str = "",
        session_id: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # TRILITH_API_KEY keeps secrets out of source for cloud deployments.
        self.api_key = api_key or os.environ.get("TRILITH_API_KEY") or ""
        self.tenant_id = tenant_id or os.environ.get("TRILITH_TENANT_ID") or ""
        self.owner_id = owner_id
        self.session_id = session_id

    def _identity(self, overrides: dict[str, Any]) -> dict[str, Any]:
        identity = {
            "tenant_id": overrides.pop("tenant_id", None) or self.tenant_id,
            "owner_id": overrides.pop("owner_id", None) or self.owner_id,
            "session_id": overrides.pop("session_id", None) or self.session_id,
        }
        return {k: v for k, v in identity.items() if v}

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Trilith HTTP {exc.code}: {detail}") from exc

    def _get(self, path: str) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(f"{self.base_url}{path}", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Trilith HTTP {exc.code}: {detail}") from exc

    def whoami(self) -> dict[str, Any]:
        """Identity the server resolved for this client. Useful for debugging auth."""
        return self._get("/v1/whoami")

    def write(
        self,
        id: str,
        content: str,
        tier: str = "SEMANTIC",
        scope: str = "TENANT",
        provenance: str = "",
        **identity: Any,
    ) -> dict[str, Any]:
        """Store an item.

        `scope` defaults to TENANT — visible to everyone in your tenant, and
        readable without naming a user. Use USER or SESSION to make an item
        private, and pass the matching `owner_id`/`session_id`; an item scoped
        to a user nobody is named for cannot be isolated, so it stays
        tenant-visible.
        """
        return self._post(
            "/v1/write",
            {
                "id": id,
                "tier": tier,
                "content": content,
                "scope": scope,
                "provenance": provenance,
                **self._identity(identity),
            },
        )

    def assemble(
        self,
        task: str,
        budget: int = 200,
        requester_scope: Optional[str] = None,
        **identity: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "task": task,
            "budget": budget,
            **self._identity(identity),
        }
        if requester_scope:
            body["requester_scope"] = requester_scope
        return self._post("/v1/assemble", body)

    def forget(self, scope: str, **identity: Any) -> dict[str, Any]:
        return self._post("/v1/forget", {"scope": scope, **self._identity(identity)})

    def fold(self, subtask_id: str, **identity: Any) -> dict[str, Any]:
        """Collapse a procedural sub-task's steps into a single summary item."""
        return self._post(
            "/v1/fold", {"subtask_id": subtask_id, **self._identity(identity)}
        )

    def purge_expired(self, **identity: Any) -> dict[str, Any]:
        """Physically delete items past their TTL."""
        return self._post("/v1/purge-expired", self._identity(identity))

    def memory_block(
        self,
        task: str,
        budget: int = 200,
        requester_scope: Optional[str] = None,
        **identity: Any,
    ) -> str:
        """Ready-to-inject bullet list for LLM prompts."""
        ctx = self.assemble(
            task, budget=budget, requester_scope=requester_scope, **identity
        )
        items = ctx.get("items") or []
        return "\n".join(f"- {i.get('content', '')}" for i in items)
