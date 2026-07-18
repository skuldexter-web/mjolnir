"""
mjolnir.interface.banner
--------------------------
Startup ASCII art for MJOLNIR. Cyan-to-magenta gradient rendered with
rich markup so it works over SSH sessions with 256-color support.
"""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

ASCII_ART = r"""
 ███╗   ███╗      ██╗ ██████╗ ██╗     ███╗   ██╗██╗██████╗
 ████╗ ████║      ██║██╔═══██╗██║     ████╗  ██║██║██╔══██╗
 ██╔████╔██║      ██║██║   ██║██║     ██╔██╗ ██║██║██████╔╝
 ██║╚██╔╝██║ ██   ██║██║   ██║██║     ██║╚██╗██║██║██╔══██╗
 ██║ ╚═╝ ██║ ╚█████╔╝╚██████╔╝███████╗██║ ╚████║██║██║  ██║
 ╚═╝     ╚═╝  ╚════╝  ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚═╝╚═╝  ╚═╝
"""

TAGLINE = "WHAT SHOULD BE, OR SHOULD NOT."

_GRADIENT = ["#00f5ff", "#33d4ff", "#66b3ff", "#9992ff", "#cc70ff", "#ff4dd8"]


def _gradient_text(art: str) -> Text:
    lines = art.splitlines()
    styled = Text()
    step = max(1, len(lines) // len(_GRADIENT))
    for i, line in enumerate(lines):
        color = _GRADIENT[min(i // step, len(_GRADIENT) - 1)]
        styled.append(line + "\n", style=color)
    return styled


def render_banner(console: Console, model: str, anonymous: bool) -> None:
    console.print(_gradient_text(ASCII_ART))
    console.print(f"[bold magenta]{TAGLINE}[/bold magenta]", justify="center")
    console.print()
    mode = "[bold red]ANONYMOUS (Tor)[/bold red]" if anonymous else "[bold green]DIRECT[/bold green]"
    console.print(
        f"  [cyan]model[/cyan] {model}    [cyan]mode[/cyan] {mode}    "
        f"[cyan]engine[/cyan] Ollama (local-only)",
        justify="center",
    )
    console.print("  [dim]type 'exit' or Ctrl+D to quit  ·  '/help' for commands[/dim]", justify="center")
    console.print()
