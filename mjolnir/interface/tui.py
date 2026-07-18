"""
mjolnir.interface.tui
------------------------
Terminal front-end for Mjolnir. Renders structured [THINKING],
[EXECUTING TOOL], [TERMINAL OUTPUT], and [RESPONSE] blocks, and wires
up user confirmation prompts for destructive tool actions.
"""

from __future__ import annotations

import logging

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from mjolnir.agents.execution_loop import ExecutionLoop
from mjolnir.config.settings import Settings
from mjolnir.interface.banner import render_banner
from mjolnir.llm.client import OllamaClient, OllamaError
from mjolnir.tools import file_system, terminal
from mjolnir.tools.registry import registry

logger = logging.getLogger("mjolnir.tui")

STYLE_MAP = {
    "THINKING": "cyan",
    "EXECUTING TOOL": "yellow",
    "TERMINAL OUTPUT": "white on grey11",
    "RESPONSE": "green",
    "ERROR": "bold red",
}

HELP_TEXT = """\
Available commands:
  /help              Show this help
  /model <name>      Switch model (must be Qwen/Gemma, <=14B)
  /anon on|off        Toggle anonymous mode (routes via Tor SOCKS proxy)
  /clear             Clear conversation history
  exit / quit         Quit Mjolnir
"""


class MjolnirTUI:
    def __init__(self) -> None:
        self.console = Console()
        self.settings = Settings.load()
        self.client = OllamaClient(self.settings)
        self.registry = registry
        terminal.set_confirm_hook(self._confirm)
        file_system.set_confirm_hook(self._confirm)
        self.loop = ExecutionLoop(self.client, self.registry, self._render_block)
        self.session: PromptSession = PromptSession(history=InMemoryHistory())

    def _confirm(self, description: str) -> bool:
        answer = self.console.input(
            f"[bold yellow]\\[CONFIRM][/bold yellow] {description}\n"
            f"Proceed? [y/N] "
        )
        return answer.strip().lower() in ("y", "yes")

    def _render_block(self, label: str, content: str) -> None:
        style = STYLE_MAP.get(label, "white")
        if label == "RESPONSE":
            self.console.print(Panel(Markdown(content or "(empty response)"), title="[RESPONSE]", border_style=style))
        else:
            self.console.print(f"[{style}]\\[{label}][/{style}] {content}")

    def _preflight(self) -> bool:
        if not self.client.health_check():
            self.console.print(
                "[bold red][ERROR][/bold red] Cannot reach Ollama at "
                f"{self.settings.ollama_host}. Is it running? Try: ollama serve"
            )
            return False
        try:
            if not self.client.ensure_model_available():
                self.console.print(
                    f"[yellow][*] Model '{self.settings.model}' not found locally. Pulling...[/yellow]"
                )
                for status in self.client.pull_model():
                    self.console.print(f"  [dim]{status}[/dim]")
        except OllamaError as exc:
            self.console.print(f"[bold red][ERROR][/bold red] {exc}")
            return False
        return True

    def _handle_command(self, text: str) -> bool:
        """Return True if the input was a slash-command (already handled)."""
        if not text.startswith("/"):
            return False

        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()

        if cmd == "/help":
            self.console.print(HELP_TEXT)
        elif cmd == "/clear":
            self.loop.context.history.clear()
            self.console.print("[green]Conversation history cleared.[/green]")
        elif cmd == "/model" and len(parts) > 1:
            from mjolnir.config.settings import validate_model

            try:
                validate_model(parts[1].strip())
            except ValueError as exc:
                self.console.print(f"[bold red]{exc}[/bold red]")
            else:
                self.settings.model = parts[1].strip()
                self.settings.save()
                self.client = OllamaClient(self.settings)
                self.loop.client = self.client
                self.console.print(f"[green]Model switched to {self.settings.model}[/green]")
        elif cmd == "/anon" and len(parts) > 1:
            self.settings.anonymous_mode = parts[1].strip().lower() == "on"
            self.settings.save()
            self.client = OllamaClient(self.settings)
            self.loop.client = self.client
            state = "enabled" if self.settings.anonymous_mode else "disabled"
            self.console.print(f"[green]Anonymous mode {state}.[/green]")
        else:
            self.console.print(f"[yellow]Unknown command: {text}[/yellow] (try /help)")
        return True

    def run(self) -> None:
        render_banner(self.console, self.settings.model, self.settings.anonymous_mode)
        if not self._preflight():
            return

        while True:
            try:
                user_input = self.session.prompt("mjolnir> ").strip()
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]Farewell.[/dim]")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                self.console.print("[dim]Farewell.[/dim]")
                break
            if self._handle_command(user_input):
                continue

            self.loop.run_turn(user_input)


def launch() -> None:
    MjolnirTUI().run()
