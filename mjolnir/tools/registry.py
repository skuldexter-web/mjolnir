"""
mjolnir.tools.registry
------------------------
Decorator-based registry that tracks tool functions and produces
Ollama/OpenAI-style tool schemas for function calling.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("mjolnir.tools")


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., dict[str, Any]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self, name: str, description: str, parameters: dict[str, Any]
    ) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
        def decorator(func: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
            self._tools[name] = ToolSpec(name, description, parameters, func)
            return func

        return decorator

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in self._tools.values()
        ]

    def invoke(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        spec = self._tools.get(name)
        if spec is None:
            return {"ok": False, "output": f"Unknown tool: {name}"}
        try:
            return spec.handler(**args)
        except TypeError as exc:
            return {"ok": False, "output": f"Bad arguments for {name}: {exc}"}
        except Exception as exc:  # noqa: BLE001 - surface all tool failures to the model
            logger.exception("Tool %s raised an exception", name)
            return {"ok": False, "output": f"Tool {name} failed: {exc}"}


# Global registry instance shared across the app.
registry = ToolRegistry()
