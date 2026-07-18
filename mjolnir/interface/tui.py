"""
mjolnir.interface.tui
------------------------
Full-screen terminal dashboard for Mjolnir: a bordered TERMINAL panel on
the left, an AGENT MAP panel and a SUBSYSTEM MENU telemetry panel on the
right, a status bar, and a chat input line — styled after classic
autonomous-agent terminal dashboards.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field

from prompt_toolkit import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame
from rich.console import Console

from mjolnir.agents.execution_loop import ExecutionLoop
from mjolnir.config.settings import Settings
from mjolnir.interface.banner import render_banner
from mjolnir.llm.client import OllamaClient, OllamaError
from mjolnir.tools import desktop, file_system, security, terminal  # noqa: F401
from mjolnir.tools.registry import registry

logger = logging.getLogger("mjolnir.tui")

MAX_LOG_LINES = 500
VISIBLE_LOG_LINES = 60

STYLE = Style.from_dict(
    {
        "frame.border": "fg:#00ff9c",
        "frame.label": "fg:#00ff9c bold",
        "log.system": "fg:#5fd7af",
        "log.you.label": "fg:#ffffff bold",
        "log.you.text": "fg:#9fe6c8",
        "log.bullet": "fg:#00e5ff bold",
        "log.tool": "fg:#00e5ff",
        "log.output": "fg:#7fbfa0",
        "log.response": "fg:#33ff99",
        "log.error": "fg:#ff5f5f bold",
        "log.confirm": "fg:#ffd166 bold",
        "agentmap.idle": "fg:#ffffff",
        "agentmap.active": "fg:#ff6a3d bold",
        "agentmap.label": "fg:#d0ffe8",
        "sub.label": "fg:#5fd7af",
        "sub.value": "fg:#eafff5 bold",
        "sub.sep": "fg:#2b6f5c",
        "statusbar": "bg:#0f3d3d fg:#eafff5",
        "statusbar.key": "bg:#1fae94 fg:#00120d bold",
        "input.prompt": "fg:#00ff9c bold",
        "input.text": "fg:#eafff5",
    }
)

HELP_LINES = [
    "Available commands:",
    "  /help              Show this help",
    "  /model <name>      Switch model (must be Qwen/Gemma, <=14B)",
    "  /anon on|off        Toggle anonymous mode (routes via Tor SOCKS proxy)",
    "  /clear             Clear conversation history",
    "  exit / quit         Quit Mjolnir  (or Ctrl+Q)",
]


@dataclass
class DashboardState:
    model: str
    mode: str = "GENERAL"
    agent_state: str = "IDLE"  # IDLE, THINKING, EXECUTING_TOOL, RESPONDING
    agents: int = 1
    started_at: float = field(default_factory=time.monotonic)
    bytes_sent: int = 0
    bytes_recv: int = 0
    requests: int = 0
    tokens_est: int = 0
    anonymous: bool = False

    def elapsed(self) -> str:
        secs = int(time.monotonic() - self.started_at)
        return f"{secs // 60:02d}:{secs % 60:02d}"


class MjolnirTUI:
    def __init__(self) -> None:
        self.console = Console()
        self.settings = Settings.load()
        self.client = OllamaClient(self.settings)
        self.registry = registry
        terminal.set_confirm_hook(self._confirm)
        file_system.set_confirm_hook(self._confirm)
        security.set_confirm_hook(self._confirm)
        self.loop = ExecutionLoop(self.client, self.registry, self._render_simple)

        self.state = DashboardState(model=self.settings.model, anonymous=self.settings.anonymous_mode)
        self.log_lines: list[tuple[str, str]] = []
        self.scroll_offset = 0

        self._confirm_pending = False
        self._confirm_answer: str | None = None
        self._confirm_event = threading.Event()

        self.app: Application | None = None
        self.input_buffer = Buffer(multiline=False, accept_handler=self._on_accept)

    # ------------------------------------------------------------------
    # Non-dashboard (plain console) rendering, used for -i / --instruction
    # ------------------------------------------------------------------
    def _render_simple(self, label: str, content: str) -> None:
        colors = {
            "THINKING": "cyan",
            "EXECUTING TOOL": "yellow",
            "TERMINAL OUTPUT": "white on grey11",
            "RESPONSE": "green",
            "ERROR": "bold red",
        }
        style = colors.get(label, "white")
        self.console.print(f"[{style}]\\[{label}][/{style}] {content}")

    # ------------------------------------------------------------------
    # Confirmation flow — safe across the background execution thread
    # ------------------------------------------------------------------
    def _confirm(self, description: str) -> bool:
        if self.app is None:
            answer = self.console.input(f"[CONFIRM] {description}\nProceed? [y/N] ")
            return answer.strip().lower() in ("y", "yes")

        self._append_log("log.confirm", f"⚠ [CONFIRM] {description} — type 'y' to proceed, anything else to cancel")
        self._confirm_event.clear()
        self._confirm_pending = True
        self._invalidate()
        self._confirm_event.wait()
        self._confirm_pending = False
        return self._confirm_answer == "y"

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------
    def _append_log(self, style: str, text: str) -> None:
        for line in text.splitlines() or [""]:
            self.log_lines.append((style, line))
        if len(self.log_lines) > MAX_LOG_LINES:
            self.log_lines = self.log_lines[-MAX_LOG_LINES:]
        self.scroll_offset = 0
        self._invalidate()

    def _invalidate(self) -> None:
        if self.app is not None:
            self.app.invalidate()

    def _render_dashboard(self, label: str, content: str) -> None:
        self.state.requests += 1
        self.state.bytes_recv += len(content.encode("utf-8", errors="ignore"))
        self.state.tokens_est += max(1, len(content) // 4)

        if label == "THINKING":
            self.state.agent_state = "THINKING"
            self._append_log("log.bullet", f"● {content}")
        elif label == "EXECUTING TOOL":
            self.state.agent_state = "EXECUTING_TOOL"
            self._append_log("log.tool", f"● executing: {content}")
        elif label == "TERMINAL OUTPUT":
            for line in (content or "(no output)").splitlines():
                self._append_log("log.output", f"  {line}")
        elif label == "RESPONSE":
            self.state.agent_state = "IDLE"
            self._append_log("log.response", "")
            self._append_log("log.response", content or "(empty response)")
            self._append_log("log.response", "")
        elif label == "ERROR":
            self.state.agent_state = "IDLE"
            self._append_log("log.error", f"✕ [ERROR] {content}")
        else:
            self._append_log("log.system", content)

    # ------------------------------------------------------------------
    # Preflight
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------
    def _handle_command(self, text: str) -> bool:
        if not text.startswith("/"):
            return False

        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()

        if cmd == "/help":
            for line in HELP_LINES:
                self._append_log("log.system", line)
        elif cmd == "/clear":
            self.loop.context.history.clear()
            self.log_lines.clear()
            self._append_log("log.system", "Conversation history cleared.")
        elif cmd == "/model" and len(parts) > 1:
            from mjolnir.config.settings import validate_model

            try:
                validate_model(parts[1].strip())
            except ValueError as exc:
                self._append_log("log.error", str(exc))
            else:
                self.settings.model = parts[1].strip()
                self.settings.save()
                self.client = OllamaClient(self.settings)
                self.loop.client = self.client
                self.state.model = self.settings.model
                self._append_log("log.system", f"Model switched to {self.settings.model}")
        elif cmd == "/anon" and len(parts) > 1:
            self.settings.anonymous_mode = parts[1].strip().lower() == "on"
            self.settings.save()
            self.client = OllamaClient(self.settings)
            self.loop.client = self.client
            self.state.anonymous = self.settings.anonymous_mode
            state = "enabled" if self.settings.anonymous_mode else "disabled"
            self._append_log("log.system", f"Anonymous mode {state}.")
        else:
            self._append_log("log.system", f"Unknown command: {text} (try /help)")
        return True

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------
    def _on_accept(self, buf: Buffer) -> bool:
        text = buf.text.strip()
        buf.text = ""

        if self._confirm_pending:
            self._confirm_answer = text.strip().lower()
            self._confirm_event.set()
            return False

        if not text:
            return False

        if text.lower() in ("exit", "quit"):
            if self.app is not None:
                self.app.exit()
            return False

        self.state.bytes_sent += len(text.encode("utf-8", errors="ignore"))

        if self._handle_command(text):
            return False

        self._append_log("log.you.label", "You:")
        self._append_log("log.you.text", text)
        self._append_log("log.system", "")

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, self._run_turn_safe, text)
        return False

    def _run_turn_safe(self, text: str) -> None:
        self.loop.render = self._render_dashboard
        try:
            self.loop.run_turn(text)
        except Exception as exc:  # noqa: BLE001 - surface unexpected failures in the dashboard
            logger.exception("Unhandled error during agent turn")
            self._append_log("log.error", f"✕ [ERROR] {exc}")
        finally:
            self.state.agent_state = "IDLE"
            self._invalidate()

    # ------------------------------------------------------------------
    # Panel content providers
    # ------------------------------------------------------------------
    def _terminal_text(self) -> FormattedText:
        visible = self.log_lines[-(VISIBLE_LOG_LINES + self.scroll_offset) : len(self.log_lines) - self.scroll_offset or None]
        result: list[tuple[str, str]] = []
        for style, line in visible:
            result.append((f"class:{style}", line))
            result.append(("", "\n"))
        return FormattedText(result)

    def _agent_map_text(self) -> FormattedText:
        active = self.state.agent_state != "IDLE"
        dot_style = "class:agentmap.active" if active else "class:agentmap.idle"
        return FormattedText(
            [
                (dot_style, "●"),
                ("class:agentmap.label", " Root Agent"),
                ("", "\n"),
            ]
        )

    def _subsystem_text(self) -> FormattedText:
        s = self.state
        rows = [
            ("LLM", s.model.upper()),
            ("MODE", s.mode),
            ("AGNTS", str(s.agents)),
            ("PROGR", "RUNNING" if s.agent_state != "IDLE" else "IDLE"),
            ("TIME", s.elapsed()),
        ]
        elapsed_s = max(1, int(time.monotonic() - s.started_at))
        req_rate = s.requests / elapsed_s
        sent_rate = (s.bytes_sent / 1024) / elapsed_s
        recv_rate = (s.bytes_recv / 1024) / elapsed_s

        out: list[tuple[str, str]] = []
        for label, value in rows:
            out.append(("class:sub.label", f"{label:<7}: "))
            out.append(("class:sub.value", value))
            out.append(("", "\n"))
        out.append(("class:sub.sep", "--------- :::: ---------\n"))
        out.append(("class:sub.label", "Request rate : "))
        out.append(("class:sub.value", f"{req_rate:.2f} req/s\n"))
        out.append(("class:sub.label", "Bytes sent   : "))
        out.append(("class:sub.value", f"{sent_rate:.2f} KB/s\n"))
        out.append(("class:sub.label", "Bytes recv   : "))
        out.append(("class:sub.value", f"{recv_rate:.2f} KB/s\n"))
        out.append(("class:sub.sep", "--------- :::: ---------\n"))
        out.append(("class:sub.label", "Engine  : "))
        out.append(("class:sub.value", "Ollama (local)\n"))
        out.append(("class:sub.label", "Anon    : "))
        out.append(("class:sub.value", "ON (Tor)" if s.anonymous else "OFF"))
        out.append(("", "\n"))
        out.append(("class:sub.label", "~tokens : "))
        out.append(("class:sub.value", f"{s.tokens_est / 1000:.1f}K"))
        return FormattedText(out)

    def _status_bar_text(self) -> FormattedText:
        segments = [
            ("class:statusbar.key", " ↑↓ "),
            ("class:statusbar", " Scroll terminal   "),
            ("class:statusbar.key", " Enter "),
            ("class:statusbar", " Send message   "),
            ("class:statusbar.key", " /help "),
            ("class:statusbar", " Commands   "),
            ("class:statusbar.key", " Ctrl+Q "),
            ("class:statusbar", " Exit  "),
        ]
        return FormattedText(segments)

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------
    def _build_layout(self) -> Layout:
        terminal_window = Window(
            content=FormattedTextControl(self._terminal_text),
            wrap_lines=True,
        )
        agent_map_window = Window(content=FormattedTextControl(self._agent_map_text), height=D(min=3))
        subsystem_window = Window(content=FormattedTextControl(self._subsystem_text))

        left_pane = Frame(terminal_window, title="TERMINAL", style="class:frame.border")
        right_pane = HSplit(
            [
                Frame(agent_map_window, title="AGENT MAP", style="class:frame.border", height=D(weight=1)),
                Frame(subsystem_window, title="SUBSYSTEM MENU", style="class:frame.border", height=D(weight=2)),
            ]
        )

        main_area = VSplit([left_pane, right_pane], padding=0)

        status_bar = Window(content=FormattedTextControl(self._status_bar_text), height=1, style="class:statusbar")

        input_row = VSplit(
            [
                Window(FormattedTextControl([("class:input.prompt", ">_ ")]), width=3, height=1),
                Window(BufferControl(buffer=self.input_buffer), height=1, style="class:input.text"),
            ]
        )

        root = HSplit([main_area, status_bar, input_row])
        return Layout(root, focused_element=self.input_buffer)

    def _build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-q")
        def _(event):
            event.app.exit()

        @kb.add("c-c")
        def _(event):
            event.app.exit()

        @kb.add("up")
        def _(event):
            self.scroll_offset = min(self.scroll_offset + 1, max(0, len(self.log_lines) - 1))

        @kb.add("down")
        def _(event):
            self.scroll_offset = max(self.scroll_offset - 1, 0)

        return kb

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def run(self) -> None:
        render_banner(self.console, self.settings.model, self.settings.anonymous_mode)
        if not self._preflight():
            return

        self._append_log("log.system", f"◆ Starting MJOLNIR ({self.settings.model}) ...")
        self._append_log("log.system", "")

        self.app = Application(
            layout=self._build_layout(),
            key_bindings=self._build_keybindings(),
            style=STYLE,
            full_screen=True,
            mouse_support=False,
        )
        self.app.run()
        self.console.print("[dim]Farewell.[/dim]")


def launch() -> None:
    MjolnirTUI().run()
