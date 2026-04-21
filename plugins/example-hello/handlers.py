"""Example plugin handlers."""

from __future__ import annotations


async def hello_world(params: dict, ctx: object) -> object:  # type: ignore[type-arg]
    """A simple greeting tool."""
    from koda.services.tool_dispatcher import AgentToolResult

    name = params.get("name", "World")
    return AgentToolResult(
        tool="hello_world",
        success=True,
        output=f"Hello, {name}! From the example-hello plugin.",
    )
