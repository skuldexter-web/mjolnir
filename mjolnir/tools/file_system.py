"""
mjolnir.tools.file_system
----------------------------
File read/write/inspect tools for the agent. Writes outside the user's
home directory are gated behind a confirmation hook (mirrors the
terminal tool's pattern) since that's the most common source of
accidental damage from an autonomous agent.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from mjolnir.config.settings import Settings

logger = logging.getLogger("mjolnir.tools.fs")

ConfirmHook = Callable[[str], bool]
_confirm_hook: ConfirmHook | None = None


def set_confirm_hook(hook: ConfirmHook) -> None:
    global _confirm_hook
    _confirm_hook = hook


def _resolve(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _outside_home(path: Path) -> bool:
    home = Path.home().resolve()
    try:
        path.relative_to(home)
        return False
    except ValueError:
        return True


def read_file(path: str, max_bytes: int = 200_000) -> dict[str, str | bool]:
    """Read a text file from disk, truncated to max_bytes."""
    target = _resolve(path)
    if not target.exists():
        return {"ok": False, "output": f"No such file: {target}"}
    if not target.is_file():
        return {"ok": False, "output": f"Not a regular file: {target}"}
    try:
        data = target.read_bytes()[:max_bytes]
        return {"ok": True, "output": data.decode("utf-8", errors="replace")}
    except OSError as exc:
        return {"ok": False, "output": f"Read failed: {exc}"}


def write_file(path: str, content: str, overwrite: bool = True) -> dict[str, str | bool]:
    """Write text content to a file, creating parent directories as needed."""
    settings = Settings.load()
    target = _resolve(path)

    if target.exists() and not overwrite:
        return {"ok": False, "output": f"File already exists and overwrite=False: {target}"}

    if settings.safety.confirm_file_writes_outside_home and _outside_home(target):
        if _confirm_hook is None or not _confirm_hook(str(target)):
            return {"ok": False, "output": f"Write not performed: user did not confirm write outside $HOME ({target})."}

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"ok": True, "output": f"Wrote {len(content)} bytes to {target}"}
    except OSError as exc:
        return {"ok": False, "output": f"Write failed: {exc}"}


def list_directory(path: str = ".", show_hidden: bool = False) -> dict[str, str | bool]:
    """List the contents of a directory."""
    target = _resolve(path)
    if not target.exists() or not target.is_dir():
        return {"ok": False, "output": f"Not a directory: {target}"}
    entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    lines = []
    for entry in entries:
        if not show_hidden and entry.name.startswith("."):
            continue
        marker = "/" if entry.is_dir() else ""
        lines.append(f"{entry.name}{marker}")
    return {"ok": True, "output": "\n".join(lines) or "(empty directory)"}


from mjolnir.tools.registry import registry  # noqa: E402

registry.register(
    name="read_file",
    description="Read the contents of a text file on the local filesystem.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read."},
            "max_bytes": {"type": "integer", "description": "Max bytes to read (default 200000)."},
        },
        "required": ["path"],
    },
)(read_file)

registry.register(
    name="write_file",
    description=(
        "Write text content to a file, creating directories as needed. Writes outside "
        "the user's home directory may require confirmation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Destination file path."},
            "content": {"type": "string", "description": "Text content to write."},
            "overwrite": {"type": "boolean", "description": "Overwrite if the file exists (default true)."},
        },
        "required": ["path", "content"],
    },
)(write_file)

registry.register(
    name="list_directory",
    description="List the contents of a directory on the local filesystem.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory to list (default '.')."},
            "show_hidden": {"type": "boolean", "description": "Include dotfiles (default false)."},
        },
    },
)(list_directory)
