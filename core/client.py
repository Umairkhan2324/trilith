"""Lean HTTP client for trilith serve (stdlib only — no extra deps)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class TrilithClient:
    """Plug-and-play client for REST gateway (default http://127.0.0.1:8080)."""

    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Trilith HTTP {exc.code}: {detail}") from exc

    def write(
        self,
        id: str,
        content: str,
        tier: str = "SEMANTIC",
        scope: str = "USER",
        provenance: str = "",
    ) -> dict[str, Any]:
        return self._post(
            "/v1/write",
            {
                "id": id,
                "tier": tier,
                "content": content,
                "scope": scope,
                "provenance": provenance,
            },
        )

    def assemble(
        self,
        task: str,
        budget: int = 200,
        requester_scope: str = "USER",
    ) -> dict[str, Any]:
        return self._post(
            "/v1/assemble",
            {"task": task, "budget": budget, "requester_scope": requester_scope},
        )

    def forget(self, scope: str) -> dict[str, Any]:
        return self._post("/v1/forget", {"scope": scope})

    def memory_block(
        self,
        task: str,
        budget: int = 200,
        requester_scope: str = "USER",
    ) -> str:
        """Ready-to-inject bullet list for LLM prompts."""
        ctx = self.assemble(task, budget=budget, requester_scope=requester_scope)
        items = ctx.get("items") or []
        return "\n".join(f"- {i.get('content', '')}" for i in items)
