"""Unit tests for TrilithClient (mocked HTTP)."""

from __future__ import annotations

import json
from unittest.mock import patch

from core.client import TrilithClient


class _Resp:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_assemble_and_memory_block():
    client = TrilithClient("http://127.0.0.1:8080")
    payload = {
        "items": [{"id": "1", "tier": "SEMANTIC", "content": "Alice uses Python"}],
        "tokens_used": 5,
        "excluded_items": [],
    }
    with patch("urllib.request.urlopen", return_value=_Resp(payload)):
        ctx = client.assemble("languages?", budget=100)
        assert ctx["items"][0]["id"] == "1"
        block = client.memory_block("languages?")
        assert "Alice uses Python" in block


def test_write_and_forget():
    client = TrilithClient()
    with patch("urllib.request.urlopen", return_value=_Resp({"success": True, "id": "x"})):
        assert client.write("x", "hello")["success"] is True
    with patch(
        "urllib.request.urlopen",
        return_value=_Resp({"success": True, "deleted_episodic_count": 0}),
    ):
        assert client.forget("USER")["success"] is True
