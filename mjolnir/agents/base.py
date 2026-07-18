"""
mjolnir.agents.base
--------------------
Minimal agent state container. Mjolnir uses a single-agent loop (no
subagent spawning) to keep the system auditable and lightweight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class AgentState(Enum):
    IDLE = auto()
    THINKING = auto()
    EXECUTING_TOOL = auto()
    RESPONDING = auto()
    ERROR = auto()


@dataclass
class AgentContext:
    """Rolling conversation + execution context for a single Mjolnir session."""

    history: list[dict[str, str]] = field(default_factory=list)
    state: AgentState = AgentState.IDLE
    last_tool_result: dict[str, Any] | None = None
    turn_count: int = 0

    def add_user_message(self, content: str) -> None:
        self.history.append({"role": "user", "content": content})
        self.turn_count += 1

    def add_assistant_message(self, content: str) -> None:
        self.history.append({"role": "assistant", "content": content})

    def add_tool_result(self, tool_name: str, content: str) -> None:
        self.history.append({"role": "tool", "name": tool_name, "content": content})
        self.last_tool_result = {"tool": tool_name, "content": content}

    def trim(self, max_messages: int = 40) -> None:
        """Keep the context window bounded; system prompt is re-added separately."""
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]
