"""Anthropic / Claude tool schemas + dispatcher for Trilith."""

from __future__ import annotations

import json
from typing import Any

from core.client import TrilithClient

# Anthropic Messages API tool definitions (plug into `tools=[...]`)
TRILITH_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "trilith_write",
        "description": "Store a durable fact or event in Trilith memory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "content": {"type": "string"},
                "tier": {
                    "type": "string",
                    "enum": ["SEMANTIC", "PROCEDURAL", "EPISODIC"],
                    "default": "SEMANTIC",
                },
                "scope": {
                    "type": "string",
                    "enum": ["USER", "TENANT", "SESSION", "GLOBAL"],
                    "default": "USER",
                },
            },
            "required": ["id", "content"],
        },
    },
    {
        "name": "trilith_assemble",
        "description": "Fetch budgeted, ranked context before answering the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "budget": {"type": "integer", "default": 300},
                "requester_scope": {"type": "string", "default": "USER"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "trilith_forget",
        "description": "Physically purge all Trilith memory for a scope.",
        "input_schema": {
            "type": "object",
            "properties": {"scope": {"type": "string"}},
            "required": ["scope"],
        },
    },
]


def run_trilith_tool(
    name: str,
    tool_input: dict[str, Any],
    client: TrilithClient | None = None,
) -> str:
    """Execute a Claude tool_use block against Trilith; return JSON string."""
    c = client or TrilithClient()
    if name == "trilith_write":
        return json.dumps(
            c.write(
                id=tool_input["id"],
                content=tool_input["content"],
                tier=tool_input.get("tier", "SEMANTIC"),
                scope=tool_input.get("scope", "USER"),
            )
        )
    if name == "trilith_assemble":
        return json.dumps(
            c.assemble(
                task=tool_input["task"],
                budget=int(tool_input.get("budget", 300)),
                requester_scope=tool_input.get("requester_scope", "USER"),
            )
        )
    if name == "trilith_forget":
        return json.dumps(c.forget(tool_input["scope"]))
    return json.dumps({"error": f"unknown tool: {name}"})
