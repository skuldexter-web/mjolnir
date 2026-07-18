"""
mjolnir.agents.execution_loop
------------------------------
The core think -> act -> observe -> respond loop. Renders structured
blocks ([THINKING], [EXECUTING TOOL], [TERMINAL OUTPUT], [RESPONSE])
through the callbacks provided by the TUI, so the interface layer stays
decoupled from agent logic.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from mjolnir.agents.base import AgentContext, AgentState
from mjolnir.llm.client import OllamaClient, OllamaError
from mjolnir.llm.templates import build_messages
from mjolnir.tools.registry import ToolRegistry

logger = logging.getLogger("mjolnir.agent")

MAX_TOOL_HOPS = 6

# Callback signature: (block_name: str, content: str) -> None
RenderHook = Callable[[str, str], None]


class ExecutionLoop:
    def __init__(self, client: OllamaClient, registry: ToolRegistry, render: RenderHook) -> None:
        self.client = client
        self.registry = registry
        self.render = render
        self.context = AgentContext()

    def run_turn(self, user_input: str) -> str:
        self.context.add_user_message(user_input)
        self.context.state = AgentState.THINKING

        final_text = ""
        for hop in range(MAX_TOOL_HOPS):
            messages = build_messages(self.context.history[:-1], user_input) if hop == 0 else self._replay_messages()
            self.render("THINKING", f"Reasoning (pass {hop + 1}/{MAX_TOOL_HOPS})...")

            try:
                response = self.client.chat(messages, tools=self.registry.schemas())
            except OllamaError as exc:
                self.context.state = AgentState.ERROR
                self.render("ERROR", str(exc))
                return f"[error] {exc}"

            message = response.get("message", {})
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                final_text = message.get("content", "").strip()
                self.context.add_assistant_message(final_text)
                self.context.state = AgentState.RESPONDING
                self.render("RESPONSE", final_text)
                break

            self.context.add_assistant_message(message.get("content", ""))
            self.context.state = AgentState.EXECUTING_TOOL

            for call in tool_calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                self.render("EXECUTING TOOL", f"{name}({args})")
                result = self.registry.invoke(name, args)
                self.render("TERMINAL OUTPUT", result.get("output", ""))
                self.context.add_tool_result(name, json.dumps(result))
        else:
            final_text = "[warning] Reached maximum tool-call hops without a final answer."
            self.render("RESPONSE", final_text)

        self.context.trim()
        self.context.state = AgentState.IDLE
        return final_text

    def _replay_messages(self) -> list[dict[str, Any]]:
        from mjolnir.llm.templates import SYSTEM_PROMPT

        return [{"role": "system", "content": SYSTEM_PROMPT}, *self.context.history]
